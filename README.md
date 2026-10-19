# Butterfly–Robot Forewing Morphospace

> A Biological Reference Morphospace for Comparing Butterfly and Robotic Forewings

## 📚 Project Overview

This repository is the code and data release for the paper *A Biological Reference Morphospace for Comparing Butterfly and Robotic Forewings*. Using **383 butterfly forewings** as a reference set, it builds a reusable, reproducible geometric morphospace that lets **robotic / engineered forewings** be placed in the same morphological coordinate system for quantitative comparison.

The repository contains three independent but chainable pipelines:

- **Forewing geometry feature extraction** — detect the wing root and tip, extract the outline, and compute 11 normalized geometric descriptors
- **UMAP + KMeans morphospace** — unsupervised dimensionality reduction and clustering of the reference set, producing a frozen "reference morphospace" that new wings can be `transform`-projected into
- **Aspect-ratio vs. outline contrast** — search for wing pairs with similar aspect ratio (AR) but clearly different outlines, and render publication-quality silhouette comparisons

Datasets involved:

- **Reference set (383 specimens)** across 13 taxa (Hesperiidae, Lycaenidae, Papilioninae, Pieridae, Biblidinae, Charaxinae, Danainae, Heliconiinae, Limenitidinae, Nymphalinae, Satyrinae, Parnassiinae, Riodinidae)
- **Engineering set (11 specimens)**: AirPulse, eMotionButterflies, Fujikawa, RoboButterfly-I, Shinshu, Tanaka, Tu_2025, USTButterfly, USTButterfly-II, USTButterfly-S, Zhao_2026

## 🎯 Key Features

✅ **End-to-end automation** — from PNG images to an 11-feature morphology table in one command  
✅ **Planform standardization** — root translated to the origin, root→tip rotated onto the +x axis, span normalized to 1  
✅ **A shared morphological coordinate system** — butterflies and robots land in the same normalized planform space  
✅ **Unsupervised morphology clustering** — UMAP embedding + KMeans, yielding 7 morphology clusters  
✅ **Three hard guards** — nearest-neighbour consistency, rank preservation, and trustworthiness must all pass  
✅ **Frozen-model projection** — once fixed, the reference model is never refit; new samples are only transformed and predicted  
✅ **Two OOD policies** — strict rejection (`strict_rejection`) or warning-only (`warning_only`)  
✅ **Reproducibility throughout** — random seeds, input SHA-256, code SHA-256, and full artifact manifests  
✅ **Cluster stability audit** — fixed embedding, KMeans re-run across 100 random states  
✅ **AR–outline decoupling** — similar aspect ratio does not imply similar shape; pairs are matched and rendered at 600 dpi  
✅ **Publication-ready figures** — Times New Roman, exported as both PNG and SVG  

## 📁 Repository Structure

