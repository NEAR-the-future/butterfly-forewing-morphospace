"""Render representative AR pairs as separate, unnormalized black silhouettes.

The AR values and pair selection come from ``ar_shape_contrast_results.json``.
Only the figure presentation changes: each specimen is re-extracted in its
original image coordinates and placed in an independent left/right panel.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import image_tool  # noqa: E402


FONT_FAMILY = "Times New Roman"
TITLE_FONT_SIZE = 28
FIGURE_DPI = 600


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render the selected AR pairs as left/right original-coordinate "
            "black wing silhouettes."
        )
    )
    parser.add_argument("results_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=PROJECT_DIR / "wing_import",
    )
    parser.add_argument(
        "--node-exe",
        type=Path,
        default=None,
        help="Optional Node.js executable for automatic Excel creation.",
    )
    parser.add_argument(
        "--preview-dir",
        type=Path,
        default=None,
        help="Optional workbook-render verification directory.",
    )
    parser.add_argument("--dpi", type=int, default=FIGURE_DPI)
    args = parser.parse_args(argv)
    if args.dpi < 72:
        parser.error("--dpi must be >= 72")
    return args


def configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "font.family": FONT_FAMILY,
            "font.weight": "bold",
            "axes.titleweight": "bold",
            "axes.titlesize": TITLE_FONT_SIZE,
            "savefig.dpi": FIGURE_DPI,
        }
    )


def extract_original_contour(image_path: Path) -> np.ndarray:
    image = image_tool.import_image(str(image_path))
    root = image_tool.detect_red_dot(image)
    edge_points, _ = image_tool.extract_edge_profile(image, red_dot_coords=root)
    if not edge_points:
        raise RuntimeError(f"No contour extracted: {image_path.name}")
    contour = np.asarray(edge_points, dtype=float).reshape(-1, 2)
    if len(contour) < 3 or not np.all(np.isfinite(contour)):
        raise RuntimeError(f"Invalid contour: {image_path.name}")
    return contour


def draw_black_silhouette(
    ax: plt.Axes,
    contour: np.ndarray,
    panel_label: str,
    name: str,
) -> None:
    points = np.asarray(contour, dtype=float).reshape(-1, 2)
    ax.fill(
        points[:, 0],
        points[:, 1],
        facecolor="black",
        edgecolor="black",
        linewidth=1.2,
        antialiased=True,
    )

    min_x, min_y = np.min(points, axis=0)
    max_x, max_y = np.max(points, axis=0)
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    pad = 0.065 * max(width, height)
    ax.set_xlim(min_x - pad, max_x + pad)
    # Image-coordinate presentation: y increases downward, as in the source.
    ax.set_ylim(max_y + pad, min_y - pad)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    title, title_size = format_panel_title(panel_label, name)
    ax.set_title(
        title,
        fontfamily=FONT_FAMILY,
        fontsize=title_size,
        fontweight="bold",
        color="black",
        pad=16,
        linespacing=0.92,
    )


def format_panel_title(panel_label: str, name: str) -> tuple[str, int]:
    """Keep titles large while wrapping long specimen names cleanly."""
    if len(name) <= 18:
        return f"({panel_label}) {name}", 28
    if len(name) <= 22:
        return f"({panel_label}) {name}", 24

    candidate_indices = [
        index
        for index, character in enumerate(name)
        if character in {"_", "-"} and 4 <= index <= len(name) - 5
    ]
    if candidate_indices:
        midpoint = len(name) / 2.0
        split_index = min(candidate_indices, key=lambda index: abs(index - midpoint))
        first_line = name[: split_index + 1]
        second_line = name[split_index + 1 :]
    else:
        split_index = len(name) // 2
        first_line = name[:split_index]
        second_line = name[split_index:]
    return f"({panel_label}) {first_line}\n{second_line}", 22


def render_pair(
    contour_a: np.ndarray,
    contour_b: np.ndarray,
    name_a: str,
    name_b: str,
    output_path: Path,
    dpi: int,
) -> None:
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(18.0, 7.4),
        facecolor="white",
    )
    draw_black_silhouette(axes[0], contour_a, "a", name_a)
    draw_black_silhouette(axes[1], contour_b, "b", name_b)
    fig.subplots_adjust(
        left=0.015,
        right=0.985,
        bottom=0.04,
        top=0.80,
        wspace=0.065,
    )
    fig.savefig(
        output_path,
        dpi=dpi,
        facecolor="white",
    )
    plt.close(fig)


def build_excel_rows(
    representatives: list[dict],
    measurement_by_name: dict[str, dict],
) -> list[dict]:
    rows: list[dict] = []
    for pair in representatives:
        rank = int(pair["representative_rank"])
        for panel, name in (("a", pair["wing_a"]), ("b", pair["wing_b"])):
            measurement = measurement_by_name[name]
            rows.append(
                {
                    "figure": f"Pair_{rank:03d}.png",
                    "panel": f"({panel})",
                    "name": name,
                    "normalized_area": float(measurement["normalized_area"]),
                }
            )
    return rows


def run_workbook_builder(
    node_exe: Path,
    data_json: Path,
    workbook_path: Path,
    preview_dir: Path,
) -> None:
    builder = SCRIPT_DIR / "build_representative_ar_workbook.mjs"
    command = [
        str(node_exe.resolve()),
        str(builder),
        str(data_json),
        str(workbook_path),
        str(preview_dir),
    ]
    try:
        subprocess.run(command, cwd=SCRIPT_DIR, check=True)
    except subprocess.CalledProcessError:
        if not workbook_path.is_file() or workbook_path.stat().st_size == 0:
            raise
        print(
            "Workbook builder returned a late non-zero status, but the workbook "
            f"was saved: {workbook_path}"
        )
    sidecar = Path(f"{workbook_path}.inspect.ndjson")
    if sidecar.is_file():
        sidecar.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_matplotlib()

    results_path = args.results_json.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    input_dir = args.input_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pair_image_dir = output_dir / "pair_images"
    pair_image_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    measurement_by_name = {
        row["name"]: row
        for row in payload["measurements"]
        if row["status"] == "ok"
    }
    representatives = sorted(
        (
            row
            for row in payload["matches"]
            if row["representative_rank"] is not None
        ),
        key=lambda row: int(row["representative_rank"]),
    )
    if not representatives:
        raise RuntimeError("No representative pairs found in the results JSON")

    contour_cache: dict[str, np.ndarray] = {}
    for pair in representatives:
        rank = int(pair["representative_rank"])
        names = (pair["wing_a"], pair["wing_b"])
        contours: list[np.ndarray] = []
        for name in names:
            if name not in contour_cache:
                measurement = measurement_by_name[name]
                relative_path = Path(measurement["relative_path"])
                image_path = input_dir / relative_path
                contour_cache[name] = extract_original_contour(image_path)
            contours.append(contour_cache[name])

        output_path = pair_image_dir / f"Pair_{rank:03d}.png"
        render_pair(
            contour_a=contours[0],
            contour_b=contours[1],
            name_a=names[0],
            name_b=names[1],
            output_path=output_path,
            dpi=args.dpi,
        )
        print(f"Saved {output_path}")

    workbook_rows = build_excel_rows(representatives, measurement_by_name)
    workbook_data = {
        "metadata": {
            "source_results_json": str(results_path),
            "ar_formula": "AR = 1 / normalized_planform_area",
            "pair_count": len(representatives),
            "sample_count": len(workbook_rows),
        },
        "rows": workbook_rows,
    }
    data_json = output_dir / "representative_normalized_ar.json"
    data_json.write_text(
        json.dumps(workbook_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    workbook_path = output_dir / "representative_pairs_normalized_AR.xlsx"
    if args.node_exe is not None:
        preview_dir = (
            args.preview_dir.expanduser().resolve()
            if args.preview_dir is not None
            else SCRIPT_DIR / ".verification" / output_dir.name
        )
        run_workbook_builder(
            node_exe=args.node_exe.expanduser(),
            data_json=data_json,
            workbook_path=workbook_path,
            preview_dir=preview_dir,
        )

    print(f"Side-by-side pair figures: {len(representatives)}")
    print(f"AR rows: {len(workbook_rows)}")
    if workbook_path.is_file():
        print(f"Workbook: {workbook_path}")
    print(f"Output directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
