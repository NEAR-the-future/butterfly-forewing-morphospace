# Image integrity and figure preparation

Journal image-integrity screening is automated and unforgiving. These rules are the difference
between a correction and a retraction.

## Allowed without declaration

- Cropping that removes empty space (as long as no data-bearing region is removed).
- Rotation by a multiple of 90°, and flips (state the flip if orientation is meaningful).
- Uniform brightness, contrast and gamma applied to the **entire** image.
- Conversion to grayscale for a whole figure.
- Resizing with a high-quality resampler, provided the source genuinely resolves the target.
- Adding scale bars, arrows, panel letters, and outlines.
- Lossless format conversion and compression that does not alter pixels.

## Allowed only when declared in the figure legend

- Any non-linear adjustment: gamma, shadow/highlight recovery, sigmoid curves, local contrast or
  CLAHE, deconvolution, background flattening, unsharp masking.
- Background subtraction or flat-field correction that changes relative intensities.
- Splicing lanes from the same gel/blot, with the splice stated and the whole membrane shown.
- Reuse of a control panel across figures, if identical and stated.
- Any change applied to one panel and not its comparison panel — usually a defect, not a fix.

## Never allowed

- Adding, removing or moving any feature or object in an image.
- Cloning, healing, inpainting, or content-aware fill.
- Selective erasure of a blemish, band, cell, or outlier while leaving the rest of the field intact.
- Adjusting one region differently from the rest of the same image.
- Reusing a western blot/gel panel to represent a different experiment.
- Presenting a non-linear adjustment as raw data.
- Presenting upscaled or interpolated artwork as native high-resolution data.
- Compositing a figure from panels acquired under settings that are described as identical.
- Tracing a photograph into "vector" art and presenting it as data.

## Mandatory in the legend or methods

- Every non-linear operation, by name.
- Any splices, by panel and by the boundaries between them.
- n per panel, error-bar definition, and the statistical test.
- Scale-bar value and how the calibration was derived.
- For microscopy: acquisition modality, bit depth, whether the image is a maximum-intensity
  projection or a single plane, and any deconvolution.
- For gels: the full membrane view in the supplement when a cropped region is shown in the main text.

## Screening checklist before submission

Run through this for every figure, and record the answer:

- [ ] Every panel traces to an acquisition file; filenames recorded.
- [ ] No pixel was added or erased by a generative or healing tool.
- [ ] Any non-linear step is named in the legend.
- [ ] Comparisons within a figure share acquisition settings and identical processing.
- [ ] No panel appears twice without a stated reason.
- [ ] Scale bars survive the final resizing and are correct at the printed size.
- [ ] Colour encodes information accessibly (no red/green-only encoding; no rainbow for quantitative
      maps).
- [ ] Text in the figure is legible at final printed size (≥ 5–7 pt) and is a vector layer when the
      output format is vector.
- [ ] Panel letters are consistent in position, font and size across all figures in the manuscript.
- [ ] The figure has a self-contained legend that matches the panel order.
- [ ] The raw acquisition files are archived and can be supplied on request.
- [ ] Any tool used for the edits is named in the methods if the journal requires it.

## Produce a manifest

`figtool.py` writes a manifest for every `apply` run: the source, the ordered operations, their
parameters, the size and mode before and after each step, the output path, DPI and byte size, and a
flag on every non-linear operation. Keep the manifest with the figure. When a reviewer asks how a
panel was prepared, the manifest *is* the answer.

## Common integrity traps in practice

| Situation | Trap | Correct handling |
|---|---|---|
| Uneven illumination in a brightfield image | Applying a local correction only to the treated panel | Apply the identical operation to every panel in the comparison, or apply none |
| Two conditions photographed on different days | Slight exposure drift read as a real difference | Normalise identically, state the acquisition days, or repeat on one day |
| Faint band in a blot | Boosting only that blot | Show the whole membrane and the loading control |
| A crowded field | Removing debris | Keep the debris and mention it, or re-acquire |
| Low-resolution source | Upscaling to reach 300 dpi | Re-acquire or reduce the printed size; never upscale and claim resolution |
| Multi-panel figure | Panels resampled by different factors | Use one factor for the whole figure, then re-verify every scale bar |
| Colour map | Rainbow for a quantitative heat map | Use a perceptually uniform map (viridis, magma, cividis) |
| Reused control | Same control in three figures | Allowed if identical and declared; better to re-run or re-label clearly |
