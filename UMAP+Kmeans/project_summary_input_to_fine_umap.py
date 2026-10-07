
import argparse
import colorsys
import hashlib
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, to_hex, to_rgba
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import joblib
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_PATH = SCRIPT_DIR / "summary_input-all.xlsx"
DEFAULT_FINE_SEARCH_ROOT = SCRIPT_DIR / "fine_search_results"
MODEL_ARTIFACT_NAME = "best_reference_umap_model.joblib"
DEFAULT_PROJECTION_SUBDIR = "summary_input_projection"
EXPECTED_ARTIFACT_SCHEMA_VERSION = 1
INPUT_COLOR_GOLDEN_RATIO = 0.618033988749895
INPUT_COLOR_SATURATIONS = (0.78, 0.70, 0.86)
INPUT_COLOR_VALUES = (0.90, 0.78)
ROW_WISE_TRANSFORM_MODE = "row_wise_independent_transform"
NEAREST_REFERENCE_SPACE = "frozen_umap_space"
NEAREST_REFERENCE_METRIC = "euclidean"
OOD_METHOD = "full_feature_standardized_reference_leave_one_out_nn"
OOD_POLICY_STRICT_REJECTION = "strict_rejection"
OOD_POLICY_WARNING_ONLY = "warning_only"
DEFAULT_OOD_REFERENCE_QUANTILE = 0.985
DEFAULT_OOD_FEATURES = [
    "Area",
    "WingArea_BBoxAreaRatio",
    "TipArea_R0p1_WingAreaRatio",
    "Roundness",
    "LE_TE_ratio",
    "TipCurvature",
    "LE_Bending",
    "TE_Bending",
    "TE_MaxCurvX",
    "TE_Distal_Bending",
    "TE_Distal_SignedCurvature",
]
KMEANS_COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#9467bd",
    "#d62728",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]
TYPE_NUMBER_COLORS = [
    "#1f77b4",
    "#aec7e8",
    "#ff7f0e",
    "#ffbb78",
    "#2ca02c",
    "#98df8a",
    "#d62728",
    "#ff9896",
    "#9467bd",
    "#c5b0d5",
    "#8c564b",
    "#c49c94",
    "#e377c2",
    "#ffbb78",
]
TYPE_NUMBER_NAMES = {
    "1": "Hesperiidae",
    "2": "Lycaenidae",
    "3": "Papilionidae",
    "4": "Pieridae",
    "5": "Biblidinae",
    "6": "Charaxinae",
    "7": "Danainae",
    "8": "Heliconiinae",
    "9": "Limenitidinae",
    "10": "Nymphalinae",
    "11": "Satyrinae",
    "12": "Parnassiinae",
    "13": "Riodinidae",
    "14": "Pieridae",
}
PIE_FONT_FAMILY = "Times New Roman"
PIE_LEGEND_FONT_SIZE = 21
PIE_LEGEND_TITLE_FONT_SIZE = 21
PIE_TITLE_FONT_SIZE = 22
PIE_EMPTY_FONT_SIZE = 25
PIE_SUPTITLE_FONT_SIZE = 25

plt.rcParams.update(
    {
        "font.family": "Times New Roman",
        "font.size": 13,
        "axes.titlesize": 16,
        "axes.labelsize": 15,
        "xtick.labelsize": 13,
        "ytick.labelsize": 13,
        "legend.fontsize": 13,
    }
)


def input_diamond_color(input_number):
    """Return a stable, non-cycling color for one-based input numbering."""
    color_index = max(int(input_number) - 1, 0)
    hue = (color_index * INPUT_COLOR_GOLDEN_RATIO) % 1.0
    saturation = INPUT_COLOR_SATURATIONS[color_index % len(INPUT_COLOR_SATURATIONS)]
    value_group = color_index // len(INPUT_COLOR_SATURATIONS)
    value = INPUT_COLOR_VALUES[value_group % len(INPUT_COLOR_VALUES)]
    return to_hex(colorsys.hsv_to_rgb(hue, saturation, value))


def input_diamond_legend_handle(input_number, markersize=9.5):
    return Line2D(
        [0],
        [0],
        linestyle="none",
        marker="D",
        markersize=markersize,
        markerfacecolor=input_diamond_color(input_number),
        markeredgecolor="black",
        markeredgewidth=0.8,
    )


