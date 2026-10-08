# TeX error catalogue and environment facts

Facts about this machine, then the errors you will actually hit.

## Environment

| Item | Value |
|---|---|
| Distribution | TeX Live 2026 |
| Binaries | `C:\texlive\2026\bin\windows` |
| Engines | `pdflatex`, `xelatex`, `lualatex`, `latex`, `latexmk`, `platex`, `uplatex` |
| Bibliography | `bibtex`, `biber`, `bibtexu`, `bib2gls` |
| Index | `makeindex`, `texindy`, `xindy` |
| Conversion | `dvisvgm`, `dvips`, `xdvipsk`, `htlatex` |
| Utilities | `latexdiff`, `latexpand`, `latexindent`, `bibcop`, `biburl2doi` |
| **Not installed** | `pandoc`, `ghostscript` (`gs`), `qpdf`, `mutool`, `tectonic` |
| Network | none — no package can be downloaded with `tlmgr` |

Consequences: never plan a pipeline that needs pandoc or Ghostscript; never promise a CTAN package
that is not already in the installation. Check with `kpsewhich <file>` before using anything exotic.

## Error triage

Read `build-report.json` first; the parsed error list is ordered and de-duplicated. Then, only if
needed, search the `.log` for the **first** error — LaTeX cascades, and the last error is usually
noise.

| Error text | Real cause | Fix |
|---|---|---|
| `! Undefined control sequence` | misspelled macro, missing `\usepackage`, or a package loaded too late | find the line number from `-file-line-error`; add or move the package |
| `! LaTeX Error: File 'x.sty' not found` | package absent from TeX Live or wrong name | `kpsewhich x.sty`; if absent, rewrite without it |
| `! I can't find file 'x'` | path problem, wrong extension, or spaces/`#`/`%` in the name | rename the file, place it beside the main `.tex`, drop the extension |
| `! Package inputenc Error: Unicode character` | non-ASCII in a `pdflatex` document | escape it, or switch to `xelatex` |
| `! Font ... not loadable` | font not installed, or a CJK font requested from `pdflatex` | use an installed family; use `xelatex` + `ctex`/`xeCJK` for CJK |
| `! Missing $ inserted` | `_`, `^`, `%`, `&`, `#` or a math symbol in text mode | escape it or wrap in `$…$` |
| `! Missing } inserted` | unbalanced brace, often inside a caption or a citation | balance from the reported line backwards |
| `! Emergency stop` | cascade from an earlier error | fix the first error in the log |
| `! Paragraph ended before \\x was complete` | blank line inside a command argument | remove the blank line |
| `! Too many unprocessed floats` | more floats than can be placed | add `[h]`/`[t]`, use `\clearpage`, or reduce floats |
| `! Dimension too large` | huge coordinate in TikZ/picture | rescale the coordinate system |
| `pdfTeX error: ... libpng: internal error` | corrupt or unusual PNG, or a TIFF named `.png` | re-encode the image as a real PNG or PDF |
| `File 'x.pdf' not found` with `\includegraphics` | graphic outside the search path | keep graphics beside the main file or set `\graphicspath` |
| `! LaTeX Error: Something's wrong--perhaps a missing \item` | list environment malformed | check `\item` placement |

## Warning triage

| Warning | Meaning | Action |
|---|---|---|
| `Reference 'x' undefined` | label missing, or one more pass needed | run again; if it persists, the label does not exist |
| `Citation 'x' undefined` | key absent from the `.bib`, or bib tool not run, or stale `.bbl` | check the `.blg`; delete the `.aux`/`.bbl` and rebuild |
| `Label(s) may have changed. Rerun` | expected on a first build | the build loop runs the extra pass automatically |
| `Overfull \hbox (Npt too wide)` | a line sticks into the margin | rephrase, allow hyphenation, or use `\sloppy` locally |
| `Underfull \hbox (badness N)` | loose line spacing | usually cosmetic; ignore or rephrase |
| `Missing character: There is no X in font` | the glyph is absent from the font | change the font or replace the character |
| `Font shape ... not available` | font substitution happened | declare the shape or accept the substitute |
| `Package hyperref Warning: Token not allowed` | math in a bookmark | add `\texorpdfstring` |

## The build loop in this environment

`scripts/texbuild.py` performs:

1. engine pass 1 (builds `.aux`, discovers `\bibdata`);
2. `bibtex`/`biber` **inside the output directory** with `BIBINPUTS`/`BSTINPUTS`/`TEXINPUTS` set to
   the source directory plus a trailing separator (the trailing separator is what keeps TeX Live's
   own `plain.bst` and friends findable — removing it breaks every standard style);
3. `makeindex` when an index is detected;
4. engine passes until the log stops asking for a rerun, up to `--max-passes`;
5. a JSON report with parsed errors and warnings, and the PDF copied to `--pdf`.

Status is `ok` only when the PDF exists **and** no citation or reference is unresolved. A PDF with
`[?]` citations is reported as `needs-fix`, with exit code 1, on purpose.

## Determinism and metadata

- `SOURCE_DATE_EPOCH` is set by the build script so repeated builds produce stable timestamps.
- Remove `\date{\today}` from deliverables that must be byte-stable; set an explicit date.
- `hyperref` with `pdftitle`/`pdfauthor` populates the PDF metadata; a PDF with empty Title/Author
  fails many journal checks. `scripts/pdfqa.py` reports it.
- Beware `\input{...}` of files with a UTF-8 BOM: it becomes a stray character in the output.

## Shell escape

`-shell-escape` lets the document run external programs. Enable it only for a source the user
trusts, and say so. Packages that need it: `minted` (also needs Pygments), `svg` (needs Inkscape),
`pythontex`, `gnuplottex`. None of those helpers are installed here.
