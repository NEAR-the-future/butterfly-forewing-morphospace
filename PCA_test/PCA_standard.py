from pathlib import Path

import os
os.environ["OMP_NUM_THREADS"] = "2"

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


A4_HALF_WIDTH_IN = 105 / 25.4
PCA_2D_FIGSIZE = (A4_HALF_WIDTH_IN, 3.0)
PCA_3D_FIGSIZE = (A4_HALF_WIDTH_IN, 3.6)

TICK_FONTSIZE = 6
LABEL_FONTSIZE = 7
TITLE_FONTSIZE = 9
LEGEND_FONTSIZE = 6
LEGEND_TITLE_FONTSIZE = 7

POINT_SIZE = 10
POINT_ALPHA = 0.86

TYPE_NUMBER_COLOR_ALIASES = {"14": "4"}
TYPE_NUMBER_REFERENCE_ORDER = [str(i) for i in range(1, 14)]

FAMILY_CODE_MAP = {
    "Hesperiidae": 1,
    "Lycaenidae": 2,
    "Papilioninae": 3,
    "Pieridae": 4,
    "Biblidinae": 5,
    "Charaxinae": 6,
    "Danainae": 7,
    "Heliconiinae": 8,
    "Limenitidinae": 9,
    "Nymphalinae": 10,
    "Satyrinae": 11,
    "Parnassiinae": 12,
    "Riodinidae": 13,
}
TYPE_TO_FAMILY = {str(code): family for family, code in FAMILY_CODE_MAP.items()}

matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["font.serif"] = [
    "Times New Roman",
    "Times New Roman PS MT",
    "Times",
    "Nimbus Roman",
    "DejaVu Serif"
]

matplotlib.rcParams["svg.fonttype"] = "none"

matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42

matplotlib.rcParams["axes.unicode_minus"] = False

matplotlib.rcParams["figure.dpi"] = 150
matplotlib.rcParams["savefig.dpi"] = 600

print("Times New Roman font path:")
print(font_manager.findfont("Times New Roman"))

SCRIPT_DIR = Path(__file__).resolve().parent
path = SCRIPT_DIR / "summary_11.xlsx"
label_col = "Type Number"
output_dir = SCRIPT_DIR / "pca_11_features_output_standard_all_samples"
PCA_OUTLIERS_TO_REMOVE = 0
os.makedirs(output_dir, exist_ok=True)


def class_sort_key(value):
    text = str(value)
    try:
        return 0, float(text)
    except ValueError:
        return 1, text


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


def type_number_display_label(value):
    normalized = normalize_type_number_label(value)
    return TYPE_TO_FAMILY.get(normalized, f"Type {normalized}")


def type_number_color_map(labels):
    labels = np.asarray(labels).astype(str)
    classes = sorted(pd.unique(labels), key=class_sort_key)

    reference_keys = [type_number_color_key(label) for label in TYPE_NUMBER_REFERENCE_ORDER]
    extra_keys = sorted(
        {
            type_number_color_key(label)
            for label in classes
            if type_number_color_key(label) not in reference_keys
        },
        key=class_sort_key
    )

    ordered_keys = reference_keys + extra_keys
    cmap = plt.get_cmap("tab20")
    colors_by_key = {
        key: cmap(index % cmap.N)
        for index, key in enumerate(ordered_keys)
    }

    return {
        label: colors_by_key[type_number_color_key(label)]
        for label in classes
    }


def get_discrete_colors(n_colors):
    palette = []
    palette.extend(plt.cm.tab20.colors)
    palette.extend(plt.cm.tab20b.colors)
    palette.extend(plt.cm.tab20c.colors)

    if n_colors <= len(palette):
        return palette[:n_colors]

    return [palette[index % len(palette)] for index in range(n_colors)]


def cluster_color_map(labels):
    labels = np.asarray(labels)
    unique_labels = sorted(pd.unique(labels))
    colors = get_discrete_colors(len(unique_labels))

    return {
        cluster_label: colors[index]
        for index, cluster_label in enumerate(unique_labels)
    }


