# Butterfly Wing Aspect-Ratio Shape Contrast Analysis

This repository provides a workflow for identifying butterfly wings with similar aspect ratios (ARs) but different wing outlines, and generating publication-style black silhouette comparisons.

The main goal is not only to calculate wing aspect ratio, but to demonstrate that wings with similar AR values can still have substantially different planform shapes.

---

## Overview

The workflow consists of two main stages:

1. AR analysis and pair selection
   - Extract wing outlines from processed butterfly images.
   - Detect the wing root and tip.
   - Normalize wing span.
   - Calculate aspect ratio (AR).
   - Find wing pairs with similar AR values but different outlines.

2. Figure rendering
   - Re-extract the original wing contours.
   - Render selected pairs as clean black silhouettes.
   - Produce side-by-side comparison figures.

---

# Workflow Structure

wing_import/
    |
    |  processed butterfly wing PNG images
    |
    v
ar_shape_contrast_5pct.py
    |
    |  contour extraction
    |  root/tip detection
    |  span normalization
    |  AR calculation
    |  AR similarity search
    |
    v
ar_shape_contrast_results.json
    |
    v
render_original_side_by_side.py
    |
    v
output/
    |
    +-- pair_images/
            Pair_001.png
            Pair_002.png

---

# Main Scripts

## 1. ar_shape_contrast_5pct.py

This is the main analysis pipeline.

Functions:

- Wing outline extraction
- Root marker detection
- Tip detection
- Span normalization
- Aspect ratio calculation
- Pairwise AR comparison
- Representative pair selection

Aspect ratio calculation:

AR = span^2 / wing area

After span normalization:

AR = 1 / normalized planform area

Pairs are selected using symmetric relative AR difference:

|AR_A - AR_B| / ((AR_A + AR_B) / 2) <= threshold

Default threshold:

5%

---

## 2. render_original_side_by_side.py

This script generates the final figures.

It does not search for pairs.

Instead, it reads:

ar_shape_contrast_results.json

and uses the selected representative pairs.

It then:

- Loads original wing images
- Extracts original contour coordinates
- Draws black filled silhouettes
- Saves side-by-side comparison figures

Output:

output/
    pair_images/
        Pair_001.png
        Pair_002.png

This is the script responsible for producing the final silhouette images.

---

# Supporting Files

## wing_ar_analysis.py

An earlier standalone AR measurement script.

It performs a simpler black/white contour-based AR calculation.

It is not required for the final silhouette figures.

---

## build_ar_shape_contrast_workbook.mjs

Optional Excel workbook generator.

Creates reports containing:

- Analysis parameters
- AR measurements
- Matching pairs
- Representative pairs

Requires Node.js and artifact-tool.

---

## build_representative_ar_workbook.mjs

A smaller workbook export utility for normalized AR information.

---

## verify_ar_shape_contrast.py

Quality-control script.

Checks:

- JSON consistency
- Representative pairs
- Workbook integrity
- Output completeness

---

# Input Data

Required input:

wing_import/

Example:

wing_import/
    Charaxinae-5.png
    Hesperiidae-24.png

Images should contain:

- Black wing silhouette
- Red wing-root marker
- Optional blue wing-tip marker

Expected format:

PNG images

---

# Installation

Python requirements:

pip install numpy opencv-python matplotlib

Python version:

Python 3.10+

---

Optional Excel generation:

Install Node.js and:

npm install @oai/artifact-tool

---

# Usage

## Step 1: Run AR analysis

python ar_shape_contrast_5pct.py \
    --input-dir wing_import \
    --output-dir outputs/run_001 \
    --threshold-percent 5

Output:

outputs/run_001/

    ar_shape_contrast_results.json

---

## Step 2: Generate silhouette figures

python render_original_side_by_side.py \
    outputs/run_001/ar_shape_contrast_results.json \
    outputs/run_001/figures \
    --input-dir wing_import

Output:

outputs/run_001/figures/

    pair_images/
        Pair_001.png
        Pair_002.png

---

# Output Interpretation

Each figure contains:

- Left panel: wing A
- Right panel: wing B
- Black filled silhouette
- Original coordinate geometry

Selected pairs have:

- Similar aspect ratios
- Different outline shapes

This allows comparison of wing shape differences that are not captured by AR alone.

---

# Conceptual Summary

Aspect ratio is a useful geometric descriptor, but it does not uniquely describe wing shape.

This workflow demonstrates:

Similar AR
+
Different outline geometry
=
Different wing planforms

---

# File Summary

File | Purpose

ar_shape_contrast_5pct.py
Main AR calculation and pair selection

render_original_side_by_side.py
Final silhouette figure generation

wing_ar_analysis.py
Standalone AR analysis utility

build_ar_shape_contrast_workbook.mjs
Excel report generation

build_representative_ar_workbook.mjs
Small AR workbook export

verify_ar_shape_contrast.py
Output validation

---