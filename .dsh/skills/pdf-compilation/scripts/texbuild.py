#!/usr/bin/env python3
"""Deterministic LaTeX build loop with log triage.

Runs the required pass sequence, stops on real errors, and writes a JSON report
with parsed errors, warnings, missing files and the pass count.

Usage:
  texbuild.py MAIN.tex [--engine auto|pdflatex|xelatex|lualatex] [--bib auto|bibtex|biber|none]
                       [--index auto|makeindex|none] [--outdir DIR] [--jobname NAME]
                       [--pdf OUT.pdf] [--report FILE] [--shell-escape] [--max-passes N]
                       [--extra-args "--flag"] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TEXLIVE_BIN = Path(r"C:\texlive\2026\bin\windows")

ENGINE_PACKAGES = {
    "xelatex": ["fontspec", "unicode-math", "ctex", "xeCJK", "polyglossia", "mathspec",
                "zhnumber", "xeCJKfntef"],
    "lualatex": ["luatextra", "luatexja", "luacode", "luamplib"],
    "pdflatex": [],
}

ERROR_PATTERNS = [
    (re.compile(r"^!\s*(.*)$", re.M), "error"),
    (re.compile(r"^! LaTeX Error: (.*)$", re.M), "error"),
    (re.compile(r"^! Package ([^\s]+) Error: (.*)$", re.M), "package-error"),
    (re.compile(r"^! I can't find file `([^']*)'", re.M), "missing-file"),
    (re.compile(r"^! Undefined control sequence", re.M), "undefined-control-sequence"),
    (re.compile(r"^! Missing \\$", re.M), "missing-math-shift"),
    (re.compile(r"^! Emergency stop", re.M), "emergency-stop"),
    (re.compile(r"^! File `([^']*)' not found", re.M), "missing-file"),
    (re.compile(r"^! Font [^\n]* not loadable", re.M), "missing-font"),
]

WARN_PATTERNS = [
    (re.compile(r"LaTeX Warning: (Reference `[^']*' on page \d+ undefined)"), "undefined-ref"),
    (re.compile(r"LaTeX Warning: (Citation `[^']*' on page \d+ undefined)"), "undefined-citation"),
    (re.compile(r"LaTeX Warning: (There were undefined references)"), "undefined-refs"),
    (re.compile(r"LaTeX Warning: (Label\(s\) may have changed)"), "rerun-needed"),
    (re.compile(r"Package (\w+) Warning: (.*)"), "package-warning"),
    (re.compile(r"Overfull \\hbox \((\d+\.\d+)pt too wide\)"), "overfull-hbox"),
    (re.compile(r"Underfull \\hbox"), "underfull-hbox"),
    (re.compile(r"Overfull \\vbox"), "overfull-vbox"),
    (re.compile(r"Missing character: There is no (.*?) in font"), "missing-character"),
    (re.compile(r"pdfTeX warning: (.*)"), "pdftex-warning"),
]

FIX_HINTS = {
    "undefined-control-sequence": "a package is missing, a macro is misspelled, or a package must be loaded before use",
    "missing-file": "check the path (no spaces/non-ASCII), the TEXINPUTS search path, and the extension",
    "missing-font": "install the font or switch to one that is present; for CJK prefer xeCJK/ctex with a family in C:\\Windows\\Fonts",
    "emergency-stop": "an earlier error cascaded; fix the first error in the log, not this one",
    "missing-math-shift": "a $ is unbalanced — count math shifts in the offending environment",
    "package-error": "read the package documentation; many errors are caused by an option clash",
    "undefined-ref": "run one more pass, or the label/citation key does not exist",
    "undefined-citation": "the key is absent from the .bib, or bibtex/biber was not run, or the .bbl is stale",
    "rerun-needed": "one more pass is required for cross-references to settle",
    "overfull-hbox": "a line is too wide: rephrase, allow hyphenation, or use \\sloppy locally",
    "missing-character": "the glyph is absent from the selected font; switch fonts or use a fallback",
}


def kpathsea_path(*dirs: Path | str) -> str:
    """Build a kpathsea search path.

    A trailing separator must be kept: it tells kpathsea to append its compiled-in
    default paths, so overriding the variable does not hide plain.bst / natbib and
    the rest of the TeX Live tree.
    """
    parts = [str(d) for d in dirs]
    if not parts:
        parts = ["."]
    return os.pathsep.join(parts) + os.pathsep


def find_tool(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    cand = TEXLIVE_BIN / exe
    if cand.is_file():
        return str(cand)
    which = shutil.which(name)
    return which


def detect_engine(tex: str) -> tuple[str, str]:
    for engine, packages in ENGINE_PACKAGES.items():
        for pkg in packages:
            if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b" + re.escape(pkg) + r"\b",
                         tex) or re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^}]*" +
                                           re.escape(pkg) + r"\b", tex):
                return engine, f"detected package/class '{pkg}'"
    if re.search(r"[\u4e00-\u9fff]", tex):
        package_hint = ("the source contains CJK characters; with pdflatex use "
                        "\\usepackage[utf8]{inputenc}+CJKutf8, or switch to xelatex with ctex")
        return "xelatex", package_hint
    return "pdflatex", "no engine-specific package found"


def needs_bib(tex: str, aux: Path | None) -> tuple[str, str]:
    if re.search(r"\\addbibresource|\\printbibliography|\\usepackage(?:\[[^\]]*\])?\{biblatex\}",
                 tex):
        return "biber", "biblatex detected"
    if re.search(r"\\bibliography\{|\\bibliographystyle\{|\\usepackage(?:\[[^\]]*\])?\{natbib\}",
                 tex):
        return "bibtex", "natbib/\\bibliography detected"
    if aux and aux.is_file():
        aux_text = aux.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\\bibdata\{", aux_text):
            if re.search(r"\\abx@aux@", aux_text):
                return "biber", "biblatex control file present"
            return "bibtex", "\\bibdata in the .aux file"
    return "none", "no bibliography command found"


def needs_index(tex: str) -> str:
    if re.search(r"\\makeindex|\\printindex|\\usepackage(?:\[[^\]]*\])?\{imakeidx\}", tex):
        return "makeindex"
    return "none"


def run(cmd: list[str], cwd: Path, timeout: int,
        env_extra: dict[str, str] | None = None) -> tuple[int, str, float, bool]:
    env = dict(os.environ)
    env.setdefault("SOURCE_DATE_EPOCH", "1700000000")
    env["TEXMFVAR"] = env.get("TEXMFVAR", str(Path(env.get("TEMP", ".")) / "texmf-var"))
    if env_extra:
        env.update(env_extra)
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), time.time() - started, False
    except subprocess.TimeoutExpired as exc:
        partial = ""
        for stream in (exc.stdout, exc.stderr):
            if stream:
                partial += stream if isinstance(stream, str) else stream.decode("utf-8", "replace")
        return 124, partial, time.time() - started, True


def parse_log(log_path: Path, tex_log_text: str | None = None) -> dict:
    text = tex_log_text or ""
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8", errors="replace")
    # keep only the part before the final statistics block to avoid matching
    # package documentation echoes
    errors: list[dict] = []
    warnings: list[dict] = []
    seen: set[str] = set()
    for pattern, kind in ERROR_PATTERNS:
        for m in pattern.finditer(text):
            detail = (m.group(1) if m.groups() else m.group(0)).strip()[:200]
            key = f"{kind}:{detail}"
            if key in seen:
                continue
            seen.add(key)
            errors.append({"kind": kind, "detail": detail, "hint": FIX_HINTS.get(kind, "")})
    for pattern, kind in WARN_PATTERNS:
        count = 0
        sample = ""
        for m in pattern.finditer(text):
            count += 1
            if not sample:
                groups = [g for g in m.groups() if g]
                sample = (groups[-1] if groups else m.group(0)).strip()[:160]
        if count:
            warnings.append({"kind": kind, "count": count, "sample": sample,
                             "hint": FIX_HINTS.get(kind, "")})
    return {"errors": errors, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="LaTeX build loop with log triage.")
    ap.add_argument("main", help="path to the main .tex file")
    ap.add_argument("--engine", choices=["auto", "pdflatex", "xelatex", "lualatex", "latex"],
                    default="auto")
    ap.add_argument("--bib", choices=["auto", "bibtex", "biber", "none"], default="auto")
    ap.add_argument("--index", choices=["auto", "makeindex", "none"], default="auto")
    ap.add_argument("--outdir", help="build directory (default: alongside the main file)")
    ap.add_argument("--jobname")
    ap.add_argument("--pdf", help="copy the finished PDF here")
    ap.add_argument("--report", help="write the JSON report here")
    ap.add_argument("--shell-escape", action="store_true",
                    help="enable \\write18 (runs external commands: only with trusted sources)")
    ap.add_argument("--max-passes", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=300, help="seconds per tool invocation")
    ap.add_argument("--extra-args", default="", help="extra engine arguments, space separated")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    main_tex = Path(args.main).resolve()
    if not main_tex.is_file():
        print(f"error: {main_tex} not found", file=sys.stderr)
        return 2
    src_dir = main_tex.parent
    outdir = Path(args.outdir).resolve() if args.outdir else src_dir
    outdir.mkdir(parents=True, exist_ok=True)
    jobname = args.jobname or main_tex.stem
    tex = main_tex.read_text(encoding="utf-8", errors="replace")

    report: dict = {"main": str(main_tex), "outdir": str(outdir), "jobname": jobname,
                    "passes": [], "errors": [], "warnings": [], "started": time.strftime("%Y-%m-%dT%H:%M:%S")}

    engine = args.engine
    reason = "explicitly requested"
    if engine == "auto":
        engine, reason = detect_engine(tex)
    engine_path = find_tool(engine)
    if not engine_path:
        report["errors"].append({"kind": "missing-engine",
                                 "detail": f"{engine} not found on PATH or in {TEXLIVE_BIN}",
                                 "hint": "TeX Live is expected at C:\\texlive\\2026\\bin\\windows"})
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json
              else f"error: {engine} not found")
        return 2
    report["engine"] = {"name": engine, "path": engine_path, "reason": reason}

    aux = outdir / f"{jobname}.aux"
    bib_tool = args.bib
    bib_reason = "explicitly requested"
    if bib_tool == "auto":
        bib_tool, bib_reason = needs_bib(tex, aux)
    index_tool = args.index
    if index_tool == "auto":
        index_tool = needs_index(tex)
    report["bib"] = {"tool": bib_tool, "reason": bib_reason}
    report["index"] = {"tool": index_tool}

    base_cmd = [engine_path, "-interaction=nonstopmode", "-file-line-error",
                f"-jobname={jobname}", f"-output-directory={outdir}"]
    if args.shell_escape:
        base_cmd.append("-shell-escape")
    base_cmd += [a for a in args.extra_args.split() if a]
    base_cmd.append(str(main_tex))

    def do_pass(label: str, cmd: list[str], cwd: Path | None = None,
                env_extra: dict[str, str] | None = None) -> bool:
        code, output, secs, timed_out = run(cmd, cwd or src_dir, args.timeout, env_extra)
        entry = {"label": label, "cmd": cmd, "cwd": str(cwd or src_dir), "exit": code,
                 "seconds": round(secs, 1), "timed_out": timed_out}
        report["passes"].append(entry)
        if not args.json:
            status = "TIMEOUT" if timed_out else ("ok" if code == 0 else f"exit {code}")
            print(f"[{label}] {status} in {secs:.1f}s")
        if timed_out:
            report["errors"].append({"kind": "timeout", "detail": f"{label} exceeded {args.timeout}s",
                                     "hint": "raise --timeout or reduce the figure sizes"})
        return code == 0 and not timed_out

    ok = do_pass("latex-1", base_cmd)
    if not ok:
        report["status"] = "failed-early"
        report.update(parse_log(outdir / f"{jobname}.log"))
        return finish(args, report, outdir, jobname)

    bib_search = {"BIBINPUTS": kpathsea_path(src_dir, outdir),
                  "BSTINPUTS": kpathsea_path(src_dir, outdir),
                  "TEXINPUTS": kpathsea_path(src_dir, outdir)}

    if bib_tool != "none":
        tool = find_tool(bib_tool)
        if not tool:
            report["warnings"].append({"kind": "missing-bib-tool", "count": 1,
                                       "sample": f"{bib_tool} not found",
                                       "hint": "install it or pass --bib none"})
        else:
            # bibtex/biber must run where the .aux/.bcf lives, and must still see
            # the .bib/.bst sources in the source directory
            bib_cmd = [tool, jobname] if bib_tool == "bibtex" else [tool, f"{jobname}.bcf"]
            bib_ok = do_pass(bib_tool, bib_cmd, cwd=outdir, env_extra=bib_search)
            report["bib"]["cmd"] = bib_cmd
            report["bib"]["ok"] = bib_ok
            blg = outdir / f"{jobname}.blg"
            if blg.is_file():
                report["bib_log_tail"] = blg.read_text(
                    encoding="utf-8", errors="replace").splitlines()[-20:]
            if not bib_ok:
                tail = report.get("bib_log_tail", [])
                report["errors"].append({
                    "kind": "bibliography-failed",
                    "detail": f"{bib_tool} exited non-zero"
                              + (f": {tail[-1][:160]}" if tail else ""),
                    "hint": "check the .blg log; a key missing from the .bib, a syntax error, "
                            "or a non-ASCII character in the key are the usual causes"})

    if index_tool != "none":
        tool = find_tool(index_tool)
        if tool:
            do_pass(index_tool, [tool, f"{jobname}.idx"], cwd=outdir)

    for i in range(2, args.max_passes + 1):
        label = f"latex-{i}"
        ok = do_pass(label, base_cmd)
        if not ok:
            break
        log_text = ""
        log_path = outdir / f"{jobname}.log"
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"Rerun to get|Label\(s\) may have changed|undefined references", log_text):
            break

    report.update(parse_log(outdir / f"{jobname}.log"))
    pdf_path = outdir / f"{jobname}.pdf"
    report["pdf"] = {"path": str(pdf_path), "exists": pdf_path.is_file(),
                     "bytes": pdf_path.stat().st_size if pdf_path.is_file() else 0}
    if args.pdf and pdf_path.is_file():
        target = Path(args.pdf).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf_path, target)
        report["pdf"]["copied_to"] = str(target)

    # a produced PDF with unresolved citations or references is not a good build
    blocking = [w for w in report["warnings"]
                if w["kind"] in {"undefined-citation", "undefined-refs"}
                or (w["kind"] == "undefined-ref" and w.get("count", 0) > 2)]
    unresolved = bool(blocking) or any(e["kind"] == "bibliography-failed" for e in report["errors"])
    if pdf_path.is_file():
        report["status"] = "needs-fix" if unresolved else "ok"
    else:
        report["status"] = "failed"
    if unresolved:
        report["unresolved"] = [
            f"{w['kind']} x{w.get('count', 1)}: {w.get('sample', '')[:120]}" for w in blocking
        ] or [e["detail"] for e in report["errors"] if e["kind"] == "bibliography-failed"]
    return finish(args, report, outdir, jobname)


def finish(args, report: dict, outdir: Path, jobname: str) -> int:
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report_path = Path(args.report).resolve() if args.report else outdir / "build-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\nstatus: {report['status']}  passes: {len(report['passes'])}  "
              f"pdf: {'yes' if report.get('pdf', {}).get('exists') else 'no'}")
        if report.get("unresolved"):
            print("  UNRESOLVED:")
            for u in report["unresolved"]:
                print(f"    - {u}")
        for e in report["errors"][:12]:
            print(f"  ERROR [{e['kind']}] {e['detail']}")
            if e.get("hint"):
                print(f"        hint: {e['hint']}")
        for w in report["warnings"][:12]:
            print(f"  WARN  [{w['kind']}] x{w.get('count', 1)} {w.get('sample', '')[:120]}")
            if w.get("hint"):
                print(f"        hint: {w['hint']}")
        print(f"report: {report_path}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
