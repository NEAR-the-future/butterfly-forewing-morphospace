"""Compact integrity checks for an AR-shape-contrast output directory."""

from __future__ import annotations

import argparse
import csv
import json
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "summary_11.csv",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    payload = json.loads(
        (output_dir / "ar_shape_contrast_results.json").read_text(encoding="utf-8")
    )
    with args.summary_csv.resolve().open(encoding="utf-8", newline="") as handle:
        summary_areas = {
            row["Name"]: float(row["Area"])
            for row in csv.DictReader(handle)
        }

    measured_areas = {
        row["name"]: row["normalized_area"]
        for row in payload["measurements"]
        if row["status"] == "ok"
    }
    common_names = set(summary_areas) & set(measured_areas)
    max_area_delta = max(
        abs(summary_areas[name] - measured_areas[name])
        for name in common_names
    )

    matches = payload["matches"]
    representatives = [
        row for row in matches if row["representative_rank"] is not None
    ]
    representative_names = [
        name
        for row in representatives
        for name in (row["wing_a"], row["wing_b"])
    ]

    workbook_path = output_dir / "butterfly_AR_shape_contrast_5pct.xlsx"
    with zipfile.ZipFile(workbook_path) as archive:
        bad_member = archive.testzip()
        worksheet_count = sum(
            member.startswith("xl/worksheets/sheet") and member.endswith(".xml")
            for member in archive.namelist()
        )

    print(f"summary_common={len(common_names)}")
    print(f"max_area_delta={max_area_delta:.3e}")
    print(f"matches={len(matches)}")
    print(
        "max_pair_relative_difference="
        f"{max(row['relative_difference'] for row in matches):.12f}"
    )
    print(f"representatives={len(representatives)}")
    print(
        "max_representative_relative_difference="
        f"{max(row['relative_difference'] for row in representatives):.12f}"
    )
    print(f"representative_unique_wings={len(set(representative_names))}")
    print(
        "representative_cross_family="
        f"{sum(row['cross_family'] for row in representatives)}"
    )
    print(f"xlsx_bytes={workbook_path.stat().st_size}")
    print(f"xlsx_crc_error={bad_member}")
    print(f"worksheet_xml_count={worksheet_count}")
    print(
        "inspect_sidecar_exists="
        f"{Path(str(workbook_path) + '.inspect.ndjson').exists()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
