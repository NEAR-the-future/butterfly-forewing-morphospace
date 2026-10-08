# Image techniques for scientific figures

## Pixel budgets: size the figure before editing it

A printed width in millimetres and a required DPI determine the pixel width exactly:

```
pixels = mm / 25.4 * dpi
```

`figtool.py mm2px --mm 89 --dpi 300` prints the value plus the standard column widths.

| Printed width | 300 dpi | 600 dpi | 1200 dpi |
|---|---|---|---|
| 85 mm (single column) | 1004 px | 2008 px | 4016 px |
| 114 mm (1.5 column) | 1346 px | 2693 px | 5386 px |
| 174 mm (double column) | 2055 px | 4110 px | 8220 px |

Rules:

- **Never upscale to reach a DPI.** Upscaling adds no information; `figtool.py` warns when an
  operation increases the pixel count. Re-acquire, or reduce the printed size instead.
- **Line art needs more resolution than photographs.** Plots and schematics: 600–1200 dpi, or vector.
- **Edit at final resolution.** Resize first, then annotate, so scale bars and text are pixel-exact.
  (The bundled tool applies annotation operations after geometry and colour steps for this reason.)
- **Work in 16-bit per channel when correcting**, then convert to 8-bit for delivery unless the
  journal accepts 16-bit TIFF.

## Correction order

Apply in this order and stop as soon as the image is acceptable:

1. **Crop** to the region of interest, keeping every data-bearing pixel you intend to interpret.
2. **White balance** (`white_balance`) for colour casts from the illumination or camera.
3. **Flat-field / background flattening** (`background_flatten`, sigma ≈ 30–60 px for a typical
   field) for uneven illumination. This is a non-linear local operation: declare it.
4. **Levels / auto levels** (`levels`, `auto_levels`) for a global black and white point. Use a small
   clip (0.1–0.5%) so a hot pixel does not define the white point.
5. **Denoise** (`denoise`) only if noise obscures the feature being measured; state it.
6. **Unsharp mask** (`sharpen`, radius 1–2 px, percent 50–100, threshold 2–4) — never on images used
   for quantitative intensity measurement.
7. **Convert mode** (`to_grayscale`, `to_cmyk`) as the journal requires.
8. **Annotate** — scale bars, arrows, panel letters.
9. **Save** at the target DPI with the journal's format and compression.

Every step beyond step 1 changes pixel values; the manifest records which ones, and the legend must
name the non-linear ones.

## Scale bars

- Measure the calibration first (a stage micrometer, a known pitch, or the microscope's own scale),
  then compute the bar length in pixels: `length_px = physical_length / pixel_size`.
- Draw the bar **after** the final resize, and re-verify it if anything resizes the figure later.
- Give the bar a contrasting outline so it survives both a light and a dark background.
- Label the bar with the physical length and unit (`10 µm`), not the magnification.
- If panels have different pixel sizes, each panel needs its own correctly scaled bar.

## Panel composition

- One gutter width for the whole figure; consistent panel size unless the content demands otherwise.
- Panel letters: lower case for most journals, upper case for others — check the venue. Same font,
  same size, same corner in every figure of the manuscript.
- Align panels on a grid; align axes across panels that share a scale (a shared axis is better still).
- Do not let text or scale bars overlap the data region.
- Keep the assembled figure within the venue's column width: use
  `figtool.py compose ... --width-mm 174` (or 85 for a single column) so the final print size is
  correct by construction.
- When an assembly scales the panels uniformly, every scale bar and font size must be re-verified —
  the tool prints this warning.

## Colour

- Encode quantitative maps with a perceptually uniform, colour-blind-safe map: viridis, magma,
  cividis. Never jet/rainbow. `colorize_map` provides viridis, magma, cividis, gray, and a
  blue-white-red diverging map.
- For categorical data use at most 4–5 colours with distinct lightness; do not use red vs green.
- For diverging data centre the map on the meaningful midpoint, not the data mean by default.
- Test the figure through a deuteranopia simulation before submission.
- For print, ask whether the venue wants RGB or CMYK; supply an ICC profile when CMYK is required.
- Never use colour alone to carry the message — add a marker shape, a line style, or a direct label.

## Format and compression

| Output | Use for | Settings |
|---|---|---|
| TIFF (LZW) | raster figures for submission | 8 or 16 bit, flattened, DPI set explicitly |
| PDF | vector plots, diagrams, composed figures with vector text | embed fonts |
| PNG | screenshots, web, when TIFF is not accepted | lossless, DPI set |
| JPEG | photographs when the venue allows it | quality ≥ 95, no chroma subsampling (`4:4:4`) |
| EPS | legacy vector requirement | convert from PDF where possible |
| SVG | web/HTML deliverables | keep text as text |

Always set the DPI metadata explicitly; many journals read it and reject a figure with no DPI.
Decide about the alpha channel deliberately: flatten for TIFF, keep for PNG if transparency matters.

## Measuring without destroying evidence

When a figure must support a quantitative claim, the measurement should come from the raw data, not
from the rendered figure. If you must measure from an image:

- use the unmodified, non-annotated source;
- never measure from a JPEG (compression artefacts shift edges);
- state the measurement tool and the threshold or edge criterion;
- keep the measurement script and its outputs as the figure's supporting data.
