#!/usr/bin/env python3
"""Check an exported figure against common journal production specs.

Encodes typical requirements; every threshold is a default to confirm against
the target journal's live guidelines. Verdicts are pass / warn / fail / unknown.

Usage:
  figqa.py FIGURE [FIGURE ...] [--journal nature|science|cell|plos|generic]
                  [--json] [--min-dpi N] [--purpose photo|line-art|mixed]
                  [--target-width-mm N] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Pillow is required: {exc}")

JOURNALS = {
    "nature": {"min_dpi_photo": 300, "min_dpi_line": 600, "widths_mm": [89, 120, 183],
               "formats": [".tif", ".tiff", ".eps", ".pdf", ".png"],
               "max_single_column_mm": 90, "note": "confirm limits in the current author guidelines"},
    "science": {"min_dpi_photo": 300, "min_dpi_line": 600, "widths_mm": [55, 120, 183],
                "formats": [".tif", ".tiff", ".eps", ".pdf"],
                "max_single_column_mm": 57, "note": "confirm limits in the current author guidelines"},
    "cell": {"min_dpi_photo": 300, "min_dpi_line": 1000, "widths_mm": [85, 114, 174],
             "formats": [".tif", ".tiff", ".eps", ".pdf", ".ai"],
             "max_single_column_mm": 90, "note": "confirm limits in the current author guidelines"},
    "plos": {"min_dpi_photo": 300, "min_dpi_line": 600, "widths_mm": [83, 173],
             "formats": [".tif", ".tiff", ".eps", ".png"],
             "max_single_column_mm": 85, "note": "confirm limits in the current author guidelines"},
    "generic": {"min_dpi_photo": 300, "min_dpi_line": 600, "widths_mm": [85, 114, 174],
                "formats": [".tif", ".tiff", ".eps", ".pdf", ".png"],
                "max_single_column_mm": 90, "note": "generic defaults; confirm per journal"},
}

VECTOR_EXT = {".pdf", ".eps", ".ai", ".svg"}


def check(path: Path, journal: str, purpose: str, min_dpi: int,
          target_width_mm: float | None) -> dict:
    spec = JOURNALS[journal]
    ext = path.suffix.lower()
    checks: list[dict] = []

    def add(name, verdict, detail):
        checks.append({"check": name, "verdict": verdict, "detail": detail})

    result = {"file": str(path), "journal": journal, "purpose": purpose,
              "journal_spec": spec, "checks": checks, "bytes": path.stat().st_size}

    add("extension", "pass" if ext in spec["formats"] else "fail",
        f"{ext or '(none)'} (accepted: {', '.join(spec['formats'])})")

    if ext in VECTOR_EXT:
        result["kind"] = "vector"
        add("kind", "pass", "vector artwork: resolution limits do not apply; verify fonts are embedded")
        if path.stat().st_size > 20 * 1024 * 1024:
            add("size", "warn", f"{path.stat().st_size/1048576:.1f} MB is large for a vector figure")
        return result

    result["kind"] = "raster"
    with Image.open(path) as im:
        size = im.size
        mode = im.mode
        dpi = im.info.get("dpi")
        icc = len(im.info.get("icc_profile", b"") or b"")
        # Pillow returns IFDRational for DPI; it is not JSON serialisable
        dpi_json = None
        if isinstance(dpi, (tuple, list)):
            dpi_json = [float(v) for v in dpi]
        elif dpi is not None:
            dpi_json = float(dpi)
        result.update({"size": list(size), "mode": mode,
                       "dpi": dpi_json,
                       "icc_profile_bytes": icc})
        if mode in {"RGBA", "LA", "P"}:
            add("alpha", "warn", "alpha channel present: flatten for TIFF, or supply the layered file if asked")
        if mode == "1":
            add("mode", "pass", "1-bit line art")
        elif mode == "L":
            add("mode", "pass", "grayscale")
        elif mode == "CMYK":
            add("mode", "pass", "CMYK (print) — confirm the journal wants CMYK and supply a profile")
        elif mode in {"RGB", "RGBA"}:
            add("mode", "pass", "RGB (screen/online) — confirm whether print requires CMYK")
        else:
            add("mode", "warn", f"unusual colour mode {mode}")

        effective_dpi = None
        if dpi_json:
            effective_dpi = float(dpi_json[0]) if isinstance(dpi_json, list) else float(dpi_json)

        required = min_dpi or (spec["min_dpi_line"] if purpose == "line-art"
                               else spec["min_dpi_photo"])
        if effective_dpi is None:
            add("resolution", "unknown",
                f"no DPI recorded; required {required} dpi for {purpose}. "
                f"Pixel width {size[0]} px implies {required} dpi at "
                f"{round(size[0]/required*25.4,1)} mm — set the DPI explicitly on export.")
        else:
            verdict = "pass" if effective_dpi + 0.5 >= required else "fail"
            add("resolution", verdict, f"{effective_dpi:g} dpi recorded, {required} dpi required for {purpose}")

        printable_dpi = effective_dpi or required
        width_mm = round(size[0] / printable_dpi * 25.4, 1)
        height_mm = round(size[1] / printable_dpi * 25.4, 1)
        result["width_mm_at_effective_dpi"] = width_mm
        result["height_mm_at_effective_dpi"] = height_mm

        widths = spec["widths_mm"]
        if target_width_mm:
            delta = abs(width_mm - float(target_width_mm))
            add("width", "pass" if delta <= 2 else "warn",
                f"{width_mm} mm vs requested {target_width_mm} mm")
        else:
            closest = min(widths, key=lambda w: abs(w - width_mm))
            delta = abs(width_mm - closest)
            if delta <= 3:
                add("width", "pass", f"{width_mm} mm matches a standard column width ({closest} mm)")
            elif width_mm < widths[0] - 3:
                add("width", "warn", f"{width_mm} mm is narrower than the smallest standard column ({widths[0]} mm)")
            else:
                add("width", "warn",
                    f"{width_mm} mm is {delta:.1f} mm from the nearest standard width ({closest} mm)")

        # interpolation heuristic: interpolated upscales have unusually smooth
        # high-frequency content relative to their pixel count
        if size[0] * size[1] > 0:
            import numpy as np
            arr = np.asarray(im.convert("L")).astype("float32")
            if arr.shape[0] > 8 and arr.shape[1] > 8:
                hf = float(np.abs(np.diff(arr, axis=1)).mean())
                px_mp = size[0] * size[1] / 1e6
                if hf < 1.2 and px_mp > 1.0:
                    add("interpolation", "warn",
                        f"very low high-frequency energy ({hf:.2f}) for a {px_mp:.1f} MP image: "
                        "this may be upscaled artwork rather than native resolution")
                else:
                    add("interpolation", "pass", f"high-frequency energy {hf:.2f} is plausible for native artwork")

        if path.stat().st_size > 25 * 1024 * 1024:
            add("size", "warn", f"{path.stat().st_size/1048576:.1f} MB may exceed the upload limit; "
                                "consider LZW TIFF or JPEG quality 95")
        if icc == 0 and mode == "CMYK":
            add("colour_profile", "warn", "CMYK without an embedded ICC profile")
    return result


def format_text(results: list[dict], out_lines: list[str] | None = None) -> str:
    lines: list[str] = []
    for r in results:
        lines.append(f"# {r['file']}")
        lines.append(f"kind={r.get('kind')} size={r.get('size')} mode={r.get('mode')} "
                     f"dpi={r.get('dpi')} bytes={r.get('bytes')}")
        if r.get("width_mm_at_effective_dpi"):
            lines.append(f"physical size at effective dpi: "
                         f"{r['width_mm_at_effective_dpi']} x {r['height_mm_at_effective_dpi']} mm")
        lines.append(f"spec source: {r['journal']} ({r['journal_spec']['note']})")
        for c in r["checks"]:
            lines.append(f"  {c['verdict'].upper():7} {c['check']:16} {c['detail']}")
        lines.append("")
    lines.append("NOTE: thresholds are typical production defaults encoded in this script; "
                 "confirm every number against the target journal's current guidelines.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Journal figure production-spec checker.")
    ap.add_argument("figures", nargs="+")
    ap.add_argument("--journal", choices=sorted(JOURNALS), default="generic")
    ap.add_argument("--purpose", choices=["photo", "line-art", "mixed"], default="photo")
    ap.add_argument("--min-dpi", type=float, default=0.0)
    ap.add_argument("--target-width-mm", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    results = []
    for raw in args.figures:
        path = Path(raw)
        if not path.is_file():
            print(f"warning: not a file: {path}", file=sys.stderr)
            continue
        results.append(check(path, args.journal, args.purpose, args.min_dpi, args.target_width_mm))

    report = json.dumps(results, indent=2, ensure_ascii=False) if args.json else format_text(results)
    fails = sum(1 for r in results for c in r["checks"] if c["verdict"] == "fail")
    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(results)} figure(s), {fails} failing check(s))")
    else:
        print(report)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
