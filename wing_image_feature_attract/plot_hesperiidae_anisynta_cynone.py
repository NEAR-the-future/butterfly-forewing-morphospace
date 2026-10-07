from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

import image_tool
import shape_tool
from wing_image_analysis import (
    area_bbox_ratio,
    compute_geometry_from_contour,
    extract_distal_segment,
    fit_distal_curve,
    fit_edge_curve,
    smooth_contour,
    split_le_te_by_root_tip,
    tip_area_to_wing_area_ratio,
    tip_curvature,
)


BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "wing_import" / "Hesperiidae_Anisynta_cynone.png"
OUTPUT_DIR = BASE_DIR / "edge_visual_data_clean"


def extract_wing_points(image_path):
    original = image_tool.import_image(str(image_path))
    wing_root = image_tool.detect_red_dot(original)
    if not wing_root:
        raise RuntimeError(f"No red root marker detected in {image_path.name}")

    edge_points, _ = image_tool.extract_edge_profile(
        original,
        red_dot_coords=wing_root,
    )
    if not edge_points:
        raise RuntimeError(f"No edge points found in {image_path.name}")

    manual_tip = image_tool.detect_blue_circle(original)
    if manual_tip is not None:
        wing_tip = manual_tip
    else:
        wing_tip = shape_tool.tip_locate(
            edge_points,
            wing_root,
            bending_threshold=35,
            window_size=15,
        )

    if wing_tip is None:
        raise RuntimeError(f"No wing tip detected in {image_path.name}")

    return edge_points, wing_root, wing_tip


def compute_plot_data(image_path):
    edge_points, wing_root, wing_tip = extract_wing_points(image_path)

    contour_pts = np.asarray(edge_points, dtype=np.float32).reshape(-1, 2)
    root = np.asarray(wing_root, dtype=np.float32).reshape(2,)
    tip = np.asarray(wing_tip, dtype=np.float32).reshape(2,)

    contour_t = image_tool.transform_points_by_span(contour_pts, root, tip)
    contour_1x2 = np.asarray(contour_t, dtype=np.float32).reshape(-1, 1, 2)

    geo = compute_geometry_from_contour(contour_1x2)
    wing_area = geo["area"]
    wing_area_bbox_ratio = area_bbox_ratio(contour_t, wing_area)
    tip_area_wing_ratio = tip_area_to_wing_area_ratio(
        contour_t,
        wing_area,
        tip=(1.0, 0.0),
        radius=0.1,
    )

    contour_s, _ = smooth_contour(contour_t)
    le_pts, te_pts = split_le_te_by_root_tip(
        contour_s,
        root_point=(0.0, 0.0),
        tip_point=(1.0, 0.0),
    )

    tip_info = tip_curvature(
        contour_s,
        tip=(1.0, 0.0),
        radius=0.05,
        poly_deg=3,
        n_samples=200,
        return_details=True,
    )

    le_fit = fit_edge_curve(le_pts, poly_deg=3, n_samples=400, fit_x_range=(0.1, 0.9))
    te_fit = fit_edge_curve(te_pts, poly_deg=3, n_samples=400, fit_x_range=(0.1, 0.9))

    distal_feat = extract_distal_segment(
        te_pts,
        tip_point=(1.0, 0.0),
        ref_x=te_fit["max_curv_x"],
        trim_frac=(0.10, 0.95),
    )
    distal_fit = fit_distal_curve(
        distal_feat["distal_segment_used"],
        poly_deg=3,
        n_samples=300,
    )

    return {
        "contour_smoothed": contour_s,
        "le_pts": le_pts,
        "te_pts": te_pts,
        "le_fit": le_fit,
        "te_fit": te_fit,
        "tip_info": tip_info,
        "distal_feat": distal_feat,
        "distal_fit": distal_fit,
        "wing_area_bbox_ratio": wing_area_bbox_ratio,
        "tip_area_wing_ratio": tip_area_wing_ratio,
    }