def completed_fine_run(run_dir):
    """Return completion time only for a completed fine run with an exported winner."""
    run_dir = Path(run_dir)
    try:
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        manifest = json.loads((run_dir / "best_reference_umap_manifest.json").read_text(encoding="utf-8"))
        if (status.get("status") != "complete" or status.get("complete") is not True
                or status.get("winner_available") is not True
                or manifest.get("workflow_stage") != "hard_guard_fine_reference_exploration_and_model_fit"
                or manifest.get("hard_guards_passed") is not True
                or not (run_dir / MODEL_ARTIFACT_NAME).is_file()):
            return None
        if status.get("completed_umap_fits") != status.get("planned_umap_fits"):
            return None
        completed = datetime.fromisoformat(manifest["created_utc"].replace("Z", "+00:00"))
        if completed.tzinfo is None:
            completed = completed.replace(tzinfo=timezone.utc)
        return completed.astimezone(timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def resolve_fine_model(fine_search_dir=None, root=None):
    """Select the newest completed fine-search winner, never the old coarse model."""
    if fine_search_dir is not None:
        run_dir = Path(fine_search_dir).resolve()
        if completed_fine_run(run_dir) is None:
            raise ValueError(f"Not a completed fine-search run with an exported winner: {run_dir}")
        return run_dir / MODEL_ARTIFACT_NAME
    root = Path(root) if root is not None else DEFAULT_FINE_SEARCH_ROOT
    candidates = []
    if root.is_dir():
        for run_dir in root.iterdir():
            if run_dir.is_dir() and (completed := completed_fine_run(run_dir)) is not None:
                candidates.append((completed, run_dir.name, run_dir))
    if not candidates:
        raise FileNotFoundError(
            f"No completed fine-search winner found under {root}. "
            "Finish fine_search_reference_umap_kmeans.py or specify --model-artifact."
        )
    return max(candidates)[2].resolve() / MODEL_ARTIFACT_NAME


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Project unseen rows with UMAP.transform into a frozen reference space; "
            "the stored reference coordinates and fitted models are never refitted."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--input-sheet", default=None)
    model_source = parser.add_mutually_exclusive_group()
    model_source.add_argument("--fine-search-dir", type=Path, default=None,
                              help="Completed fine-search run directory; default: newest completed run.")
    model_source.add_argument("--model-artifact", type=Path, default=None,
                              help="Explicit model file, overriding automatic fine-run discovery.")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Default: projection subdirectory of the selected model's run directory.")
    parser.add_argument("--grid-size", type=int, default=500)
    parser.add_argument("--umap-grid-pad", type=float, default=0.05)
    parser.add_argument(
        "--ood-reference-quantile",
        type=float,
        default=DEFAULT_OOD_REFERENCE_QUANTILE,
        help=(
            "Reference leave-one-out nearest-neighbor distance quantile used as "
            "the OOD rejection threshold (default: %(default)s)."
        ),
    )
    parser.add_argument("--no-pies", action="store_true")
    args = parser.parse_args()
    if args.model_artifact is None:
        args.model_artifact = resolve_fine_model(args.fine_search_dir)
    args.model_artifact = args.model_artifact.resolve()
    if args.output_dir is None:
        args.output_dir = args.model_artifact.parent / DEFAULT_PROJECTION_SUBDIR
    print(f"Fine-search model: {args.model_artifact}", flush=True)
    return args


def read_table(path, sheet=None):
    path = Path(path)
    if path.suffix.lower() in {".csv", ".tsv"}:
        return pd.read_csv(path, sep="\t" if path.suffix.lower() == ".tsv" else ",")
    return pd.read_excel(path, sheet_name=0 if sheet is None else sheet, engine="openpyxl")


def read_input_rows(path, sheet=None):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Missing unseen input table/folder: {path}")
    if not path.is_dir():
        frame = read_table(path, sheet)
        frame["_Input_Source_File"] = path.name
        return frame

    parts = []
    files = sorted(
        item
        for item in path.iterdir()
        if item.is_file()
        and not item.name.startswith("~$")
        and item.suffix.lower() in {".xlsx", ".xls", ".csv", ".tsv"}
    )
    if not files:
        raise FileNotFoundError(f"No input workbook/csv files found in: {path}")
    for item in files:
        frame = read_table(item, sheet)
        frame["_Input_Source_File"] = item.name
        parts.append(frame)
    return pd.concat(parts, ignore_index=True)


def sha256_array(values):
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(array.tobytes()).hexdigest()


def arrays_exactly_equal(left, right):
    return np.array_equal(np.asarray(left), np.asarray(right), equal_nan=True)


def class_sort_key(value):
    text = normalize_type_number_label(value)
    try:
        return (0, float(text))
    except (TypeError, ValueError):
        return (1, str(text))


def normalize_type_number_label(value):
    if pd.isna(value):
        return "nan"
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


def type_label_sort_key(value):
    return class_sort_key(normalize_type_number_label(value))


def type_number_color_map(labels, reference_labels=None):
    normalized = [normalize_type_number_label(value) for value in labels]
    reference = normalized if reference_labels is None else [
        normalize_type_number_label(value) for value in reference_labels
    ]
    ordered = sorted(pd.unique(reference), key=class_sort_key)
    fallback = plt.get_cmap("tab20")
    colors = {}
    for index, label in enumerate(ordered):
        try:
            number = int(float(label))
        except ValueError:
            number = -1
        if number == 14:
            colors[label] = TYPE_NUMBER_COLORS[3]
        elif 1 <= number <= len(TYPE_NUMBER_COLORS):
            colors[label] = TYPE_NUMBER_COLORS[number - 1]
        else:
            colors[label] = fallback(index % fallback.N)
    return colors


def kmeans_color_list(cluster_count):
    colors = KMEANS_COLORS[: int(cluster_count)]
    if len(colors) < int(cluster_count):
        colors.extend(
            plt.get_cmap("tab20")(index)
            for index in range(len(colors), int(cluster_count))
        )
    return colors


def save_figure_png_and_svg(output_path, dpi=220):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    png_path = output_path.with_suffix(".png")
    svg_path = output_path.with_suffix(".svg")
    plt.savefig(png_path, dpi=dpi, bbox_inches="tight")
    plt.savefig(svg_path, format="svg", bbox_inches="tight")
    return png_path, svg_path


def save_type_number_color_legend_svg(output_dir, filename="type_number_color_legend.svg"):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    class_order = [str(i) for i in range(1, 14)]
    colors = type_number_color_map(class_order, reference_labels=class_order)
    handles = [
        Patch(
            facecolor=colors[label],
            edgecolor="none",
            label=TYPE_NUMBER_NAMES.get(label, label),
        )
        for label in class_order
    ]
    fig, ax = plt.subplots(figsize=(2.8, 7.2))
    ax.axis("off")
    ax.legend(
        handles=handles,
        loc="center",
        frameon=True,
        prop={"family": PIE_FONT_FAMILY, "size": PIE_LEGEND_FONT_SIZE},
    )
    svg_path = output_dir / filename
    fig.savefig(svg_path, format="svg", bbox_inches="tight")
    plt.close(fig)
    return svg_path


def save_projection_legend(
    reference_types,
    input_names,
    input_numbers,
    model,
    output_base,
):
    normalized_types = np.asarray(
        [normalize_type_number_label(value) for value in reference_types], dtype=str
    )
    type_order = [
        label
        for label in sorted(pd.unique(normalized_types), key=class_sort_key)
        if label.lower() != "nan"
    ]
    type_colors = type_number_color_map(type_order, reference_labels=type_order)
    type_handles = [
        Line2D(
            [0],
            [0],
            linestyle="none",
            marker="o",
            markersize=9,
            markerfacecolor=type_colors[label],
            markeredgecolor="none",
        )
        for label in type_order
    ]
    type_labels = [TYPE_NUMBER_NAMES.get(label, str(label)) for label in type_order]

    input_handles = [
        input_diamond_legend_handle(number)
        for number in input_numbers
    ]
    input_labels = [f"{name}" for name in input_names]

    cluster_colors = kmeans_color_list(model.n_clusters)
    cluster_handles = [
        Patch(
            facecolor=to_rgba(cluster_colors[cluster], 0.10),
            edgecolor="#4d4d4d",
            linewidth=0.8,
        )
        for cluster in range(int(model.n_clusters))
    ]
    cluster_labels = [
        f"KMeans cluster {cluster + 1}" for cluster in range(int(model.n_clusters))
    ]

    handles = type_handles + input_handles + cluster_handles
    labels = type_labels + input_labels + cluster_labels
    figure_height = max(5.0, 0.43 * len(handles) + 1.2)
    fig, ax = plt.subplots(figsize=(5.2, figure_height))
    ax.axis("off")
    ax.legend(
        handles=handles,
        labels=labels,
        loc="center",
        frameon=True,
        borderpad=0.8,
        labelspacing=0.60,
        handlelength=1.8,
        handleheight=1.2,
    )
    fig.tight_layout(pad=0.25)
    written = save_figure_png_and_svg(output_base)
    plt.close(fig)
    return written


def plot_cluster_pies(cluster_labels, type_labels, output_dir):
    """Draw reference-cluster composition; projected unseen rows are not counted."""
    clusters_array = np.asarray(cluster_labels, dtype=int)
    types_array = np.asarray([normalize_type_number_label(value) for value in type_labels], dtype=str)
    types_array = np.where(types_array == "14", "4", types_array)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    class_order = sorted(pd.unique(types_array), key=class_sort_key)
    colors = type_number_color_map(class_order, reference_labels=class_order)
    save_type_number_color_legend_svg(output_dir)

    summary_rows = []
    clusters = sorted(np.unique(clusters_array))
    for cluster in clusters:
        mask = clusters_array == cluster
        counts = pd.Series(types_array[mask]).value_counts()
        counts = counts.loc[sorted(counts.index, key=class_sort_key)]
        total = int(counts.sum())
        for label, count in counts.items():
            summary_rows.append(
                {
                    "Cluster": int(cluster),
                    "Type Number": label,
                    "Count": int(count),
                    "Ratio": float(count / total) if total else np.nan,
                    "Population": "reference_only",
                }
            )

        present = [(label, int(counts.get(label, 0))) for label in class_order]
        present = [(label, count) for label, count in present if count > 0]
        fig, ax = plt.subplots(figsize=(9, 7))
        if not present:
            ax.text(
                0.5,
                0.5,
                f"Cluster {cluster}\nNo reference samples",
                ha="center",
                va="center",
                fontsize=PIE_EMPTY_FONT_SIZE,
                transform=ax.transAxes,
            )
            ax.axis("off")
        else:
            wedge_labels = [label for label, _ in present]
            values = [count for _, count in present]
            wedges, _ = ax.pie(
                values,
                labels=None,
                colors=[colors[label] for label in wedge_labels],
                startangle=90,
                counterclock=False,
                wedgeprops={"edgecolor": "white", "linewidth": 1},
            )
            for label, count in counts.sort_values(ascending=False).head(2).items():
                label = str(label)
                if label not in wedge_labels:
                    continue
                wedge = wedges[wedge_labels.index(label)]
                angle = (wedge.theta1 + wedge.theta2) / 2.0
                ax.text(
                    0.5 * np.cos(np.deg2rad(angle)),
                    0.5 * np.sin(np.deg2rad(angle)),
                    f"{count / total * 100:.1f}%",
                    ha="center",
                    va="center",
                    fontsize=PIE_TITLE_FONT_SIZE,
                )
            ax.set_title(
                f"Cluster {cluster}: Type composition (n={total})",
                fontsize=PIE_TITLE_FONT_SIZE,
            )
        fig.tight_layout()
        save_figure_png_and_svg(output_dir / f"pie_cluster_{int(cluster)}_type_number.png")
        plt.close(fig)

    if clusters:
        n_cols = min(3, len(clusters))
        n_rows = int(np.ceil(len(clusters) / n_cols))
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(7.2 * n_cols, 6.4 * n_rows))
        axes = np.asarray(axes).reshape(-1)
        for ax, cluster in zip(axes, clusters):
            mask = clusters_array == cluster
            counts = pd.Series(types_array[mask]).value_counts()
            total = int(counts.sum())
            present = [(label, int(counts.get(label, 0))) for label in class_order]
            present = [(label, count) for label, count in present if count > 0]
            if present:
                ax.pie(
                    [count for _, count in present],
                    labels=None,
                    colors=[colors[label] for label, _ in present],
                    startangle=90,
                    counterclock=False,
                    wedgeprops={"edgecolor": "white", "linewidth": 1},
                )
                ax.set_title(f"Cluster {cluster} (reference n={total})", fontsize=PIE_TITLE_FONT_SIZE)
            else:
                ax.axis("off")
        for ax in axes[len(clusters) :]:
            ax.axis("off")
        fig.suptitle(
            "Reference Type Number composition by frozen UMAP KMeans cluster",
            fontsize=PIE_SUPTITLE_FONT_SIZE,
        )
        fig.tight_layout()
        save_figure_png_and_svg(output_dir / "pie_all_clusters_type_number.png")
        plt.close(fig)
    return pd.DataFrame(summary_rows)


