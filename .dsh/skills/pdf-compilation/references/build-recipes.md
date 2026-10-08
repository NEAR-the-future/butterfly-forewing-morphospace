# Build recipes

Copy-ready starting points. All of them build with the engines installed here and no network.

## 1. Plain article with a bibliography (pdflatex + bibtex)

```latex
\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{graphicx,booktabs,amsmath}
\usepackage[colorlinks=true,linkcolor=blue,citecolor=blue]{hyperref}
\hypersetup{pdftitle={Real Title},pdfauthor={Real Author}}   % metadata matters

\title{Real Title}
\author{Real Author}
\date{2026-01-15}          % explicit date, not \today, for reproducibility

\begin{document}
\maketitle
\begin{abstract}...\end{abstract}
...
\bibliographystyle{plain}
\bibliography{refs}
\end{document}
```

Build: `texbuild.py main.tex --outdir build --pdf out.pdf`

## 2. CJK document (xelatex)

```latex
\documentclass[11pt]{ctexart}          % or: \usepackage[UTF8]{ctex}
\usepackage{graphicx,booktabs}
\usepackage{fontspec}
\setmainfont{Times New Roman}          % must be installed on this machine
\setCJKmainfont{SimSun}                % or Microsoft YaHei / SimHei
\begin{document}
中文正文与 English terms 混排。
\end{document}
```

Build: `texbuild.py main.tex --engine auto` (the detector picks `xelatex` for `ctex`/`xeCJK` or any
CJK content). Verify the font family exists in `C:\Windows\Fonts` before using it; an invented font
name fails with `! Font ... not loadable`.

For `pdflatex` + CJK, the classic route is `\usepackage{CJKutf8}` with
`\begin{CJK}{UTF8}{gbsn}` … `\end{CJK}`. Prefer `xelatex` — it handles UTF-8 and system fonts
directly and avoids encoding traps.

## 3. Structured methods and a key resources table (Cell-style skeleton)

```latex
\documentclass[11pt]{article}
\usepackage{booktabs,longtable,array}
\begin{document}
\section*{STAR Methods}
\subsection*{Key resources table}
\begin{longtable}{lll}
\toprule
Reagent or resource & Source & Identifier \\
\midrule
\endhead
Antibody X & Vendor & Cat# 12345; RRID:AB\_123456 \\
\bottomrule
\end{longtable}
\end{document}
```

Note `\_` and `\#` escaping inside table cells — the most common compile error in methods tables.

## 4. Multi-panel figure with vector graphics

```latex
\usepackage{graphicx,subcaption}
\begin{figure}[t]
  \centering
  \begin{subfigure}[b]{0.48\linewidth}
    \includegraphics[width=\linewidth]{panel_a.pdf}
    \caption{}\label{fig:a}
  \end{subfigure}\hfill
  \begin{subfigure}[b]{0.48\linewidth}
    \includegraphics[width=\linewidth]{panel_b.pdf}
    \caption{}\label{fig:b}
  \end{subfigure}
  \caption{\textbf{Claim stated as a sentence.} (\textbf{a}) ... (\textbf{b}) ...}
  \label{fig:panels}
\end{figure}
```

- `pdflatex` accepts PDF/PNG/JPEG only. EPS needs `epstopdf` plus shell escape — avoid it.
- Prefer PDF for plots and diagrams, PNG for rasters at ≥ 300 dpi at final size.
- Reduce a 40 MB PNG before inclusion; oversized images are the usual cause of a build timeout.

## 5. Index, glossary, and nomenclature

```latex
\usepackage{makeidx}\makeindex        % or imakeidx, which runs makeindex itself
\usepackage{nomencl}\makenomenclature
```

Build order: engine → `makeindex main.idx` → engine. `texbuild.py` detects `\makeindex`/`\printindex`.

## 6. Markdown to PDF without pandoc

No pandoc on this machine. Two supported routes:

1. Convert to DOCX with `python-docx` (see the `office-docx` skill) and export through the bundled
   LibreOffice path documented by the office skills.
2. Generate LaTeX directly from the Markdown structure (headings, lists, tables, code) and compile
   with `texbuild.py`. This keeps full control of typography and is the better route for anything
   that must look like a paper.

## 7. Converting a PDF figure to SVG or vice versa

- `dvisvgm --pdf figure.pdf -o figure.svg` converts a PDF to SVG (for HTML/web deliverables).
- There is no Ghostscript, so `epstopdf` (which needs it) is unavailable: convert EPS with a Python
  route or ask the user for a PDF.
- `pdfqa.py` can confirm page geometry, font embedding and metadata of the result.

## 8. Reproducible build wrapper

```powershell
$py = "C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$skill = "<skill-dir>"
& $py "$skill\scripts\texbuild.py" main.tex --engine auto --bib auto `
      --outdir build --pdf "out\main.pdf" --report "out\build-report.json"
if ($LASTEXITCODE -ne 0) { Get-Content "out\build-report.json" | Select-Object -First 60 }
& $py "$skill\scripts\pdfqa.py" "out\main.pdf" --expect-pages 12 --require-fonts-embedded
```

Exit codes: `texbuild.py` returns 0 only for status `ok`; `pdfqa.py` returns 1 when any check fails.
Use them in CI or in a delivery script.
