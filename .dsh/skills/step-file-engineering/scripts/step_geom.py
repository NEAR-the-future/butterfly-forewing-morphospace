#!/usr/bin/env python3
"""Geometric facts derivable from a STEP file without a CAD kernel.

Tier 2 of the step-file-engineering skill. Everything here is computed from the
CONTROL POINTS stored in the file. For polyhedral models the global bounding box
is exact; for models with splines, cylinders or tori it is the box of the control
net, which CONTAINS the true surface but is not equal to it. Volume, surface area,
mass properties and tessellation require a real kernel and are refused here.

Usage:
  step_geom.py bounds  FILE [--mode all|vertices] [--json] [--out FILE]
  step_geom.py points  FILE [--limit N] [--out FILE.csv]
  step_geom.py project FILE [--view xy|xz|yz|iso] [--out FILE.svg] [--size PX]
  step_geom.py groups  FILE [--json]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step_tool import StepFile, decode_step_string  # noqa: E402

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

REFUSED = {"volume", "area", "surface", "mass", "stl", "mesh", "tessellate", "boolean",
           "fillet", "shell", "intersect", "union", "difference"}

UNIT_TO_MM = {"$": 1000.0, ".MILLI.": 1.0, ".CENTI.": 10.0, ".MICRO.": 0.001,
              ".DECI.": 100.0, ".KILO.": 1_000_000.0, ".NANO.": 1e-6}


def length_unit_factor(model: StepFile) -> tuple[float, str]:
    """Return (factor to millimetres, label). Defaults to a warning, not a guess."""
    for unit in model.units():
        if unit["kind"] == "length":
            if unit.get("to_metre"):
                return unit["to_metre"] * 1000.0, f"SI {unit['prefix']}metre"
            return 1.0, f"conversion-based ({unit['prefix']})"
    return float("nan"), "UNKNOWN —?no length unit in the file"


def cartesian_points(model: StepFile, mode: str = "vertices") -> list[tuple[float, float, float, int]]:
    """Collect control points.

    mode=all        every CARTESIAN_POINT in the file, including construction aids
                    and points left behind by a removal (widest, safest box)
    mode=vertices   only points referenced by a VERTEX_POINT (the shape's corners)
    mode=referenced only points reachable from a SHAPE_REPRESENTATION item
                    (strictly the retained geometry)
    """
    out: list[tuple[float, float, float, int]] = []
    if mode == "all":
        wanted_ids = None
    elif mode == "vertices":
        wanted_ids = set()
        for e in model.by_type("VERTEX_POINT"):
            wanted_ids |= set(model.refs_out(e.eid))
    else:
        wanted_ids = set()
        for e in model.entities.values():
            if "SHAPE_REPRESENTATION" not in e.type:
                continue
            for item in model.refs_out(e.eid):
                wanted_ids |= _reachable_points(model, item)
    for e in model.by_type("CARTESIAN_POINT"):
        if wanted_ids is not None and e.eid not in wanted_ids:
            continue
        coords = _coords(e)
        if coords:
            out.append((*coords, e.eid))
    return out


def _coords(entity) -> tuple[float, float, float] | None:
    for p in entity.params:
        m = re.match(r"^\(\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*\)$", p.strip())
        if m:
            try:
                return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
            except ValueError:
                return None
    return None


def bbox(points: list[tuple[float, float, float, int]]) -> dict | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return {
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
        "size": [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)],
        "center": [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2],
        "centroid_of_points": [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)],
        "count": len(points),
        "diagonal": math.dist((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))),
    }


def product_groups(model: StepFile) -> dict[int, list[int]]:
    """Map PRODUCT_DEFINITION id -> CARTESIAN_POINT entity ids reachable from its
    shape representation."""
    groups: dict[int, set[int]] = {}
    for pds in model.by_type("PRODUCT_DEFINITION_SHAPE"):
        refs = [int(p[1:]) for p in pds.params if p.startswith("#")]
        for pd in refs:
            if model.entities.get(pd) and model.entities[pd].type == "PRODUCT_DEFINITION":
                points = groups.setdefault(pd, set())
                for sdr in model.by_type("SHAPE_DEFINITION_REPRESENTATION"):
                    sdr_refs = [int(p[1:]) for p in sdr.params if p.startswith("#")]
                    if pds.eid not in sdr_refs:
                        continue
                    for rep_id in sdr_refs:
                        rep = model.entities.get(rep_id)
                        if rep is None or "SHAPE_REPRESENTATION" not in rep.type:
                            continue
                        for item_id in model.refs_out(rep_id):
                            points |= _reachable_points(model, item_id)
                groups[pd] = points
    return {k: sorted(v) for k, v in groups.items() if v}


def _reachable_points(model: StepFile, root: int, cap: int = 200_000,
                      truncated: list | None = None) -> set[int]:
    """Every CARTESIAN_POINT reachable from root through the entity graph."""
    seen: set[int] = set()
    points: set[int] = set()
    stack = [root]
    while stack:
        eid = stack.pop()
        if eid in seen:
            continue
        if len(seen) >= cap:
            if truncated is not None:
                truncated.append(root)
            break
        seen.add(eid)
        ent = model.entities.get(eid)
        if ent is None:
            continue
        if ent.type == "CARTESIAN_POINT":
            points.add(eid)
            continue
        stack.extend(model.refs_out(eid))
    return points


def has_transforms(model: StepFile) -> bool:
    for t in ("ITEM_DEFINED_TRANSFORMATION", "REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION",
              "CONTEXT_DEPENDENT_SHAPE_REPRESENTATION"):
        if model.by_type(t):
            return True
    return False


def project(points, view: str) -> list[tuple[float, float]]:
    if view == "xy":
        return [(p[0], p[1]) for p in points]
    if view == "xz":
        return [(p[0], p[2]) for p in points]
    if view == "yz":
        return [(p[1], p[2]) for p in points]
    # isometric: rotate 45 degrees about Z then tilt about X
    cx, sx = math.cos(math.radians(45)), math.sin(math.radians(45))
    cy = math.cos(math.radians(35.264))
    sy = math.sin(math.radians(35.264))
    out = []
    for p in points:
        x = p[0] * cx - p[1] * sx
        y = p[0] * sx + p[1] * cx
        out.append((x, y * cy - p[2] * sy))
    return out


def svg_projection(points, view: str, size: int, label: str) -> str:
    pts = project(points, view)
    if not pts:
        raise SystemExit("no points to project")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = max(1e-9, maxx - minx)
    h = max(1e-9, maxy - miny)
    margin = size * 0.06
    scale = min((size - 2 * margin) / w, (size - 2 * margin) / h)
    parts = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">',
        f'<rect width="{size}" height="{size}" fill="white"/>',
        f'<g stroke="#1f4e79" stroke-width="1.1" fill="none" opacity="0.9">',
    ]
    for (x, y) in pts:
        px = margin + (x - minx) * scale
        # SVG y grows downward, model y grows upward
        py = size - margin - (y - miny) * scale
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="1.1" fill="#1f4e79" stroke="none"/>')
    parts.append("</g>")
    parts.append(f'<text x="8" y="{size - 8}" font-family="Arial, sans-serif" font-size="11" '
                 f'fill="#333">{label} - {view.upper()} projection of {len(pts)} control points '
                 f'(bounds, not surfaces)</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def cmd_bounds(args) -> int:
    model = StepFile.load(Path(args.file))
    requested = args.mode
    points = cartesian_points(model, requested)
    fallback = None
    if not points and requested != "all":
        # a file that stores control points but has no VERTEX_POINT (or no shape
        # representation) would otherwise answer "no geometry" and hide a usable
        # bounding box. Fall back to every point, and say so rather than silently
        # changing the question that was asked.
        points = cartesian_points(model, "all")
        if points:
            fallback = (f"mode '{requested}' selected no points; reported mode 'all' instead "
                        f"({len(points)} point(s)). Re-run with --mode all to make this explicit.")
    factor, unit_label = length_unit_factor(model)
    box = bbox(points)
    if box is None:
        print(json.dumps({"error": "no CARTESIAN_POINT entities found",
                          "file": str(model.path)}, indent=2))
        return 2
    confidence = ("exact for polyhedral models" if not model.by_type("B_SPLINE_CURVE")
                  and not model.by_type("CYLINDRICAL_SURFACE")
                  and not model.by_type("TOROIDAL_SURFACE")
                  and not model.by_type("B_SPLINE_SURFACE")
                  else "bounds of the control net: contains the true surface, may exceed it")
    report = {
        "file": str(model.path),
        "mode": "all" if fallback else requested,
        "requested_mode": requested,
        "mode_fallback": fallback,
        "unit": {"native": unit_label, "to_mm": None if math.isnan(factor) else factor},
        "point_count": len(points),
        "bbox_native": box,
        "bbox_mm": None if math.isnan(factor) else {
            k: [round(v * factor, 4) for v in box[k]] if isinstance(box[k], list) else
               round(box[k] * factor, 4)
            for k in ("min", "max", "size", "center", "centroid_of_points", "diagonal")
        },
        "confidence": confidence,
        "has_assembly_transforms": has_transforms(model),
        "refused": sorted(REFUSED),
        "note": ("bounding boxes, centroids and extents only. Volume, surface area, mass "
                 "properties and tessellation require OpenCASCADE/cadquery or FreeCAD "
                 "(scripts/cad_bridge.py --probe)."),
    }
    if math.isnan(factor):
        report["warning"] = ("no length unit found in the file: values are in unknown model "
                             "units - do not label them mm")
    if fallback:
        report["warning"] = ((report.get("warning", "") + " " + fallback).strip())
    if report["has_assembly_transforms"]:
        report["warning"] = (report.get("warning", "") +
                             " assembly placement transforms are present; bounds of components "
                             "in local part coordinates may not match the assembled position.").strip()
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
        print(f"wrote {args.out}")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"{report['file']}")
        print(f"  unit: {unit_label} (to_mm={report['unit']['to_mm']})")
        print(f"  points: {len(points)}  mode: {args.mode}")
        print(f"  bbox native: min={box['min']} max={box['max']}")
        print(f"  size native: {box['size']}  diagonal={box['diagonal']:.4f}")
        print(f"  center: {box['center']}")
        print(f"  confidence: {confidence}")
        if report.get("warning"):
            print(f"  WARNING: {report['warning']}")
        if report["bbox_mm"]:
            print(f"  size mm: {report['bbox_mm']['size']}")
    return 0


def cmd_points(args) -> int:
    model = StepFile.load(Path(args.file))
    points = cartesian_points(model, args.mode)
    if args.limit:
        step = max(1, len(points) // args.limit)
        points = points[::step][: args.limit]
    target = Path(args.out)
    with open(target, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["entity_id", "x", "y", "z"])
        for x, y, z, eid in points:
            writer.writerow([eid, x, y, z])
    print(f"wrote {target} ({len(points)} point(s), mode={args.mode})")
    return 0


def cmd_project(args) -> int:
    model = StepFile.load(Path(args.file))
    points = cartesian_points(model, args.mode)
    if not points and args.mode != "all":
        points = cartesian_points(model, "all")
        if points:
            print(f"note: mode '{args.mode}' selected no points; projected all {len(points)} "
                  f"point(s) instead", file=sys.stderr)
    if not points:
        raise SystemExit("no CARTESIAN_POINT entities found")
    label = model.path.name
    svg = svg_projection(points, args.view, args.size, label)
    Path(args.out).write_text(svg, encoding="utf-8")
    print(f"wrote {args.out} ({args.view} projection of {len(points)} point(s))")
    print("note: this is a point-cloud projection, not a rendered surface")
    return 0


def cmd_groups(args) -> int:
    model = StepFile.load(Path(args.file))
    groups = product_groups(model)
    factor, unit_label = length_unit_factor(model)
    out = []
    for pd, point_ids in sorted(groups.items()):
        pid, pname = model.product_names_for_definition(pd)
        pts = [(*_coords(model.entities[i]), i) for i in point_ids
               if model.entities.get(i) is not None and _coords(model.entities[i])]
        box = bbox(pts)
        out.append({"product_definition": pd, "product_id": pid, "product_name": pname,
                    "points": len(pts), "bbox_native": box,
                    "bbox_mm": None if (box is None or math.isnan(factor)) else
                    {k: [round(v * factor, 4) for v in box[k]] for k in ("min", "max", "size")}})
    if args.json:
        print(json.dumps({"unit": unit_label, "products": out}, indent=2, ensure_ascii=False))
    else:
        print(f"unit: {unit_label}   products with geometry: {len(out)}")
        for o in out:
            size = o["bbox_native"]["size"] if o["bbox_native"] else None
            print(f"  {o['product_id']:14} {o['product_name'][:28]:28} points={o['points']:5} "
                  f"size={size}")
        if has_transforms(model):
            print("  WARNING: assembly transforms present; component boxes are in local "
                  "part coordinates")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Kernel-free geometric facts from a STEP file.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("bounds"); p.add_argument("file")
    p.add_argument("--mode", choices=["all", "vertices", "referenced"], default="vertices")
    p.add_argument("--json", action="store_true"); p.add_argument("--out")
    p.set_defaults(func=cmd_bounds)

    p = sub.add_parser("points"); p.add_argument("file")
    p.add_argument("--mode", choices=["all", "vertices", "referenced"], default="vertices")
    p.add_argument("--limit", type=int, default=0); p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_points)

    p = sub.add_parser("project"); p.add_argument("file")
    p.add_argument("--view", choices=["xy", "xz", "yz", "iso"], default="iso")
    p.add_argument("--size", type=int, default=800)
    p.add_argument("--mode", choices=["all", "vertices", "referenced"], default="vertices")
    p.add_argument("--out", required=True); p.set_defaults(func=cmd_project)

    p = sub.add_parser("groups"); p.add_argument("file")
    p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_groups)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