def validate_artifact(artifact):
    required = {
        "schema_version",
        "workflow",
        "selected_features",
        "preprocessor",
        "umap_reducer",
        "kmeans_model",
        "reference_coordinates",
        "reference_processed_features",
        "reference_clusters",
        "reference_table",
        "metadata",
    }
    missing = sorted(required.difference(artifact))
    if missing:
        raise ValueError(f"Frozen model artifact is missing fields: {missing}")
    if int(artifact["schema_version"]) != EXPECTED_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported artifact schema {artifact['schema_version']}; "
            f"expected {EXPECTED_ARTIFACT_SCHEMA_VERSION}."
        )
    if artifact["workflow"] != "reference_fit_then_unseen_transform":
        raise ValueError(f"Unexpected artifact workflow: {artifact['workflow']}")

    reference_coordinates = np.asarray(artifact["reference_coordinates"], dtype=np.float64)
    reducer_embedding = np.asarray(artifact["umap_reducer"].embedding_, dtype=np.float64)
    reference_count = len(reference_coordinates)
    related_lengths = {
        "reference_processed_features": len(artifact["reference_processed_features"]),
        "reference_clusters": len(artifact["reference_clusters"]),
        "reference_table": len(artifact["reference_table"]),
    }
    mismatched = {key: value for key, value in related_lengths.items() if value != reference_count}
    if reference_coordinates.ndim != 2 or reference_coordinates.shape[1] != 2:
        raise ValueError(
            f"Frozen reference coordinates must have shape (n, 2), got {reference_coordinates.shape}."
        )
    if mismatched:
        raise ValueError(
            f"Frozen artifact reference lengths do not match {reference_count} coordinates: {mismatched}"
        )
    if not arrays_exactly_equal(reference_coordinates, reducer_embedding):
        raise ValueError("Stored reference coordinates differ from the fitted reducer.embedding_.")
    expected_hash = artifact["metadata"].get("reference_coordinates_sha256")
    actual_hash = sha256_array(reference_coordinates)
    if expected_hash and expected_hash != actual_hash:
        raise ValueError("Stored reference-coordinate hash does not match the model manifest.")


def transform_preprocessor(values, fitted):
    values = np.asarray(values, dtype=float)
    values = np.where(np.isfinite(values), values, np.nan)
    imputed = fitted["imputer"].transform(values)
    return np.asarray(fitted["scaler"].transform(imputed), dtype=np.float64)


def resolve_ood_features(artifact, reference_table, input_frame):
    stored = artifact.get("best_result", {}).get("feature_space_reference_features")
    if isinstance(stored, str):
        stored = [item.strip() for item in stored.split(";") if item.strip()]
    elif stored is not None:
        stored = [str(item).strip() for item in stored if str(item).strip()]

    candidates = []
    if stored:
        candidates.append(("artifact full-feature guard", stored))
    candidates.append(("default 11-feature morphology space", DEFAULT_OOD_FEATURES))

    failures = []
    for source, features in candidates:
        features = list(dict.fromkeys(features))
        missing_reference = [
            feature for feature in features if feature not in reference_table.columns
        ]
        missing_input = [
            feature for feature in features if feature not in input_frame.columns
        ]
        if not missing_reference and not missing_input:
            return features, source
        failures.append(
            f"{source}: missing from reference={missing_reference}, "
            f"missing from input={missing_input}"
        )
    raise ValueError(
        "Cannot apply the complete-feature OOD rule because no valid full "
        "morphology feature set is available. " + " | ".join(failures)
    )


