---
name: publication-figures
description: "Production-grade scientific image and figure work: non-destructive photo/scan correction, cropping and resampling to journal pixel budgets, scaling and assembling multi-panel figures with panel letters, scale bars, annotations and colour-blind-safe palettes, plus export to TIFF/PNG/PDF/EPS at the resolution a journal requires. Ships scripts/figtool.py (deterministic, JSON-driven raster edits) and scripts/figqa.py (checks an exported figure against journal production specs). Use when editing microscopy or specimen images, building a figure, resizing artwork, or preparing figures for submission."
whenToUse: "Load for any task involving image editing, photo or scan cleanup, figure assembly, panel composition, scale bars, resizing, or journal figure-format compliance."
---

# Publication figures and image editing

This skill owns the production side; the integrity rules below override any aesthetic preference.
`references/integrity-checklist.md` is the submission screening list; `references/image-techniques.md`
holds the correction order, pixel budgets, colour and format recipes.

Companion skills: PPT decks containing figures → `slide-editing`; references to figures in the text
→ `academic-citations-and-references`; figure legends → `academic-paper-writing`.

## The integrity rules that override aesthetics

These are the reasons figures get a paper corrected or retracted. They are not optional.

1. **Never misrepresent the data.** No cloning/healing to remove objects, no selective erasure, no
   adding content that was not acquired. Declare every non-linear operation applied to a scientific
   image (gamma, shadow/highlight recovery, local contrast, deconvolution) in the legend.
2. **Comparisons must be like-for-like.** Panels compared visually must share acquisition settings
   and identical processing. Splitting one image into several panels is allowed only if the split is
   stated and the pieces do not overlap.
3. **Gels and blots**: keep the full lane and the molecular-weight markers in the figure, show the
   whole membrane when a cropped region is used, and never splice lanes silently. Add the
   "Samples were run on the same gel but were non-adjacent" note when true.
4. **Microscopy**: report the scale bar in the panel (not only in the legend), keep the scale bar's
   calibration correct after cropping and resizing, and state bit depth and whether the image is a
   maximum-intensity projection.
5. **Colour**: do not use rainbow/jet for quantitative maps (use viridis, magma, cividis, or a
   perceptually uniform alternative); do not rely on red/green discrimination alone; check
   deuteranopia and protanopia renderings before submission.
6. **Vector vs raster**: use vector for plots, diagrams, and schematics; raster only for acquisition
   images. Never trace a photo into fake vector art.
7. **Keep the originals.** Always edit a copy. Record every command you ran so the edit is
   reproducible; the scripts below do this automatically via a run manifest.

## Workflow

1. **Triage the source.** Measure before editing:
   ```powershell
   & "C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
     "<skill-dir>\scripts\figtool.py" probe "<input>" --json
   ```
   Record width/height, DPI, colour mode, bit depth, ICC profile, alpha, and the true colour
   distribution. A figure that is natively 150 DPI cannot become a legitimate 300 DPI figure by
   upscaling — resample up only when the source genuinely has the detail, otherwise flag it.
2. **Plan the target.** Decide the final printed width in millimetres (single-column, 1.5-column, or
   double-column for the venue) and the required DPI. Compute the required pixel width:
   `pixels = mm / 25.4 × dpi`. Choose line weights and font sizes on that basis, not by eye.
3. **Correct before composing.** Per-panel: white balance, illumination flattening, background
   subtraction, denoising, deconvolution — in that order, and only what the data supports. Use the
   edits JSON (below) so the correction is auditable.
4. **Compose panels.** Resample each panel to its slot, place with a fixed gutter, add panel letters
   (uppercase, consistent position, same font and size), scale bars, arrows, and outlines. Keep the
   figure's text in the vector layer when the output is vector.
5. **Export** to the journal's format and colour space. Flatten alpha for TIFF; keep vector text for
   PDF/EPS.
6. **Verify with the QA script** and read the warnings:
   ```powershell
   & "<python>" "<skill-dir>\scripts\figqa.py" "<figure>" --journal nature --json
   ```
7. **Report** the edit chain, the final pixel dimensions and DPI, and every operation you refused to
   perform for integrity reasons.

## figtool.py — deterministic raster edits

Edits are described in a JSON file: a list of operations applied in order, so the same input plus
the same JSON always yields the same output.

```json
[
  {"op": "crop", "box": [x0, y0, x1, y1]},
  {"op": "auto_levels", "clip_percent": 0.5},
  {"op": "background_flatten", "sigma": 40},
  {"op": "resize", "width": 1800, "resample": "lanczos"},
  {"op": "sharpen", "percent": 60, "radius": 1.2, "threshold": 3},
  {"op": "annotate_scalebar", "length_px": 200, "thickness": 8, "label": "10 \u00b5m", "anchor": "se", "margin": 24},
  {"op": "label_panel", "text": "a", "anchor": "nw", "size": 64},
  {"op": "compose", "panels": ["a.png", "b.png"], "cols": 2, "gutter": 24, "labels": ["a", "b"], "label_size": 64},
  {"op": "to_cmyk"},
  {"op": "save", "path": "Figure1.tif", "dpi": 300, "compression": "tiff_lzw"}
]
```

Supported `op` values: `crop`, `rotate`, `flip`, `resize`, `auto_levels`, `levels`,
`background_flatten`, `white_balance`, `desaturate`, `sharpen`, `blur`, `denoise`,
`colorize_map`, `flatten_background_to_white`, `annotate_scalebar`, `draw_scalebar`, `label_panel`,
`add_arrow`, `draw_rectangle`, `compose`, `to_rgb`, `to_cmyk`, `to_grayscale`, `save`.
Run `figtool.py ops` for the live list with parameters.

```powershell
& "<python>" "<skill-dir>\scripts\figtool.py" ops
& "<python>" "<skill-dir>\scripts\figtool.py" apply "<input>" --ops "<edits.json>" --out "<out-dir>"
& "<python>" "<skill-dir>\scripts\figtool.py" compose "<a.png>" "<b.png>" --cols 2 --gutter 24 --labels a,b --out "Figure1.tif" --dpi 300
```

## Journal production specs (verify against the live guidelines)

The QA script encodes common production requirements; treat every number as a default to confirm.

| Requirement | Typical value |
|---|---|
| Raster resolution | 300 DPI minimum for halftone/photo, 600–1200 DPI for line art and plots |
| Width | single column ≈ 85–90 mm, 1.5 column ≈ 114–130 mm, double column ≈ 170–180 mm |
| Fonts | sans-serif (Arial/Helvetica), 5–7 pt at final printed size, embedded in vector output |
| Colour | RGB for online-only; CMYK with a defined profile when print is required; never rely on colour alone |
| Formats | TIFF/PNG for raster; PDF/EPS/SVG for vector; JPEG only when the venue explicitly allows it |
| Layers | flatten before export unless the journal requests layered files |
| Units | scale bars only, in SI; state magnification separately if a journal demands it |
| Text in figures | no title inside the panel; all explanations belong in the legend |

## Common failures to screen for

- Upscaled artwork passed off as high-resolution (check with `probe`: interpolated files lack
  high-frequency detail).
- Panel letters missing, inconsistent, or in different fonts across panels.
- A scale bar drawn at the wrong length after resizing.
- Untranslated axis labels, mixed languages, or inconsistent units between panels.
- Legends that describe panels in a different order than the panels appear.
- Rainbow colour maps in quantitative heatmaps.
- Figures that lose the anti-aliased vector text when converted to TIFF for a journal that wanted
  vector art — export the vector format the journal asks for, do not convert to raster by default.
