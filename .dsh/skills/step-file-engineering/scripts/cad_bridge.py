#!/usr/bin/env python3
"""Detect and delegate to a real CAD kernel for true geometric operations.

Tier 3 of the step-file-engineering skill. Nothing here is emulated: when no
kernel is installed every geometric operation fails with the exact install
command instead of returning an approximation.

Usage:
  cad_bridge.py --probe [--json]
  cad_bridge.py to-stl     FILE --out FILE.stl [--linear-deflection 0.1]
  cad_bridge.py to-step    FILE --out FILE.step [--schema AP214]
  cad_bridge.py info       FILE [--json]
  cad_bridge.py props      FILE [--json]
  cad_bridge.py boolean    A B --op union|cut|common --out FILE.step
  cad_bridge.py convert    FILE --out FILE.step --schema AP203|AP214|AP242
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

FREECAD_CANDIDATES = [
    r"C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD 0.21\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe",
]

INSTALL_NOTES = {
    "cadquery": [
        'python -m pip install --upgrade cadquery',
        'python -m pip install cadquery-ocp  (bundles OpenCASCADE)',
    ],
    "ocp": [
        'python -m pip install cadquery-ocp',
    ],
    "trimesh": [
        'python -m pip install trimesh',
    ],
    "freecad": [
        'Install FreeCAD 1.0+ from https://www.freecad.org/downloads.php',
        r'Expected at C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe',
    ],
}


def probe() -> dict:
    found: dict[str, dict] = {}
    for module in ("cadquery", "OCP", "trimesh", "OCCT", "PythonOCC", "steputils", "gmsh"):
        spec = None
        try:
            spec = importlib.util.find_spec(module)
        except Exception:
            spec = None
        found[module] = {"available": spec is not None,
                         "origin": getattr(spec, "origin", None) if spec else None}
    freecad = None
    for cand in FREECAD_CANDIDATES:
        if Path(cand).is_file():
            freecad = cand
            break
    if freecad is None:
        for name in ("FreeCADCmd", "freecadcmd"):
            try:
                r = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=20)
                if r.returncode == 0:
                    freecad = name
                    break
            except Exception:
                continue
    found["FreeCAD"] = {"available": freecad is not None, "origin": freecad}

    if found["cadquery"]["available"] or found["OCP"]["available"]:
        tier, engine = 3, "OpenCASCADE via cadquery/OCP"
    elif freecad is not None:
        tier, engine = 3, f"FreeCAD ({freecad})"
    elif found["trimesh"]["available"]:
        tier, engine = 2, "trimesh only (mesh formats, NOT STEP geometry)"
    else:
        tier, engine = 1, "no kernel: text/entity-graph operations only"

    return {
        "tier": tier,
        "engine": engine,
        "modules": found,
        "capabilities": {
            "text_edits": True,
            "bounding_boxes": True,
            "volume_surface_area": tier == 3,
            "stl_export": tier == 3,
            "booleans": tier == 3,
            "schema_conversion": tier == 3,
            "fillet_shell_draft": tier == 3,
        },
        "install_notes": INSTALL_NOTES,
        "note": ("no network is available in this environment, so the kernel packages cannot be "
                 "installed here; the commands above work once network access returns."),
    }


def kernel_call(kind: str, argv: list[str]) -> int:
    """Run a real operation through cadquery/OCP when it is installed."""
    try:
        from cadquery import importers, exporters, Assembly  # type: ignore
        import cadquery as cq  # type: ignore
    except Exception as exc:
        print(f"error: cadquery is not available ({exc})", file=sys.stderr)
        print("install with: python -m pip install cadquery", file=sys.stderr)
        return 3
    if kind == "to-stl":
        ap = argparse.ArgumentParser()
        ap.add_argument("file"); ap.add_argument("--out", required=True)
        ap.add_argument("--linear-deflection", type=float, default=0.1)
        a = ap.parse_args(argv)
        shape = importers.importStep(a.file)
        exporters.export(shape, a.out, exportType="STL",
                         opt={"linearDeflection": a.linear_deflection})
        print(f"wrote {a.out} (linear deflection {a.linear_deflection})")
        return 0
    if kind == "info":
        ap = argparse.ArgumentParser()
        ap.add_argument("file"); ap.add_argument("--json", action="store_true")
        a = ap.parse_args(argv)
        shape = importers.importStep(a.file)
        solids = shape.solids().vals() if hasattr(shape, "solids") else []
        data = {"file": a.file, "solids": len(solids),
                "volume_mm3": round(sum(s.Volume() for s in solids), 4) if solids else None,
                "area_mm2": round(sum(s.Area() for s in solids), 4) if solids else None,
                "bbox": list(shape.val().BoundingBox().toTuple()) if solids else None,
                "is_valid": bool(shape.val().isValid()) if solids else None}
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    print(f"error: operation '{kind}' is not implemented for the detected kernel", file=sys.stderr)
    return 4


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if not argv:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(add_help=True,
                                 description="CAD kernel bridge for STEP geometry.")
    ap.add_argument("command", nargs="?", help="probe | to-stl | info | props | convert | boolean")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    ap.add_argument("--probe", action="store_true", help="report the available tier")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.probe or args.command in (None, "probe"):
        info = probe()
        if args.json:
            print(json.dumps(info, indent=2, ensure_ascii=False))
        else:
            print(f"TIER {info['tier']} — {info['engine']}")
            for name, state in info["modules"].items():
                mark = "yes" if state["available"] else "no "
                print(f"  [{mark}] {name:10} {state['origin'] or ''}")
            print("capabilities:")
            for k, v in info["capabilities"].items():
                print(f"  {'yes' if v else 'no ':4} {k}")
            print("install (requires network):")
            for pkg, cmds in info["install_notes"].items():
                print(f"  {pkg}: " + "; ".join(cmds))
            print(f"note: {info['note']}")
        return 0

    if args.command in {"to-stl", "info", "props"}:
        code = kernel_call("to-stl" if args.command == "to-stl" else "info", args.rest)
        if code == 3:
            print(json.dumps(probe(), indent=2, ensure_ascii=False))
        return code

    if args.command in {"convert", "boolean"}:
        print(f"error: '{args.command}' needs a real kernel and is not implemented yet.", file=sys.stderr)
        print("install cadquery (python -m pip install cadquery) and use its API directly; "
              "this bridge deliberately refuses to approximate geometry.", file=sys.stderr)
        return 3

    print(f"unknown command '{args.command}'. Use: probe, to-stl, info, props, convert, boolean",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
