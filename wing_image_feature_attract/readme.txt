# Butterfly Wing Morphology Feature Extraction and Visualization Pipeline

## Overview

This repository contains a complete workflow for extracting butterfly
wing morphology features and generating visualization outputs from wing
images.

The project is organized into three main tasks:

1.  Feature extraction and quantitative summary generation
2.  Wing geometry validation and quality control
3.  Morphological visualization and figure generation

The overall goal is to transform raw wing images into standardized
geometric representations for comparative morphology analysis.

------------------------------------------------------------------------

# Workflow Overview

    Raw wing images
            |
            v
    Feature extraction pipeline
            |
            |-- image loading
            |-- root and tip detection
            |-- contour extraction
            |-- wing coordinate generation
            |-- morphology feature calculation
            |
            v
    Summary feature tables
            |
            +-----------------------+
            |                       |
            v                       v
    Visualization workflow 1   Visualization workflow 2
    (extraction check)         (morphology plots)
            |
            v
    Publication figures

------------------------------------------------------------------------

# 1. Feature Extraction Pipeline

## Main driver

### `main_func.py`

This is the main entry point for processing wing images.

Functions:

-   Create output folders
-   Read images from `wing_import/`
-   Detect wing root markers
-   Extract wing contours
-   Save contour coordinates
-   Generate extraction check figures

Input:

    wing_import/

Output:

    wing_coordinate/

        *_edge_coordinates.csv


    edge_visual_data/

        Section_xxx.png
        Platform_xxx.png

The script controls the complete image-processing workflow and calls the
supporting modules.

------------------------------------------------------------------------

## Image processing module

### `image_tool.py`

This module provides basic image processing functions.

Main functions:

### Image loading

-   Import PNG images
-   Convert image format for analysis

### Marker detection

-   Detect red wing-root marker
-   Detect blue wing-tip marker

### Contour extraction

The module extracts wing boundary coordinates using:

-   grayscale conversion
-   edge detection
-   gradient-based refinement
-   contour ordering

The output is an ordered list of wing boundary points.

------------------------------------------------------------------------

## Shape and tip analysis

### `shape_tool.py`

This module analyzes wing geometry and determines wing-tip position.

Functions include:

-   contour path separation
-   leading and trailing edge identification
-   wing-tip correction
-   curvature-based tip detection

The detected root and tip coordinates are used for span alignment and
further morphology analysis.

------------------------------------------------------------------------

## Morphology feature calculation

### `wing_image_analysis.py`

This module calculates geometric descriptors from extracted contours.

Examples:

-   wing area
-   perimeter
-   centroid
-   moments
-   maximum chord length
-   area ratios
-   tip-region features
-   edge curvature features

The extracted measurements provide quantitative morphology variables for
downstream analysis.

------------------------------------------------------------------------

# 2. Visualization Pipeline I: Extraction Validation

## `section_tool.py`

Purpose:

Validate whether the wing contour extraction is correct.

Functions:

-   divide wings into spanwise sections
-   separate leading and trailing edges
-   check section intersections
-   visualize contour splitting

Output examples:

    edge_visual_data/

        Section_xxx.png

These figures are mainly used for checking extraction quality.

------------------------------------------------------------------------

# 3. Visualization Pipeline II: Morphological Visualization

## `plot_hesperiidae_anisynta_cynone.py`

Purpose:

Generate detailed morphology figures from individual wing images.

Workflow:

1.  Load wing image
2.  Extract contour
3.  Detect root and tip
4.  Transform coordinates into span-aligned space
5.  Calculate morphology parameters
6.  Plot fitted geometric features

Visualized features include:

-   smoothed contour
-   leading edge
-   trailing edge
-   wing-tip curvature
-   distal wing region

Output:

    edge_visual_data_clean/

These figures are designed for detailed morphology interpretation and
publication use.

------------------------------------------------------------------------

# 4. Supporting Validation Tool

## `tip_setting_feasibility_check.py`

Purpose:

Compare different wing-tip definitions.

The script evaluates:

-   manual blue tip marker
-   farthest point from root
-   algorithm-detected tip

Outputs:

    tip_setting_feasibility_check/

        TipCheck_xxx.png
        TipCheck_points_summary.csv

This helps determine whether automatic tip detection is consistent with
manual annotation.

------------------------------------------------------------------------

# Input Data

All scripts use butterfly wing images stored in:

    wing_import/

Expected image format:

-   PNG image
-   visible wing silhouette
-   red root marker
-   optional blue tip marker

Example:

    wing_import/

        Hesperiidae_Anisynta_cynone.png
        Danainae-2.png

For processing the complete dataset, rename:

    wing_import-ALL

to:

    wing_import

so that the scripts can automatically read all images.

------------------------------------------------------------------------

# Recommended Usage Order

## Step 1: Prepare images

Place all wing images into:

    wing_import/

------------------------------------------------------------------------

## Step 2: Run feature extraction

Run:

    python main_func.py

This generates:

-   contour coordinates
-   intermediate extraction data
-   validation figures

------------------------------------------------------------------------

## Step 3: Check extraction quality

Run:

    python tip_setting_feasibility_check.py

Check:

-   root position
-   tip position
-   automatic tip detection

------------------------------------------------------------------------


# File Relationship

    main_func.py
          |
          +----------------+
          |                |
          v                v
    image_tool.py     shape_tool.py
          |
          v
    wing_image_analysis.py
          |
          v
    Morphology features


    section_tool.py
          |
          v
    Extraction validation


    plot_hesperiidae_anisynta_cynone.py
          |
          v
    Publication morphology figures


    tip_setting_feasibility_check.py
          |
          v
    Tip detection validation

------------------------------------------------------------------------

# Main Outputs

## Feature extraction outputs

    wing_coordinate/

        *_edge_coordinates.csv

Contains:

-   ordered contour coordinates
-   wing root information

------------------------------------------------------------------------

## Quantitative morphology outputs

Generated measurements include:

-   specimen information
-   geometric parameters
-   morphology descriptors

These tables can be used for downstream statistical analysis.

------------------------------------------------------------------------

## Visualization outputs

Two main categories:

### Extraction validation

Used to verify:

-   contour extraction
-   root detection
-   tip detection
-   span alignment

### Morphology visualization

Used for:

-   geometric interpretation
-   comparison between specimens
-   publication figures

------------------------------------------------------------------------

# Summary

This project provides a complete butterfly wing morphology analysis
workflow:

1.  Extract wing boundaries from images.
2.  Calculate quantitative morphology features.
3.  Validate extraction accuracy.
4.  Generate publication-quality morphology visualizations.

The final outputs provide standardized wing geometry data for
comparative morphological analysis.