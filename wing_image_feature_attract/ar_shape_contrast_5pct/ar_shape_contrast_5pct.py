"""Find butterfly wings with similar aspect ratio but different outlines.

The measurement path intentionally mirrors ``tip_setting_feasibility_check.py``
and the main wing-analysis workflow:

1. detect the red wing-root marker;
2. extract the ordered wing outline with ``image_tool.extract_edge_profile``;
3. use the blue manual tip when available, otherwise use
   ``shape_tool.tip_locate`` with the current parameters;
4. rotate the root--tip span onto the x axis and normalize the span to 1;
5. calculate the unsmoothed normalized planform area and AR = 1 / area.

All AR pairs within the requested symmetric relative-difference threshold are
retained.  A small, non-repeating subset is selected for figures by looking for
very close AR values and low outline intersection-over-union (IoU).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import image_tool  # noqa: E402
import shape_tool  # noqa: E402


SUPPORTED_EXTENSIONS = {".png"}
DEFAULT_THRESHOLD_PERCENT = 5.0
DEFAULT_PRIORITY_THRESHOLD_PERCENT = 1.0
DEFAULT_REPRESENTATIVE_COUNT = 12
DEFAULT_MASK_RESOLUTION = 512
DEFAULT_DPI = 600


@dataclass
class WingMeasurement:
    sample_index: int
    name: str
    family: str
    file_name: str
    relative_path: str
    status: str
    contour_points: int | None = None
    normalized_area: float | None = None
    ar: float | None = None
    span_px: float | None = None
    tip_source: str = ""
    root_x_px: float | None = None
    root_y_px: float | None = None
    tip_x_px: float | None = None
    tip_y_px: float | None = None
    min_x_norm: float | None = None
    max_x_norm: float | None = None
    min_y_norm: float | None = None
    max_y_norm: float | None = None
    note: str = ""


@dataclass
class ARPair:
    pair_id: int
    wing_a_index: int
    wing_b_index: int
    wing_a: str
    family_a: str
    wing_b: str
    family_b: str
    ar_a: float
    ar_b: float
    absolute_difference: float
    relative_difference: float
    shape_iou: float
    shape_difference: float
    cross_family: bool
    representative_rank: int | None = None
    image_file: str = ""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate butterfly-wing AR with the current root/tip workflow, "
            "retain all pairs within a threshold, and draw dissimilar outlines."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=PROJECT_DIR / "wing_import",
        help="Input directory containing processed wing PNG images.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. If omitted, a timestamped folder is created under "
            "./outputs."
        ),
    )
    parser.add_argument(
        "--threshold-percent",
        type=float,
        default=DEFAULT_THRESHOLD_PERCENT,
        help="Maximum symmetric relative AR difference in percent (default: 5).",
    )
    parser.add_argument(
        "--priority-threshold-percent",
        type=float,
        default=DEFAULT_PRIORITY_THRESHOLD_PERCENT,
        help=(
            "Prefer representative figures from this stricter AR threshold "
            "(default: 1)."
        ),
    )
    parser.add_argument(
        "--representative-count",
        type=int,
        default=DEFAULT_REPRESENTATIVE_COUNT,
        help="Number of one-to-one representative outline figures (default: 12).",
    )
    parser.add_argument(
        "--mask-resolution",
        type=int,
        default=DEFAULT_MASK_RESOLUTION,
        help="Raster resolution used only for outline IoU ranking (default: 512).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help="DPI for individual pair figures (default: 600).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search the input directory recursively.",
    )
    parser.add_argument(
        "--node-exe",
        type=Path,
        default=None,
        help=(
            "Optional Node.js executable. If supplied, the Excel workbook is "
            "built automatically with artifact-tool."
        ),
    )
    parser.add_argument(
        "--skip-workbook",
        action="store_true",
        help="Do not invoke the companion Excel workbook builder.",
    )
    parser.add_argument(
        "--preview-dir",
        type=Path,
        default=None,
        help="Optional directory for workbook-render verification previews.",
    )
    args = parser.parse_args(argv)

    numeric_checks = [
        ("--threshold-percent", args.threshold_percent, 0.0, None),
        ("--priority-threshold-percent", args.priority_threshold_percent, 0.0, None),
    ]
    for label, value, minimum, maximum in numeric_checks:
        if not math.isfinite(value) or value < minimum or (
            maximum is not None and value > maximum
        ):
            parser.error(f"{label} must be finite and >= {minimum}")
    if args.representative_count < 1:
        parser.error("--representative-count must be >= 1")
    if args.mask_resolution < 128:
        parser.error("--mask-resolution must be >= 128")
    if args.dpi < 72:
        parser.error("--dpi must be >= 72")
    return args


def as_point(point: object) -> tuple[float, float] | None:
    if point is None:
        return None
    array = np.asarray(point, dtype=float).reshape(2)
    if not np.all(np.isfinite(array)):
        return None
    return float(array[0]), float(array[1])


def infer_family(name: str) -> str:
    """Return the family/subfamily label encoded at the start of each name."""
    known_labels = (
        "Pieridae-Coliadinae",
        "Biblidinae",
        "Charaxinae",
        "Danainae",
        "Heliconiinae",
        "Hesperiidae",
        "Limenitidinae",
        "Lycaenidae",
        "Nymphalinae",
        "Papilionidae",
        "Parnassiinae",
        "Pieridae",
        "Riodinidae",
        "Satyrinae",
    )
    for label in known_labels:
        if name.startswith(label):
            return label
    return name.split("_", 1)[0].split("-", 1)[0]


def algorithm_detected_tip(
    edge_points: Sequence[Sequence[float]],
    root: tuple[float, float],
) -> tuple[float, float] | None:
    """Use exactly the same tip parameters as the current analysis workflow."""
    with contextlib.redirect_stdout(io.StringIO()):
        tip = shape_tool.tip_locate(
            edge_points,
            root,
            bending_threshold=35,
            window_size=15,
        )
    return as_point(tip)


def find_images(input_dir: Path, recursive: bool) -> list[Path]:
    iterator: Iterable[Path] = input_dir.rglob("*") if recursive else input_dir.iterdir()
    return sorted(
        (
            path
            for path in iterator
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.relative_to(input_dir).as_posix().casefold(),
    )


def measure_image(
    image_path: Path,
    input_dir: Path,
    sample_index: int,
) -> tuple[WingMeasurement, np.ndarray | None]:
    name = image_path.stem
    record = WingMeasurement(
        sample_index=sample_index,
        name=name,
        family=infer_family(name),
        file_name=image_path.name,
        relative_path=image_path.relative_to(input_dir).as_posix(),
        status="failed",
    )

    try:
        image = image_tool.import_image(str(image_path))
        root = as_point(image_tool.detect_red_dot(image))
        if root is None:
            raise RuntimeError("No red root marker detected")

        edge_points, _ = image_tool.extract_edge_profile(image, red_dot_coords=root)
        if not edge_points:
            raise RuntimeError("No ordered contour points extracted")

        manual_tip = as_point(image_tool.detect_blue_circle(image))
        if manual_tip is not None:
            tip = manual_tip
            tip_source = "manual_blue_marker"
        else:
            tip = algorithm_detected_tip(edge_points, root)
            tip_source = "algorithm_tip_locate"

        if tip is None:
            raise RuntimeError("No wing tip available")

        contour = np.asarray(edge_points, dtype=np.float32).reshape(-1, 2)
        root_array = np.asarray(root, dtype=np.float32).reshape(2)
        tip_array = np.asarray(tip, dtype=np.float32).reshape(2)
        span_px = float(np.linalg.norm(tip_array - root_array))
        if not math.isfinite(span_px) or span_px <= 0:
            raise RuntimeError("Root-tip span is not positive")

        normalized = image_tool.transform_points_by_span(
            contour,
            root_array,
            tip_array,
            force_y_positive=True,
            normalize_span=True,
        )
        normalized = np.asarray(normalized, dtype=np.float32).reshape(-1, 2)
        if len(normalized) < 3 or not np.all(np.isfinite(normalized)):
            raise RuntimeError("Normalized contour is invalid")

        normalized_area = float(
            cv2.contourArea(normalized.reshape(-1, 1, 2))
        )
        if not math.isfinite(normalized_area) or normalized_area <= 0:
            raise RuntimeError("Normalized planform area is not positive")

        ar = 1.0 / normalized_area
        if not math.isfinite(ar) or ar <= 0:
            raise RuntimeError("Calculated aspect ratio is not positive")

        record.status = "ok"
        record.contour_points = int(len(normalized))
        record.normalized_area = normalized_area
        record.ar = float(ar)
        record.span_px = span_px
        record.tip_source = tip_source
        record.root_x_px = float(root[0])
        record.root_y_px = float(root[1])
        record.tip_x_px = float(tip[0])
        record.tip_y_px = float(tip[1])
        record.min_x_norm = float(np.min(normalized[:, 0]))
        record.max_x_norm = float(np.max(normalized[:, 0]))
        record.min_y_norm = float(np.min(normalized[:, 1]))
        record.max_y_norm = float(np.max(normalized[:, 1]))
        return record, normalized
    except Exception as exc:
        record.note = f"{type(exc).__name__}: {exc}"
        return record, None


def common_square_bounds(contours: Sequence[np.ndarray]) -> tuple[float, float, float, float]:
    all_min_x = min(float(np.min(contour[:, 0])) for contour in contours)
    all_max_x = max(float(np.max(contour[:, 0])) for contour in contours)
    all_min_y = min(float(np.min(contour[:, 1])) for contour in contours)
    all_max_y = max(float(np.max(contour[:, 1])) for contour in contours)
    width = max(all_max_x - all_min_x, 1e-9)
    height = max(all_max_y - all_min_y, 1e-9)
    side = max(width, height) * 1.04
    center_x = 0.5 * (all_min_x + all_max_x)
    center_y = 0.5 * (all_min_y + all_max_y)
    return (
        center_x - side / 2.0,
        center_x + side / 2.0,
        center_y - side / 2.0,
        center_y + side / 2.0,
    )


def contour_to_bitmask(
    contour: np.ndarray,
    bounds: tuple[float, float, float, float],
    resolution: int,
) -> tuple[int, int]:
    min_x, max_x, min_y, max_y = bounds
    points = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
    x = (points[:, 0] - min_x) / (max_x - min_x) * (resolution - 1)
    y = (max_y - points[:, 1]) / (max_y - min_y) * (resolution - 1)
    polygon = np.rint(np.column_stack([x, y])).astype(np.int32)
    polygon[:, 0] = np.clip(polygon[:, 0], 0, resolution - 1)
    polygon[:, 1] = np.clip(polygon[:, 1], 0, resolution - 1)

    mask = np.zeros((resolution, resolution), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon.reshape(-1, 1, 2)], color=1)
    packed = np.packbits(mask.reshape(-1), bitorder="little").tobytes()
    bitmask = int.from_bytes(packed, byteorder="little", signed=False)
    return bitmask, int(np.count_nonzero(mask))


def compare_all(
    measurements: Sequence[WingMeasurement],
    contours: Sequence[np.ndarray | None],
    threshold_fraction: float,
    mask_resolution: int,
) -> tuple[list[ARPair], tuple[float, float, float, float]]:
    valid_indices = [
        index
        for index, record in enumerate(measurements)
        if record.status == "ok" and record.ar is not None and contours[index] is not None
    ]
    valid_contours = [contours[index] for index in valid_indices]
    assert all(contour is not None for contour in valid_contours)
    typed_contours = [np.asarray(contour) for contour in valid_contours]
    bounds = common_square_bounds(typed_contours)

    masks: dict[int, tuple[int, int]] = {}
    for index in valid_indices:
        contour = contours[index]
        assert contour is not None
        masks[index] = contour_to_bitmask(contour, bounds, mask_resolution)

    pairs: list[ARPair] = []
    for left_position, index_a in enumerate(valid_indices):
        wing_a = measurements[index_a]
        assert wing_a.ar is not None
        for index_b in valid_indices[left_position + 1 :]:
            wing_b = measurements[index_b]
            assert wing_b.ar is not None
            absolute = abs(wing_a.ar - wing_b.ar)
            mean_ar = 0.5 * (wing_a.ar + wing_b.ar)
            relative = absolute / mean_ar if mean_ar > 0 else math.inf
            if relative > threshold_fraction + 1e-12:
                continue

            mask_a, _ = masks[index_a]
            mask_b, _ = masks[index_b]
            intersection = (mask_a & mask_b).bit_count()
            union = (mask_a | mask_b).bit_count()
            shape_iou = intersection / union if union else math.nan
            shape_difference = 1.0 - shape_iou if math.isfinite(shape_iou) else math.nan
            pairs.append(
                ARPair(
                    pair_id=0,
                    wing_a_index=index_a,
                    wing_b_index=index_b,
                    wing_a=wing_a.name,
                    family_a=wing_a.family,
                    wing_b=wing_b.name,
                    family_b=wing_b.family,
                    ar_a=float(wing_a.ar),
                    ar_b=float(wing_b.ar),
                    absolute_difference=float(absolute),
                    relative_difference=float(relative),
                    shape_iou=float(shape_iou),
                    shape_difference=float(shape_difference),
                    cross_family=wing_a.family != wing_b.family,
                )
            )

    pairs.sort(
        key=lambda row: (
            row.relative_difference,
            -row.shape_difference,
            row.wing_a.casefold(),
            row.wing_b.casefold(),
        )
    )
    for pair_id, pair in enumerate(pairs, start=1):
        pair.pair_id = pair_id
    return pairs, bounds


def select_representative_pairs(
    pairs: Sequence[ARPair],
    count: int,
    priority_threshold_fraction: float,
) -> list[ARPair]:
    if not pairs:
        return []

    strict = [pair for pair in pairs if pair.relative_difference <= priority_threshold_fraction]
    candidate_groups = [strict, list(pairs)] if len(strict) < count else [strict]
    selected: list[ARPair] = []
    selected_ids: set[int] = set()
    used_wings: set[int] = set()
    family_pair_counts: dict[tuple[str, str], int] = {}

    def ranked(group: Sequence[ARPair], cross_family_only: bool) -> list[ARPair]:
        return sorted(
            (
                pair
                for pair in group
                if not cross_family_only or pair.cross_family
            ),
            key=lambda row: (
                -row.shape_difference,
                row.relative_difference,
                row.wing_a.casefold(),
                row.wing_b.casefold(),
            ),
        )

    def try_add(group: Sequence[ARPair], cross_family_only: bool, combo_cap: int) -> None:
        for pair in ranked(group, cross_family_only):
            if len(selected) >= count:
                return
            if pair.pair_id in selected_ids:
                continue
            if pair.wing_a_index in used_wings or pair.wing_b_index in used_wings:
                continue
            family_key = tuple(sorted((pair.family_a, pair.family_b)))
            if family_pair_counts.get(family_key, 0) >= combo_cap:
                continue
            selected.append(pair)
            selected_ids.add(pair.pair_id)
            used_wings.update((pair.wing_a_index, pair.wing_b_index))
            family_pair_counts[family_key] = family_pair_counts.get(family_key, 0) + 1

    for group in candidate_groups:
        for combo_cap in (1, 2, count):
            try_add(group, cross_family_only=True, combo_cap=combo_cap)
            if len(selected) >= count:
                break
        if len(selected) >= count:
            break

    if len(selected) < count:
        for group in candidate_groups:
            try_add(group, cross_family_only=False, combo_cap=count)
            if len(selected) >= count:
                break

    if len(selected) < count:
        # Final fallback allows repeated samples, but still avoids duplicate pairs.
        for pair in ranked(pairs, cross_family_only=False):
            if len(selected) >= count:
                break
            if pair.pair_id not in selected_ids:
                selected.append(pair)
                selected_ids.add(pair.pair_id)

    for rank, pair in enumerate(selected, start=1):
        pair.representative_rank = rank
        pair.image_file = f"pair_images/Pair_{rank:03d}.png"
    return selected


def draw_overlay(
    ax: plt.Axes,
    contour_a: np.ndarray,
    contour_b: np.ndarray,
) -> None:
    a = np.asarray(contour_a, dtype=float).reshape(-1, 2)
    b = np.asarray(contour_b, dtype=float).reshape(-1, 2)
    ax.fill(
        a[:, 0],
        a[:, 1],
        facecolor="black",
        edgecolor="black",
        linewidth=1.5,
        zorder=1,
    )
    ax.plot(
        np.r_[b[:, 0], b[0, 0]],
        np.r_[b[:, 1], b[0, 1]],
        color="#e00000",
        linewidth=2.35,
        solid_capstyle="round",
        solid_joinstyle="round",
        zorder=2,
    )

    both = np.vstack([a, b])
    min_x, min_y = np.min(both, axis=0)
    max_x, max_y = np.max(both, axis=0)
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    pad = 0.055 * max(width, height)
    ax.set_xlim(min_x - pad, max_x + pad)
    ax.set_ylim(min_y - pad, max_y + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")


def save_pair_figures(
    selected: Sequence[ARPair],
    contours: Sequence[np.ndarray | None],
    output_dir: Path,
    dpi: int,
) -> tuple[list[Path], Path | None]:
    image_dir = output_dir / "pair_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for pair in selected:
        contour_a = contours[pair.wing_a_index]
        contour_b = contours[pair.wing_b_index]
        assert contour_a is not None and contour_b is not None
        fig, ax = plt.subplots(figsize=(5.2, 4.2), facecolor="white")
        draw_overlay(ax, contour_a, contour_b)
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        output_path = output_dir / pair.image_file
        fig.savefig(
            output_path,
            dpi=dpi,
            facecolor="white",
            bbox_inches="tight",
            pad_inches=0.02,
        )
        plt.close(fig)
        saved.append(output_path)

    if not selected:
        return saved, None

    columns = 4
    rows = math.ceil(len(selected) / columns)
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(columns * 4.0, rows * 3.2),
        facecolor="white",
        squeeze=False,
    )
    for ax in axes.flat:
        ax.axis("off")
    for ax, pair in zip(axes.flat, selected):
        contour_a = contours[pair.wing_a_index]
        contour_b = contours[pair.wing_b_index]
        assert contour_a is not None and contour_b is not None
        draw_overlay(ax, contour_a, contour_b)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1, wspace=0.015, hspace=0.015)
    overview_path = output_dir / "representative_pairs_overview.png"
    fig.savefig(
        overview_path,
        dpi=min(360, dpi),
        facecolor="white",
        bbox_inches="tight",
        pad_inches=0.02,
    )
    plt.close(fig)
    return saved, overview_path


def write_payload(
    output_dir: Path,
    input_dir: Path,
    measurements: Sequence[WingMeasurement],
    pairs: Sequence[ARPair],
    selected: Sequence[ARPair],
    threshold_percent: float,
    priority_threshold_percent: float,
    mask_resolution: int,
    mask_bounds: tuple[float, float, float, float],
) -> Path:
    valid_count = sum(record.status == "ok" for record in measurements)
    payload = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input_directory": str(input_dir),
            "threshold_percent": float(threshold_percent),
            "threshold_fraction": float(threshold_percent / 100.0),
            "priority_threshold_percent": float(priority_threshold_percent),
            "priority_threshold_fraction": float(priority_threshold_percent / 100.0),
            "representative_count_requested": int(len(selected)),
            "mask_resolution": int(mask_resolution),
            "mask_bounds": [float(value) for value in mask_bounds],
            "ar_formula": "AR = span^2 / planform_area = 1 / normalized_planform_area",
            "relative_difference_formula": (
                "abs(AR_A - AR_B) / ((AR_A + AR_B) / 2)"
            ),
            "shape_iou_definition": (
                "intersection_area / union_area after root-tip alignment and "
                "unit-span normalization"
            ),
            "shape_difference_formula": "1 - shape_IoU",
            "images_found": int(len(measurements)),
            "valid_measurements": int(valid_count),
            "failed_measurements": int(len(measurements) - valid_count),
            "matching_pairs": int(len(pairs)),
            "representative_pairs": int(len(selected)),
        },
        "measurements": [asdict(record) for record in measurements],
        "matches": [asdict(pair) for pair in pairs],
        "representative_pair_ids": [int(pair.pair_id) for pair in selected],
    }
    json_path = output_dir / "ar_shape_contrast_results.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return json_path


def build_workbook(
    args: argparse.Namespace,
    json_path: Path,
    output_dir: Path,
) -> Path | None:
    if args.skip_workbook:
        return None

    node_exe: Path | None
    if args.node_exe is not None:
        node_exe = args.node_exe.expanduser().resolve()
    else:
        discovered = shutil.which("node")
        node_exe = Path(discovered).resolve() if discovered else None

    if node_exe is None or not node_exe.is_file():
        print(
            "Workbook not built: provide --node-exe or run the companion "
            "build_ar_shape_contrast_workbook.mjs manually."
        )
        return None

    builder = SCRIPT_DIR / "build_ar_shape_contrast_workbook.mjs"
    workbook_path = output_dir / "butterfly_AR_shape_contrast_5pct.xlsx"
    preview_dir = (
        args.preview_dir.expanduser().resolve()
        if args.preview_dir is not None
        else SCRIPT_DIR / ".verification" / output_dir.name
    )
    command = [
        str(node_exe),
        str(builder),
        str(json_path),
        str(workbook_path),
        str(preview_dir),
    ]
    try:
        subprocess.run(command, cwd=SCRIPT_DIR, check=True)
    except subprocess.CalledProcessError:
        # On some Windows artifact-tool builds, Node can return a non-zero
        # process status after the workbook and all render previews have already
        # been saved.  Treat that late exit as recoverable only when the final
        # workbook is present and non-empty; all earlier failures still raise.
        if not workbook_path.is_file() or workbook_path.stat().st_size == 0:
            raise
        print(
            "Workbook builder returned a late non-zero status, but the verified "
            f"workbook was saved successfully: {workbook_path}"
        )
    inspect_sidecar = Path(f"{workbook_path}.inspect.ndjson")
    if inspect_sidecar.is_file():
        inspect_sidecar.unlink()
    return workbook_path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_dir = args.input_dir.expanduser().resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    if args.output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = SCRIPT_DIR / "outputs" / timestamp
    else:
        output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths = find_images(input_dir, args.recursive)
    if not image_paths:
        raise FileNotFoundError(f"No PNG images found in: {input_dir}")

    measurements: list[WingMeasurement] = []
    contours: list[np.ndarray | None] = []
    total = len(image_paths)
    for sample_index, image_path in enumerate(image_paths, start=1):
        measurement, contour = measure_image(
            image_path=image_path,
            input_dir=input_dir,
            sample_index=sample_index,
        )
        measurements.append(measurement)
        contours.append(contour)
        state = "OK" if measurement.status == "ok" else "FAILED"
        print(f"[{sample_index:>3}/{total}] {state:<6} {image_path.name}")

    valid_count = sum(record.status == "ok" for record in measurements)
    if valid_count < 2:
        raise RuntimeError("Fewer than two valid wing measurements were produced")

    pairs, mask_bounds = compare_all(
        measurements=measurements,
        contours=contours,
        threshold_fraction=args.threshold_percent / 100.0,
        mask_resolution=args.mask_resolution,
    )
    selected = select_representative_pairs(
        pairs=pairs,
        count=args.representative_count,
        priority_threshold_fraction=min(
            args.priority_threshold_percent,
            args.threshold_percent,
        )
        / 100.0,
    )
    pair_paths, overview_path = save_pair_figures(
        selected=selected,
        contours=contours,
        output_dir=output_dir,
        dpi=args.dpi,
    )
    json_path = write_payload(
        output_dir=output_dir,
        input_dir=input_dir,
        measurements=measurements,
        pairs=pairs,
        selected=selected,
        threshold_percent=args.threshold_percent,
        priority_threshold_percent=min(
            args.priority_threshold_percent,
            args.threshold_percent,
        ),
        mask_resolution=args.mask_resolution,
        mask_bounds=mask_bounds,
    )
    workbook_path = build_workbook(args, json_path, output_dir)

    print("\nAnalysis complete")
    print(f"  Images found:          {len(measurements)}")
    print(f"  Valid AR measurements: {valid_count}")
    print(f"  Failed measurements:   {len(measurements) - valid_count}")
    print(f"  AR pairs within {args.threshold_percent:g}%: {len(pairs)}")
    print(f"  Representative pairs:  {len(selected)}")
    print(f"  Individual figures:    {len(pair_paths)}")
    if overview_path is not None:
        print(f"  Overview:              {overview_path}")
    print(f"  JSON:                  {json_path}")
    if workbook_path is not None:
        print(f"  Excel:                 {workbook_path}")
    print(f"  Output directory:      {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