def pairwise_euclidean(left, right):
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    squared = (
        np.sum(left * left, axis=1)[:, None]
        + np.sum(right * right, axis=1)[None, :]
        - 2.0 * left @ right.T
    )
    return np.sqrt(np.maximum(squared, 0.0))


def assess_reference_only_ood(
    reference_table,
    input_frame,
    input_names,
    feature_columns,
    feature_source,
    reference_quantile,
    name_col,
    label_col,
):
    if len(reference_table) < 2:
        raise ValueError("OOD calibration requires at least two frozen reference rows.")
    if not 0.0 < float(reference_quantile) < 1.0:
        raise ValueError("--ood-reference-quantile must be strictly between 0 and 1.")

    reference_raw = (
        reference_table.loc[:, feature_columns]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(dtype=np.float64)
    )
    input_raw = (
        input_frame.loc[:, feature_columns]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(dtype=np.float64)
    )
    reference_raw = np.where(np.isfinite(reference_raw), reference_raw, np.nan)
    input_raw = np.where(np.isfinite(input_raw), input_raw, np.nan)

    all_missing_features = [
        feature_columns[index]
        for index in range(len(feature_columns))
        if np.all(np.isnan(reference_raw[:, index]))
    ]
    if all_missing_features:
        raise ValueError(
            "OOD calibration cannot use reference features that are entirely missing: "
            f"{all_missing_features}"
        )

    
    reference_medians = np.nanmedian(reference_raw, axis=0)
    reference_imputed = np.where(
        np.isnan(reference_raw), reference_medians[None, :], reference_raw
    )
    input_imputed = np.where(
        np.isnan(input_raw), reference_medians[None, :], input_raw
    )
    reference_means = np.mean(reference_imputed, axis=0)
    reference_scales = np.std(reference_imputed, axis=0, ddof=0)
    reference_scales = np.where(reference_scales > 0.0, reference_scales, 1.0)
    reference_standardized = (
        reference_imputed - reference_means[None, :]
    ) / reference_scales[None, :]
    input_standardized = (
        input_imputed - reference_means[None, :]
    ) / reference_scales[None, :]

    reference_pairwise = pairwise_euclidean(
        reference_standardized, reference_standardized
    )
    np.fill_diagonal(reference_pairwise, np.inf)
    reference_nn_distances = np.min(reference_pairwise, axis=1)
    threshold = float(
        np.quantile(reference_nn_distances, float(reference_quantile))
    )

    input_to_reference = pairwise_euclidean(
        input_standardized, reference_standardized
    )
    nearest_indices = np.argmin(input_to_reference, axis=1).astype(int)
    nearest_distances = input_to_reference[
        np.arange(len(input_standardized)), nearest_indices
    ]
    rejected = nearest_distances > threshold
    percentiles = np.asarray(
        [
            100.0 * np.mean(reference_nn_distances <= distance)
            for distance in nearest_distances
        ],
        dtype=np.float64,
    )
    input_missing_counts = np.sum(np.isnan(input_raw), axis=1).astype(int)

    assessment_rows = []
    for input_index, input_name in enumerate(input_names):
        nearest_index = int(nearest_indices[input_index])
        reference_row = reference_table.iloc[nearest_index]
        is_rejected = bool(rejected[input_index])
        assessment_rows.append(
            {
                "Input_Index": int(input_index),
                "Input_Name": input_name,
                "OOD_Threshold_Exceeded": is_rejected,
                "OOD_Status": "REJECTED_OOD" if is_rejected else "IN_DISTRIBUTION",
                "OOD_Rejected": is_rejected,
                "OOD_Rejection_Reason": (
                    "distance_above_reference_threshold"
                    if is_rejected
                    else "distance_within_reference_threshold"
                ),
                "OOD_Method": OOD_METHOD,
                "OOD_Feature_Source": feature_source,
                "OOD_Feature_Count": int(len(feature_columns)),
                "OOD_Features": "; ".join(feature_columns),
                "OOD_Input_Missing_Feature_Count": int(
                    input_missing_counts[input_index]
                ),
                "OOD_Nearest_Reference_Row_Index": nearest_index,
                "OOD_Nearest_Reference_Original_Index": reference_row.get(
                    "Reference_Original_Index", nearest_index
                ),
                "OOD_Nearest_Reference_Name": reference_row.get(
                    name_col, f"reference_{nearest_index + 1}"
                ),
                "OOD_Nearest_Reference_Type_Number": reference_row.get(
                    label_col, np.nan
                ),
                "OOD_Nearest_Reference_KMeans_Cluster": reference_row.get(
                    "Reference_KMeans_Cluster", np.nan
                ),
                "OOD_Nearest_Distance": float(nearest_distances[input_index]),
                "OOD_Reference_Quantile": float(reference_quantile),
                "OOD_Distance_Threshold": threshold,
                "OOD_NN_Percentile": float(percentiles[input_index]),
            }
        )

    quantiles = {
        "reference_nn_min": float(np.min(reference_nn_distances)),
        "reference_nn_p25": float(np.quantile(reference_nn_distances, 0.25)),
        "reference_nn_p50": float(np.quantile(reference_nn_distances, 0.50)),
        "reference_nn_p75": float(np.quantile(reference_nn_distances, 0.75)),
        "reference_nn_p90": float(np.quantile(reference_nn_distances, 0.90)),
        "reference_nn_p95": float(np.quantile(reference_nn_distances, 0.95)),
        "reference_nn_p99": float(np.quantile(reference_nn_distances, 0.99)),
        "reference_nn_max": float(np.max(reference_nn_distances)),
    }
    calibration = {
        "ood_method": OOD_METHOD,
        "ood_feature_source": feature_source,
        "ood_reference_row_count": int(len(reference_table)),
        "ood_feature_count": int(len(feature_columns)),
        "ood_features": feature_columns,
        "ood_reference_quantile": float(reference_quantile),
        "ood_distance_threshold": threshold,
        "ood_reference_imputation": "per-feature median; reference rows only",
        "ood_reference_standardization": (
            "per-feature population mean/std; reference rows only"
        ),
        "ood_distance": "Euclidean",
        "ood_calibration_input_row_count": 0,
        **quantiles,
    }
    return (
        pd.DataFrame(assessment_rows),
        metadata_frame(calibration),
        reference_nn_distances,
    )