def set_times_new_roman(
    ax,
    tick_fontsize=TICK_FONTSIZE,
    label_fontsize=LABEL_FONTSIZE,
    title_fontsize=TITLE_FONTSIZE
):
    ax.title.set_fontname("Times New Roman")
    ax.title.set_fontsize(title_fontsize)

    ax.xaxis.label.set_fontname("Times New Roman")
    ax.xaxis.label.set_fontsize(label_fontsize)

    ax.yaxis.label.set_fontname("Times New Roman")
    ax.yaxis.label.set_fontsize(label_fontsize)

    for label in ax.get_xticklabels():
        label.set_fontname("Times New Roman")
        label.set_fontsize(tick_fontsize)

    for label in ax.get_yticklabels():
        label.set_fontname("Times New Roman")
        label.set_fontsize(tick_fontsize)

    if hasattr(ax, "zaxis"):
        ax.zaxis.label.set_fontname("Times New Roman")
        ax.zaxis.label.set_fontsize(label_fontsize)

        for label in ax.get_zticklabels():
            label.set_fontname("Times New Roman")
            label.set_fontsize(tick_fontsize)


def add_right_side_legend(ax, title=None, bbox_to_anchor=(1.03, 1.0)):
    legend = ax.legend(
        title=title,
        bbox_to_anchor=bbox_to_anchor,
        loc="upper left",
        frameon=True,
        ncol=1,
        fontsize=LEGEND_FONTSIZE,
        title_fontsize=LEGEND_TITLE_FONTSIZE,
        borderaxespad=0.0,
        labelspacing=0.25,
        handletextpad=0.35,
        borderpad=0.35,
        markerscale=1.0
    )

    if title:
        legend.get_title().set_fontname("Times New Roman")
        legend.get_title().set_fontsize(LEGEND_TITLE_FONTSIZE)

    for text in legend.get_texts():
        text.set_fontname("Times New Roman")
        text.set_fontsize(LEGEND_FONTSIZE)

    return legend


def save_figure_outputs(fig, output_dir, basename):
    base_path = os.path.join(output_dir, basename)

    svg_path = f"{base_path}.svg"
    pdf_path = f"{base_path}.pdf"
    png_path = f"{base_path}.png"

    fig.savefig(svg_path, format="svg")
    fig.savefig(pdf_path, format="pdf")
    fig.savefig(png_path, format="png", dpi=600)
    plt.close(fig)

    return svg_path, pdf_path, png_path


df = pd.read_excel(path, engine="openpyxl")

feature_cols = [
    column
    for column in df.columns
    if column != label_col and pd.api.types.is_numeric_dtype(df[column])
]

if len(feature_cols) < 3:
    raise ValueError("At least three numeric feature columns are required for 3D PCA.")

X = df[feature_cols].to_numpy(dtype=float)
X = np.where(np.isfinite(X), X, np.nan)
empty_features = [feature_cols[i] for i in np.flatnonzero(np.isnan(X).all(axis=0))]
if empty_features:
    raise ValueError(f"Features without any finite observations: {empty_features}")
y_true = np.asarray([
    normalize_type_number_label(value)
    for value in df[label_col].to_numpy()
])

print("Sample count:", len(df))
print("Class count:", df[label_col].nunique())
print("Features used:", feature_cols)

imputer = SimpleImputer(strategy="median")
X_imputed = imputer.fit_transform(X)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_imputed)
print("Preprocessing: non-finite to NaN -> median imputation -> StandardScaler")

def remove_outliers(Z, n_remove=PCA_OUTLIERS_TO_REMOVE):
    if len(Z) < 4:
        raise ValueError("At least four samples are required before outlier removal.")

    actual_n_remove = min(max(int(n_remove), 0), len(Z) - 3)
    center = np.median(Z, axis=0)
    distances = np.linalg.norm(Z - center, axis=1)

    if actual_n_remove > 0:
        outlier_idx = np.argsort(distances)[-actual_n_remove:]
    else:
        outlier_idx = np.array([], dtype=int)

    keep_idx = np.setdiff1d(np.arange(len(Z)), outlier_idx)

    return keep_idx, outlier_idx


