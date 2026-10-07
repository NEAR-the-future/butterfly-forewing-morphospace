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


BASE_DIR = Path(__file__).resolve().parent
IMPORT_DIR = BASE_DIR / "wing_import"
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

    return {
        "image": original,
        "edge_points": edge_points,
        "root": root,
        "manual_tip": manual_tip,
        "longest_tip": longest_tip,
        "detected_tip": detected_tip,
        "current_tip": current_tip,
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
    detected_tip = data["detected_tip"]

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

    if detected_tip is not None:
        ax.scatter(
            [detected_tip[0]],
            [detected_tip[1]],
            s=160,
            c="#1565ff",
            edgecolors="none",
            linewidths=0.0,
            zorder=7,
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
    ax.plot(
        current_tip[0],
        current_tip[1],
        marker="x",
        color="black",
        markersize=15,
        markeredgewidth=2.2,
        linestyle="None",
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
            marker="x",
            color="black",
            linestyle="None",
            markersize=12,
            markeredgewidth=2.2,
            label="Tip used in current workflow",
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
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor="#1565ff",
            markeredgecolor="#1565ff",
            markeredgewidth=0.0,
            markersize=13.5,
            label="Algorithm-detected point",
        ),
    ]

    fig, ax = plt.subplots(figsize=(6.6, 2.6))
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
        image_path = IMPORT_DIR / f"{name}.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Target image not found: {image_path}")

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
