import argparse
import itertools
import json
import math
import os
import shutil
import time
import warnings
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", str(os.cpu_count() or 1))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler


EPS = 1e-12
DEFAULT_SCORE_PARAMS = {
    "silhouette_weight": 1.4,
    "dbi_weight": 0.12,
    "smallest_cluster_ratio_weight": 2.0,
    "second_smallest_cluster_ratio_weight": 1.0,
    "cluster_size_entropy_weight": 1.00,
    "max_cluster_ratio_penalty_weight": 5.00,
    "spatial_occupancy_entropy_weight": 1.50,
}
RESULT_SORT_COLUMNS = [
    "selection_valid",
    "in_target_cluster_range",
    "cluster_size_valid",
    "silhouette_threshold_valid",
    "score",
    "silhouette",
]
RESULT_SORT_ASCENDING = [False, False, False, False, False, False]
RESULT_SORT_DEFAULTS = {
    "selection_valid": False,
    "in_target_cluster_range": False,
    "cluster_size_valid": False,
    "silhouette_threshold_valid": False,
    "score": np.nan,
    "silhouette": np.nan,
}
TYPE_NUMBER_COLOR_ALIASES = {"14": "4"}
EXCEL_MAX_ROWS = 1_048_576
PIE_FONT_FAMILY = "Times New Roman"
PIE_LEGEND_FONT_SIZE = 21
PIE_LEGEND_TITLE_FONT_SIZE = 21
PIE_TITLE_FONT_SIZE = PIE_LEGEND_TITLE_FONT_SIZE + 1
PIE_EMPTY_FONT_SIZE = 25


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Enumerate feature subsets and automatically search UMAP + KMeans "
            "parameters with a score aligned to explore_dimensionless_feature_sets.py."
        )
    )
    parser.add_argument("--input", type=Path, default=Path("summary_11.xlsx"))
    parser.add_argument("--output-dir", type=Path, default=Path("auto_umap_feature_search"))
    parser.add_argument("--label-col", default="Type Number")
    parser.add_argument("--name-col", default=None)
    parser.add_argument(
        "--feature-cols",
        default=None,
        help="Comma-separated feature column list. Default: all numeric columns except label/name.",
    )

    # Default is intentionally small for the first timing run
    parser.add_argument("--min-features", type=int, default=10)
    parser.add_argument("--max-features", type=int, default=11)
    parser.add_argument(
        "--feature-counts",
        default=None,
        help="Comma-separated feature counts, e.g. 10,11 or 6,7,8,9,10,11. Overrides min/max.",
    )
    parser.add_argument("--max-feature-combinations", type=int, default=None)

    parser.add_argument("--param-preset", choices=["quick", "balanced", "dense"], default="balanced")
    parser.add_argument(
        "--umap-n-neighbors-list",
        default="auto",
        help="Comma/range list such as 2-10,15, or auto.",
    )
    parser.add_argument(
        "--umap-min-dist-list",
        default="auto",
        help="Comma list such as 0,0.01,0.05,0.1,0.2, or auto.",
    )
    parser.add_argument(
        "--kmeans-n-clusters-list",
        default="auto",
        help="Comma/range list such as 3-9, or auto.",
    )

    parser.add_argument("--target-cluster-min", type=int, default=4)
    parser.add_argument("--target-cluster-max", type=int, default=7)
    parser.add_argument("--min-valid-class-count", type=int, default=4)
    parser.add_argument("--max-valid-class-count", type=int, default=30)
    parser.add_argument("--silhouette-threshold", type=float, default=0.50)
    parser.add_argument("--min-cluster-size-abs", type=int, default=10)
    parser.add_argument("--min-cluster-size-frac", type=float, default=0.03)

    parser.add_argument("--random-state", type=int, default=0)
    parser.add_argument("--umap-metric", default="euclidean")
    parser.add_argument("--umap-spread", type=float, default=1.0)
    parser.add_argument("--umap-repulsion-strength", type=float, default=1.0)
    parser.add_argument("--kmeans-init", default="k-means++")
    parser.add_argument("--kmeans-n-init", type=int, default=20)
    parser.add_argument("--kmeans-max-iter", type=int, default=300)
    parser.add_argument("--kmeans-algorithm", choices=["auto", "lloyd", "elkan"], default="auto")
    parser.add_argument("--silhouette-sample-size", type=int, default=1000)

    parser.set_defaults(use_initial_edge_filter=True)
    parser.add_argument("--use-initial-edge-filter", dest="use_initial_edge_filter", action="store_true")
    parser.add_argument("--no-initial-edge-filter", dest="use_initial_edge_filter", action="store_false")
    parser.add_argument("--initial-edge-points-to-remove", type=int, default=20)

    parser.set_defaults(save_plots=True)
    parser.add_argument("--save-plots", dest="save_plots", action="store_true")
    parser.add_argument("--no-save-plots", dest="save_plots", action="store_false")
    parser.add_argument("--top-results", type=int, default=2000)
    parser.add_argument("--write-all-results-excel", action="store_true")
    parser.add_argument("--excel-row-limit", type=int, default=1_000_000)
    parser.add_argument("--progress-every", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def parse_int_list(text):
    if text is None or str(text).strip().lower() == "auto":
        return None

    values = []
    for raw_token in str(text).replace(";", ",").split(","):
        token = raw_token.strip()
        if not token:
            continue
        if "-" in token and not token.startswith("-"):
            left, right = token.split("-", 1)
            start = int(left.strip())
            stop = int(right.strip())
            step = 1 if stop >= start else -1
            values.extend(range(start, stop + step, step))
        else:
            values.append(int(token))
    return sorted(set(values))


def parse_float_list(text):
    if text is None or str(text).strip().lower() == "auto":
        return None

    values = []
    for raw_token in str(text).replace(";", ",").split(","):
        token = raw_token.strip()
        if token:
            values.append(float(token))
    return sorted(set(values))


def parse_feature_column_list(text):
    if text is None:
        return None
    return [token.strip() for token in str(text).replace(";", ",").split(",") if token.strip()]


def unique_sorted_ints(values, low=None, high=None):
    out = []
    for value in values:
        item = int(round(value))
        if low is not None and item < low:
            continue
        if high is not None and item > high:
            continue
        out.append(item)
    return sorted(set(out))


def auto_umap_n_neighbors(n_samples, preset):
    max_neighbors = max(2, n_samples - 1)
    sqrt_n = max(2, int(round(math.sqrt(max(n_samples, 1)))))

    if preset == "quick":
        candidates = [3, 5, 8, 12, 15, sqrt_n]
    elif preset == "balanced":
        candidates = [2, 3, 4, 5, 6, 8, 10, 12, 15, sqrt_n, 2 * sqrt_n]
    else:
        candidates = list(range(2, 11)) + [12, 15, 20, 30, sqrt_n, 2 * sqrt_n]

    return unique_sorted_ints(candidates, low=2, high=max_neighbors)


def auto_umap_min_dist(preset):
    if preset == "quick":
        return [0.0, 0.025, 0.05, 0.10, 0.20]
    if preset == "balanced":
        return [0.0, 0.01, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.50]
    return [
        0.0,
        0.01,
        0.015,
        0.02,
        0.025,
        0.03,
        0.035,
        0.04,
        0.05,
        0.06,
        0.07,
        0.08,
        0.09,
        0.10,
        0.12,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.50,
    ]


def auto_kmeans_clusters(n_samples, preset, target_min, target_max):
    if preset == "quick":
        low = target_min
        high = target_max
    elif preset == "balanced":
        low = max(2, target_min - 1)
        high = target_max + 2
    else:
        low = max(2, target_min - 2)
        high = target_max + 3

    high = min(high, n_samples - 1)
    return list(range(low, high + 1))


def resolve_parameter_grid(n_samples, args):
    n_neighbors = parse_int_list(args.umap_n_neighbors_list)
    min_dist = parse_float_list(args.umap_min_dist_list)
    n_clusters = parse_int_list(args.kmeans_n_clusters_list)

    if n_neighbors is None:
        n_neighbors = auto_umap_n_neighbors(n_samples, args.param_preset)
    else:
        n_neighbors = unique_sorted_ints(n_neighbors, low=2, high=max(2, n_samples - 1))

    if min_dist is None:
        min_dist = auto_umap_min_dist(args.param_preset)

    if n_clusters is None:
        n_clusters = auto_kmeans_clusters(
            n_samples,
            args.param_preset,
            args.target_cluster_min,
            args.target_cluster_max,
        )
    else:
        n_clusters = unique_sorted_ints(n_clusters, low=2, high=max(2, n_samples - 1))

    if not n_neighbors:
        raise ValueError("Empty UMAP n_neighbors list after clamping.")
    if not min_dist:
        raise ValueError("Empty UMAP min_dist list.")
    if not n_clusters:
        raise ValueError("Empty KMeans n_clusters list after clamping.")

    return n_neighbors, min_dist, n_clusters


def resolve_feature_columns(df, args):
    explicit = parse_feature_column_list(args.feature_cols)
    if explicit is not None:
        missing = [col for col in explicit if col not in df.columns]
        if missing:
            raise ValueError(f"Feature columns missing from input: {missing}")
        return explicit

    exclude = {args.label_col}
    if args.name_col:
        exclude.add(args.name_col)
    return [
        col
        for col in df.columns
        if col not in exclude and pd.api.types.is_numeric_dtype(df[col])
    ]


def resolve_feature_counts(n_features, args):
    counts = parse_int_list(args.feature_counts)
    if counts is None:
        counts = list(range(args.min_features, args.max_features + 1))

    counts = [count for count in counts if 1 <= count <= n_features]
    if not counts:
        raise ValueError("No usable feature counts. Check min/max/features.")
    return counts


def build_feature_combinations(feature_cols, args):
    counts = resolve_feature_counts(len(feature_cols), args)
    combos = []
    for count in counts:
        combos.extend(itertools.combinations(feature_cols, count))

    if args.max_feature_combinations is not None:
        combos = combos[: args.max_feature_combinations]
    return combos


def preprocess_matrix(X):
    X = np.asarray(X, dtype=float)
    X = np.where(np.isfinite(X), X, np.nan)
    X_imp = SimpleImputer(strategy="median").fit_transform(X)
    return StandardScaler().fit_transform(X_imp)


def initial_edge_filter_points(Z, n_remove=20):
    Z = np.asarray(Z, dtype=np.float64)
    n_samples = len(Z)
    keep_mask = np.ones(n_samples, dtype=bool)

    if n_remove <= 0 or n_samples <= n_remove:
        return Z, keep_mask, np.array([], dtype=int), np.zeros(n_samples, dtype=np.float64)

    center = np.nanmedian(Z, axis=0)
    q75, q25 = np.nanpercentile(Z, [75, 25], axis=0)
    scale = q75 - q25
    fallback_scale = np.nanstd(Z, axis=0)
    scale = np.where(scale > EPS, scale, fallback_scale)
    scale = np.where(scale > EPS, scale, 1.0)

    edge_distance = np.linalg.norm((Z - center) / scale, axis=1)
    removed_indices = np.argsort(edge_distance)[-n_remove:]
    keep_mask[removed_indices] = False
    return Z[keep_mask], keep_mask, np.sort(removed_indices), edge_distance


def required_min_cluster_size(n_samples, args):
    return max(
        args.min_cluster_size_abs,
        int(np.ceil(args.min_cluster_size_frac * n_samples)),
    )


def is_valid_class_count(class_count, args):
    return args.min_valid_class_count <= int(class_count) <= args.max_valid_class_count


def cluster_size_summary(labels):
    labels = np.asarray(labels)
    unique, counts = np.unique(labels, return_counts=True)
    sorted_counts = np.sort(counts)
    n_samples = int(np.sum(counts)) if len(counts) else 0
    smallest_ratio = float(sorted_counts[0] / n_samples) if n_samples and len(sorted_counts) >= 1 else np.nan
    second_smallest_ratio = float(sorted_counts[1] / n_samples) if n_samples and len(sorted_counts) >= 2 else 0.0
    ratios = counts / n_samples if n_samples else np.array([], dtype=float)
    positive_ratios = ratios[ratios > EPS]
    size_entropy = -float(np.sum(positive_ratios * np.log(positive_ratios))) if len(positive_ratios) else 0.0
    if len(counts) > 1:
        size_entropy = size_entropy / float(np.log(len(counts)))

    return {
        "class_count": int(len(unique)),
        "min_cluster_size": int(counts.min()) if len(counts) else 0,
        "max_cluster_size": int(counts.max()) if len(counts) else 0,
        "smallest_cluster_ratio": smallest_ratio,
        "second_smallest_cluster_ratio": second_smallest_ratio,
        "smallest_two_cluster_ratio": smallest_ratio + second_smallest_ratio if np.isfinite(smallest_ratio) else np.nan,
        "max_cluster_ratio": float(np.max(ratios)) if len(ratios) else np.nan,
        "cluster_size_entropy": float(np.clip(size_entropy, 0.0, 1.0)),
        "cluster_sizes": "; ".join(f"{label}:{count}" for label, count in zip(unique, counts)),
    }


def spatial_occupancy_summary(X, labels):
    X = np.asarray(X, dtype=float)
    labels = np.asarray(labels)
    unique = np.unique(labels)

    volumes = []
    for label in unique:
        pts = X[labels == label]
        if len(pts) < 4:
            volumes.append(0.0)
            continue

        lo = np.nanpercentile(pts, 10, axis=0)
        hi = np.nanpercentile(pts, 90, axis=0)
        side = np.maximum(hi - lo, 0.0)
        volume = float(np.prod(side))
        volumes.append(volume if np.isfinite(volume) else 0.0)

    volumes = np.asarray(volumes, dtype=float)
    volume_sum = float(np.sum(volumes))
    if volume_sum > EPS:
        ratios = volumes / volume_sum
        positive = ratios[ratios > EPS]
        entropy = -float(np.sum(positive * np.log(positive))) if len(positive) else 0.0
        if len(unique) > 1:
            entropy = entropy / float(np.log(len(unique)))
    else:
        ratios = np.zeros_like(volumes)
        entropy = 0.0

    return {
        "spatial_occupancy_entropy": float(np.clip(entropy, 0.0, 1.0)),
        "spatial_occupancy_min_ratio": float(np.min(ratios)) if len(ratios) else np.nan,
        "spatial_occupancy_max_ratio": float(np.max(ratios)) if len(ratios) else np.nan,
        "spatial_occupancy_ratios": "; ".join(
            f"{label}:{ratio:.6f}" for label, ratio in zip(unique, ratios)
        ),
        "spatial_occupancy_volumes": "; ".join(
            f"{label}:{volume:.6g}" for label, volume in zip(unique, volumes)
        ),
    }


def safe_cluster_scores(Z, labels, sample_size_limit, random_state):
    Z = np.asarray(Z, dtype=np.float64)
    labels = np.asarray(labels)
    try:
        n_samples = len(labels)
        unique_count = len(np.unique(labels))
        if n_samples <= 1 or unique_count <= 1 or unique_count >= n_samples:
            return np.nan, np.nan

        if sample_size_limit and sample_size_limit > 0 and n_samples > sample_size_limit:
            sil = silhouette_score(
                Z,
                labels,
                sample_size=sample_size_limit,
                random_state=random_state,
            )
        else:
            sil = silhouette_score(Z, labels)
        dbi = davies_bouldin_score(Z, labels)
        return float(sil), float(dbi)
    except Exception:
        return np.nan, np.nan


def classification_score(
    silhouette,
    dbi,
    smallest_ratio,
    second_smallest_ratio,
    cluster_size_entropy,
    max_cluster_ratio,
    spatial_occupancy_entropy,
    score_params,
):
    if not np.isfinite(silhouette):
        return np.nan

    dbi_value = dbi if np.isfinite(dbi) else 0.0
    smallest_value = smallest_ratio if np.isfinite(smallest_ratio) else 0.0
    second_smallest_value = second_smallest_ratio if np.isfinite(second_smallest_ratio) else 0.0
    size_entropy_value = cluster_size_entropy if np.isfinite(cluster_size_entropy) else 0.0
    max_ratio_value = max_cluster_ratio if np.isfinite(max_cluster_ratio) else 1.0
    spatial_value = spatial_occupancy_entropy if np.isfinite(spatial_occupancy_entropy) else 0.0

    return float(
        score_params["silhouette_weight"] * silhouette
        - score_params["dbi_weight"] * dbi_value
        + score_params["smallest_cluster_ratio_weight"] * smallest_value
        + score_params["second_smallest_cluster_ratio_weight"] * second_smallest_value
        + score_params["cluster_size_entropy_weight"] * size_entropy_value
        - score_params["max_cluster_ratio_penalty_weight"] * max_ratio_value
        + score_params["spatial_occupancy_entropy_weight"] * spatial_value
    )


def selection_key(row):
    return (
        1 if row.get("selection_valid") else 0,
        1 if row.get("in_target_cluster_range") else 0,
        1 if row.get("cluster_size_valid") else 0,
        1 if row.get("silhouette_threshold_valid") else 0,
        np.nan_to_num(row.get("score"), nan=-999.0),
        np.nan_to_num(row.get("silhouette"), nan=-999.0),
    )


def make_kmeans(args, n_clusters):
    kwargs = {
        "n_clusters": int(n_clusters),
        "init": args.kmeans_init,
        "n_init": args.kmeans_n_init,
        "max_iter": args.kmeans_max_iter,
        "random_state": args.random_state,
    }
    if args.kmeans_algorithm != "auto":
        kwargs["algorithm"] = args.kmeans_algorithm
    return KMeans(**kwargs)


def evaluate_kmeans(Z2, n_clusters, args):
    if n_clusters >= len(Z2):
        return None, None, None

    model = make_kmeans(args, n_clusters)
    labels = model.fit_predict(Z2)

    raw_sil, dbi = safe_cluster_scores(
        Z2,
        labels,
        sample_size_limit=args.silhouette_sample_size,
        random_state=args.random_state,
    )
    size_info = cluster_size_summary(labels)
    spatial_info = spatial_occupancy_summary(Z2, labels)
    class_count_valid = is_valid_class_count(size_info["class_count"], args)
    silhouette = raw_sil if class_count_valid else np.nan
    silhouette_threshold_valid = bool(
        np.isfinite(silhouette) and silhouette >= args.silhouette_threshold
    )
    min_required = required_min_cluster_size(len(labels), args)
    cluster_size_valid = size_info["min_cluster_size"] >= min_required
    in_target = args.target_cluster_min <= n_clusters <= args.target_cluster_max
    selection_valid = bool(in_target and cluster_size_valid and silhouette_threshold_valid)

    score = classification_score(
        silhouette,
        dbi,
        size_info["smallest_cluster_ratio"],
        size_info["second_smallest_cluster_ratio"],
        size_info["cluster_size_entropy"],
        size_info["max_cluster_ratio"],
        spatial_info["spatial_occupancy_entropy"],
        DEFAULT_SCORE_PARAMS,
    )

    row = {
        "kmeans_n_clusters": int(n_clusters),
        "cluster_count": size_info["class_count"],
        "class_count_valid": class_count_valid,
        "in_target_cluster_range": in_target,
        "selection_valid": selection_valid,
        "raw_silhouette": raw_sil,
        "silhouette": silhouette,
        "silhouette_threshold_valid": silhouette_threshold_valid,
        "davies_bouldin": dbi,
        "score": score,
        "cluster_size_valid": cluster_size_valid,
        "min_cluster_size": size_info["min_cluster_size"],
        "max_cluster_size": size_info["max_cluster_size"],
        "required_min_cluster_size": min_required,
        "smallest_cluster_ratio": size_info["smallest_cluster_ratio"],
        "second_smallest_cluster_ratio": size_info["second_smallest_cluster_ratio"],
        "smallest_two_cluster_ratio": size_info["smallest_two_cluster_ratio"],
        "max_cluster_ratio": size_info["max_cluster_ratio"],
        "cluster_size_entropy": size_info["cluster_size_entropy"],
        "spatial_occupancy_entropy": spatial_info["spatial_occupancy_entropy"],
        "spatial_occupancy_min_ratio": spatial_info["spatial_occupancy_min_ratio"],
        "spatial_occupancy_max_ratio": spatial_info["spatial_occupancy_max_ratio"],
        "spatial_occupancy_ratios": spatial_info["spatial_occupancy_ratios"],
        "spatial_occupancy_volumes": spatial_info["spatial_occupancy_volumes"],
        "cluster_sizes": size_info["cluster_sizes"],
    }
    return row, labels, model


def sorted_results_df(rows):
    if not rows:
        return pd.DataFrame()
    return sorted_like_results(pd.DataFrame(rows))


def build_best_labels_df(df, best_payload):
    out = df.copy()
    keep_mask = best_payload["keep_mask"]
    labels = np.asarray(best_payload["labels"])
    Z2 = np.asarray(best_payload["Z2"])

    out["Auto_UMAP_Selected_Features"] = "; ".join(best_payload["features"])
    out["Auto_Removed_By_Initial_Edge_Filter"] = ~keep_mask
    out["Auto_Initial_Edge_Distance"] = best_payload["edge_distance"]
    out["Auto_UMAP1"] = np.nan
    out["Auto_UMAP2"] = np.nan
    out["Auto_KMeans_Cluster"] = -1
    out.loc[keep_mask, "Auto_UMAP1"] = Z2[:, 0]
    out.loc[keep_mask, "Auto_UMAP2"] = Z2[:, 1]
    out.loc[keep_mask, "Auto_KMeans_Cluster"] = labels
    return out


def class_sort_key(value):
    text = str(value)
    try:
        return (0, float(text))
    except ValueError:
        return (1, text)


def normalize_type_number_label(value):
    text = str(value)
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def type_number_color_key(value):
    normalized = normalize_type_number_label(value)
    return TYPE_NUMBER_COLOR_ALIASES.get(normalized, normalized)


def type_number_color_map(labels, reference_labels=None):
    labels = np.asarray(labels).astype(str)
    if reference_labels is None:
        reference_labels = labels
    reference_labels = np.asarray(reference_labels).astype(str)

    classes = sorted(pd.unique(reference_labels), key=class_sort_key)
    color_keys = sorted({type_number_color_key(cls) for cls in classes}, key=class_sort_key)
    cmap = plt.get_cmap("tab20")
    colors_by_key = {key: cmap(idx % cmap.N) for idx, key in enumerate(color_keys)}

    label_classes = sorted(pd.unique(labels), key=class_sort_key)
    return {cls: colors_by_key[type_number_color_key(cls)] for cls in label_classes}


def get_discrete_colors(n):
    palette = []
    palette.extend(plt.cm.tab20.colors)
    palette.extend(plt.cm.tab20b.colors)
    palette.extend(plt.cm.tab20c.colors)

    if n <= len(palette):
        return palette[:n]
    return [palette[i % len(palette)] for i in range(n)]


def cluster_color_map(labels):
    labels = np.asarray(labels)
    unique_labels = sorted(pd.unique(labels))
    colors = get_discrete_colors(len(unique_labels))
    return {cluster: colors[idx] for idx, cluster in enumerate(unique_labels)}


def make_umap_grid(xa, xb, grid_step=0.03, pad=0.5):
    xa = np.asarray(xa, dtype=np.float64)
    xb = np.asarray(xb, dtype=np.float64)

    x_min, x_max = xa.min() - pad, xa.max() + pad
    y_min, y_max = xb.min() - pad, xb.max() + pad
    xx, yy = np.meshgrid(
        np.arange(x_min, x_max, grid_step, dtype=np.float64),
        np.arange(y_min, y_max, grid_step, dtype=np.float64),
    )
    return xx, yy


def save_figure_png_and_svg(save_path, dpi=200):
    save_path = os.path.abspath(save_path)
    root, ext = os.path.splitext(save_path)
    ext = ext.lower()

    if ext == ".svg":
        svg_path = save_path
        png_path = root + ".png"
    else:
        png_path = save_path
        svg_path = root + ".svg"

    plt.savefig(png_path, dpi=dpi, bbox_inches="tight")
    plt.savefig(svg_path, format="svg", bbox_inches="tight")


def plot_2d_true_labels(
    xa,
    xb,
    labels,
    title,
    xlabel,
    ylabel,
    save_path,
    legend_title=None,
    boundary_model=None,
    grid_step=0.03,
    show_boundary=True,
    boundary_alpha=0.18,
    color_reference_labels=None,
):
    xa = np.asarray(xa, dtype=np.float64)
    xb = np.asarray(xb, dtype=np.float64)
    labels = np.asarray(labels).astype(str)

    plt.figure(figsize=(8, 6))

    if (boundary_model is not None) and show_boundary and (len(xa) > 0):
        xx, yy = make_umap_grid(xa, xb, grid_step=grid_step, pad=0.5)
        grid = np.c_[xx.ravel(), yy.ravel()].astype(np.float64)
        zz = boundary_model.predict(grid).reshape(xx.shape)
        n_clusters = int(len(np.unique(zz)))

        plt.contourf(
            xx,
            yy,
            zz,
            alpha=boundary_alpha,
            levels=np.arange(n_clusters + 1) - 0.5,
        )

        plt.contour(
            xx,
            yy,
            zz,
            colors="k",
            linewidths=0.6,
            alpha=0.7,
            levels=np.arange(n_clusters + 1) - 0.5,
        )

    classes = sorted(pd.unique(labels), key=class_sort_key)
    colors = type_number_color_map(labels, reference_labels=color_reference_labels)

    for cls in classes:
        mask = labels == cls
        plt.scatter(
            xa[mask],
            xb[mask],
            label=str(cls),
            alpha=0.86,
            s=35,
            color=colors[cls],
            edgecolors="none",
            linewidths=0,
        )

    if legend_title is not None:
        plt.legend(title=legend_title, bbox_to_anchor=(1.02, 1), loc="upper left", frameon=True)

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    save_figure_png_and_svg(save_path, dpi=200)
    plt.close()


def plot_2d_cluster_with_boundary(
    xa,
    xb,
    labels,
    model,
    title,
    xlabel,
    ylabel,
    save_path,
    legend_title=None,
    grid_step=0.03,
):
    xa = np.asarray(xa, dtype=np.float64)
    xb = np.asarray(xb, dtype=np.float64)
    labels = np.asarray(labels)

    plt.figure(figsize=(8, 6))

    unique_labels = sorted(pd.unique(labels))
    colors = cluster_color_map(labels)

    xx, yy = make_umap_grid(xa, xb, grid_step=grid_step, pad=0.5)
    grid = np.c_[xx.ravel(), yy.ravel()].astype(np.float64)
    zz = model.predict(grid).reshape(xx.shape)
    n_clusters = int(len(np.unique(zz)))

    plt.contourf(
        xx,
        yy,
        zz,
        alpha=0.18,
        levels=np.arange(n_clusters + 1) - 0.5,
    )

    for cluster in unique_labels:
        mask = labels == cluster
        plt.scatter(
            xa[mask],
            xb[mask],
            label=f"Cluster {cluster}",
            alpha=0.88,
            s=35,
            color=colors[cluster],
        )

    plt.contour(
        xx,
        yy,
        zz,
        colors="k",
        linewidths=0.6,
        alpha=0.7,
        levels=np.arange(n_clusters + 1) - 0.5,
    )

    centers = model.cluster_centers_
    plt.scatter(
        centers[:, 0],
        centers[:, 1],
        marker="X",
        s=140,
        color="black",
        linewidth=1.0,
        label="Centers",
    )
    for idx, (x, y) in enumerate(centers):
        plt.text(x, y, f" {idx}", color="black", fontsize=10, weight="bold", va="center")

    if legend_title is not None:
        plt.legend(title=legend_title, bbox_to_anchor=(1.02, 1), loc="upper left")

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    save_figure_png_and_svg(save_path, dpi=200)
    plt.close()


def save_type_number_color_legend_svg(save_dir, filename="type_number_color_legend.svg"):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    class_order = [str(i) for i in range(1, 15)]
    color_map = type_number_color_map(class_order, reference_labels=class_order)
    handles = [
        Patch(facecolor=color_map[label], edgecolor="none", label=label)
        for label in class_order
    ]

    fig, ax = plt.subplots(figsize=(2.8, 7.2))
    ax.axis("off")
    legend = ax.legend(
        handles=handles,
        title="Type Number",
        loc="center",
        frameon=True,
        prop={"family": PIE_FONT_FAMILY, "size": PIE_LEGEND_FONT_SIZE},
    )
    legend.get_title().set_fontfamily(PIE_FONT_FAMILY)
    legend.get_title().set_fontsize(PIE_LEGEND_TITLE_FONT_SIZE)
    svg_path = save_dir / filename
    fig.savefig(svg_path, format="svg", bbox_inches="tight")
    plt.close(fig)
    return svg_path


def plot_cluster_class_pies(
    cluster_labels,
    true_labels,
    save_dir,
    class_order=None,
    prefix="kmeans_cluster",
    legend_title="TRUE",
):
    cluster_labels = np.asarray(cluster_labels)
    true_labels = np.asarray(true_labels).astype(str)
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    if class_order is None:
        class_order = sorted(pd.unique(true_labels), key=class_sort_key)
    else:
        class_order = [str(item) for item in class_order]

    color_map = type_number_color_map(class_order, reference_labels=class_order)
    unique_clusters = sorted(pd.unique(cluster_labels))
    written = [save_type_number_color_legend_svg(save_dir)]

    for cluster in unique_clusters:
        mask = cluster_labels == cluster
        labels_in_cluster = true_labels[mask]
        counts = pd.Series(labels_in_cluster).value_counts()

        values = []
        colors_present = []

        for cls in class_order:
            count = int(counts.get(cls, 0))
            if count > 0:
                values.append(count)
                colors_present.append(color_map[cls])

        total = int(np.sum(values))
        plt.figure(figsize=(9, 7))

        if total == 0:
            plt.text(
                0.5,
                0.5,
                f"Cluster {cluster}\nNo samples",
                ha="center",
                va="center",
                fontsize=PIE_EMPTY_FONT_SIZE,
                fontname=PIE_FONT_FAMILY,
            )
            plt.axis("off")
        else:
            plt.pie(
                values,
                labels=None,
                colors=colors_present,
                startangle=90,
                counterclock=False,
                wedgeprops={"edgecolor": "white", "linewidth": 1},
            )
            plt.title(
                f"Cluster {cluster}: class composition (n={total})",
                fontname=PIE_FONT_FAMILY,
                fontsize=PIE_TITLE_FONT_SIZE,
            )

        plt.tight_layout()
        png_path = save_dir / f"{prefix}_{cluster}_pie.png"
        save_figure_png_and_svg(png_path, dpi=200)
        plt.close()
        written.append(png_path)
        written.append(png_path.with_suffix(".svg"))

    return written


def sorted_like_results(df):
    if df.empty:
        return df
    for column, default in RESULT_SORT_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default
    return df.sort_values(
        RESULT_SORT_COLUMNS,
        ascending=RESULT_SORT_ASCENDING,
    ).reset_index(drop=True)


def write_df_sheet_chunks(writer, df, base_sheet_name, max_rows):
    if df.empty:
        df.to_excel(writer, sheet_name=base_sheet_name[:31], index=False)
        return

    chunk_size = max(1, min(int(max_rows), EXCEL_MAX_ROWS - 1))
    if len(df) <= chunk_size:
        df.to_excel(writer, sheet_name=base_sheet_name[:31], index=False)
        return

    for idx, start in enumerate(range(0, len(df), chunk_size), start=1):
        sheet_name = f"{base_sheet_name}_{idx:03d}"[:31]
        df.iloc[start : start + chunk_size].to_excel(writer, sheet_name=sheet_name, index=False)


def build_feature_count_summary(results_df):
    rows = []
    if results_df.empty or "selected_feature_count" not in results_df.columns:
        return pd.DataFrame(rows)

    for feature_count, part in results_df.groupby("selected_feature_count", sort=True):
        ranked = sorted_like_results(part.copy())
        best = ranked.iloc[0].to_dict()
        rows.append(
            {
                "selected_feature_count": int(feature_count),
                "feature_set_count": int(part["feature_set_id"].nunique()) if "feature_set_id" in part.columns else np.nan,
                "evaluated_parameter_rows": int(len(part)),
                "selection_valid_rows": int(part.get("selection_valid", pd.Series(dtype=bool)).fillna(False).sum()),
                "best_feature_set_id": best.get("feature_set_id"),
                "best_selected_features": best.get("selected_features"),
                "best_umap_n_neighbors": best.get("umap_n_neighbors"),
                "best_umap_min_dist": best.get("umap_min_dist"),
                "best_kmeans_n_clusters": best.get("kmeans_n_clusters"),
                "best_score": best.get("score"),
                "best_silhouette": best.get("silhouette"),
                "best_raw_silhouette": best.get("raw_silhouette"),
                "best_davies_bouldin": best.get("davies_bouldin"),
                "best_selection_valid": best.get("selection_valid"),
                "best_cluster_sizes": best.get("cluster_sizes"),
            }
        )
    return pd.DataFrame(rows)


def save_best_individual_outputs(
    save_dir,
    best_payload,
    args,
    title_prefix,
    pie_dir_name="cluster_pies",
    write_legacy_names=False,
):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    output_paths = {}
    labels_xlsx = save_dir / "best_auto_umap_labels.xlsx"
    metadata_xlsx = save_dir / "best_auto_umap_metadata.xlsx"
    best_labels = build_best_labels_df(best_payload["df"], best_payload)
    best_labels.to_excel(labels_xlsx, index=False)
    pd.DataFrame([best_payload["row"]]).to_excel(metadata_xlsx, index=False)

    output_paths["labels_xlsx"] = labels_xlsx
    output_paths["metadata_xlsx"] = metadata_xlsx

    if not args.save_plots:
        return output_paths

    true_with_boundary_png = save_dir / "best_auto_umap_2d_true_with_kmeans_boundary.png"
    cluster_boundary_png = save_dir / "best_auto_umap_2d_kmeans_boundary.png"
    y_true_filtered = best_payload["y_true"][best_payload["keep_mask"]]
    class_order = sorted(pd.unique(best_payload["y_true"].astype(str)), key=class_sort_key)

    plot_2d_true_labels(
        best_payload["Z2"][:, 0],
        best_payload["Z2"][:, 1],
        y_true_filtered,
        title=f"{title_prefix} UMAP 2D colored by TRUE class + KMeans boundary",
        xlabel="UMAP1",
        ylabel="UMAP2",
        save_path=true_with_boundary_png,
        legend_title="TRUE",
        boundary_model=best_payload["model"],
        grid_step=0.03,
        show_boundary=True,
        color_reference_labels=best_payload["y_true"],
    )

    plot_2d_cluster_with_boundary(
        best_payload["Z2"][:, 0],
        best_payload["Z2"][:, 1],
        best_payload["labels"],
        model=best_payload["model"],
        title=f"{title_prefix} UMAP 2D + KMeans (clusters={best_payload['model'].n_clusters})",
        xlabel="UMAP1",
        ylabel="UMAP2",
        save_path=cluster_boundary_png,
        legend_title="KMeans",
        grid_step=0.03,
    )

    pie_dir = save_dir / pie_dir_name
    plot_cluster_class_pies(
        cluster_labels=best_payload["labels"],
        true_labels=y_true_filtered,
        save_dir=pie_dir,
        class_order=class_order,
        prefix="best_auto_cluster",
        legend_title="TRUE",
    )

    output_paths["true_with_boundary_png"] = true_with_boundary_png
    output_paths["true_with_boundary_svg"] = true_with_boundary_png.with_suffix(".svg")
    output_paths["cluster_boundary_png"] = cluster_boundary_png
    output_paths["cluster_boundary_svg"] = cluster_boundary_png.with_suffix(".svg")
    output_paths["pie_dir"] = pie_dir

    if write_legacy_names:
        legacy_true_png = save_dir / "best_auto_umap_true_labels.png"
        legacy_cluster_png = save_dir / "best_auto_umap_kmeans.png"
        shutil.copyfile(true_with_boundary_png, legacy_true_png)
        shutil.copyfile(true_with_boundary_png.with_suffix(".svg"), legacy_true_png.with_suffix(".svg"))
        shutil.copyfile(cluster_boundary_png, legacy_cluster_png)
        shutil.copyfile(cluster_boundary_png.with_suffix(".svg"), legacy_cluster_png.with_suffix(".svg"))
        output_paths["legacy_true_with_boundary_png"] = legacy_true_png
        output_paths["legacy_true_with_boundary_svg"] = legacy_true_png.with_suffix(".svg")
        output_paths["legacy_cluster_boundary_png"] = legacy_cluster_png
        output_paths["legacy_cluster_boundary_svg"] = legacy_cluster_png.with_suffix(".svg")

    return output_paths


def config_rows(args, feature_cols, combos, n_neighbors, min_dist, n_clusters, elapsed=None):
    rows = [
        ("input", str(args.input)),
        ("output_dir", str(args.output_dir)),
        ("label_col", args.label_col),
        ("name_col", args.name_col),
        ("feature_columns", "; ".join(feature_cols)),
        ("feature_column_count", len(feature_cols)),
        ("feature_combination_count", len(combos)),
        ("param_preset", args.param_preset),
        ("umap_n_neighbors_list", ", ".join(str(v) for v in n_neighbors)),
        ("umap_min_dist_list", ", ".join(str(v) for v in min_dist)),
        ("kmeans_n_clusters_list", ", ".join(str(v) for v in n_clusters)),
        ("parameter_grid_size", len(n_neighbors) * len(min_dist) * len(n_clusters)),
        ("total_kmeans_evaluations", len(combos) * len(n_neighbors) * len(min_dist) * len(n_clusters)),
        ("target_cluster_min", args.target_cluster_min),
        ("target_cluster_max", args.target_cluster_max),
        ("min_valid_class_count", args.min_valid_class_count),
        ("max_valid_class_count", args.max_valid_class_count),
        ("silhouette_threshold", args.silhouette_threshold),
        ("min_cluster_size_abs", args.min_cluster_size_abs),
        ("min_cluster_size_frac", args.min_cluster_size_frac),
        ("random_state", args.random_state),
        ("kmeans_n_init", args.kmeans_n_init),
        ("initial_edge_filter", args.use_initial_edge_filter),
        ("initial_edge_points_to_remove", args.initial_edge_points_to_remove),
        ("score_function", "classification_score aligned with explore_dimensionless_feature_sets.py"),
        ("score_params", json.dumps(DEFAULT_SCORE_PARAMS, ensure_ascii=False)),
    ]
    if elapsed is not None:
        rows.append(("elapsed_seconds", elapsed))
    return pd.DataFrame(rows, columns=["key", "value"])


def save_outputs(
    args,
    results_df,
    best_payload,
    best_payloads_by_feature_count,
    feature_cols,
    combos,
    n_neighbors,
    min_dist,
    n_clusters,
    elapsed,
):
    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_csv = args.output_dir / "auto_umap_feature_search_all_results.csv"
    best_per_feature_csv = args.output_dir / "auto_umap_feature_search_best_per_feature_set.csv"
    result_xlsx = args.output_dir / "auto_umap_feature_search_results.xlsx"
    process_xlsx = args.output_dir / "auto_umap_feature_search_process.xlsx"

    results_df.to_csv(all_csv, index=False, encoding="utf-8-sig")
    best_per_feature = (
        sorted_like_results(results_df.copy())
        .groupby("feature_set_id", as_index=False)
        .head(1)
        .reset_index(drop=True)
    )
    best_per_feature = best_per_feature.sort_values("feature_set_index").reset_index(drop=True)
    best_per_feature_count = (
        sorted_like_results(results_df.copy())
        .groupby("selected_feature_count", as_index=False)
        .head(1)
        .reset_index(drop=True)
    )
    best_per_feature_count = best_per_feature_count.sort_values("selected_feature_count").reset_index(drop=True)
    feature_count_summary = build_feature_count_summary(results_df)
    best_per_feature.to_csv(best_per_feature_csv, index=False, encoding="utf-8-sig")

    config_df = config_rows(args, feature_cols, combos, n_neighbors, min_dist, n_clusters, elapsed=elapsed)
    score_df = pd.DataFrame(
        [{"parameter": key, "value": value} for key, value in DEFAULT_SCORE_PARAMS.items()]
    )

    excel_results = results_df
    sheet_name = "all_results"
    if not args.write_all_results_excel or len(results_df) > args.excel_row_limit:
        excel_results = results_df.head(args.top_results)
        sheet_name = "top_results"

    try:
        with pd.ExcelWriter(result_xlsx, engine="openpyxl") as writer:
            excel_results.to_excel(writer, sheet_name=sheet_name, index=False)
            best_per_feature.to_excel(writer, sheet_name="best_per_feature_set", index=False)
            best_per_feature_count.to_excel(writer, sheet_name="best_per_feature_count", index=False)
            feature_count_summary.to_excel(writer, sheet_name="feature_count_summary", index=False)
            results_df.head(1).to_excel(writer, sheet_name="best_overall", index=False)
            config_df.to_excel(writer, sheet_name="run_config", index=False)
            score_df.to_excel(writer, sheet_name="score_params", index=False)
    except PermissionError:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_xlsx = args.output_dir / f"auto_umap_feature_search_results_{timestamp}.xlsx"
        with pd.ExcelWriter(result_xlsx, engine="openpyxl") as writer:
            excel_results.to_excel(writer, sheet_name=sheet_name, index=False)
            best_per_feature.to_excel(writer, sheet_name="best_per_feature_set", index=False)
            best_per_feature_count.to_excel(writer, sheet_name="best_per_feature_count", index=False)
            feature_count_summary.to_excel(writer, sheet_name="feature_count_summary", index=False)
            results_df.head(1).to_excel(writer, sheet_name="best_overall", index=False)
            config_df.to_excel(writer, sheet_name="run_config", index=False)
            score_df.to_excel(writer, sheet_name="score_params", index=False)

    try:
        with pd.ExcelWriter(process_xlsx, engine="openpyxl") as writer:
            write_df_sheet_chunks(writer, results_df, "all_results", args.excel_row_limit)
            if "evaluation_index" in results_df.columns:
                evaluation_order = results_df.sort_values("evaluation_index").reset_index(drop=True)
                write_df_sheet_chunks(writer, evaluation_order, "evaluation_order", args.excel_row_limit)
            best_per_feature.to_excel(writer, sheet_name="best_per_feature_set", index=False)
            best_per_feature_count.to_excel(writer, sheet_name="best_per_feature_count", index=False)
            feature_count_summary.to_excel(writer, sheet_name="feature_count_summary", index=False)
            results_df.head(1).to_excel(writer, sheet_name="best_overall", index=False)
            config_df.to_excel(writer, sheet_name="run_config", index=False)
            score_df.to_excel(writer, sheet_name="score_params", index=False)
    except PermissionError:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        process_xlsx = args.output_dir / f"auto_umap_feature_search_process_{timestamp}.xlsx"
        with pd.ExcelWriter(process_xlsx, engine="openpyxl") as writer:
            write_df_sheet_chunks(writer, results_df, "all_results", args.excel_row_limit)
            if "evaluation_index" in results_df.columns:
                evaluation_order = results_df.sort_values("evaluation_index").reset_index(drop=True)
                write_df_sheet_chunks(writer, evaluation_order, "evaluation_order", args.excel_row_limit)
            best_per_feature.to_excel(writer, sheet_name="best_per_feature_set", index=False)
            best_per_feature_count.to_excel(writer, sheet_name="best_per_feature_count", index=False)
            feature_count_summary.to_excel(writer, sheet_name="feature_count_summary", index=False)
            results_df.head(1).to_excel(writer, sheet_name="best_overall", index=False)
            config_df.to_excel(writer, sheet_name="run_config", index=False)
            score_df.to_excel(writer, sheet_name="score_params", index=False)

    overall_paths = save_best_individual_outputs(
        args.output_dir,
        best_payload,
        args,
        title_prefix="Best auto",
        pie_dir_name="best_auto_cluster_pies",
        write_legacy_names=True,
    )

    feature_count_root = args.output_dir / "best_by_feature_count"
    if feature_count_root.exists():
        shutil.rmtree(feature_count_root)
    feature_count_root.mkdir(parents=True, exist_ok=True)

    overall_count = int(best_payload["row"]["selected_feature_count"])
    feature_count_dirs = []
    for feature_count in sorted(best_payloads_by_feature_count):
        suffix = "_best" if int(feature_count) == overall_count else ""
        folder = feature_count_root / f"feature_count_{int(feature_count)}{suffix}"
        save_best_individual_outputs(
            folder,
            best_payloads_by_feature_count[feature_count],
            args,
            title_prefix=f"Best feature-count {int(feature_count)}",
            pie_dir_name="cluster_pies",
            write_legacy_names=False,
        )
        feature_count_dirs.append(folder)

    output_paths = {
        "all_csv": all_csv,
        "best_per_feature_csv": best_per_feature_csv,
        "result_xlsx": result_xlsx,
        "process_xlsx": process_xlsx,
        "best_by_feature_count_dir": feature_count_root,
    }
    output_paths.update(overall_paths)
    for idx, folder in enumerate(feature_count_dirs, start=1):
        output_paths[f"feature_count_best_dir_{idx}"] = folder

    return output_paths


def run_search(df, feature_cols, combos, n_neighbors, min_dist, n_clusters, args):
    import umap

    rows = []
    best_key = None
    best_payload = None
    best_by_feature_count = {}
    y_true = df[args.label_col].astype(str).to_numpy() if args.label_col in df.columns else None
    start = time.perf_counter()

    for combo_idx, features in enumerate(combos, start=1):
        combo_start = time.perf_counter()
        selected_df = df.loc[:, list(features)]
        feature_set_id = f"fs_{combo_idx:05d}"

        try:
            X_std_full = preprocess_matrix(selected_df.to_numpy(dtype=float))
            if args.use_initial_edge_filter:
                X_std, keep_mask, removed_indices, edge_distance = initial_edge_filter_points(
                    X_std_full,
                    n_remove=args.initial_edge_points_to_remove,
                )
            else:
                X_std = X_std_full
                keep_mask = np.ones(len(df), dtype=bool)
                removed_indices = np.array([], dtype=int)
                edge_distance = np.zeros(len(df), dtype=float)

            combo_best_row = None
            combo_best_key = None

            for neighbor in n_neighbors:
                if neighbor >= len(X_std):
                    continue

                for dist in min_dist:
                    reducer = umap.UMAP(
                        n_components=2,
                        n_neighbors=int(neighbor),
                        min_dist=float(dist),
                        metric=args.umap_metric,
                        spread=args.umap_spread,
                        repulsion_strength=args.umap_repulsion_strength,
                        random_state=args.random_state,
                        n_jobs=-1,
                    )
                    Z2 = np.asarray(reducer.fit_transform(X_std), dtype=np.float64)

                    for clusters in n_clusters:
                        row, labels, model = evaluate_kmeans(Z2, int(clusters), args)
                        if row is None:
                            continue

                        row.update(
                            {
                                "evaluation_index": len(rows) + 1,
                                "feature_set_id": feature_set_id,
                                "feature_set_index": combo_idx,
                                "selected_feature_count": len(features),
                                "selected_features": "; ".join(features),
                                "umap_n_neighbors": int(neighbor),
                                "umap_min_dist": float(dist),
                                "kept_sample_count": int(len(X_std)),
                                "initial_edge_removed_count": int(len(removed_indices)),
                                "initial_edge_removed_indices": "; ".join(str(i) for i in removed_indices),
                            }
                        )
                        rows.append(row)

                        current_key = selection_key(row)
                        if combo_best_key is None or current_key > combo_best_key:
                            combo_best_key = current_key
                            combo_best_row = row

                        if best_key is None or current_key > best_key:
                            best_key = current_key
                            best_payload = {
                                "df": df,
                                "features": tuple(features),
                                "row": row.copy(),
                                "Z2": Z2.copy(),
                                "labels": np.asarray(labels).copy(),
                                "model": model,
                                "centers": np.asarray(model.cluster_centers_).copy(),
                                "keep_mask": keep_mask.copy(),
                                "edge_distance": np.asarray(edge_distance).copy(),
                                "y_true": y_true.copy() if y_true is not None else np.array([]),
                            }

                        feature_count = len(features)
                        count_best = best_by_feature_count.get(feature_count)
                        if count_best is None or current_key > count_best["key"]:
                            best_by_feature_count[feature_count] = {
                                "key": current_key,
                                "payload": {
                                    "df": df,
                                    "features": tuple(features),
                                    "row": row.copy(),
                                    "Z2": Z2.copy(),
                                    "labels": np.asarray(labels).copy(),
                                    "model": model,
                                    "centers": np.asarray(model.cluster_centers_).copy(),
                                    "keep_mask": keep_mask.copy(),
                                    "edge_distance": np.asarray(edge_distance).copy(),
                                    "y_true": y_true.copy() if y_true is not None else np.array([]),
                                },
                            }

            combo_elapsed = time.perf_counter() - combo_start
            if args.progress_every > 0 and (
                combo_idx == 1 or combo_idx % args.progress_every == 0 or combo_idx == len(combos)
            ):
                if combo_best_row is None:
                    best_text = "no valid parameter result"
                else:
                    best_text = (
                        f"best score={combo_best_row['score']:.4f}, "
                        f"sil={combo_best_row['silhouette']:.4f}, "
                        f"k={combo_best_row['kmeans_n_clusters']}, "
                        f"nn={combo_best_row['umap_n_neighbors']}, "
                        f"dist={combo_best_row['umap_min_dist']}"
                    )
                print(
                    f"[{combo_idx}/{len(combos)}] {feature_set_id} "
                    f"({len(features)} features, {combo_elapsed:.1f}s): {best_text}"
                )

        except Exception as exc:
            rows.append(
                {
                    "evaluation_index": len(rows) + 1,
                    "feature_set_id": feature_set_id,
                    "feature_set_index": combo_idx,
                    "selected_feature_count": len(features),
                    "selected_features": "; ".join(features),
                    "error": str(exc),
                    "selection_valid": False,
                    "score": np.nan,
                    "silhouette": np.nan,
                }
            )
            print(f"[{combo_idx}/{len(combos)}] {feature_set_id} failed: {exc}")

    elapsed = time.perf_counter() - start
    results_df = sorted_results_df(rows)
    if best_payload is None:
        raise RuntimeError("No valid UMAP + KMeans result was produced.")
    best_payloads_by_feature_count = {
        feature_count: info["payload"]
        for feature_count, info in best_by_feature_count.items()
    }
    return results_df, best_payload, best_payloads_by_feature_count, elapsed


def print_dry_run(feature_cols, combos, n_neighbors, min_dist, n_clusters):
    param_grid = len(n_neighbors) * len(min_dist) * len(n_clusters)
    total = len(combos) * param_grid
    full_6_to_11 = sum(
        math.comb(len(feature_cols), count)
        for count in range(6, min(11, len(feature_cols)) + 1)
    )
    print("Dry run summary")
    print(f"Feature columns ({len(feature_cols)}): {feature_cols}")
    print(f"Feature combinations selected: {len(combos)}")
    print(f"Full 6-11 feature combination count for these columns: {full_6_to_11}")
    print(f"UMAP n_neighbors: {n_neighbors}")
    print(f"UMAP min_dist: {min_dist}")
    print(f"KMeans n_clusters: {n_clusters}")
    print(f"Parameter grid per feature set: {param_grid}")
    print(f"Total KMeans evaluations: {total}")


def main():
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Missing input file: {args.input}")

    df = pd.read_excel(args.input, engine="openpyxl")
    feature_cols = resolve_feature_columns(df, args)
    if args.label_col not in df.columns:
        raise ValueError(f"Missing label column: {args.label_col}")
    if not feature_cols:
        raise ValueError("No feature columns were resolved.")

    combos = build_feature_combinations(feature_cols, args)
    if args.use_initial_edge_filter and len(df) > args.initial_edge_points_to_remove:
        effective_n = len(df) - args.initial_edge_points_to_remove
    else:
        effective_n = len(df)
    effective_n = max(2, effective_n)
    n_neighbors, min_dist, n_clusters = resolve_parameter_grid(effective_n, args)

    print_dry_run(feature_cols, combos, n_neighbors, min_dist, n_clusters)
    if args.dry_run:
        return

    results_df, best_payload, best_payloads_by_feature_count, elapsed = run_search(
        df,
        feature_cols,
        combos,
        n_neighbors,
        min_dist,
        n_clusters,
        args,
    )

    output_paths = save_outputs(
        args,
        results_df,
        best_payload,
        best_payloads_by_feature_count,
        feature_cols,
        combos,
        n_neighbors,
        min_dist,
        n_clusters,
        elapsed,
    )

    best_row = results_df.iloc[0].to_dict()
    full_6_to_11 = sum(
        math.comb(len(feature_cols), count)
        for count in range(6, min(11, len(feature_cols)) + 1)
    )
    avg_per_feature_set = elapsed / max(len(combos), 1)
    estimated_full_seconds = avg_per_feature_set * full_6_to_11

    print("\nBest auto UMAP result:")
    print(json.dumps(
        {
            "feature_set_id": best_row.get("feature_set_id"),
            "selected_feature_count": best_row.get("selected_feature_count"),
            "selected_features": best_row.get("selected_features"),
            "umap_n_neighbors": best_row.get("umap_n_neighbors"),
            "umap_min_dist": best_row.get("umap_min_dist"),
            "kmeans_n_clusters": best_row.get("kmeans_n_clusters"),
            "silhouette": best_row.get("silhouette"),
            "davies_bouldin": best_row.get("davies_bouldin"),
            "score": best_row.get("score"),
            "selection_valid": best_row.get("selection_valid"),
        },
        indent=2,
        ensure_ascii=False,
    ))

    print("\nTiming:")
    print(f"Elapsed seconds: {elapsed:.1f}")
    print(f"Average seconds per feature set: {avg_per_feature_set:.2f}")
    print(f"Estimated seconds for full 6-11 feature enumeration: {estimated_full_seconds:.1f}")

    print("\nGenerated files:")
    for path in output_paths.values():
        print(f" - {path}")


if __name__ == "__main__":
    main()