keep_idx, outlier_idx = remove_outliers(X_scaled)
X_clean = X_scaled[keep_idx]
y_clean = y_true[keep_idx]

print(f"Removed {len(outlier_idx)} outliers. Remaining samples: {len(keep_idx)}")

pca_3d = PCA(n_components=3, random_state=0)
Z3 = pca_3d.fit_transform(X_clean)
pc1_3d, pc2_3d, pc3_3d = Z3[:, 0], Z3[:, 1], Z3[:, 2]

pca_2d = PCA(n_components=2, random_state=0)
Z2 = pca_2d.fit_transform(X_clean)
pc1_2d, pc2_2d = Z2[:, 0], Z2[:, 1]

print("Explained variance ratio for 3D PCA:", pca_3d.explained_variance_ratio_)
print("Explained variance ratio for 2D PCA:", pca_2d.explained_variance_ratio_)
variance_rows = []
for space, model in [("2D", pca_2d), ("3D", pca_3d)]:
    cumulative = np.cumsum(model.explained_variance_ratio_)
    for i, ratio in enumerate(model.explained_variance_ratio_):
        variance_rows.append({
            "PCA_space": space,
            "component": f"PC{i + 1}",
            "explained_variance": model.explained_variance_[i],
            "explained_variance_ratio": ratio,
            "explained_variance_percent": ratio * 100,
            "cumulative_variance_ratio": cumulative[i],
            "cumulative_variance_percent": cumulative[i] * 100,
        })
variance_df = pd.DataFrame(variance_rows)
variance_df.to_csv(output_dir / "pca_explained_variance.csv", index=False)
pc1_percent, pc2_percent = pca_2d.explained_variance_ratio_ * 100
print(f"Figure 4: PC1 = {pc1_percent:.2f}%, PC2 = {pc2_percent:.2f}%, "
      f"PC1 + PC2 = {pc1_percent + pc2_percent:.2f}%")

def auto_kmeans(Z, k_range=range(2, 20), random_state=0):
    valid_k_values = [k for k in k_range if 2 <= k < len(Z)]

    if not valid_k_values:
        raise ValueError(
            "Not enough samples are available for silhouette-based KMeans selection."
        )

    best_silhouette = -1.0
    best_k = None
    best_labels = None

    for k in valid_k_values:
        model = KMeans(
            n_clusters=k,
            n_init=50,
            random_state=random_state
        )

        labels = model.fit_predict(Z)
        silhouette = silhouette_score(Z, labels)

        if silhouette > best_silhouette:
            best_silhouette = silhouette
            best_k = k
            best_labels = labels

    return best_k, best_labels, best_silhouette


best_k_3d, cluster_3d, best_silhouette_3d = auto_kmeans(Z3)
best_k_2d, cluster_2d, best_silhouette_2d = auto_kmeans(Z2)

print(
    f"Best k for 3D PCA: {best_k_3d}. "
    f"Silhouette score: {best_silhouette_3d:.4f}"
)

print(
    f"Best k for 2D PCA: {best_k_2d}. "
    f"Silhouette score: {best_silhouette_2d:.4f}"
)