def transform_rows_independently(reducer, processed_rows):
    processed_rows = np.asarray(processed_rows, dtype=np.float64)
    transformed_rows = [
        np.asarray(reducer.transform(processed_rows[index : index + 1]), dtype=np.float64)[0]
        for index in range(len(processed_rows))
    ]
    return np.vstack(transformed_rows)


def row_name(frame, index, name_col):
    if name_col in frame.columns and pd.notna(frame.iloc[index][name_col]):
        return str(frame.iloc[index][name_col])
    return f"unseen_{index + 1}"


def coordinate_limits(reference_coordinates, input_coordinates, pad):
    points = np.vstack([reference_coordinates, input_coordinates])
    x_min, y_min = np.nanmin(points, axis=0)
    x_max, y_max = np.nanmax(points, axis=0)
    x_span = max(float(x_max - x_min), 1.0)
    y_span = max(float(y_max - y_min), 1.0)
    pad = max(float(pad), 0.0)
    x_limits = (float(x_min - pad * x_span), float(x_max + pad * x_span))
    y_limits = (float(y_min - pad * y_span), float(y_max + pad * y_span))
    return x_limits, y_limits


def make_grid(reference_coordinates, input_coordinates, grid_size, pad):
    x_limits, y_limits = coordinate_limits(reference_coordinates, input_coordinates, pad)
    xs = np.linspace(*x_limits, int(grid_size))
    ys = np.linspace(*y_limits, int(grid_size))
    xx, yy = np.meshgrid(xs, ys)
    return xx, yy, x_limits, y_limits


def add_kmeans_regions(ax, model, reference_coordinates, input_coordinates, grid_size, pad):
    xx, yy, x_limits, y_limits = make_grid(
        reference_coordinates, input_coordinates, grid_size, pad
    )
    grid = np.c_[xx.ravel(), yy.ravel()]
    region = model.predict(grid).reshape(xx.shape)
    cluster_count = int(model.n_clusters)
    colors = kmeans_color_list(cluster_count)
    cmap = ListedColormap(colors)
    levels = np.arange(cluster_count + 1) - 0.5
    ax.contourf(xx, yy, region, levels=levels, cmap=cmap, alpha=0.10)
    ax.contour(xx, yy, region, levels=levels, colors="black", linewidths=0.6, alpha=0.65)
    return colors, x_limits, y_limits


def plot_input_diamonds(ax, input_coordinates, input_names, input_numbers):
    input_colors = [input_diamond_color(number) for number in input_numbers]
    ax.scatter(
        input_coordinates[:, 0],
        input_coordinates[:, 1],
        marker="D",
        s=110,
        color=input_colors,
        edgecolor="black",
        linewidth=0.9,
        zorder=8,
    )
    legend_handles = [
        input_diamond_legend_handle(number)
        for number in input_numbers
    ]
    legend_labels = [str(name) for name in input_names]
    return legend_handles, legend_labels


def plot_cluster_projection(
    reference_coordinates,
    reference_clusters,
    input_coordinates,
    input_names,
    input_numbers,
    model,
    output_base,
    grid_size,
    pad,
):
    fig, ax = plt.subplots(figsize=(9.5, 7.2))
    colors, x_limits, y_limits = add_kmeans_regions(
        ax, model, reference_coordinates, input_coordinates, grid_size, pad
    )
    for cluster in sorted(np.unique(reference_clusters)):
        mask = reference_clusters == cluster
        ax.scatter(
            reference_coordinates[mask, 0],
            reference_coordinates[mask, 1],
            s=34,
            alpha=0.84,
            color=colors[int(cluster)],
            label=f"Reference cluster {int(cluster)}",
            edgecolors="none",
        )
    input_handles, input_labels = plot_input_diamonds(
        ax, input_coordinates, input_names, input_numbers
    )
    centers = np.asarray(model.cluster_centers_)
    ax.scatter(centers[:, 0], centers[:, 1], marker="X", s=130, color="black", label="KMeans centers")
    ax.set_xlabel("UMAP1")
    ax.set_ylabel("UMAP2")
    ax.set_title("Unseen observations projected into the frozen reference UMAP space")
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)
    reference_handles, reference_labels = ax.get_legend_handles_labels()
    reference_legend = ax.legend(
        reference_handles,
        reference_labels,
        title="Frozen reference",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
    )
    ax.add_artist(reference_legend)
    ax.legend(
        handles=input_handles,
        labels=input_labels,
        title="FWAV input",
        bbox_to_anchor=(1.02, 0),
        loc="lower left",
    )
    fig.tight_layout()
    save_figure_png_and_svg(output_base)
    plt.close(fig)


def plot_true_label_projection(
    reference_coordinates,
    reference_types,
    input_coordinates,
    input_names,
    input_numbers,
    model,
    output_base,
    grid_size,
    pad,
    reference_output_base=None,
):
    """Optionally export the same plot with unseen points and legends hidden."""
    fig, ax = plt.subplots(figsize=(9.5, 7.2))
    _, x_limits, y_limits = add_kmeans_regions(
        ax, model, reference_coordinates, input_coordinates, grid_size, pad
    )
    normalized_types = np.asarray(
        [normalize_type_number_label(value) for value in reference_types], dtype=str
    )
    colors = type_number_color_map(normalized_types, reference_labels=normalized_types)
    for type_label in sorted(pd.unique(normalized_types), key=class_sort_key):
        mask = normalized_types == type_label
        ax.scatter(
            reference_coordinates[mask, 0],
            reference_coordinates[mask, 1],
            s=34,
            alpha=0.86,
            color=colors[type_label],
            label=str(type_label),
            edgecolors="none",
        )
    input_handles, input_labels = plot_input_diamonds(
        ax, input_coordinates, input_names, input_numbers
    )
    input_points = ax.collections[-1]
    ax.set_xlabel("UMAP1")
    ax.set_ylabel("UMAP2")
    ax.set_title("Frozen reference coordinates and transform-only unseen projections")
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)
    type_handles, type_labels = ax.get_legend_handles_labels()
    type_legend = ax.legend(
        type_handles,
        type_labels,
        title="Type Number",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
    )
    ax.add_artist(type_legend)
    input_legend = ax.legend(
        handles=input_handles,
        labels=input_labels,
        title="FWAV input",
        bbox_to_anchor=(1.02, 0),
        loc="lower left",
    )
    fig.tight_layout()
    save_figure_png_and_svg(output_base)
    if reference_output_base is not None:
        input_points.set_visible(False)
        type_legend.set_visible(False)
        input_legend.set_visible(False)
        save_figure_png_and_svg(reference_output_base)
    plt.close(fig)


