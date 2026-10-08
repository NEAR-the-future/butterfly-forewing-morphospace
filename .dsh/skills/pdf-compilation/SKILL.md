---
name: pdf-compilation
description: "Compile and deliver PDFs from LaTeX, Markdown, tables, and Office sources; run the multi-pass build loop (engine, bib, makeindex, rerun) until references and cross-references settle; triage TeX errors from the raw log; handle CJK and font embedding; and verify the finished PDF (page count, embedded fonts, metadata, encryption, size). Ships scripts/texbuild.py (deterministic build loop with log triage) and scripts/pdfqa.py (PDF structure and font-embedding checks). Use when producing a PDF from source, fixing a failing LaTeX build, or verifying a PDF before delivery."
whenToUse: "Load for any task whose output is a PDF built from source, any LaTeX compile failure, or any verification of a PDF deliverable."
---

# PDF compilation and verification

This environment has **TeX Live 2026** installed at `C:\texlive\2026\bin\windows` and no network
access. Available engines include `pdflatex`, `xelatex`, `lualatex`, `latexmk`, `bibtex`, `biber`,
`makeindex`, `texindy`, `dvisvgm`, `dvips`, and `htlatex`. There is **no** pandoc, no
Ghostscript (`gs`), and no `qpdf` — check before relying on them, and never assume a tool exists
because a tutorial mentions it.

`references/tex-troubleshooting.md` holds the error-catalogue; `references/build-recipes.md` holds
copy-ready document templates including a CJK setup that works with the installed fonts.

## Build pipeline

1. **Identify the source and the required engine.**
   - `.tex` → engine from the class/packages: `fontspec`, `unicode-math`, `ctex`, `xeCJK` need
     `xelatex` or `lualatex`; plain `inputenc`/`fontenc` works with `pdflatex`.
   - `.md` → no pandoc here. Convert programmatically (python-docx into DOCX then Office→PDF, or
     generate LaTeX directly) and say which route you took.
   - `.docx`/`.pptx`/`.xlsx` → the `office-*` skills own the conversion mechanics.
   - Tables from data → generate LaTeX (`booktabs`, `siunitx`) rather than pasting text.
2. **Build with the script**, which runs the full pass sequence and stops on real errors:
   ```powershell
   & "C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
     "<skill-dir>\scripts\texbuild.py" "<main.tex>" --engine auto --bib auto --outdir "<build-dir>"
   ```
   It selects the engine, runs latex → bib/biber → latex → latex (and makeindex when an index is
   detected), copies the PDF to the requested output path, and writes `build-report.json` with the
   parsed errors, warnings, missing files, and the number of passes needed.
3. **Triage failures from the report**, not by re-reading the whole log. Undefined control sequence,
   missing package, missing file, and "too many unprocessed floats" have distinct fixes — see the
   error catalogue.
4. **Verify the output** before delivering:
   ```powershell
   & "<python>" "<skill-dir>\scripts\pdfqa.py" "<out.pdf>" --json
   ```
   It reports page count, file size, encryption, embedded-vs-referenced fonts, linearisation, and
   metadata (title/author/subject/keywords), and warns about the common delivery defects.
5. **Clean up**: keep the build directory inside the task workspace, leave `.aux/.log/.toc` only if
   the user wants an incremental build, and never write build artefacts into the skill directory.

## Rules that prevent most build failures

- **Never delete the `.aux` files** between passes while debugging cross-references; delete them only
  for a deliberate clean build, and say so.
- **Run enough passes.** "??" in the output means one more pass is needed; after adding a
  bibliography, three passes are the minimum with `bibtex`.
- **File names**: no spaces, no non-ASCII, no `#`/`%`/`&` in paths or `\includegraphics` arguments.
  Rename or copy the asset instead of escaping.
- **Graphics formats**: `pdflatex` takes PDF/PNG/JPEG only (no EPS without `epstopdf` + shell
  escape); `xelatex` additionally accepts EPS via conversion. Vector art → PDF, raster → PNG/JPEG.
  Oversized PNGs should be downsampled before inclusion; a 40 MB PNG will fail or time out.
- **Fonts**: use fonts that are installed. For CJK, `ctex` with `xelatex` and an installed family
  (e.g. `SimSun`, `Microsoft YaHei`, `Noto Serif CJK SC` if present) — verify with
  `fc-list`-equivalent or by checking `C:\Windows\Fonts`. Never invent a font name.
- **Shell escape** (`-shell-escape`, `minted`, `svg`, `pythontex`) is a security-relevant request:
  ask before enabling it, and only with user-supplied sources.
- **Determinism**: set `SOURCE_DATE_EPOCH` and avoid `\today` in deliverables that must be
  reproducible; report the timestamp policy you used.
- **Encoding**: UTF-8 everywhere; use `inputenc` for `pdflatex` or switch to `xelatex` rather than
  fighting mojibake. Special characters `% & _ # $ { } ~ ^ \` must be escaped in text.
- **Bibliography**: `biber` for `biblatex`, `bibtex` for `natbib`/plain styles; the `.bib` must be
  in the search path or named relative to the main file. Missing `.bbl` is a silent failure mode —
  read the `.blg` log when citations come out as `[?]`.

## Delivery checks

Report, for every PDF deliverable:

- page count and page size, whether it is a single file, and whether it is encrypted or
  password-protected;
- whether **all** fonts are embedded (subset embedding is fine; a referenced non-embedded font is a
  rejection risk for journals and printers);
- metadata present (title, author) and free of stale template values;
- file size and whether images were downsampled for it;
- whether hyperlinks/bookmarks are required and present;
- the exact command used to reproduce the PDF.

Deliver the PDF as the primary artefact and keep the source plus a one-line build command so the
user can rebuild after edits.
