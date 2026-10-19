from __future__ import annotations

import contextlib
import csv
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

import image_tool
import shape_tool
from wing_image_analysis import (
    extract_distal_segment,
    fit_edge_curve,
    smooth_contour,
    split_le_te_by_root_tip,
)


BASE_DIR = Path(__file__).resolve().parent
IMPORT_DIR = BASE_DIR / "wing_import"
IMPORT_FALLBACK_DIR = BASE_DIR / "wing_import-ALL"
OUTPUT_DIR = BASE_DIR / "tip_setting_feasibility_check"

TARGET_NAMES = [
    "Danainae-2",
    "Lycaenidae_Theclinesthes_serpentata",
    "Lycaenidae_Ogyris_subteristris",
    "Nymphalinae-10"
]

FONT_FAMILY = "Times New Roman"
DPI = 600
FIG_WIDTH_IN = 12.0


TIP_RANGE_RADIUS_NORM = 0.05

TIP_RANGE_COLOR = "#1565ff"

TIP_RANGE_DASH_STYLE = (0, (4, 2, 8, 2, 4, 2))
FINAL_TIP_COLOR = "#1565ff"
DISTAL_TURN_COLOR = "#ff2ec4"


def configure_matplotlib():
    plt.rcParams.update(
        {
            "font.family": FONT_FAMILY,
            "font.size": 18,
            "axes.titlesize": 24,
            "axes.titleweight": "bold",
            "legend.fontsize": 16,
            "savefig.dpi": DPI,
        }
    )


def as_point(point):
    if point is None:
        return None
    p = np.asarray(point, dtype=float).reshape(2,)
    if not np.all(np.isfinite(p)):
        return None
    return float(p[0]), float(p[1])


def farthest_point_from_root(edge_points, root):
    pts = np.asarray(edge_points, dtype=float).reshape(-1, 2)
    root_arr = np.asarray(root, dtype=float).reshape(2,)
    idx = int(np.argmax(np.linalg.norm(pts - root_arr, axis=1)))
    return float(pts[idx, 0]), float(pts[idx, 1])


def algorithm_detected_tip(edge_points, root):
    with contextlib.redirect_stdout(io.StringIO()):
        tip = shape_tool.tip_locate(
            edge_points,
            root,
            bending_threshold=35,
            window_size=15,
        )
    return as_point(tip)


def normalise_with_span(edge_points, root, tip):

    contour_px = np.asarray(edge_points, dtype=float).reshape(-1, 2)
    root = np.asarray(root, dtype=float).reshape(2,)
    tip = np.asarray(tip, dtype=float).reshape(2,)

    contour_norm = image_tool.transform_points_by_span(contour_px, root, tip)

    span_vec = tip - root
    span_px = float(np.hypot(span_vec[0], span_vec[1]))
    angle = float(np.arctan2(span_vec[1], span_vec[0]))
    cos_a = float(np.cos(angle))
    sin_a = float(np.sin(angle))
    y_flip = bool(np.mean(contour_norm[:, 1]) < 0.0)

    def to_pixel(points):
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        rotated_x = pts[:, 0] * span_px
        rotated_y = pts[:, 1] * span_px
        if y_flip:
            rotated_y = -rotated_y
        x = rotated_x * cos_a - rotated_y * sin_a + root[0]
        y = rotated_x * sin_a + rotated_y * cos_a + root[1]
        return np.column_stack([x, y])

    return contour_norm, to_pixel, span_px


def analyse_distal_region(edge_points, root, tip):

    root = np.asarray(root, dtype=float).reshape(2,)
    tip = np.asarray(tip, dtype=float).reshape(2,)

    contour_norm, to_pixel, span_px = normalise_with_span(edge_points, root, tip)

    contour_smooth, _ = smooth_contour(contour_norm)
    _, te_pts = split_le_te_by_root_tip(
        contour_smooth,
        root_point=(0.0, 0.0),
        tip_point=(1.0, 0.0),
    )

    te_fit = fit_edge_curve(te_pts, poly_deg=3, n_samples=400, fit_x_range=(0.1, 0.9))
    te_max_curv_x = float(te_fit["max_curv_x"])

    distal_feat = extract_distal_segment(
        te_pts,
        tip_point=(1.0, 0.0),
        ref_x=te_max_curv_x,
        trim_frac=(0.10, 0.95),
    )

    result = {
        "span_px": span_px,
        "te_max_curv_x": te_max_curv_x,
        "turn_point_norm": None,
        "turn_point_px": None,
    }

    turn_point = distal_feat.get("turn_point")
    if turn_point is not None:
        turn_point = np.asarray(turn_point, dtype=float).reshape(2,)
        if np.all(np.isfinite(turn_point)):
            result["turn_point_norm"] = (float(turn_point[0]), float(turn_point[1]))
            px = to_pixel(turn_point)[0]
            result["turn_point_px"] = (float(px[0]), float(px[1]))

    return result


