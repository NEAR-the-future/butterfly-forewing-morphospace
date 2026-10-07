import argparse
import hashlib
import json
import os
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

try:
    SEARCH_OMP_THREADS = max(
        1,
        int(os.environ.get("UMAP_SEARCH_THREADS", str(os.cpu_count() or 1))),
    )
except ValueError:
    SEARCH_OMP_THREADS = max(1, os.cpu_count() or 1)
try:
    KMEANS_SAFE_THREADS = max(1, int(os.environ.get("KMEANS_SAFE_THREADS", "2")))
except ValueError:
    KMEANS_SAFE_THREADS = 2
os.environ["OMP_NUM_THREADS"] = str(SEARCH_OMP_THREADS)
# Do not globally set MKL_NUM_THREADS!! UMAP's spectral initialisation uses it.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
warnings.filterwarnings(
    "ignore",
    message=r"n_jobs value .* overridden to 1 by setting random_state.*",
    category=UserWarning,
    module=r"umap\.umap_",
)
warnings.filterwarnings(
    "ignore",
    message=r"Spectral initialisation failed!",
    category=UserWarning,
    module=r"umap\.spectral",
)

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

import auto_umap_feature_set_search as base


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REFERENCE_PATH = SCRIPT_DIR / "summary_11.xlsx"
DEFAULT_GUARD_INPUT_PATH = SCRIPT_DIR / "summary_input-all.xlsx"
DEFAULT_GUARD_INPUT_NAME = "AirPulse"

DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "explore_runs" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
MODEL_ARTIFACT_NAME = "best_reference_umap_model.joblib"
ARTIFACT_SCHEMA_VERSION = 1


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Search feature subsets and UMAP + KMeans parameters using only the "
            "reference workbook, then save a frozen model artifact for unseen-row transform."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_REFERENCE_PATH)
    parser.add_argument("--input-sheet", default=None)
    parser.add_argument("--guard-input", type=Path, default=DEFAULT_GUARD_INPUT_PATH)
    parser.add_argument("--guard-input-sheet", default=None)
    parser.add_argument("--guard-input-name", default=DEFAULT_GUARD_INPUT_NAME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--label-col", default="Type Number")
    parser.add_argument("--name-col", default="Name")
    parser.add_argument(
        "--feature-cols",
        default=None,
        help="Comma-separated features. Default: all numeric columns except label/name.",
    )
    parser.add_argument("--min-features", type=int, default=6)
    parser.add_argument("--max-features", type=int, default=11)
    parser.add_argument("--feature-counts", default=None)
    parser.add_argument("--max-feature-combinations", type=int, default=None)

    parser.add_argument(
        "--search-mode",
        choices=["fast", "full"],
        default="fast",
        help=(
            "fast uses a paper-oriented 30-UMAP/120-KMeans grid per feature set; "
            "full uses the original preset grid (110/770 for balanced)."
        ),
    )
    parser.add_argument("--param-preset", choices=["quick", "balanced", "dense"], default="balanced")
    parser.add_argument("--umap-n-neighbors-list", default="auto")
    parser.add_argument("--umap-min-dist-list", default="auto")
    parser.add_argument("--kmeans-n-clusters-list", default="auto")
    parser.add_argument(
        "--umap-init",
        choices=["random", "spectral"],
        default="random",
        help="UMAP initialisation. random is faster and avoids spectral solver failures.",
    )
    parser.add_argument(
        "--umap-n-epochs",
        type=int,
        default=None,
        help=(
            "UMAP optimisation epochs. Default: 300 in fast mode; "
            "the umap-learn default in full mode."
        ),
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

    parser.set_defaults(use_initial_edge_filter=False)
    parser.add_argument(
        "--use-initial-edge-filter",
        dest="use_initial_edge_filter",
        action="store_true",
        help="Optionally remove reference edge rows before UMAP fitting (default: keep all 383 rows).",
    )
    parser.add_argument("--no-initial-edge-filter", dest="use_initial_edge_filter", action="store_false")
    parser.add_argument("--initial-edge-points-to-remove", type=int, default=20)
    parser.add_argument("--top-results", type=int, default=2000)
    parser.add_argument("--excel-row-limit", type=int, default=1_000_000)
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Print a feature-set start/end summary every N feature sets; 0 disables it.",
    )
    parser.add_argument(
        "--evaluation-progress-every",
        type=int,
        default=0,
        help=(
            "Optional detailed logging: print every N UMAP/KMeans evaluations. "
            "Default 0 keeps one summary line per feature set."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_table(path, sheet=None):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Missing reference table: {path}")
    if path.suffix.lower() in {".csv", ".tsv"}:
        return pd.read_csv(path, sep="\t" if path.suffix.lower() == ".tsv" else ",")
    return pd.read_excel(path, sheet_name=0 if sheet is None else sheet, engine="openpyxl")


def resolve_search_parameter_grid(n_samples, args):
    
    if args.search_mode == "full":
        return base.resolve_parameter_grid(n_samples, args)

    explicit_neighbors = base.parse_int_list(args.umap_n_neighbors_list)
    explicit_min_dist = base.parse_float_list(args.umap_min_dist_list)
    explicit_clusters = base.parse_int_list(args.kmeans_n_clusters_list)

    if explicit_neighbors is None:
        n_neighbors = [3, 4, 5, 8, 12, 20]
    else:
        n_neighbors = explicit_neighbors
    n_neighbors = base.unique_sorted_ints(
        n_neighbors,
        low=2,
        high=max(2, n_samples - 1),
    )

    if explicit_min_dist is None:
        
        min_dist = [0.0, 0.01, 0.05, 0.10, 0.20]
    else:
        min_dist = sorted(set(float(value) for value in explicit_min_dist))

    if explicit_clusters is None:
        n_clusters = list(
            range(
                max(2, int(args.target_cluster_min)),
                min(int(args.target_cluster_max), n_samples - 1) + 1,
            )
        )
    else:
        n_clusters = base.unique_sorted_ints(
            explicit_clusters,
            low=2,
            high=max(2, n_samples - 1),
        )

    if not n_neighbors or not min_dist or not n_clusters:
        raise ValueError("The resolved fast search grid is empty.")
    return n_neighbors, min_dist, n_clusters


def resolve_umap_n_epochs(args):
    if args.umap_n_epochs is not None:
        if args.umap_n_epochs <= 0:
            raise ValueError("--umap-n-epochs must be positive.")
        return int(args.umap_n_epochs)
    return 300 if args.search_mode == "fast" else None


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_array(values):
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(array.tobytes()).hexdigest()


def fit_reference_preprocessor(values):
    """Fit preprocessing on reference observations only."""
    values = np.asarray(values, dtype=float)
    values = np.where(np.isfinite(values), values, np.nan)
    imputer = SimpleImputer(strategy="median")
    imputed = imputer.fit_transform(values)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(imputed)
    return {"imputer": imputer, "scaler": scaler}, np.asarray(scaled, dtype=np.float64)


def transform_with_reference_preprocessor(values, fitted):
    values = np.asarray(values, dtype=float)
    values = np.where(np.isfinite(values), values, np.nan)
    imputed = fitted["imputer"].transform(values)
    return np.asarray(fitted["scaler"].transform(imputed), dtype=np.float64)


def build_neighbor_guard_context(reference_df, feature_cols, args):
    guard_df = read_table(args.guard_input, args.guard_input_sheet).reset_index(drop=True)
    if args.name_col not in guard_df.columns:
        raise ValueError(
            f"Missing name column in guard input table: {args.name_col}"
        )
    normalized_names = guard_df[args.name_col].astype(str).str.strip()
    matches = np.flatnonzero(normalized_names.eq(str(args.guard_input_name).strip()).to_numpy())
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one guard row named {args.guard_input_name!r} in "
            f"{args.guard_input}, found {len(matches)}."
        )
    missing = [feature for feature in feature_cols if feature not in guard_df.columns]
    if missing:
        raise ValueError(f"Guard input table is missing feature columns: {missing}")

    target_row_index = int(matches[0])
    reference_raw = reference_df.loc[:, feature_cols].apply(
        pd.to_numeric, errors="coerce"
    ).to_numpy(dtype=float)
    full_preprocessor, reference_processed = fit_reference_preprocessor(reference_raw)
    target_raw = guard_df.loc[[target_row_index], feature_cols].apply(
        pd.to_numeric, errors="coerce"
    ).to_numpy(dtype=float)
    target_processed = transform_with_reference_preprocessor(
        target_raw, full_preprocessor
    )[0]
    full_distances = np.linalg.norm(reference_processed - target_processed, axis=1)
    full_nearest_index = int(np.argmin(full_distances))
    reference_names = reference_df[args.name_col].astype(str).to_numpy()
    return {
        "source": Path(args.guard_input),
        "target_frame": guard_df.loc[[target_row_index]].copy(),
        "target_row_index": target_row_index,
        "target_name": str(guard_df.iloc[target_row_index][args.name_col]),
        "feature_cols": tuple(feature_cols),
        "reference_processed": np.asarray(reference_processed, dtype=np.float64),
        "target_processed": np.asarray(target_processed, dtype=np.float64),
        "reference_names": reference_names,
        "full_feature_nearest_original_index": full_nearest_index,
        "full_feature_nearest_name": str(reference_names[full_nearest_index]),
        "full_feature_nearest_distance": float(full_distances[full_nearest_index]),
    }


def evaluate_transform_neighbor_guard(
    reducer,
    selected_preprocessor,
    selected_features,
    reference_coordinates,
    keep_mask,
    guard_context,
):
    target_selected_raw = guard_context["target_frame"].loc[
        :, list(selected_features)
    ].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    target_selected = transform_with_reference_preprocessor(
        target_selected_raw, selected_preprocessor
    )

    stored_embedding_before = np.asarray(reducer.embedding_, dtype=np.float64).copy()
    target_coordinates = np.asarray(
        reducer.transform(target_selected), dtype=np.float64
    )
    stored_embedding_after = np.asarray(reducer.embedding_, dtype=np.float64)
    if not np.array_equal(
        stored_embedding_before, stored_embedding_after, equal_nan=True
    ):
        raise RuntimeError(
            "UMAP.transform changed the stored reference embedding during guard validation."
        )

    kept_original_indices = np.flatnonzero(np.asarray(keep_mask, dtype=bool))
    kept_feature_reference = guard_context["reference_processed"][keep_mask]
    feature_distances = np.linalg.norm(
        kept_feature_reference - guard_context["target_processed"], axis=1
    )
    umap_distances = np.linalg.norm(
        np.asarray(reference_coordinates, dtype=np.float64) - target_coordinates[0],
        axis=1,
    )
    feature_position = int(np.argmin(feature_distances))
    umap_position = int(np.argmin(umap_distances))
    feature_original_index = int(kept_original_indices[feature_position])
    umap_original_index = int(kept_original_indices[umap_position])
    neighbor_preserved = feature_original_index == umap_original_index
    names = guard_context["reference_names"]
    return {
        "guard_input_name": guard_context["target_name"],
        "guard_input_source_row_index": int(guard_context["target_row_index"]),
        "guard_input_transform_count": 1,
        "neighbor_preserved": bool(neighbor_preserved),
        "deformation_rejected": False,
        "guarded_selection_valid": bool(neighbor_preserved),
        "feature_space_nearest_names": str(names[feature_original_index]),
        "umap_space_nearest_names": str(names[umap_original_index]),
        "feature_space_nearest_original_indices": feature_original_index,
        "umap_space_nearest_original_indices": umap_original_index,
        "feature_space_nearest_distances": float(feature_distances[feature_position]),
        "umap_space_nearest_distances": float(umap_distances[umap_position]),
        "feature_space_reference_dimension": int(len(guard_context["feature_cols"])),
        "feature_space_reference_features": "; ".join(guard_context["feature_cols"]),
        "guard_reference_coordinates_unchanged": True,
    }


def evaluate_kmeans_batch_with_safe_threads(coordinates, cluster_counts, args):
    
    evaluations = []
    with threadpool_limits(limits=KMEANS_SAFE_THREADS, user_api="openmp"):
        for clusters in cluster_counts:
            evaluation_start = time.perf_counter()
            row, labels, model = base.evaluate_kmeans(coordinates, int(clusters), args)
            evaluations.append(
                (
                    int(clusters),
                    row,
                    labels,
                    model,
                    time.perf_counter() - evaluation_start,
                )
            )
    return evaluations


def format_duration(seconds):
    if seconds is None or not np.isfinite(seconds):
        return "--:--:--"
    seconds = max(0, int(round(float(seconds))))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_step_time(seconds):
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.3f}s"
    return f"{format_duration(seconds)} ({seconds:.1f}s)"


def progress_eta(start_time, completed, total):
    elapsed = time.perf_counter() - start_time
    if completed <= 0:
        return elapsed, np.nan
    remaining = max(int(total) - int(completed), 0)
    return elapsed, elapsed / completed * remaining


def should_report(index, total, every):
    return every > 0 and (index == 1 or index % every == 0 or index == total)


def selection_payload(df, features, row, preprocessor, reducer, Z_ref, labels, model, keep_mask, edge_distance):
    return {
        "df": df,
        "features": tuple(features),
        "row": row.copy(),
        "preprocessor": preprocessor,
        "reducer": reducer,
        "Z_ref": np.asarray(Z_ref).copy(),
        "labels": np.asarray(labels).copy(),
        "model": model,
        "keep_mask": np.asarray(keep_mask).copy(),
        "edge_distance": np.asarray(edge_distance).copy(),
    }


def run_search(
    df,
    feature_cols,
    combos,
    n_neighbors,
    min_dist,
    n_clusters,
    guard_context,
    args,
):
    import umap

    rows = []
    best_key = None
    best_payload = None
    best_by_feature_count = {}
    start = time.perf_counter()
    total_feature_sets = len(combos)
    umap_fits_per_feature_set = len(n_neighbors) * len(min_dist)
    evaluations_per_feature_set = umap_fits_per_feature_set * len(n_clusters)
    total_umap_fits = total_feature_sets * umap_fits_per_feature_set
    total_evaluations = total_feature_sets * evaluations_per_feature_set
    completed_umap_fits = 0
    completed_evaluations = 0
    cumulative_umap_seconds = 0.0
    cumulative_guard_seconds = 0.0
    cumulative_kmeans_seconds = 0.0
    umap_n_epochs = resolve_umap_n_epochs(args)

    print("\nReference-only fit + transform-only neighbor-guard search started", flush=True)
    print(
        f"Guard target: {guard_context['target_name']} | required nearest reference: "
        f"{guard_context['full_feature_nearest_name']} "
        f"(row {guard_context['full_feature_nearest_original_index']})",
        flush=True,
    )
    print(f"UMAP/search threads: {SEARCH_OMP_THREADS}", flush=True)
    print(f"Temporary KMeans threads: {KMEANS_SAFE_THREADS}", flush=True)
    print(f"Feature sets: {total_feature_sets}", flush=True)
    print(f"UMAP fits: {total_umap_fits}", flush=True)
    print(f"UMAP epochs: {umap_n_epochs if umap_n_epochs is not None else 'umap-learn default'}", flush=True)
    print(f"KMeans parameter evaluations (generations): {total_evaluations}", flush=True)

    for combo_idx, features in enumerate(combos, start=1):
        combo_start = time.perf_counter()
        feature_set_id = f"fs_{combo_idx:05d}"
        features = tuple(features)
        try:
            raw = df.loc[:, list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
            preprocessor, processed_full = fit_reference_preprocessor(raw)
            if args.use_initial_edge_filter:
                processed, keep_mask, removed_indices, edge_distance = base.initial_edge_filter_points(
                    processed_full,
                    n_remove=args.initial_edge_points_to_remove,
                )
            else:
                processed = processed_full
                keep_mask = np.ones(len(df), dtype=bool)
                removed_indices = np.array([], dtype=int)
                edge_distance = np.zeros(len(df), dtype=float)

            combo_best_row = None
            combo_best_key = None
            for neighbor_idx, neighbor in enumerate(n_neighbors, start=1):
                if int(neighbor) >= len(processed):
                    continue
                for dist_idx, dist in enumerate(min_dist, start=1):
                    umap_start = time.perf_counter()
                    reducer = umap.UMAP(
                        n_components=2,
                        n_neighbors=int(neighbor),
                        min_dist=float(dist),
                        metric=args.umap_metric,
                        spread=args.umap_spread,
                        repulsion_strength=args.umap_repulsion_strength,
                        random_state=args.random_state,
                        n_jobs=-1,
                        init=args.umap_init,
                        n_epochs=umap_n_epochs,
                        transform_seed=args.random_state,
                    )
                    Z_ref = np.asarray(reducer.fit_transform(processed), dtype=np.float64)
                    umap_elapsed = time.perf_counter() - umap_start
                    cumulative_umap_seconds += umap_elapsed
                    completed_umap_fits += 1
                    guard_start = time.perf_counter()
                    guard_result = evaluate_transform_neighbor_guard(
                        reducer,
                        preprocessor,
                        features,
                        Z_ref,
                        keep_mask,
                        guard_context,
                    )
                    cumulative_guard_seconds += time.perf_counter() - guard_start
                    overall_elapsed, overall_eta = progress_eta(
                        start, completed_umap_fits, total_umap_fits
                    )
                    if should_report(
                        completed_umap_fits,
                        total_umap_fits,
                        args.evaluation_progress_every,
                    ):
                        print(
                            f"  [UMAP {completed_umap_fits}/{total_umap_fits}] "
                            f"fs={combo_idx}/{total_feature_sets}, "
                            f"nn={int(neighbor)}, min_dist={float(dist):g} "
                            f"| fit={format_step_time(umap_elapsed)} "
                            f"| elapsed={format_duration(overall_elapsed)} "
                            f"| rough ETA={format_duration(overall_eta)}",
                            flush=True,
                        )

                    batch_evaluations = evaluate_kmeans_batch_with_safe_threads(
                        Z_ref, n_clusters, args
                    )
                    for clusters, row, labels, model, evaluation_elapsed in batch_evaluations:
                        cumulative_kmeans_seconds += evaluation_elapsed
                        completed_evaluations += 1
                        evaluation_total_elapsed, evaluation_eta = progress_eta(
                            start, completed_evaluations, total_evaluations
                        )
                        if row is None:
                            if should_report(
                                completed_evaluations,
                                total_evaluations,
                                args.evaluation_progress_every,
                            ):
                                print(
                                    f"    [Generation {completed_evaluations}/{total_evaluations}] "
                                    f"k={int(clusters)} skipped "
                                    f"| KMeans={format_step_time(evaluation_elapsed)} "
                                    f"| elapsed={format_duration(evaluation_total_elapsed)} "
                                    f"| ETA={format_duration(evaluation_eta)}",
                                    flush=True,
                                )
                            continue
                        row.update(
                            {
                                "evaluation_index": len(rows) + 1,
                                "feature_set_id": feature_set_id,
                                "feature_set_index": combo_idx,
                                "selected_feature_count": len(features),
                                "selected_features": "; ".join(features),
                                "search_mode": args.search_mode,
                                "umap_n_neighbors": int(neighbor),
                                "umap_min_dist": float(dist),
                                "umap_init": args.umap_init,
                                "umap_n_epochs": (
                                    int(umap_n_epochs) if umap_n_epochs is not None else "umap-learn default"
                                ),
                                "reference_sample_count": int(len(df)),
                                "umap_fit_sample_count": int(len(Z_ref)),
                                "kept_training_sample_count": int(len(Z_ref)),
                                "guard_input_sample_count": 1,
                                "unseen_rows_used_in_preprocessing_fit": 0,
                                "unseen_rows_used_in_umap_fit": 0,
                                "unseen_rows_used_in_kmeans_fit": 0,
                                "initial_edge_removed_count": int(len(removed_indices)),
                                "initial_edge_removed_indices": "; ".join(str(i) for i in removed_indices),
                            }
                        )
                        auto_selection_valid = bool(row["selection_valid"])
                        row.update(guard_result)
                        row["selection_valid_before_neighbor_guard"] = auto_selection_valid
                        row["auto_selection_valid"] = auto_selection_valid

                        row["selection_valid"] = bool(
                            guard_result["guarded_selection_valid"]
                        )
                        rows.append(row)
                        current_key = base.selection_key(row)
                        guard_passed = bool(guard_result["neighbor_preserved"])
                        if guard_passed and (
                            combo_best_key is None or current_key > combo_best_key
                        ):
                            combo_best_key = current_key
                            combo_best_row = row

                        count_best = best_by_feature_count.get(len(features))
                        improves_overall = guard_passed and (
                            best_key is None or current_key > best_key
                        )
                        improves_feature_count = (
                            guard_passed
                            and (count_best is None or current_key > count_best["key"])
                        )
                        if improves_overall or improves_feature_count:
                            payload = selection_payload(
                                df,
                                features,
                                row,
                                preprocessor,
                                reducer,
                                Z_ref,
                                labels,
                                model,
                                keep_mask,
                                edge_distance,
                            )
                        if improves_overall:
                            best_key = current_key
                            best_payload = payload
                        if improves_feature_count:
                            best_by_feature_count[len(features)] = {"key": current_key, "payload": payload}

                        if should_report(
                            completed_evaluations,
                            total_evaluations,
                            args.evaluation_progress_every,
                        ):
                            print(
                                f"    [Generation {completed_evaluations}/{total_evaluations}] "
                                f"fs={combo_idx}/{total_feature_sets}, "
                                f"nn={int(neighbor)}, min_dist={float(dist):g}, "
                                f"k={int(clusters)} "
                                f"| KMeans={format_step_time(evaluation_elapsed)} "
                                f"| score={float(row['score']):.4f}, "
                                f"sil={float(row['silhouette']):.4f}, "
                                f"valid={bool(row['selection_valid'])} "
                                f"| elapsed={format_duration(evaluation_total_elapsed)} "
                                f"| ETA={format_duration(evaluation_eta)}",
                                flush=True,
                            )

            if should_report(combo_idx, total_feature_sets, args.progress_every):
                combo_elapsed = time.perf_counter() - combo_start
                cumulative, combo_eta = progress_eta(start, combo_idx, total_feature_sets)
                if combo_best_row is None:
                    result = "no AirPulse neighbor-preserving result"
                else:
                    result = (
                        f"score={combo_best_row['score']:.4f}, "
                        f"sil={combo_best_row['silhouette']:.4f}, "
                        f"k={combo_best_row['kmeans_n_clusters']}, "
                        f"nn={combo_best_row['umap_n_neighbors']}, "
                        f"dist={combo_best_row['umap_min_dist']}"
                    )
                print(
                    f"[Feature set {combo_idx}/{total_feature_sets}] {feature_set_id} "
                    f"| feature_count={len(features)} "
                    f"| features={'; '.join(features)} "
                    f"| set_time={format_step_time(combo_elapsed)} "
                    f"| elapsed={format_duration(cumulative)} "
                    f"| ETA={format_duration(combo_eta)} "
                    f"| best: {result}",
                    flush=True,
                )
        except Exception as exc:
            rows.append(
                {
                    "evaluation_index": len(rows) + 1,
                    "feature_set_id": feature_set_id,
                    "feature_set_index": combo_idx,
                    "selected_feature_count": len(features),
                    "selected_features": "; ".join(features),
                    "selection_valid": False,
                    "score": np.nan,
                    "silhouette": np.nan,
                    "error": str(exc),
                }
            )
            combo_elapsed = time.perf_counter() - combo_start
            print(
                f"[Feature set {combo_idx}/{total_feature_sets}] {feature_set_id} FAILED "
                f"after {format_step_time(combo_elapsed)}: {exc}",
                flush=True,
            )

    if best_payload is None:
        raise RuntimeError("No valid reference-only UMAP + KMeans result was produced.")
    total_elapsed = time.perf_counter() - start
    print("\nSearch-loop timing summary", flush=True)
    print(f"Total elapsed: {format_duration(total_elapsed)} ({total_elapsed:.1f} s)", flush=True)
    print(
        f"Average per feature set: "
        f"{format_step_time(total_elapsed / max(total_feature_sets, 1))}",
        flush=True,
    )
    print(
        f"Average UMAP fit: "
        f"{format_step_time(cumulative_umap_seconds / max(completed_umap_fits, 1))}",
        flush=True,
    )
    print(
        f"Average one-row transform guard: "
        f"{format_step_time(cumulative_guard_seconds / max(completed_umap_fits, 1))}",
        flush=True,
    )
    print(
        f"Average KMeans generation: "
        f"{format_step_time(cumulative_kmeans_seconds / max(completed_evaluations, 1))}",
        flush=True,
    )
    return (
        base.sorted_results_df(rows),
        best_payload,
        {count: info["payload"] for count, info in best_by_feature_count.items()},
        total_elapsed,
    )


def build_labels_table(best_payload, label_col, name_col):
    df = best_payload["df"].copy()
    keep_mask = best_payload["keep_mask"]
    df.insert(0, "Reference_Original_Index", np.arange(len(df), dtype=int))
    df["Reference_Used_For_UMAP_Fit"] = keep_mask
    df["Reference_Initial_Edge_Distance"] = best_payload["edge_distance"]
    df["Reference_UMAP1"] = np.nan
    df["Reference_UMAP2"] = np.nan
    df["Reference_KMeans_Cluster"] = pd.Series([pd.NA] * len(df), dtype="Int64")
    df.loc[keep_mask, "Reference_UMAP1"] = best_payload["Z_ref"][:, 0]
    df.loc[keep_mask, "Reference_UMAP2"] = best_payload["Z_ref"][:, 1]
    df.loc[keep_mask, "Reference_KMeans_Cluster"] = best_payload["labels"]
    ordered = [
        "Reference_Original_Index",
        name_col,
        label_col,
        "Reference_Used_For_UMAP_Fit",
        "Reference_UMAP1",
        "Reference_UMAP2",
        "Reference_KMeans_Cluster",
    ]
    return df.loc[:, [col for col in ordered if col in df.columns] + [col for col in df.columns if col not in ordered]]


def save_outputs(args, results_df, best_payload, feature_cols, combos, n_neighbors, min_dist, n_clusters, elapsed):
    output_start = time.perf_counter()
    stage_start = output_start
    print("\nSaving reference-only outputs", flush=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_csv = args.output_dir / "reference_umap_feature_search_all_results.csv"
    result_xlsx = args.output_dir / "reference_umap_feature_search_results.xlsx"
    labels_xlsx = args.output_dir / "best_reference_umap_labels.xlsx"
    metadata_xlsx = args.output_dir / "best_reference_umap_metadata.xlsx"
    artifact_path = args.output_dir / MODEL_ARTIFACT_NAME

    results_df.to_csv(all_csv, index=False, encoding="utf-8-sig")
    best_per_feature = (
        results_df.groupby("feature_set_id", group_keys=False).head(1).reset_index(drop=True)
        if not results_df.empty
        else pd.DataFrame()
    )
    best_per_count = (
        results_df.groupby("selected_feature_count", group_keys=False).head(1).reset_index(drop=True)
        if not results_df.empty and "selected_feature_count" in results_df.columns
        else pd.DataFrame()
    )
    config = pd.DataFrame(
        [
            ("workflow_stage", "reference_exploration_and_model_fit"),
            ("reference_input", str(args.input)),
            ("reference_sample_count", len(best_payload["df"])),
            ("guard_input", str(args.guard_input)),
            ("guard_input_name", args.guard_input_name),
            ("guard_input_rows_transformed_per_umap_candidate", 1),
            ("unseen_input_used_in_any_model_fit", False),
            ("neighbor_guard_required", True),
            ("best_neighbor_guard_passed", best_payload["row"]["neighbor_preserved"]),
            (
                "best_feature_space_nearest",
                best_payload["row"]["feature_space_nearest_names"],
            ),
            (
                "best_umap_space_nearest",
                best_payload["row"]["umap_space_nearest_names"],
            ),
            ("candidate_feature_columns", "; ".join(feature_cols)),
            ("selected_features", "; ".join(best_payload["features"])),
            ("feature_combination_count", len(combos)),
            ("search_mode", args.search_mode),
            ("umap_n_neighbors_list", ", ".join(str(v) for v in n_neighbors)),
            ("umap_min_dist_list", ", ".join(str(v) for v in min_dist)),
            ("umap_init", args.umap_init),
            (
                "umap_n_epochs",
                resolve_umap_n_epochs(args)
                if resolve_umap_n_epochs(args) is not None
                else "umap-learn default",
            ),
            ("kmeans_n_clusters_list", ", ".join(str(v) for v in n_clusters)),
            ("umap_search_openmp_threads", SEARCH_OMP_THREADS),
            ("kmeans_safe_openmp_threads", KMEANS_SAFE_THREADS),
            ("feature_progress_every", args.progress_every),
            ("evaluation_progress_every", args.evaluation_progress_every),
            ("initial_edge_filter", args.use_initial_edge_filter),
            ("elapsed_seconds", f"{elapsed:.6f}"),
        ],
        columns=["key", "value"],
    )
    with pd.ExcelWriter(result_xlsx, engine="openpyxl") as writer:
        results_df.head(args.top_results).to_excel(writer, sheet_name="top_results", index=False)
        best_per_feature.to_excel(writer, sheet_name="best_per_feature_set", index=False)
        best_per_count.to_excel(writer, sheet_name="best_per_feature_count", index=False)
        results_df.head(1).to_excel(writer, sheet_name="best_overall", index=False)
        config.to_excel(writer, sheet_name="run_config", index=False)
    print(
        f"[Output 1/4] Search CSV/XLSX saved "
        f"| stage_time={format_step_time(time.perf_counter() - stage_start)}",
        flush=True,
    )

    stage_start = time.perf_counter()
    labels = build_labels_table(best_payload, args.label_col, args.name_col)
    labels.to_excel(labels_xlsx, index=False)
    pd.DataFrame([best_payload["row"]]).to_excel(metadata_xlsx, index=False)
    print(
        f"[Output 2/4] Reference labels/metadata saved "
        f"| stage_time={format_step_time(time.perf_counter() - stage_start)}",
        flush=True,
    )

    stage_start = time.perf_counter()
    keep_mask = np.asarray(best_payload["keep_mask"], dtype=bool)
    reference_kept = labels.loc[keep_mask].reset_index(drop=True)
    Z_ref = np.asarray(best_payload["Z_ref"], dtype=np.float64)
    processed_full_raw = best_payload["df"].loc[:, list(best_payload["features"])].apply(
        pd.to_numeric, errors="coerce"
    ).to_numpy(dtype=float)
    processed_full_raw = np.where(np.isfinite(processed_full_raw), processed_full_raw, np.nan)
    processed_full = best_payload["preprocessor"]["scaler"].transform(
        best_payload["preprocessor"]["imputer"].transform(processed_full_raw)
    )
    processed_kept = np.asarray(processed_full[keep_mask], dtype=np.float64)

    metadata = {
        "workflow_stage": "reference_exploration_and_model_fit",
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "reference_source": str(Path(args.input).resolve()),
        "reference_source_sha256": sha256_file(args.input),
        "reference_sample_count": int(len(best_payload["df"])),
        "reference_umap_fit_count": int(len(Z_ref)),
        "selected_features": list(best_payload["features"]),
        "label_col": args.label_col,
        "name_col": args.name_col,
        "umap_n_neighbors": int(best_payload["row"]["umap_n_neighbors"]),
        "umap_min_dist": float(best_payload["row"]["umap_min_dist"]),
        "umap_init": args.umap_init,
        "umap_n_epochs": (
            resolve_umap_n_epochs(args)
            if resolve_umap_n_epochs(args) is not None
            else "umap-learn default"
        ),
        "kmeans_n_clusters": int(best_payload["row"]["kmeans_n_clusters"]),
        "reference_coordinates_sha256": sha256_array(Z_ref),
        "unseen_rows_used_during_fit": 0,
        "guard_input_source": str(Path(args.guard_input).resolve()),
        "guard_input_source_sha256": sha256_file(args.guard_input),
        "guard_input_name": str(best_payload["row"]["guard_input_name"]),
        "guard_input_source_row_index": int(
            best_payload["row"]["guard_input_source_row_index"]
        ),
        "guard_input_used_during_fit": False,
        "guard_input_transform_count_for_selected_model": 1,
        "neighbor_guard_required": True,
        "neighbor_guard_passed": bool(best_payload["row"]["neighbor_preserved"]),
        "feature_space_nearest_name": str(
            best_payload["row"]["feature_space_nearest_names"]
        ),
        "umap_space_nearest_name": str(
            best_payload["row"]["umap_space_nearest_names"]
        ),
        "feature_space_nearest_original_index": int(
            best_payload["row"]["feature_space_nearest_original_indices"]
        ),
        "umap_space_nearest_original_index": int(
            best_payload["row"]["umap_space_nearest_original_indices"]
        ),
        "guard_reference_coordinates_unchanged": bool(
            best_payload["row"]["guard_reference_coordinates_unchanged"]
        ),
    }
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "workflow": "reference_fit_then_unseen_transform",
        "selected_features": list(best_payload["features"]),
        "label_col": args.label_col,
        "name_col": args.name_col,
        "preprocessor": best_payload["preprocessor"],
        "umap_reducer": best_payload["reducer"],
        "kmeans_model": best_payload["model"],
        "reference_coordinates": Z_ref,
        "reference_processed_features": processed_kept,
        "reference_clusters": np.asarray(best_payload["labels"], dtype=int),
        "reference_table": reference_kept,
        "reference_keep_mask": keep_mask,
        "metadata": metadata,
        "best_result": best_payload["row"],
    }
    joblib.dump(artifact, artifact_path, compress=3)
    (args.output_dir / "best_reference_umap_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[Output 3/4] Frozen model artifact saved "
        f"| stage_time={format_step_time(time.perf_counter() - stage_start)}",
        flush=True,
    )

    stage_start = time.perf_counter()
    y_true = reference_kept[args.label_col].astype(str).to_numpy()
    base.plot_2d_true_labels(
        Z_ref[:, 0],
        Z_ref[:, 1],
        y_true,
        title="Reference-only UMAP space colored by Type Number",
        xlabel="UMAP1",
        ylabel="UMAP2",
        save_path=args.output_dir / "best_reference_umap_true_labels.png",
        legend_title=args.label_col,
        boundary_model=best_payload["model"],
        color_reference_labels=y_true,
    )
    base.plot_2d_cluster_with_boundary(
        Z_ref[:, 0],
        Z_ref[:, 1],
        best_payload["labels"],
        model=best_payload["model"],
        title="Reference-only UMAP + KMeans space",
        xlabel="UMAP1",
        ylabel="UMAP2",
        save_path=args.output_dir / "best_reference_umap_kmeans.png",
        legend_title="KMeans",
    )
    print(
        f"[Output 4/4] Reference figures saved "
        f"| stage_time={format_step_time(time.perf_counter() - stage_start)} "
        f"| total_output_time={format_step_time(time.perf_counter() - output_start)}",
        flush=True,
    )
    return {
        "model_artifact": artifact_path,
        "manifest": args.output_dir / "best_reference_umap_manifest.json",
        "labels": labels_xlsx,
        "metadata": metadata_xlsx,
        "results": result_xlsx,
        "all_results": all_csv,
    }


def main():
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    args = parse_args()
    df = read_table(args.input, args.input_sheet)
    if args.label_col not in df.columns:
        raise ValueError(f"Missing label column in reference table: {args.label_col}")
    if args.name_col and args.name_col not in df.columns:
        raise ValueError(f"Missing name column in reference table: {args.name_col}")

    feature_cols = base.resolve_feature_columns(df, args)
    if not feature_cols:
        raise ValueError("No numeric feature columns were resolved.")
    guard_context = build_neighbor_guard_context(df, feature_cols, args)
    combos = base.build_feature_combinations(feature_cols, args)
    effective_n = len(df)
    if args.use_initial_edge_filter and len(df) > args.initial_edge_points_to_remove:
        effective_n -= args.initial_edge_points_to_remove
    n_neighbors, min_dist, n_clusters = resolve_search_parameter_grid(max(2, effective_n), args)

    print("Reference-only fit + transform-only guard dry-run summary", flush=True)
    print(f"Reference rows: {len(df)}", flush=True)
    print("Unseen input rows used in any model fit: 0", flush=True)
    print(f"Guard input rows transformed per UMAP candidate: 1", flush=True)
    print(
        f"Guard target: row {guard_context['target_row_index']} "
        f"({guard_context['target_name']})",
        flush=True,
    )
    print(
        f"Fixed {len(feature_cols)}D feature-space nearest reference: "
        f"row {guard_context['full_feature_nearest_original_index']} "
        f"({guard_context['full_feature_nearest_name']})",
        flush=True,
    )
    print(f"Feature columns ({len(feature_cols)}): {feature_cols}", flush=True)
    print(f"Feature combinations: {len(combos)}", flush=True)
    print(f"Search mode: {args.search_mode}", flush=True)
    print(f"UMAP n_neighbors: {n_neighbors}", flush=True)
    print(f"UMAP min_dist: {min_dist}", flush=True)
    print(f"UMAP init: {args.umap_init}", flush=True)
    resolved_epochs = resolve_umap_n_epochs(args)
    print(
        f"UMAP epochs: {resolved_epochs if resolved_epochs is not None else 'umap-learn default'}",
        flush=True,
    )
    print(f"KMeans n_clusters: {n_clusters}", flush=True)
    print(f"UMAP/search threads: {SEARCH_OMP_THREADS}", flush=True)
    print(f"Temporary KMeans threads: {KMEANS_SAFE_THREADS}", flush=True)
    parameter_grid = len(n_neighbors) * len(min_dist) * len(n_clusters)
    print(f"Parameter grid per feature set: {parameter_grid}", flush=True)
    print(f"Total UMAP fits: {len(combos) * len(n_neighbors) * len(min_dist)}", flush=True)
    print(f"Total KMeans evaluations (generations): {len(combos) * parameter_grid}", flush=True)
    if args.dry_run:
        return

    results_df, best_payload, _, elapsed = run_search(
        df,
        feature_cols,
        combos,
        n_neighbors,
        min_dist,
        n_clusters,
        guard_context,
        args,
    )
    paths = save_outputs(
        args,
        results_df,
        best_payload,
        feature_cols,
        combos,
        n_neighbors,
        min_dist,
        n_clusters,
        elapsed,
    )
    print("\nBest reference-only UMAP result:", flush=True)
    print(json.dumps(best_payload["row"], ensure_ascii=False, indent=2, default=str), flush=True)
    print("\nOverall timing:", flush=True)
    print(f"Elapsed seconds: {elapsed:.1f}", flush=True)
    print(f"Average seconds per feature set: {elapsed / max(len(combos), 1):.2f}", flush=True)
    print("\nGenerated files:", flush=True)
    for path in paths.values():
        print(f" - {path}", flush=True)


if __name__ == "__main__":
    main()