```
butterfly-forewing-morphospace/
├── README.md                        # this file
├── LICENSE                          # MIT License (c) 2026 NEAR the future
├── .gitignore                       # ignores __pycache__ / results / outputs / *.csv etc.
│
├── forewing_data/                   # raw forewing imagery (390 files)
│   ├── readme.txt                   # provenance notes and specimen counts
│   ├── refs.xlsx                    # 6 data sources: citations and species counts
│   ├── 说明.txt                      # per-taxon source ranges (ref-6 etc.)
│   ├── Biblidinae/  Charaxinae/  Danainae/  Heliconiinae/
│   ├── Hesperiidae/ Limenitidinae/ Lycaenidae/ Nymphalidae/
│   ├── Papilioninae/ Parnassiinae/ Pieridae/ Riodinidae/ Satyrinae/
│   └── <taxon>/ref1-5/              # supplementary images for that source range
│
├── wing_image_feature_attract/      # Pipeline 1: geometry feature extraction
│   ├── wing_image_analysis.py       # batch driver: PNG -> summary_11.csv
│   ├── main_func.py                 # directory setup, per-image driver, check figures
│   ├── image_tool.py                # image I/O, red root / blue tip detection, contour extraction
│   ├── shape_tool.py                # tip localization, perimeter, moments, sectional area
│   ├── section_tool.py              # spanwise sections and LE/TE splitting (standalone, unused)
│   ├── tip_setting_feasibility_check.py    # compares three tip definitions
│   ├── plot_hesperiidae_anisynta_cynone.py # single-specimen publication figures
│   ├── build_wing_ar_workbook.mjs   # AR Excel report builder (Node.js, optional)
│   ├── summary_11.csv               # 13-column feature table for the 11 engineering wings
│   ├── wing_import/                 # 11 engineering forewing images (default pipeline input)
│   ├── wing_import-ALL/             # 383 reference butterfly forewing images
│   ├── wing_import-test/            # 9 test images + 说明.txt
│   ├── wing_coordinate/             # 409 outline coordinate CSVs (X,Y,is_wing_root)
│   ├── edge_visual_data/            # 789 extraction/fit check figures (Section_* / EdgeFit_*)
│   ├── edge_visual_data_clean/      # 2 publication figures
│   ├── tip_setting_feasibility_check/  # tip-definition comparison output
│   └── ar_shape_contrast_5pct/      # Pipeline 3: AR vs. outline contrast
│       ├── ar_shape_contrast_5pct.py        # AR measurement + pair search (argparse)
│       ├── render_original_side_by_side.py  # silhouette comparison rendering (argparse)
│       ├── verify_ar_shape_contrast.py      # output integrity check (argparse)
│       ├── build_ar_shape_contrast_workbook.mjs      # Excel report (Node.js, optional)
│       ├── build_representative_ar_workbook.mjs      # normalized AR table (Node.js, optional)
│       ├── readme.txt               # sub-pipeline documentation
│       └── outputs/<run_id>/        # pair figures, JSON, xlsx
│
└── UMAP+Kmeans/                     # Pipeline 2: reference morphospace
    ├── auto_umap_feature_set_search.py        # coarse sweep: feature subsets x parameter grid
    ├── explore_reference_umap_kmeans.py       # first reference model (fast / full)
    ├── fine_search_reference_umap_kmeans.py   # fine search: produces the frozen model
    ├── fine_search_metrics.py                 # cluster quality metrics and composite score
    ├── fine_search_guards.py                  # three hard guards and OOD threshold
    ├── project_summary_input_to_fine_umap.py  # project new samples (strict OOD rejection)
    ├── project_summary_input_to_fine_umap_ood_warning_only.py  # projection (warn only)
    ├── audit_kmeans_random_state.py           # KMeans random-state stability audit
    ├── reference_model_io.py                  # model loading and consistency checks
    ├── readme.txt                     # docs + pinned dependency versions
    ├── summary_11.xlsx                # 383 x 13 reference feature table
    ├── summary_input-all.xlsx         # 11 x 13 feature table to be projected
    ├── reference_umap_feature_search/ # first-round reference model and archive (113 MB results)
    ├── fine_search_results/<run_id>/  # final frozen model, manifests, projection output
    └── kmeans_random_state_audit/     # cluster stability audit results
```

### Data directories

| Directory | Contents | Count / format |
| --- | --- | --- |
| [forewing_data/](forewing_data/) | Raw forewing photographs, organized by taxon (includes 6 `ref1-5` subdirectories) | 387 images (365 JPG + 22 PNG) + 3 metadata files incl. [refs.xlsx](forewing_data/refs.xlsx) |
| [wing_import-ALL/](wing_image_feature_attract/wing_import-ALL/) | Processed reference set (black silhouette + red root marker) | 383 PNG |
| [wing_import/](wing_image_feature_attract/wing_import/) | Processed engineering / robotic forewings | 11 PNG |
| [wing_import-test/](wing_image_feature_attract/wing_import-test/) | Small test image set | 9 PNG |
| [wing_coordinate/](wing_image_feature_attract/wing_coordinate/) | Ordered outline coordinates (`X,Y,is_wing_root`; 523–6 233 rows per wing, mean ≈1 223) | 409 CSV = 383 reference + 26 engineering/legacy |
| [edge_visual_data/](wing_image_feature_attract/edge_visual_data/) | Extraction check and leading/trailing edge fit figures | 394 Section_* + 395 EdgeFit_* |
| [edge_visual_data_clean/](wing_image_feature_attract/edge_visual_data_clean/) | Publication-quality single-specimen figures | 2 PNG |
| [tip_setting_feasibility_check/](wing_image_feature_attract/tip_setting_feasibility_check/) | Tip-definition comparison | 4 specimen figures + legend + summary CSV |