def resolve_image_path(name):
    for directory in (IMPORT_DIR, IMPORT_FALLBACK_DIR):
        candidate = directory / f"{name}.png"
        if candidate.exists():
            return candidate
    return None


def extract_tip_check_data(image_path):
    original = image_tool.import_image(str(image_path))

    root = as_point(image_tool.detect_red_dot(original))
    if root is None:
        raise RuntimeError(f"No red root marker detected: {image_path.name}")

    edge_points, _ = image_tool.extract_edge_profile(original, red_dot_coords=root)
    if not edge_points:
        raise RuntimeError(f"No contour points extracted: {image_path.name}")

    manual_tip = as_point(image_tool.detect_blue_circle(original))
    longest_tip = farthest_point_from_root(edge_points, root)
    detected_tip = algorithm_detected_tip(edge_points, root)
    current_tip = manual_tip if manual_tip is not None else detected_tip

    if current_tip is None:
        raise RuntimeError(f"No current tip available: {image_path.name}")

    distal = analyse_distal_region(edge_points, root, current_tip)

    return {
        "image": original,
        "edge_points": edge_points,
        "root": root,
        "manual_tip": manual_tip,
        "longest_tip": longest_tip,
        "detected_tip": detected_tip,
        "current_tip": current_tip,
        "distal": distal,
    }


def figure_size_for_image(image):
    height, width = image.shape[:2]
    return FIG_WIDTH_IN, FIG_WIDTH_IN * height / width


def plot_tip_check(data, name, output_dir):
    image = data["image"]
    edge_points = data["edge_points"]
    root = data["root"]
    current_tip = data["current_tip"]
    longest_tip = data["longest_tip"]

    fig, ax = plt.subplots(figsize=figure_size_for_image(image))
    ax.imshow(image)

    pts = np.asarray(edge_points, dtype=float).reshape(-1, 2)
    ax.scatter(
        pts[:, 0],
        pts[:, 1],
        s=7,
        c="red",
        edgecolors="none",
        alpha=0.75,
        zorder=3,
    )

    ax.plot(
        [root[0], current_tip[0]],
        [root[1], current_tip[1]],
        color="#c8c800",
        linewidth=3.2,
        solid_capstyle="round",
        zorder=4,
    )

    ax.scatter(
        [longest_tip[0]],
        [longest_tip[1]],
        s=110,
        facecolors="none",
        edgecolors="#17a34a",
        linewidths=2.4,
        zorder=6,
    )

    tip_range_radius_px = TIP_RANGE_RADIUS_NORM * data["distal"]["span_px"]
    ax.add_patch(
        plt.Circle(
            (current_tip[0], current_tip[1]),
            tip_range_radius_px,
            fill=False,
            linestyle=TIP_RANGE_DASH_STYLE,
            linewidth=2.4,
            color=TIP_RANGE_COLOR,
            alpha=0.95,
            zorder=5,
        )
    )

    turn_point_px = data["distal"]["turn_point_px"]
    if turn_point_px is not None:
        ax.scatter(
            [turn_point_px[0]],
            [turn_point_px[1]],
            marker="D",
            s=170,
            c=DISTAL_TURN_COLOR,
            edgecolors="none",
            linewidths=0.0,
            zorder=10,
        )

    ax.plot(
        root[0],
        root[1],
        marker="+",
        color="black",
        markersize=16,
        markeredgewidth=2.0,
        linestyle="None",
        zorder=8,
    )


    ax.scatter(
        [current_tip[0]],
        [current_tip[1]],
        s=180,
        c=FINAL_TIP_COLOR,
        edgecolors="none",
        linewidths=0.0,
        zorder=9,
    )

    ax.set_title(name, pad=12)
    ax.axis("off")
    fig.tight_layout(pad=0.15)

    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"TipCheck_{name}.png"
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return output_path