def plot_edge_fit_clean(plot_data, output_dir, name):
    contour_smoothed = np.asarray(plot_data["contour_smoothed"], dtype=float).reshape(-1, 2)
    le_pts = np.asarray(plot_data["le_pts"], dtype=float).reshape(-1, 2)
    te_pts = np.asarray(plot_data["te_pts"], dtype=float).reshape(-1, 2)
    le_fit = plot_data["le_fit"]
    te_fit = plot_data["te_fit"]
    tip_info = plot_data["tip_info"]
    distal_feat = plot_data["distal_feat"]
    distal_fit = plot_data["distal_fit"]

    distal_seg_used = distal_feat.get("distal_segment_used")
    turn_point = distal_feat.get("turn_point")
    if distal_seg_used is not None:
        distal_seg_used = np.asarray(distal_seg_used, dtype=float).reshape(-1, 2)
    if turn_point is not None:
        turn_point = np.asarray(turn_point, dtype=float).reshape(2,)

    fig, ax = plt.subplots(figsize=(11, 5.5))

    x_scale = np.max(contour_smoothed[:, 0]) - np.min(contour_smoothed[:, 0])
    y_scale = np.max(contour_smoothed[:, 1]) - np.min(contour_smoothed[:, 1])
    if not np.isfinite(x_scale) or x_scale <= 1e-12:
        x_scale = 1.0
    if not np.isfinite(y_scale) or y_scale <= 1e-12:
        y_scale = 1.0

    le_offset = -0.03 * y_scale
    te_offset = 0.10 * y_scale
    distal_dx = 0.03 * x_scale
    distal_dy = 0.12 * y_scale

    ax.plot(
        contour_smoothed[:, 0],
        contour_smoothed[:, 1],
        color="0.65",
        linewidth=1.6,
        alpha=0.95,
        label="Smoothed contour",
    )

    if len(le_pts) > 0:
        ax.scatter(le_pts[:, 0], le_pts[:, 1], s=10, c="tab:blue", alpha=0.75, label="LE points")

    if len(te_pts) > 0:
        ax.scatter(te_pts[:, 0], te_pts[:, 1], s=10, c="tab:orange", alpha=0.45, label="TE points")

    if le_fit is not None and le_fit["x_eval"] is not None:
        ax.plot(
            le_fit["x_eval"],
            le_fit["y_fit"] + le_offset,
            linestyle="--",
            c="blue",
            linewidth=2.2,
            alpha=0.95,
            label=f'LE fit (offset, bend={le_fit["bending"]:.4f})',
        )

    if te_fit is not None and te_fit["x_eval"] is not None:
        ax.plot(
            te_fit["x_eval"],
            te_fit["y_fit"] + te_offset,
            linestyle="--",
            c="darkorange",
            linewidth=2.2,
            alpha=0.95,
            label=f'TE fit (offset, bend={te_fit["bending"]:.4f})',
        )

        if np.isfinite(te_fit["max_curv_x"]) and np.isfinite(te_fit["max_curv_y"]):
            ax.plot(
                te_fit["max_curv_x"],
                te_fit["max_curv_y"] + te_offset,
                "o",
                color="darkorange",
                markersize=6,
                label=f'TE max-curv x={te_fit["max_curv_x"]:.3f}',
            )

    if distal_seg_used is not None and len(distal_seg_used) > 0:
        ax.plot(
            distal_seg_used[:, 0],
            distal_seg_used[:, 1],
            color="limegreen",
            linewidth=3.0,
            alpha=0.95,
            label="TE distal used (10%-95%)",
        )

    if turn_point is not None and np.all(np.isfinite(turn_point)):
        ax.plot(
            turn_point[0],
            turn_point[1],
            marker="D",
            color="purple",
            markersize=8,
            label="Distal turning point",
        )

    if distal_fit is not None and distal_fit["x_eval"] is not None:
        ax.plot(
            distal_fit["x_eval"] + distal_dx,
            distal_fit["y_fit"] + distal_dy,
            linestyle="--",
            c="limegreen",
            linewidth=2.4,
            alpha=0.95,
            label=(
                f'Distal fit (offset, bend={distal_fit["bending"]:.4f}, '
                f'signed_k={distal_fit["signed_curvature"]:.4f})'
            ),
        )

    tip_point = np.array([1.0, 0.0], dtype=float)
    tip_radius = tip_info["radius"]
    tip_circle = plt.Circle(
        (tip_point[0], tip_point[1]),
        tip_radius,
        fill=False,
        linestyle="--",
        linewidth=1.8,
        color="crimson",
        alpha=0.90,
        label=f"Tip range (r={tip_radius:.2f})",
    )
    ax.add_patch(tip_circle)

    ax.plot(tip_point[0], tip_point[1], marker="*", color="crimson", markersize=12, label="Tip point")

    if tip_info["fit_x"] is not None and tip_info["fit_y"] is not None:
        ax.plot(
            tip_info["fit_x"],
            tip_info["fit_y"],
            color="crimson",
            linewidth=2.0,
            linestyle="-",
            alpha=0.90,
            label="Tip local fit",
        )

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Spanwise (x)")
    ax.set_ylabel("Chordwise (y)")

    extra_handles = []
    extra_labels = []

    if np.isfinite(tip_info["curvature"]):
        extra_handles.append(plt.Line2D([], [], linestyle="None"))
        extra_labels.append(f'Tip curvature = {tip_info["curvature"]:.4f}')

    if distal_fit is not None and np.isfinite(distal_fit["bending"]):
        extra_handles.append(plt.Line2D([], [], linestyle="None"))
        extra_labels.append(f'Distal bending = {distal_fit["bending"]:.4f}')

    if distal_fit is not None and np.isfinite(distal_fit["signed_curvature"]):
        extra_handles.append(plt.Line2D([], [], linestyle="None"))
        extra_labels.append(f'Distal signed curvature = {distal_fit["signed_curvature"]:.4f}')

    if np.isfinite(plot_data["wing_area_bbox_ratio"]):
        extra_handles.append(plt.Line2D([], [], linestyle="None"))
        extra_labels.append(f'Wing area / bbox area = {plot_data["wing_area_bbox_ratio"]:.4f}')

    if np.isfinite(plot_data["tip_area_wing_ratio"]):
        extra_handles.append(plt.Line2D([], [], linestyle="None"))
        extra_labels.append(f'Tip area (r=0.10) / wing area = {plot_data["tip_area_wing_ratio"]:.4f}')

    handles, labels = ax.get_legend_handles_labels()
    handles.extend(extra_handles)
    labels.extend(extra_labels)
    ax.legend(
        handles,
        labels,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        borderaxespad=0.0,
        frameon=True,
    )

    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"EdgeFit_{name}.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_wing_schematic(plot_data, output_dir, name):
    """Draw a clean root-tip schematic from the same normalized wing contour."""
    contour = np.asarray(plot_data["contour_smoothed"], dtype=float).reshape(-1, 2)
    contour = contour[np.all(np.isfinite(contour), axis=1)]
    if len(contour) < 2:
        raise RuntimeError("Not enough finite contour points for the wing schematic")

    root = np.array([0.0, 0.0], dtype=float)
    tip = np.array([1.0, 0.0], dtype=float)

    x_min = min(float(np.min(contour[:, 0])), root[0])
    x_max = max(float(np.max(contour[:, 0])), tip[0])
    y_min = min(float(np.min(contour[:, 1])), root[1])
    y_max = max(float(np.max(contour[:, 1])), root[1])

    x_span = max(x_max - x_min, 1.0)
    y_span = max(y_max - y_min, 0.5)

    x_left = x_min - 0.08 * x_span
    x_arrow_end = x_max + 0.20 * x_span
    x_label_x = x_arrow_end + 0.035 * x_span
    y_arrow_end = y_max + 0.15 * y_span
    y_label_y = y_arrow_end + 0.035 * y_span
    root_tip_label_y = y_min - 0.12 * y_span
    coordinate_label_y = y_min - 0.27 * y_span

    fig, ax = plt.subplots(figsize=(8.0, 4.8))

    arrow_style = dict(
        arrowstyle="-|>",
        color="black",
        linewidth=1.7,
        mutation_scale=17,
        shrinkA=0,
        shrinkB=0,
    )
    ax.annotate(
        "",
        xy=(x_arrow_end, 0.0),
        xytext=(root[0], root[1]),
        arrowprops=arrow_style,
        zorder=1,
    )
    ax.annotate(
        "",
        xy=(0.0, y_arrow_end),
        xytext=(root[0], root[1]),
        arrowprops=arrow_style,
        zorder=1,
    )

    ax.plot(
        contour[:, 0],
        contour[:, 1],
        color="black",
        linewidth=2.6,
        solid_capstyle="round",
        solid_joinstyle="round",
        zorder=3,
    )
    ax.plot(
        [root[0], tip[0]],
        [root[1], tip[1]],
        linestyle="None",
        marker="o",
        color="black",
        markersize=6.5,
        zorder=4,
    )

    text_style = dict(color="black", fontfamily="serif")
    ax.text(x_label_x, 0.0, "X", fontsize=19, ha="left", va="center", **text_style)
    ax.text(0.0, y_label_y, "Y", fontsize=19, ha="center", va="bottom", **text_style)
    ax.text(root[0], root_tip_label_y, "Root", fontsize=17, ha="center", va="top", **text_style)
    ax.text(tip[0], root_tip_label_y, "Tip", fontsize=17, ha="center", va="top", **text_style)
    ax.text(root[0], coordinate_label_y, "(0,0)", fontsize=16, ha="center", va="top", **text_style)
    ax.text(tip[0], coordinate_label_y, "(1,0)", fontsize=16, ha="center", va="top", **text_style)

    ax.set_xlim(x_left, x_label_x + 0.09 * x_span)
    ax.set_ylim(coordinate_label_y - 0.10 * y_span, y_label_y + 0.10 * y_span)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"WingSchematic_{name}.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path


def main():
    plot_data = compute_plot_data(IMAGE_PATH)
    edge_fit_path = plot_edge_fit_clean(plot_data, OUTPUT_DIR, IMAGE_PATH.stem)
    schematic_path = plot_wing_schematic(plot_data, OUTPUT_DIR, IMAGE_PATH.stem)
    print(f"Saved: {edge_fit_path}")
    print(f"Saved: {schematic_path}")


if __name__ == "__main__":
    main()