## 🚀 Quick Start

### 1. Install dependencies

Pipeline 1 (feature extraction and AR contrast) needs only:

```bash
pip install numpy scipy matplotlib opencv-python
```

Pipeline 2 (UMAP + KMeans) additionally needs the dimensionality-reduction and clustering stack. There is no `requirements.txt` in the repository — the **pinned versions are recorded at the top of [UMAP+Kmeans/readme.txt](UMAP+Kmeans/readme.txt)** (verified on Python 3.11.7):

```bash
pip install numpy==1.26.4 pandas==2.1.4 scipy==1.11.4 scikit-learn==1.7.2 \
            umap-learn==0.5.11 numba==0.59.0 llvmlite==0.42.0 \
            pynndescent==0.6.0 joblib==1.2.0 threadpoolctl==3.5.0 \
            matplotlib==3.8.0 openpyxl==3.0.10
```

> Keep these versions when reproducing saved models; otherwise the UMAP object deserialized by `joblib` may not behave identically.

**Optional (Excel reports)**: [build_wing_ar_workbook.mjs](wing_image_feature_attract/build_wing_ar_workbook.mjs) and the two `.mjs` builders under `ar_shape_contrast_5pct` require Node.js and `@oai/artifact-tool`. That package is not on the public npm registry, so these three scripts **cannot run** in a normal environment. The Python pipelines do not depend on them — just pass `--skip-workbook`.

### 2. Step 1 — Extract forewing geometry features

```bash
cd wing_image_feature_attract
python wing_image_analysis.py
```

This script takes **no command-line arguments**. Its input is fixed to `wing_import/*.png` (non-recursive):

- writes `summary_11.csv` into the **current working directory**, so run it from `wing_image_feature_attract/`
- writes `wing_coordinate/{image_name}_edge_coordinates.csv`
- writes `edge_visual_data/Section_*.png` and `edge_visual_data/EdgeFit_*.png`

To process all 383 reference specimens, rename `wing_import-ALL` to `wing_import` first (`main_func.find_image_files` only reads that directory name):

```bash
mv wing_import wing_import_robot_backup
mv wing_import-ALL wing_import
python wing_image_analysis.py
```

Auxiliary check scripts (also without CLI arguments; their inputs must exist in `wing_import/`):

```bash
python tip_setting_feasibility_check.py        # compares 3 tip definitions (4 fixed specimens)
python plot_hesperiidae_anisynta_cynone.py     # renders single-specimen publication figures
```

### 3. Step 2 — Build the reference morphospace

```bash
cd ../UMAP+Kmeans

# (optional) standalone coarse sweep over feature subsets x parameter grid
python auto_umap_feature_set_search.py \
    --input summary_11.xlsx --output-dir auto_umap_feature_search

# 2a) first reference model; also produces the archive consumed by the fine search
#     fast mode (default): 30 UMAP x 120 KMeans configurations per feature set
python explore_reference_umap_kmeans.py --output-dir reference_umap_feature_search

# 2b) fine search: 15 000 UMAP fits x 7 K values = 105 000 KMeans evaluations
python fine_search_reference_umap_kmeans.py
```

The fine search's default `--archive` and `--model-artifact` already point at the files produced by step 2a inside `reference_umap_feature_search/`, so no extra arguments are needed; `auto_umap_feature_set_search.py` writes to a separate directory and the two do not consume each other's output. The reference fine search took about **8 228 seconds (≈2.3 h)** and supports `--dry-run` (write the plan only) and `--resume` (continue an identical plan).

### 4. Step 3 — Audit clustering stability

```bash
python audit_kmeans_random_state.py
```

Holds the UMAP coordinates fixed and re-runs KMeans across 100 random states, reporting the adjusted Rand index (ARI) and any changed specimens. Note that its `--labels` default **hard-codes the run ID** `20260926_234406_930698`; pass `--labels` explicitly when using a different run directory.

### 5. Step 4 — Aspect-ratio vs. outline contrast