def save_legend(output_dir):
    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor="red",
            markeredgecolor="red",
            markeredgewidth=0.0,
            markersize=7,
            alpha=0.75,
            label="Extracted contour pts",
        ),
        Line2D([0], [0], color="#c8c800", linewidth=3.2, label="Span line (root -> tip)"),
        Line2D(
            [0],
            [0],
            marker="+",
            color="black",
            linestyle="None",
            markersize=13,
            markeredgewidth=2.0,
            label="Root",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor=FINAL_TIP_COLOR,
            markeredgecolor=FINAL_TIP_COLOR,
            markeredgewidth=0.0,
            markersize=13.5,
            label="Final tip used in current workflow",
        ),
        Line2D(
            [0],
            [0],
            color=TIP_RANGE_COLOR,
            linestyle=TIP_RANGE_DASH_STYLE,
            linewidth=2.4,
            label=f"Tip range (r={TIP_RANGE_RADIUS_NORM:.2f} normalized)",
        ),
        Line2D(
            [0],
            [0],
            marker="D",
            linestyle="None",
            markerfacecolor=DISTAL_TURN_COLOR,
            markeredgecolor=DISTAL_TURN_COLOR,
            markeredgewidth=0.0,
            markersize=12,
            label="Distal turning point",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor="none",
            markeredgecolor="#17a34a",
            markeredgewidth=2.2,
            markersize=10,
            label="Longest point from root",
        ),
    ]

    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    ax.axis("off")
    ax.legend(
        handles=handles,
        loc="center",
        frameon=True,
        edgecolor="0.75",
        facecolor="white",
        framealpha=1.0,
        ncol=1,
        handlelength=2.2,
        borderpad=0.7,
        labelspacing=0.55,
    )

    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "TipCheck_legend.png"
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return output_path


def write_summary(rows, output_dir):
    summary_path = output_dir / "TipCheck_points_summary.csv"
    columns = [
        "name",
        "has_manual_blue_tip",
        "root_x",
        "root_y",
        "manual_tip_x",
        "manual_tip_y",
        "longest_tip_x",
        "longest_tip_y",
        "algorithm_tip_x",
        "algorithm_tip_y",
        "current_tip_x",
        "current_tip_y",
        "tip_range_radius_norm",
        "tip_range_radius_px",
        "te_max_curv_x_norm",
        "distal_turn_x",
        "distal_turn_y",
    ]

    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return summary_path


def point_columns(prefix, point):
    if point is None:
        return {f"{prefix}_x": "", f"{prefix}_y": ""}
    return {f"{prefix}_x": f"{point[0]:.6f}", f"{prefix}_y": f"{point[1]:.6f}"}


def main():
    configure_matplotlib()
    OUTPUT_DIR.mkdir(exist_ok=True)

    summary_rows = []
    saved_paths = []

    for name in TARGET_NAMES:
        image_path = resolve_image_path(name)
        if image_path is None:
            raise FileNotFoundError(
                f"Target image not found: tried {IMPORT_DIR} and {IMPORT_FALLBACK_DIR}"
            )

        data = extract_tip_check_data(image_path)
        saved_paths.append(plot_tip_check(data, name, OUTPUT_DIR))

        row = {
            "name": name,
            "has_manual_blue_tip": "YES" if data["manual_tip"] is not None else "NO",
        }
        row.update(point_columns("root", data["root"]))
        row.update(point_columns("manual_tip", data["manual_tip"]))
        row.update(point_columns("longest_tip", data["longest_tip"]))
        row.update(point_columns("algorithm_tip", data["detected_tip"]))
        row.update(point_columns("current_tip", data["current_tip"]))

        distal = data["distal"]
        row["tip_range_radius_norm"] = f"{TIP_RANGE_RADIUS_NORM:.6f}"
        row["tip_range_radius_px"] = f"{TIP_RANGE_RADIUS_NORM * distal['span_px']:.6f}"
        row["te_max_curv_x_norm"] = f"{distal['te_max_curv_x']:.6f}"
        turn_point_px = distal["turn_point_px"]
        row["distal_turn_x"] = "" if turn_point_px is None else f"{turn_point_px[0]:.6f}"
        row["distal_turn_y"] = "" if turn_point_px is None else f"{turn_point_px[1]:.6f}"

        summary_rows.append(row)

    legend_path = save_legend(OUTPUT_DIR)
    summary_path = write_summary(summary_rows, OUTPUT_DIR)

    print("Saved tip feasibility check figures:")
    for path in saved_paths:
        print(f"  {path}")
    print(f"Saved legend: {legend_path}")
    print(f"Saved point summary: {summary_path}")


if __name__ == "__main__":
    main()