def plot_2d_true_labels(x, y, labels, title, save_basename):
    fig, ax = plt.subplots(figsize=PCA_2D_FIGSIZE)

    labels = np.asarray(labels).astype(str)
    classes = sorted(pd.unique(labels), key=class_sort_key)
    colors = type_number_color_map(labels)

    for category in classes:
        mask = labels == category

        ax.scatter(
            x[mask],
            y[mask],
            label=type_number_display_label(category),
            alpha=POINT_ALPHA,
            s=POINT_SIZE,
            color=colors[category],
            edgecolors="none",
            linewidths=0
        )

    ax.set_xlabel(f"PC1 ({pca_2d.explained_variance_ratio_[0]:.2%})")
    ax.set_ylabel(f"PC2 ({pca_2d.explained_variance_ratio_[1]:.2%})")
    ax.set_title(title)

    set_times_new_roman(ax)
    add_right_side_legend(ax)

    fig.subplots_adjust(
        left=0.16,
        right=0.72,
        bottom=0.18,
        top=0.86
    )

    return save_figure_outputs(
        fig,
        output_dir,
        save_basename
    )


def plot_2d_cluster(x, y, labels, title, save_basename):
    fig, ax = plt.subplots(figsize=PCA_2D_FIGSIZE)

    labels = np.asarray(labels)
    unique_labels = sorted(pd.unique(labels))
    colors = cluster_color_map(labels)

    for cluster_label in unique_labels:
        mask = labels == cluster_label

        ax.scatter(
            x[mask],
            y[mask],
            label=f"Cluster {cluster_label}",
            alpha=POINT_ALPHA,
            s=POINT_SIZE,
            color=colors[cluster_label],
            edgecolors="none",
            linewidths=0
        )

    ax.set_xlabel(f"PC1 ({pca_2d.explained_variance_ratio_[0]:.2%})")
    ax.set_ylabel(f"PC2 ({pca_2d.explained_variance_ratio_[1]:.2%})")
    ax.set_title(title)

    set_times_new_roman(ax)
    add_right_side_legend(ax, title="KMeans")

    fig.subplots_adjust(
        left=0.16,
        right=0.68,
        bottom=0.18,
        top=0.86
    )

    return save_figure_outputs(
        fig,
        output_dir,
        save_basename
    )


def plot_3d_true_labels(xs, ys, zs, labels, title, save_basename):
    fig = plt.figure(figsize=PCA_3D_FIGSIZE)
    ax = fig.add_subplot(111, projection="3d")

    labels = np.asarray(labels).astype(str)
    classes = sorted(pd.unique(labels), key=class_sort_key)
    colors = type_number_color_map(labels)

    for category in classes:
        mask = labels == category

        ax.scatter(
            xs[mask],
            ys[mask],
            zs[mask],
            label=type_number_display_label(category),
            alpha=POINT_ALPHA,
            s=POINT_SIZE,
            color=colors[category],
            edgecolors="none",
            linewidths=0
        )

    ax.set_xlabel(f"PC1 ({pca_3d.explained_variance_ratio_[0]:.2%})")
    ax.set_ylabel(f"PC2 ({pca_3d.explained_variance_ratio_[1]:.2%})")
    ax.set_zlabel(f"PC3 ({pca_3d.explained_variance_ratio_[2]:.2%})")
    ax.set_title(title)

    set_times_new_roman(ax)
    add_right_side_legend(ax)

    fig.subplots_adjust(
        left=0.00,
        right=0.70,
        bottom=0.04,
        top=0.90
    )

    return save_figure_outputs(
        fig,
        output_dir,
        save_basename
    )


def plot_3d_cluster(xs, ys, zs, labels, title, save_basename):
    fig = plt.figure(figsize=PCA_3D_FIGSIZE)
    ax = fig.add_subplot(111, projection="3d")

    labels = np.asarray(labels)
    unique_labels = sorted(pd.unique(labels))
    colors = cluster_color_map(labels)

    for cluster_label in unique_labels:
        mask = labels == cluster_label

        ax.scatter(
            xs[mask],
            ys[mask],
            zs[mask],
            label=f"Cluster {cluster_label}",
            alpha=POINT_ALPHA,
            s=POINT_SIZE,
            color=colors[cluster_label],
            edgecolors="none",
            linewidths=0
        )

    ax.set_xlabel(f"PC1 ({pca_3d.explained_variance_ratio_[0]:.2%})")
    ax.set_ylabel(f"PC2 ({pca_3d.explained_variance_ratio_[1]:.2%})")
    ax.set_zlabel(f"PC3 ({pca_3d.explained_variance_ratio_[2]:.2%})")
    ax.set_title(title)

    set_times_new_roman(ax)
    add_right_side_legend(ax, title="KMeans")

    fig.subplots_adjust(
        left=0.00,
        right=0.66,
        bottom=0.04,
        top=0.90
    )

    return save_figure_outputs(
        fig,
        output_dir,
        save_basename
    )