```bash
cd ../wing_image_feature_attract/ar_shape_contrast_5pct

# 5a) AR measurement + pair search
python ar_shape_contrast_5pct.py \
    --input-dir ../wing_import-ALL \
    --output-dir outputs/run_all \
    --threshold-percent 5 \
    --representative-count 12 \
    --skip-workbook

# 5b) render representative pairs as original-coordinate black silhouettes
python render_original_side_by_side.py \
    outputs/run_all/ar_shape_contrast_results.json \
    outputs/run_all/original_side_by_side \
    --input-dir ../wing_import-ALL

# 5c) verify output integrity (read-only, prints metrics)
python verify_ar_shape_contrast.py outputs/run_all --summary-csv ../summary_11.csv
```

The published reference run in this repository (`outputs/019f9ca7-cf02-7b50-98ab-6e0898d99071/`, 5% threshold) measured all 383 images with 0 failures, found **16 955 pairs within the threshold**, and selected **12 representative pairs**. That directory name is a UUIDv7 (embedded timestamp 2026-07-26 04:21 UTC), whereas the script's default output name is `outputs/<YYYYMMDD_HHMMSS>`, so this run passed an explicit `--output-dir`.

### 6. Where to find results

**Feature extraction** (`wing_image_feature_attract/`)

- `summary_11.csv` — 13-column feature table (`Type Number`, `Name` + 11 geometric quantities)
- `wing_coordinate/{name}_edge_coordinates.csv` — ordered outline points (note: the `is_wing_root` column is always `NO`; see Important Notes #5)
- `edge_visual_data/Section_{name}.png` — outline extraction and root/span-line check
- `edge_visual_data/EdgeFit_{name}.png` — leading/trailing edge fits and tip curvature

**Reference morphospace** (`UMAP+Kmeans/fine_search_results/<run_id>/`)

- `best_reference_umap_model.joblib` — frozen UMAP reducer + KMeans model
- `best_reference_umap_manifest.json` — selected features, parameters, hashes, all guard metrics
- `best_result.json` / `selected_feature_sets.csv` / `top_single_runs.csv` — search results
- `summary_input_projection/` — projection workbook, OOD assessment, nearest references, UMAP plots

**AR vs. outline contrast** (`ar_shape_contrast_5pct/outputs/<run_id>/`)

- `ar_shape_contrast_results.json` — all measurements, all matching pairs, representative pair IDs
- `pair_images/Pair_001..012.png` — normalized pair panels
- `original_side_by_side/pair_images/Pair_001..012.png` — original-coordinate black silhouette pairs

## 🦾 Projecting Your Own Robot Wing into the Reference Morphospace

This is the end-to-end path for taking a single new robotic forewing and locating it inside the already-built UMAP space. The reference model is **never retrained** — your wing is passed through the frozen preprocessor, `UMAP.transform`, and KMeans prediction.

**Before you start**: your image must follow the same convention as the existing ones — PNG, a clean high-contrast (black on white) wing silhouette, a **red wing-root marker**, and optionally a blue wing-tip marker. The filename stem becomes the `Name` value in the feature table, so use a meaningful name (e.g. `MyRobotWing_process.png`).

### Step 1 — Add the processed wing image to `wing_import/`

```bash
cp MyRobotWing_process.png wing_image_feature_attract/wing_import/
```

The pipeline reads only `wing_import/` and only `*.png` files, non-recursively. If you previously renamed the directory to process the 383 reference specimens, restore it first so the robot wings are not mixed into the reference set.

### Step 2 — Run `wing_image_analysis.py` to produce the feature table

```bash
cd wing_image_feature_attract
python wing_image_analysis.py
```

This writes `summary_11.csv` into the current directory: one row per PNG in `wing_import/`, with the 13 columns `Type Number`, `Name`, `Area`, `WingArea_BBoxAreaRatio`, `TipArea_R0p1_WingAreaRatio`, `Roundness`, `LE_TE_ratio`, `TipCurvature`, `LE_Bending`, `TE_Bending`, `TE_MaxCurvX`, `TE_Distal_Bending`, `TE_Distal_SignedCurvature`. `Type Number` (the taxon code) is `NaN` for robotic wings, which is expected.

> The script processes **every** PNG in `wing_import/`. To isolate your wing, point a clean folder at it first, or simply keep the existing rows — every row in the file gets projected.

### Step 3 — Put the feature file in `UMAP+Kmeans/` and run the projection

```bash
# Option A — keep the CSV as-is and point --input at it
cp summary_11.csv ../UMAP+Kmeans/
cd ../UMAP+Kmeans
python project_summary_input_to_fine_umap.py --input summary_11.csv

# Option B — write a real .xlsx so the default --input path works
python -c "import pandas as pd; pd.read_csv('summary_11.csv').to_excel('summary_input-all.xlsx', index=False)"
python project_summary_input_to_fine_umap.py
```

- The script's default `--input` is `UMAP+Kmeans/summary_input-all.xlsx`. It also reads `.csv`/`.tsv` directly, which is why Option A works without converting to Excel — do **not** merely rename the CSV to `.xlsx`, since the reader picks the parser from the file extension.
- The file must carry the **same 13 column names** as `summary_11.xlsx`, because the model selects its 7 features by name.
- To compare your wing against the 11 engineering wings already shipped, **append** your row to the existing `summary_input-all.xlsx` rather than overwriting it.
- The run directory is auto-discovered as the newest completed run (currently `20260926_234406_930698`); override it with `--fine-search-dir` or `--model-artifact`.
- **OOD handling**: rows whose full-feature nearest-neighbour distance exceeds the 0.985 reference quantile (**3.2471**) are rejected under the default strict policy. If your wing is rejected but you still want to see it, run `python project_summary_input_to_fine_umap_ood_warning_only.py`, which keeps such rows and flags them as warnings instead.

### Step 4 — Inspect the projection and nearest-neighbour results

All outputs land in:

```
UMAP+Kmeans/fine_search_results/<run_id>/summary_input_projection/
```

| File | What it shows |
| --- | --- |
| `summary_input_frozen_umap_projection.xlsx` | Everything in one workbook: projected rows, OOD assessment, calibration, nearest reference, KMeans centers, invariance audit, model metadata |
| `summary_input_nearest_reference.csv` | **The nearest-neighbour table** — for each projected wing, its closest reference specimen, the distance in both feature and UMAP space, and the OOD percentile |
| `summary_input_ood_assessment.csv` | Per-row OOD distance, percentile, and accept/reject status |
| `ood_reference_calibration.csv` | The reference distance distribution (p25/p50/p75/p90/p95/p99/min/max) behind the OOD threshold |
| `frozen_umap_with_summary_input_clusters.png` / `.svg` | **The projection figure** — your wing drawn on top of the reference clusters |
| `frozen_umap_with_summary_input_true_labels.png` / `.svg` | Same view colored by taxon label |
| `frozen_umap_reference_only_true_labels.png` / `.svg` | Reference-only baseline for comparison |
| `reference_cluster_pies/` | Taxon composition pies for each of the 7 clusters |
| `projection_manifest.json` | Full provenance: model path, input path, transform mode, OOD policy and rejected names |

In short: read the **nearest-neighbour table** (`summary_input_nearest_reference.csv`) to learn which butterfly your wing is closest to, and the **projection figure** (`frozen_umap_with_summary_input_clusters.png`) to see where it lands relative to the reference clusters.

## 📈 Evaluation Metrics

### Cluster quality (`fine_search_metrics.py`)

- **Silhouette** (`silhouette_score`) — within-cluster cohesion vs. between-cluster separation
- **Davies–Bouldin index** (`davies_bouldin_score`) — lower is better
- **Cluster size balance** — smallest / second-smallest / largest cluster ratios, plus `cluster_size_entropy`
- **Spatial occupancy uniformity** — 10th–90th percentile bounding-box volume share per cluster and its entropy `spatial_occupancy_entropy`
- **Validity flags** — `partition_valid`, `in_target_cluster_range`, `cluster_size_valid`, `silhouette_threshold_valid`, `selection_valid`

**Composite score** (`SCORE_WEIGHTS`):

```
score = 1.4 · Silhouette
      − 0.12 · DBI
      + 2.0 · p_min + 1.0 · p_second + 1.0 · H_size
      − 5.0 · p_max + 1.5 · H_occupancy
```

**Selected solution:**

| Metric | Value |
| --- | --- |
| Composite score | **2.6909** |
| Silhouette | 0.5131 |
| Davies–Bouldin | 0.6717 |
| Cluster sizes | 53 / 56 / 51 / 54 / 62 / 60 / 47 |
| Cluster size entropy | 0.9980 |
| Spatial occupancy entropy | 0.9906 |

### Embedding trustworthiness (`fine_search_guards.py`)

- **Nearest-neighbour consistency** — the nearest reference must have the same name in feature space and UMAP space
- **Rank preservation** — maximum rank 50 in full feature space; observed maximum 43
- **Trustworthiness** (k=10) — 0.9200, matching the full 11-feature baseline (tolerance 1e-12)

### OOD assessment (projection stage)

- **Leave-one-out nearest-neighbour distance quantile** over the standardized full-feature reference space
- **Threshold** — the 0.985 quantile = 3.2471; anything above is treated as out of distribution
- **Diagnostics** — p25/p50/p75/p90/p95/p99/min/max calibration curve (`ood_reference_calibration.csv`)
- Observed on the reference set: p95 = 2.3649, **p99 = 3.3613**, max = 6.9622

### Cluster stability (`audit_kmeans_random_state.py`)

Fixed UMAP embedding, KMeans re-run across 100 random states (0–99):

- **Adjusted Rand index**: 0.9945 – 1.0
- **Seeds reproducing the saved partition exactly** (up to label permutation): 10 / 100
- **Maximum changed specimens**: 1 (`Hesperiidae-16`)
- Silhouette range: 0.51310 – 0.51388; DBI range: 0.67075 – 0.67170

### AR contrast metrics

- **Aspect ratio** — `AR = 1 / normalized planform area`
- **Symmetric relative difference** — `|AR_A − AR_B| / ((AR_A + AR_B)/2)`, default ≤ 5%
- **Outline IoU / `shape_difference`** — `1 − IoU`, measuring outline dissimilarity
- **`cross_family`** — whether a pair spans different taxa

## 📖 Documentation

- **[wing_image_feature_attract/readme.txt](wing_image_feature_attract/readme.txt)** — full feature-extraction and visualization pipeline documentation
- **[UMAP+Kmeans/readme.txt](UMAP+Kmeans/readme.txt)** — morphospace pipeline documentation and pinned dependency versions
- **[ar_shape_contrast_5pct/readme.txt](wing_image_feature_attract/ar_shape_contrast_5pct/readme.txt)** — AR–outline contrast sub-pipeline documentation
- **[forewing_data/readme.txt](forewing_data/readme.txt)** — reference data provenance and specimen counts
- **[forewing_data/refs.xlsx](forewing_data/refs.xlsx)** — 6 data sources with citations, species counts, and total
- **[LICENSE](LICENSE)** — MIT license

## 🔧 Extending

### Add or change a morphology feature

1. Compute the new quantity inside `main()` in [wing_image_analysis.py](wing_image_feature_attract/wing_image_analysis.py) (reuse `compute_geometry_from_contour`, `fit_edge_curve`, `tip_curvature`, etc.)
2. Update the `header` list and the `row_data` write order together — they must stay strictly aligned
3. If the feature should participate in clustering, add it via `--feature-cols` or widen `--min-features/--max-features`, then re-run pipeline 2

### Use a different reference dataset

1. Place the new `summary_11.xlsx` in `UMAP+Kmeans/` (the column structure must match: `Type Number`, `Name` + 11 features)
2. If the reference hash changes, the fine search **exits with an error** (it validates `reference_source_sha256` against the archive manifest), so re-run `explore_reference_umap_kmeans.py` first to rebuild the archive
3. Then run `fine_search_reference_umap_kmeans.py` and point the audit script at the new labels with `--labels`

### Adjust the hard guards

Guard parameters live in `build_guard_context(...)` in [fine_search_guards.py](UMAP+Kmeans/fine_search_guards.py): `exact_guard_name`, `ood_quantile`, `max_rank`, `trust_neighbors`, `numerical_tolerance`. Relaxing any of them changes which model wins, so update the documented values accordingly.

## 🔑 Important Notes

1. **Several scripts take no CLI arguments**: all parameters in `wing_image_analysis.py`, `tip_setting_feasibility_check.py`, and `plot_hesperiidae_anisynta_cynone.py` are hard-coded at the top of the source. Only the three scripts under `ar_shape_contrast_5pct/` use `argparse`.

2. **The input directory name is fixed**: the batch pipeline reads only a directory named `wing_import` (non-recursive). Processing the reference set requires renaming `wing_import-ALL`, or copying images into `wing_import`.

3. **Output paths are relative**: `wing_image_analysis.py` writes with `open("summary_11.csv", "w")`, so the file lands in the **current working directory** — run it from `wing_image_feature_attract/`. Also, `setup_directories()` creates only `wing_import` and `edge_visual_data`, **not `wing_coordinate`**, which must already exist.

4. **`wing_coordinate` holds more files than the reference set**: 409 CSVs = 383 matching `wing_import-ALL` one-to-one + 26 extras (19 engineering/platform IDs, the specimens marked discarded in `readme.txt` — `Danainae-10/19`, `Lycaenidae-17`, `Riodinidae-15` — and 3 misspelled `Papillionidae_*` duplicates). By naming: 325 are `<taxon>-<number>` and 84 contain an underscore (66 species-level names, 18 platform IDs).

5. **The `is_wing_root` column is effectively empty**: across all 500 293 data rows in the 409 coordinate CSVs, the column is **always `NO` — `YES` never occurs**, because `main_func.process_single_image` writes `YES` only on exact floating-point equality between the coordinate and the red dot, which never holds. **Read root coordinates from the `root_x_px` / `root_y_px` fields in the AR results instead.**

6. **`forewing_data` raw image counts disagree with `readme.txt`**: the directory holds 387 images (353 specimen photographs + 34 `ref1-5` reference images), while `readme.txt` claims 383 and gives a per-taxon breakdown that does not match (e.g. Danainae 21 vs. an actual 18, Pieridae 35 vs. 27, Satyrinae 27 vs. 17). **Only the [refs.xlsx](forewing_data/refs.xlsx) species sum (9+10+9+1+66+288 = 383) and the 383 files in `wing_import-ALL` agree** — 383 describes the **processed** set, not the raw file count. Note also that `Limenitidinae/ref1-5` is empty and `Pieridae/` itself contains no files (only the `Coliadinae/` and `Pierinae/` subdirectories).

7. **`main_func.py` has no `__main__` entry point**: it is a library module imported by `wing_image_analysis.py`; running it directly does nothing. Line 3, `from main_func import *`, is a self-import — redundant but harmless.

8. **`section_tool.py` is currently unreferenced**: no `.py` file imports it (it appears only in the `.pyproj` and `readme.txt`). Its `check_edge` calls the blocking `plt.show()`.

9. **Excel outputs depend on an unobtainable Node package**: every `.xlsx` report is produced by `.mjs` scripts invoking `@oai/artifact-tool` through `subprocess`, and that package is not on the public npm registry. Python only produces CSV/JSON, so `--skip-workbook` is the recommended usage without code changes.

10. **`.gitignore` conflicts with tracked files**: it ignores `*.csv`, `results/`, `outputs/`, and `fine_search_results/`, yet `summary_11.csv`, `wing_coordinate/*.csv`, `ar_shape_contrast_5pct/outputs/**`, and `UMAP+Kmeans/fine_search_results/**` are all tracked (added early or force-added). New files of those types will not be staged automatically — use `git add -f`.

11. **The repository is large**: `UMAP+Kmeans/reference_umap_feature_search/reference_umap_feature_search_all_results.csv` alone is 113 MB (≈108.6 MiB, the largest file in the repo), plus `seed_summary.csv` (1.7 MB), `top_single_runs.csv` (1.2 MB), and a ~10 MB AR results JSON. Two `node_modules/` copies of 8 528 files each remain as well. A shallow clone saves considerable time.

12. **A phantom script in the old docs**: the `wing_ar_analysis.py` mentioned in [ar_shape_contrast_5pct/readme.txt](wing_image_feature_attract/ar_shape_contrast_5pct/readme.txt) **does not exist in this repository**; the corresponding real file is [build_representative_ar_workbook.mjs](wing_image_feature_attract/ar_shape_contrast_5pct/build_representative_ar_workbook.mjs) in the same directory. A separate [build_wing_ar_workbook.mjs](wing_image_feature_attract/build_wing_ar_workbook.mjs) sits at the pipeline root.

13. **Environment consistency and path provenance**: the model manifests record the fine-search environment as Python 3.11.7 / scikit-learn 1.7.2 / umap-learn 0.5.11 / numpy 1.26.4, whereas the audit `summary.json` records Python 3.12.3 / numpy 2.4.4 / pandas 3.0.2. For cross-version reproduction, follow the pinned versions in [UMAP+Kmeans/readme.txt](UMAP+Kmeans/readme.txt). Also, the absolute paths stored in the manifests come from **sibling directories** (`UMAP+Kmeans_new\`, `New\wing_image_feature_attract\`), not from this repository; validation compares only the `summary_11.xlsx` SHA-256 (`3cd88241…`), which matches locally, so the different paths do not block re-computation.

14. **`audit_kmeans_random_state.py` hard-codes a run ID** (`20260926_234406_930698`) in its default `--labels` path, tying it to that specific fine-search result. Pass `--labels` explicitly when using a different run directory.

15. **Image marking convention**: images must carry a **red wing-root marker** (otherwise `detect_red_dot` returns `None`; the script warns and continues, but planform standardization becomes unreliable). A blue wing-tip marker is optional and, when present, takes precedence over algorithmic detection. Measurements in `tip_setting_feasibility_check` show that all 4 inspected specimens lacked a blue marker and fell back to the algorithmic tip.

16. **Data provenance and licensing**: the imagery comes from 6 public sources, listed individually in [forewing_data/refs.xlsx](forewing_data/refs.xlsx) (of which `https://www.butterfliesofamerica.com/` supplies 288 species, 75%). The code is released under the MIT license, but **redistribution of the image data must follow the terms of the original sources**.

## 📚 References

**Data sources** (see [forewing_data/refs.xlsx](forewing_data/refs.xlsx) for all 383 species)

1. Patil, S., & Magdum, S. (2017). Insight into wing venation in butterflies belonging to families Papilionidae, Nymphalidae and Pieridae from Dang Dist Gujarat, India. *Journal of Entomology and Zoology Studies*, 5, 1596–1607.
2. Gu, W. Internet dataset 1 & 2.
3. Davis, A. K., & Holden, M. T. (2015). Measuring intraspecific variation in flight-related morphology of monarch butterflies (*Danaus plexippus*): Which sex has the best flying gear? *Journal of Insects*, 2015, 591705. https://doi.org/10.1155/2015/591705
4. Butterfly Conservation SA Inc. https://butterflyconservationsa.net.au/
5. Butterflies of America. https://www.butterfliesofamerica.com/

**Methods and tools**

6. McInnes, L., Healy, J., & Melville, J. (2018). UMAP: Uniform Manifold Approximation and Projection for dimension reduction. *arXiv:1802.03426*.
7. Arthur, D., & Vassilvitskii, S. (2007). k-means++: The advantages of careful seeding. *SODA*, 1027–1035.
8. Pedregosa, F., et al. (2011). Scikit-learn: Machine learning in Python. *JMLR*, 12, 2825–2830.
9. Rousseeuw, P. J. (1987). Silhouettes: A graphical aid to the interpretation and validation of cluster analysis. *Journal of Computational and Applied Mathematics*, 20, 53–65.
10. Davies, D. L., & Bouldin, D. W. (1979). A cluster separation measure. *IEEE TPAMI*, 1(2), 224–227.
11. Venna, J., & Kaski, S. (2006). Local multidimensional scaling. *Neural Networks*, 19(6–7), 889–899. (trustworthiness measure)
12. Savitzky, A., & Golay, M. J. E. (1964). Smoothing and differentiation of data by simplified least squares procedures. *Analytical Chemistry*, 36(8), 1627–1639.
13. Bradski, G. (2000). The OpenCV Library. *Dr. Dobb's Journal of Software Tools*.

## 📧 Contact

Questions and suggestions are welcome:

- Open an issue on GitHub: https://github.com/NEAR-the-future/butterfly-forewing-morphospace
- Read the sub-pipeline documentation: [wing_image_feature_attract/readme.txt](wing_image_feature_attract/readme.txt), [UMAP+Kmeans/readme.txt](UMAP+Kmeans/readme.txt), [ar_shape_contrast_5pct/readme.txt](wing_image_feature_attract/ar_shape_contrast_5pct/readme.txt)

---

**Version**: v1.0  
**Last updated**: September 2026  
**Author**: NEAR the future  
**License**: MIT (see [LICENSE](LICENSE))