def build_nearest_reference_table(
    input_names,
    input_coordinates,
    reference_table,
    reference_coordinates,
    name_col,
    label_col,
):

    input_coordinates = np.asarray(input_coordinates, dtype=np.float64)
    reference_coordinates = np.asarray(reference_coordinates, dtype=np.float64)
    for role, coordinates, expected_rows in (
        ("Input", input_coordinates, len(input_names)),
        ("Reference", reference_coordinates, len(reference_table)),
    ):
        if coordinates.shape != (expected_rows, 2):
            raise ValueError(f"{role} UMAP coordinates must have shape ({expected_rows}, 2).")
        if not np.isfinite(coordinates).all():
            raise ValueError(f"{role} UMAP coordinates must be finite.")
    if len(reference_table) == 0:
        raise ValueError("At least one reference row is required for UMAP nearest neighbors.")

    columns = [
        "Input_Index", "Input_Name", "Input_UMAP1", "Input_UMAP2",
        "Nearest_Space", "Nearest_Metric", "Reference_Row_Index",
        "Reference_Original_Index", "Reference_Name", "Reference_Type_Number",
        "Reference_KMeans_Cluster", "Reference_UMAP1", "Reference_UMAP2", "Distance",
    ]
    rows = []
    for input_index, name in enumerate(input_names):
        umap_distances = np.linalg.norm(reference_coordinates - input_coordinates[input_index], axis=1)
        nearest_index = int(np.argmin(umap_distances))
        reference_row = reference_table.iloc[nearest_index]
        rows.append(
            {
                "Input_Index": input_index,
                "Input_Name": name,
                "Input_UMAP1": float(input_coordinates[input_index, 0]),
                "Input_UMAP2": float(input_coordinates[input_index, 1]),
                "Nearest_Space": NEAREST_REFERENCE_SPACE,
                "Nearest_Metric": NEAREST_REFERENCE_METRIC,
                "Reference_Row_Index": nearest_index,
                "Reference_Original_Index": reference_row.get("Reference_Original_Index", nearest_index),
                "Reference_Name": reference_row.get(name_col, f"reference_{nearest_index + 1}"),
                "Reference_Type_Number": reference_row.get(label_col, np.nan),
                "Reference_KMeans_Cluster": reference_row.get("Reference_KMeans_Cluster", np.nan),
                "Reference_UMAP1": float(reference_coordinates[nearest_index, 0]),
                "Reference_UMAP2": float(reference_coordinates[nearest_index, 1]),
                "Distance": float(umap_distances[nearest_index]),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def metadata_frame(metadata):
    rows = []
    for key, value in metadata.items():
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        rows.append({"key": key, "value": value})
    return pd.DataFrame(rows)


def main(ood_policy=OOD_POLICY_STRICT_REJECTION):
    warnings.filterwarnings("ignore", category=UserWarning)
    if ood_policy not in {OOD_POLICY_STRICT_REJECTION, OOD_POLICY_WARNING_ONLY}:
        raise ValueError(f"Unsupported OOD policy: {ood_policy}")
    warning_only = ood_policy == OOD_POLICY_WARNING_ONLY
    args = parse_args()
    if not 0.0 < float(args.ood_reference_quantile) < 1.0:
        raise ValueError("--ood-reference-quantile must be strictly between 0 and 1.")
    if not args.model_artifact.exists():
        raise FileNotFoundError(
            f"Missing frozen reference model: {args.model_artifact}\n"
            "Run fine_search_reference_umap_kmeans.py first."
        )

    artifact = joblib.load(args.model_artifact)
    validate_artifact(artifact)
    input_frame = read_input_rows(args.input, args.input_sheet).reset_index(drop=True)
    if input_frame.empty:
        raise ValueError("The unseen input table contains no rows to transform.")
    selected_features = list(artifact["selected_features"])
    missing = [feature for feature in selected_features if feature not in input_frame.columns]
    if missing:
        raise ValueError(f"Unseen input table is missing selected features: {missing}")

    name_col = artifact["name_col"]
    label_col = artifact["label_col"]
    input_names = [row_name(input_frame, index, name_col) for index in range(len(input_frame))]
    raw_input = input_frame.loc[:, selected_features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    input_processed = transform_preprocessor(raw_input, artifact["preprocessor"])

    reducer = artifact["umap_reducer"]
    reference_coordinates = np.asarray(artifact["reference_coordinates"], dtype=np.float64)
    reference_coordinates_before = reference_coordinates.copy()
    reducer_embedding_before = np.asarray(reducer.embedding_, dtype=np.float64).copy()
    reference_hash_before = sha256_array(reference_coordinates_before)
    reducer_hash_before = sha256_array(reducer_embedding_before)

    input_coordinates = transform_rows_independently(reducer, input_processed)

    reference_coordinates_after = np.asarray(artifact["reference_coordinates"], dtype=np.float64)
    reducer_embedding_after = np.asarray(reducer.embedding_, dtype=np.float64)
    reference_unchanged = arrays_exactly_equal(reference_coordinates_before, reference_coordinates_after)
    reducer_embedding_unchanged = arrays_exactly_equal(reducer_embedding_before, reducer_embedding_after)
    if not reference_unchanged or not reducer_embedding_unchanged:
        raise RuntimeError(
            "Invariant violation: UMAP.transform changed stored reference coordinates or reducer.embedding_."
        )

    kmeans = artifact["kmeans_model"]
    input_clusters = np.asarray(kmeans.predict(input_coordinates), dtype=int)
    cluster_distances = np.asarray(kmeans.transform(input_coordinates), dtype=np.float64)
    ordered_distances = np.sort(cluster_distances, axis=1)
    reference_table = artifact["reference_table"].copy().reset_index(drop=True)
    reference_clusters = np.asarray(artifact["reference_clusters"], dtype=int)
    ood_features, ood_feature_source = resolve_ood_features(
        artifact, reference_table, input_frame
    )
    ood_assessment, ood_calibration, _ = assess_reference_only_ood(
        reference_table=reference_table,
        input_frame=input_frame,
        input_names=input_names,
        feature_columns=ood_features,
        feature_source=ood_feature_source,
        reference_quantile=args.ood_reference_quantile,
        name_col=name_col,
        label_col=label_col,
    )
    ood_threshold_exceeded = ood_assessment[
        "OOD_Threshold_Exceeded"
    ].to_numpy(dtype=bool)
    if warning_only:
        ood_assessment["OOD_Status"] = np.where(
            ood_threshold_exceeded, "WARNING_OOD", "IN_DISTRIBUTION"
        )
        ood_assessment["OOD_Rejected"] = False
        ood_assessment["OOD_Rejection_Reason"] = np.where(
            ood_threshold_exceeded,
            "warning_only_distance_above_reference_threshold",
            "distance_within_reference_threshold",
        )
    ood_rejected = ood_assessment["OOD_Rejected"].to_numpy(dtype=bool)
    ood_threshold = float(ood_assessment["OOD_Distance_Threshold"].iloc[0])
    plotted_input_indices = np.flatnonzero(~ood_rejected)
    plotted_input_coordinates = input_coordinates[plotted_input_indices]
    plotted_input_names = [
        input_names[index] for index in plotted_input_indices
    ]
    plotted_input_numbers = (plotted_input_indices + 1).astype(int).tolist()

    nearest = build_nearest_reference_table(
        input_names,
        input_coordinates,
        reference_table,
        reference_coordinates,
        name_col,
        label_col,
    )

    for column in ("OOD_Status", "OOD_Threshold_Exceeded", "OOD_Rejected"):
        nearest[column] = ood_assessment[column].to_numpy()

    projected = input_frame.copy()
    projected.insert(0, "Projection_Role", "unseen_transform_only")
    projected.insert(1, "Projection_Transform_Mode", ROW_WISE_TRANSFORM_MODE)
    projected["Projected_UMAP1"] = input_coordinates[:, 0]
    projected["Projected_UMAP2"] = input_coordinates[:, 1]
    projected["Nearest_Space"] = NEAREST_REFERENCE_SPACE
    projected["Nearest_Metric"] = NEAREST_REFERENCE_METRIC
    for column in (
        "Reference_Row_Index", "Reference_Original_Index", "Reference_Name",
        "Reference_Type_Number", "Reference_KMeans_Cluster",
        "Reference_UMAP1", "Reference_UMAP2",
    ):
        projected[f"Nearest_{column}"] = nearest[column].to_numpy()
    projected["Nearest_Reference_Distance"] = nearest["Distance"].to_numpy()
    projected["Projected_KMeans_Cluster"] = input_clusters
    if warning_only:
        projected["Projected_KMeans_Cluster_Interpretation"] = np.where(
            ood_threshold_exceeded,
            "accepted_with_ood_warning",
            "accepted_in_distribution",
        )
    else:
        projected["Projected_KMeans_Cluster_Interpretation"] = np.where(
            ood_rejected,
            "provisional_only_rejected_by_ood",
            "accepted_in_distribution",
        )
    accepted_clusters = pd.Series(input_clusters, index=projected.index, dtype="Int64")
    accepted_clusters.loc[ood_rejected] = pd.NA
    projected["Accepted_KMeans_Cluster"] = accepted_clusters
    projected["Classification_Decision"] = ood_assessment["OOD_Status"].to_numpy()
    projected["OOD_Threshold_Exceeded"] = ood_threshold_exceeded
    projected["OOD_Rejected"] = ood_rejected
    projected["OOD_Method"] = OOD_METHOD
    projected["OOD_Distance_Threshold"] = ood_threshold
    projected["OOD_NN_Percentile"] = ood_assessment[
        "OOD_NN_Percentile"
    ].to_numpy()
    projected["OOD_Reference_Quantile"] = float(args.ood_reference_quantile)
    projected["OOD_Feature_Count"] = len(ood_features)
    projected["OOD_Features"] = "; ".join(ood_features)
    projected["Distance_To_Assigned_Center"] = cluster_distances[
        np.arange(len(input_clusters)), input_clusters
    ]
    projected["Nearest_Second_Center_Margin"] = (
        ordered_distances[:, 1] - ordered_distances[:, 0]
        if cluster_distances.shape[1] > 1
        else np.nan
    )

    rejected_names = ood_assessment.loc[
        ood_assessment["OOD_Rejected"], "Input_Name"
    ].astype(str).tolist()
    warning_names = ood_assessment.loc[
        ood_assessment["OOD_Threshold_Exceeded"], "Input_Name"
    ].astype(str).tolist()
    audit = pd.DataFrame(
        [
            ("operation", "umap_reducer.transform"),
            ("transform_mode", ROW_WISE_TRANSFORM_MODE),
            ("transform_call_count", len(input_frame)),
            ("rows_per_transform_call", 1),
            ("preprocessor_operation", "imputer.transform -> scaler.transform"),
            ("cluster_operation", "kmeans_model.predict"),
            ("model_refit_performed", False),
            ("nearest_reference_space", NEAREST_REFERENCE_SPACE),
            ("nearest_reference_metric", NEAREST_REFERENCE_METRIC),
            ("nearest_reference_candidates", "all_frozen_reference_rows"),
            ("ood_policy", ood_policy),
            ("ood_rejection_enabled", not warning_only),
            ("ood_warning_only", warning_only),
            ("ood_method", OOD_METHOD),
            ("ood_feature_source", ood_feature_source),
            ("ood_feature_count", len(ood_features)),
            ("ood_features", "; ".join(ood_features)),
            ("ood_reference_quantile", float(args.ood_reference_quantile)),
            ("ood_distance_threshold", ood_threshold),
            ("ood_reference_scaler_fit_on_reference_only", True),
            ("ood_unseen_rows_used_for_calibration", 0),
            ("ood_threshold_exceeded_count", int(np.sum(ood_threshold_exceeded))),
            ("ood_warning_names", "; ".join(warning_names)),
            ("ood_rejected_count", int(np.sum(ood_rejected))),
            ("ood_rejected_names", "; ".join(rejected_names)),
            ("ood_rejected_rows_excluded_from_plots", not warning_only),
            ("plotted_unseen_row_count", len(plotted_input_indices)),
            ("plotted_unseen_input_numbers", "; ".join(map(str, plotted_input_numbers))),
            ("unseen_row_count", len(input_frame)),
            ("reference_row_count", len(reference_coordinates)),
            ("stored_reference_coordinates_unchanged", reference_unchanged),
            ("reducer_embedding_unchanged", reducer_embedding_unchanged),
            ("reference_hash_before", reference_hash_before),
            ("reference_hash_after", sha256_array(reference_coordinates_after)),
            ("reducer_embedding_hash_before", reducer_hash_before),
            ("reducer_embedding_hash_after", sha256_array(reducer_embedding_after)),
            ("verified_utc", datetime.now(timezone.utc).isoformat()),
        ],
        columns=["check", "value"],
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    projected_csv = args.output_dir / "summary_input_projected_umap_scores.csv"
    nearest_csv = args.output_dir / "summary_input_nearest_reference.csv"
    ood_csv = args.output_dir / "summary_input_ood_assessment.csv"
    ood_calibration_csv = args.output_dir / "ood_reference_calibration.csv"
    output_xlsx = args.output_dir / "summary_input_frozen_umap_projection.xlsx"
    projected.to_csv(projected_csv, index=False, encoding="utf-8-sig")
    nearest.to_csv(nearest_csv, index=False, encoding="utf-8-sig")
    ood_assessment.to_csv(ood_csv, index=False, encoding="utf-8-sig")
    ood_calibration.to_csv(ood_calibration_csv, index=False, encoding="utf-8-sig")

    plot_cluster_projection(
        reference_coordinates,
        reference_clusters,
        plotted_input_coordinates,
        plotted_input_names,
        plotted_input_numbers,
        kmeans,
        args.output_dir / "frozen_umap_with_summary_input_clusters",
        args.grid_size,
        args.umap_grid_pad,
    )
    reference_only_base = args.output_dir / "frozen_umap_reference_only_true_labels"
    plot_true_label_projection(
        reference_coordinates,
        reference_table[label_col].to_numpy(),
        plotted_input_coordinates,
        plotted_input_names,
        plotted_input_numbers,
        kmeans,
        args.output_dir / "frozen_umap_with_summary_input_true_labels",
        args.grid_size,
        args.umap_grid_pad,
        reference_output_base=reference_only_base,
    )
    projection_legend_base = args.output_dir / "frozen_umap_projection_legend"
    projection_legend_png, projection_legend_svg = save_projection_legend(
        reference_table[label_col].to_numpy(),
        plotted_input_names,
        plotted_input_numbers,
        kmeans,
        projection_legend_base,
    )

    pie_summary = pd.DataFrame()
    pie_dir = args.output_dir / "reference_cluster_pies"
    if not args.no_pies:
        pie_summary = plot_cluster_pies(
            reference_clusters,
            reference_table[label_col].to_numpy(),
            pie_dir,
        )
        pie_summary.to_csv(
            pie_dir / "cluster_type_pie_summary.csv", index=False, encoding="utf-8-sig"
        )

    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        projected.to_excel(writer, sheet_name="projected_unseen_rows", index=False)
        ood_assessment.to_excel(writer, sheet_name="ood_assessment", index=False)
        ood_calibration.to_excel(writer, sheet_name="ood_calibration", index=False)
        reference_table.to_excel(writer, sheet_name="frozen_reference_rows", index=False)
        nearest.to_excel(writer, sheet_name="nearest_reference", index=False)
        pd.DataFrame(kmeans.cluster_centers_, columns=["UMAP1", "UMAP2"]).to_excel(
            writer, sheet_name="kmeans_centers", index_label="Cluster"
        )
        audit.to_excel(writer, sheet_name="invariance_audit", index=False)
        metadata_frame(artifact["metadata"]).to_excel(
            writer, sheet_name="model_metadata", index=False
        )
        if not pie_summary.empty:
            pie_summary.to_excel(writer, sheet_name="reference_pie_summary", index=False)

    run_manifest = {
        "workflow_stage": "unseen_transform_only",
        "model_artifact": str(args.model_artifact.resolve()),
        "input_source": str(args.input.resolve()),
        "output_workbook": str(output_xlsx.resolve()),
        "unseen_row_count": int(len(input_frame)),
        "transform_mode": ROW_WISE_TRANSFORM_MODE,
        "transform_call_count": int(len(input_frame)),
        "rows_per_transform_call": 1,
        "selected_features": selected_features,
        "nearest_reference_space": NEAREST_REFERENCE_SPACE,
        "nearest_reference_metric": NEAREST_REFERENCE_METRIC,
        "nearest_reference_candidates": "all_frozen_reference_rows",
        "nearest_reference_csv": str(nearest_csv.resolve()),
        "ood_policy": ood_policy,
        "ood_rejection_enabled": not warning_only,
        "ood_warning_only": warning_only,
        "ood_method": OOD_METHOD,
        "ood_feature_source": ood_feature_source,
        "ood_features": ood_features,
        "ood_reference_quantile": float(args.ood_reference_quantile),
        "ood_distance_threshold": ood_threshold,
        "ood_unseen_rows_used_for_calibration": 0,
        "ood_threshold_exceeded_count": int(np.sum(ood_threshold_exceeded)),
        "ood_warning_names": warning_names,
        "ood_rejected_count": int(np.sum(ood_rejected)),
        "ood_rejected_names": rejected_names,
        "ood_rejected_rows_excluded_from_plots": not warning_only,
        "plotted_unseen_row_count": int(len(plotted_input_indices)),
        "plotted_unseen_input_numbers": plotted_input_numbers,
        "plotted_unseen_input_names": plotted_input_names,
        "ood_assessment_csv": str(ood_csv.resolve()),
        "ood_calibration_csv": str(ood_calibration_csv.resolve()),
        "reference_coordinates_unchanged": bool(reference_unchanged),
        "reducer_embedding_unchanged": bool(reducer_embedding_unchanged),
        "model_refit_performed": False,
        "pie_population": "reference_only",
        "projection_legend_png": str(projection_legend_png.resolve()),
        "projection_legend_svg": str(projection_legend_svg.resolve()),
        "reference_only_true_labels_png": str(reference_only_base.with_suffix(".png").resolve()),
        "reference_only_true_labels_svg": str(reference_only_base.with_suffix(".svg").resolve()),
    }
    (args.output_dir / "projection_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Frozen-space projection complete.", flush=True)
    print(f"Unseen rows transformed: {len(input_frame)}", flush=True)
    print(f"Transform mode: {ROW_WISE_TRANSFORM_MODE}", flush=True)
    print("Model refit performed: False", flush=True)
    print(
        f"Wing pairing: {NEAREST_REFERENCE_SPACE} | {NEAREST_REFERENCE_METRIC} | "
        "all frozen reference rows",
        flush=True,
    )
    for row in nearest.itertuples(index=False):
        print(
            f"UMAP nearest {row.Input_Name}: {row.Reference_Name} | "
            f"distance={row.Distance:.6f}",
            flush=True,
        )
    print(
        f"OOD policy: {ood_policy} | {OOD_METHOD} | "
        f"q={args.ood_reference_quantile:.3f} "
        f"| threshold={ood_threshold:.6f}",
        flush=True,
    )
    for row in ood_assessment.itertuples(index=False):
        print(
            f"OOD {row.Input_Name}: {row.OOD_Status} | "
            f"distance={row.OOD_Nearest_Distance:.6f} | "
            f"reference-NN percentile={row.OOD_NN_Percentile:.2f}%",
            flush=True,
        )
    if rejected_names:
        print(
            "Excluded from projection figures and standalone legend: "
            + "; ".join(rejected_names),
            flush=True,
        )
    elif warning_only and warning_names:
        print(
            "OOD warning only; retained in figures, legend, classification, and "
            "nearest-neighbor outputs: " + "; ".join(warning_names),
            flush=True,
        )
    print(f"Reference coordinates unchanged: {reference_unchanged}", flush=True)
    print(f"Reducer embedding unchanged: {reducer_embedding_unchanged}", flush=True)
    print(f"Projection workbook: {output_xlsx}", flush=True)
    print(f"UMAP nearest-reference pairs: {nearest_csv}", flush=True)
    print(f"Standalone projection legend: {projection_legend_png}", flush=True)
    print(f"Reference-only plot (no legend): {reference_only_base.with_suffix('.png')}", flush=True)
    if not args.no_pies:
        print(f"Reference-only pie charts: {pie_dir}", flush=True)


if __name__ == "__main__":
    main()
