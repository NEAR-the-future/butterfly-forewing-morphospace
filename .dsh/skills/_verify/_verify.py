#!/usr/bin/env python3
"""Verification record for the five installed skill bundles.

Runs the same checks that were used to validate the scripts at install time, so
the user can re-verify after any edit. Writes nothing outside the directory you
pass as --artifacts.

Usage:
  verify.py --skills <.dsh/skills dir> --artifacts <scratch dir> [--python EXE]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

RESULTS: list[tuple[str, bool, str]] = []


def run(label: str, cmd: list[str], expect_zero: bool = True) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    ok = (proc.returncode == 0) == expect_zero
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = tail[0][:150] if tail else f"exit {proc.returncode}"
    RESULTS.append((label, ok, summary))
    return proc.stdout or ""


def write_sample(fig_dir: Path, step_dir: Path, tex_dir: Path) -> None:
    import numpy as np
    from PIL import Image

    fig_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    h, w = 600, 800
    xx, yy = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
    base = 120 + 80 * np.sin(6 * xx) + 40 * np.cos(5 * yy)
    img = np.stack([base * 0.6, base, base * 1.1], axis=2)
    img += rng.normal(0, 12, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    Image.fromarray(img).save(fig_dir / "panel_a.png")
    Image.fromarray(np.clip(img[:, ::-1] * 0.9, 0, 255).astype(np.uint8)).save(
        fig_dir / "panel_b.png")

    (fig_dir / "edits.json").write_text(json.dumps([
        {"op": "auto_levels", "clip_percent": 0.5},
        {"op": "resize", "width": 1051, "resample": "lanczos"},
        {"op": "label_panel", "text": "a", "anchor": "nw", "size": 46},
        {"op": "annotate_scalebar", "length_px": 210, "thickness": 7,
         "label": "10 \u00b5m", "label_size": 26, "anchor": "se", "color": "white"},
        {"op": "save", "path": "panel_a_final.tif", "dpi": 300, "compression": "tiff_lzw"},
    ], indent=2), encoding="utf-8")

    step_dir.mkdir(parents=True, exist_ok=True)
    step_sample = step_dir / "model.step"
    step_sample.write_text(
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_DESCRIPTION(('verification model'),'2;1');\n"
        "FILE_NAME('model.step','2026-01-15T09:30:00',('Tester'),('Org'),"
        "'preprocessor','system','CONFIDENTIAL','');\n"
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\n"
        "ENDSEC;\n"
        "DATA;\n"
        "#1=APPLICATION_CONTEXT('core data');\n"
        "#2=PRODUCT_CONTEXT('',#1,'mechanical');\n"
        "#3=PRODUCT('PART-001','Bracket housing','desc',(#2));\n"
        "#4=PRODUCT_DEFINITION_FORMATION('1','rev A',#3);\n"
        "#5=PRODUCT_DEFINITION_CONTEXT('part definition',#1,'design');\n"
        "#6=PRODUCT_DEFINITION('design','',#4,#5);\n"
        "#20=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));\n"
        "#21=CARTESIAN_POINT('c0',(0.,0.,0.));\n"
        "#22=CARTESIAN_POINT('c1',(120.,0.,0.));\n"
        "#23=CARTESIAN_POINT('c2',(120.,48.,12.5));\n"
        "#24=CARTESIAN_POINT('c3',(0.,48.,12.5));\n"
        "ENDSEC;\n"
        "END-ISO-10303-21;\n", encoding="utf-8")

    tex_dir.mkdir(parents=True, exist_ok=True)
    (tex_dir / "main.tex").write_text(
        "\\documentclass[11pt]{article}\n"
        "\\usepackage[T1]{fontenc}\\usepackage[utf8]{inputenc}\n"
        "\\begin{document}\n"
        "\\section{Test}\nReference \\ref{sec:test} and cite \\cite{x}.\n"
        "\\section{Test}\\label{sec:test}\n"
        "\\begin{thebibliography}{1}\\bibitem{x} A. Author. Title. 2020.\\end{thebibliography}\n"
        "\\end{document}\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify the installed skill scripts.")
    ap.add_argument("--skills", required=True, help="path to the .dsh/skills directory")
    ap.add_argument("--artifacts", required=True, help="scratch directory for test outputs")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    skills = Path(args.skills).resolve()
    art = Path(args.artifacts).resolve()
    art.mkdir(parents=True, exist_ok=True)
    figs = art / "figures"
    steps = art / "step"
    tex = art / "tex"
    write_sample(figs, steps, tex)

    py = args.python
    lint = skills / "academic-language-editing" / "scripts" / "academic_lint.py"
    audit = skills / "academic-citations-and-references" / "scripts" / "ref_audit.py"
    figtool = skills / "publication-figures" / "scripts" / "figtool.py"
    figqa = skills / "publication-figures" / "scripts" / "figqa.py"
    texbuild = skills / "pdf-compilation" / "scripts" / "texbuild.py"
    pdfqa = skills / "pdf-compilation" / "scripts" / "pdfqa.py"
    steptool = skills / "step-file-engineering" / "scripts" / "step_tool.py"
    stepgeom = skills / "step-file-engineering" / "scripts" / "step_geom.py"
    cadbridge = skills / "step-file-engineering" / "scripts" / "cad_bridge.py"

    missing = [str(p) for p in (lint, audit, figtool, figqa, texbuild, pdfqa, steptool,
                               stepgeom, cadbridge) if not p.is_file()]
    if missing:
        print("MISSING SCRIPTS:")
        for m in missing:
            print("  ", m)
        return 2

    sample_txt = art / "sample.txt"
    sample_txt.write_text(
        "We utilized a novel approach to delve into the data. The data is comprised of 12 samples "
        "and was analyzed in order to determine the outcome, which is very clear and plays an "
        "important role. It is worth noting that 5mL was used at 25\u00b0 C and P<0.05 was "
        "reported; we believe this result can't be ignored.\n", encoding="utf-8")

    run("academic_lint text", [py, str(lint), str(sample_txt), "--severity", "medium"])
    run("academic_lint json", [py, str(lint), str(sample_txt), "--format", "json"])
    run("academic_lint rules", [py, str(lint), "--list-rules"])
    run("academic_lint missing arg", [py, str(lint)], expect_zero=False)

    bib = art / "refs.bib"
    bib.write_text(
        "@article{a, author={Smith, J.}, title={T}, journal={J}, year={2020}, doi={10.1/x}}\n"
        "@book{b, title={No author}}\n", encoding="utf-8")
    run("ref_audit text", [py, str(audit), str(bib)])
    run("ref_audit json", [py, str(audit), str(bib), "--format", "json"])

    run("figtool probe", [py, str(figtool), "probe", str(figs / "panel_a.png"), "--json"])
    run("figtool apply", [py, str(figtool), "apply", str(figs / "panel_a.png"),
                          "--ops", str(figs / "edits.json"), "--out", str(figs)])
    run("figtool compose", [py, str(figtool), "compose", str(figs / "panel_a_final.tif"),
                            str(figs / "panel_b.png"), "--cols", "2", "--labels", "a,b",
                            "--width-mm", "174", "--out", str(figs / "Figure1.tif"),
                            "--dpi", "300"])
    run("figqa text", [py, str(figqa), str(figs / "Figure1.tif"), "--journal", "nature"])
    run("figqa json", [py, str(figqa), str(figs / "Figure1.tif"), "--journal", "nature", "--json"])

    run("texbuild", [py, str(texbuild), str(tex / "main.tex"), "--outdir", str(tex / "build"),
                     "--pdf", str(tex / "out.pdf"), "--report", str(tex / "build-report.json")])
    run("pdfqa text", [py, str(pdfqa), str(tex / "out.pdf"), "--require-fonts-embedded"])
    run("pdfqa json", [py, str(pdfqa), str(tex / "out.pdf"), "--json"])

    model = steps / "model.step"
    run("step_tool summary", [py, str(steptool), "summary", str(model), "--json"])
    run("step_tool validate", [py, str(steptool), "validate", str(model), "--strict"])
    run("step_tool rename", [py, str(steptool), "rename", str(model), "--product", "PART-001",
                             "--to", "\u7d27\u56fa\u4ef6 A", "--out", str(steps / "renamed.step")])
    run("step_tool validate output", [py, str(steptool), "validate", str(steps / "renamed.step")])
    run("step_geom bounds", [py, str(stepgeom), "bounds", str(model), "--json"])
    run("step_geom groups", [py, str(stepgeom), "groups", str(model), "--json"])
    run("step_geom project", [py, str(stepgeom), "project", str(model), "--out",
                              str(steps / "view.svg")])
    run("cad_bridge probe", [py, str(cadbridge), "--probe", "--json"])

    # the render must reproduce the original file byte for byte when nothing was
    # edited; compare bytes, not decoded text, because reading as text normalises
    # the line endings the writer is required to preserve
    sys.path.insert(0, str(steptool.parent))
    from step_tool import StepFile  # type: ignore
    loaded = StepFile.load(model)
    original_bytes = model.read_bytes()
    rendered_bytes = loaded.render().encode("utf-8")
    identical = rendered_bytes == original_bytes
    detail = "unchanged file re-renders byte for byte"
    if not identical:
        import difflib
        original_text = original_bytes.decode("utf-8", "replace")
        rendered_text = rendered_bytes.decode("utf-8", "replace")
        diff = [l for l in difflib.unified_diff(original_text.splitlines(), rendered_text.splitlines(),
                                                lineterm="", n=0)
                if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        detail = (f"{len(original_bytes)} vs {len(rendered_bytes)} bytes, "
                  f"{len(diff)} differing line(s)"
                  + (" | " + " | ".join(d[:80] for d in diff[:2]) if diff else ""))
    RESULTS.append(("step_tool byte-preserving render", identical, detail))

    failed = [r for r in RESULTS if not r[1]]
    print(f"{'PASS' if not failed else 'FAIL'}  {len(RESULTS) - len(failed)}/{len(RESULTS)} checks")
    for label, ok, summary in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {label:34} {summary}")
    if failed:
        print("\nFAILED CHECKS:")
        for label, _, summary in failed:
            print(f"  {label}: {summary}")
    print(f"\nartifacts: {art}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