plot_2d_true_labels(
    pc1_2d,
    pc2_2d,
    y_clean,
    "2D PCA (All Specimens)",
    "pca_2d_true_all_samples"
)

plot_2d_cluster(
    pc1_2d,
    pc2_2d,
    cluster_2d,
    f"2D PCA KMeans (k={best_k_2d}, All Specimens)",
    "pca_2d_kmeans_all_samples"
)

plot_3d_true_labels(
    pc1_3d,
    pc2_3d,
    pc3_3d,
    y_clean,
    "3D PCA (All Specimens)",
    "pca_3d_true_all_samples"
)

plot_3d_cluster(
    pc1_3d,
    pc2_3d,
    pc3_3d,
    cluster_3d,
    f"3D PCA KMeans (k={best_k_3d}, All Specimens)",
    "pca_3d_kmeans_all_samples"
)

output_df = pd.DataFrame(
    X_clean,
    columns=feature_cols
)

output_df[label_col] = y_clean
output_df["PC1_2D"] = pc1_2d
output_df["PC2_2D"] = pc2_2d
output_df["PC1_3D"] = pc1_3d
output_df["PC2_3D"] = pc2_3d
output_df["PC3_3D"] = pc3_3d
output_df["Cluster_2D"] = cluster_2d
output_df["Cluster_3D"] = cluster_3d

output_excel_path = os.path.join(
    output_dir,
    "summary_with_pca_and_clusters_all_samples.xlsx"
)

with pd.ExcelWriter(output_excel_path, engine="openpyxl") as writer:
    output_df.to_excel(writer, sheet_name="scores_and_clusters", index=False)
    variance_df.to_excel(writer, sheet_name="explained_variance", index=False)
    pd.DataFrame({
        "feature": feature_cols,
        "imputation_median": imputer.statistics_,
        "standard_scaler_mean": scaler.mean_,
        "standard_scaler_scale": scaler.scale_,
    }).to_excel(writer, sheet_name="preprocessing", index=False)

baseline_note = (
    f"PCA baseline: {len(keep_idx)} specimens; {len(feature_cols)} features.\n"
    "Non-finite values were treated as missing and imputed with feature-wise "
    "medians. Features were then standardized to zero mean and unit population "
    "variance using StandardScaler, following the preprocessing sequence used "
    "in the UMAP workflow. Constant features, if any, remain zero after centering.\n"
    f"The imputer and scaler were fitted on all {len(df)} input specimens. "
    f"Outliers removed: {len(outlier_idx)}.\n"
    f"PC1 explains {pc1_percent:.2f}% and PC2 explains {pc2_percent:.2f}% "
    f"of the total variance in the standardized feature matrix "
    f"(cumulative: {pc1_percent + pc2_percent:.2f}%).\n"
    f"2D PCA KMeans: k={best_k_2d}, silhouette={best_silhouette_2d:.6f}.\n"
    f"3D PCA KMeans: k={best_k_3d}, silhouette={best_silhouette_3d:.6f}.\n"
    "KMeans selects k from 2 through 19 by maximum Euclidean silhouette "
    "score (n_init=50, random_state=0).\n"
    "This aligns preprocessing only; it does not establish identical feature "
    "selection, specimen filtering, or clustering settings between PCA and UMAP.\n"
)
(output_dir / "pca_baseline_summary.txt").write_text(baseline_note, encoding="utf-8")

print("PCA and clustering results have been saved.")
print("Output directory:", output_dir)
print("Excel output:", output_excel_path)
