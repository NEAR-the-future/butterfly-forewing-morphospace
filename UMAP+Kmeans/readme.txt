# Verified with Python 3.11.7. Preserve versions when reproducing saved models.
numpy==1.26.4
pandas==2.1.4
scipy==1.11.4
scikit-learn==1.7.2
umap-learn==0.5.11
numba==0.59.0
llvmlite==0.42.0
pynndescent==0.6.0
joblib==1.2.0
threadpoolctl==3.5.0
matplotlib==3.8.0
openpyxl==3.0.10


# UMAP and KMeans Morphology Clustering Pipeline

## Overview

This repository contains a workflow for clustering butterfly wing
morphology based on quantitative feature measurements.

The pipeline has three main purposes:

1.  Search for suitable morphology feature combinations.
2.  Build a UMAP + KMeans reference clustering model.
3.  Project new samples into the existing morphology space.

The workflow is designed for reproducible unsupervised morphology
analysis.

------------------------------------------------------------------------

# Workflow

    Morphology feature table
            |
            v
    Feature selection and preprocessing
            |
            v
    UMAP embedding search
            |
            v
    KMeans clustering
            |
            v
    Best reference model
            |
            v
    New sample projection

------------------------------------------------------------------------

# Main Scripts

## 1. auto_umap_feature_set_search.py 

Purpose:

Find good combinations of morphology features and clustering parameters.

It searches:

-   feature subsets
-   UMAP parameters
-   KMeans cluster numbers

Input:

    summary_11.xlsx

Output:

Candidate UMAP and KMeans solutions for further refinement.

------------------------------------------------------------------------

## 2. explore_reference_umap_kmeans.py

Purpose:

Build the initial reference-only UMAP and KMeans model.

This script:

-   loads morphology features
-   standardizes the data
-   fits UMAP
-   applies KMeans clustering
-   saves the reference embedding

The reference dataset is the only dataset used for model fitting.

------------------------------------------------------------------------

## 3. fine_search_reference_umap_kmeans.py

Purpose:

Perform the final optimization of the clustering model.

It refines:

-   UMAP random seeds
-   UMAP neighbor parameters
-   UMAP minimum distance
-   KMeans cluster numbers

It exports the final model:

    best_reference_umap_model.joblib

This file contains the frozen UMAP reducer and KMeans model.

------------------------------------------------------------------------

## 4. fine_search_metrics.py

Purpose:

Evaluate clustering quality.

It calculates:

-   silhouette score
-   Davies-Bouldin index
-   cluster size balance
-   spatial distribution metrics

These metrics are combined into the final morphology clustering score.

------------------------------------------------------------------------

## 5. fine_search_guards.py

Purpose:

Check whether new samples are suitable for projection.

It evaluates:

-   distance from reference morphology space
-   nearest reference samples
-   embedding quality

This prevents unreliable projection of very different samples.

------------------------------------------------------------------------

## 6. project_summary_input_to_fine_umap.py

Purpose:

Project new samples into the trained morphology space.

Workflow:

    New sample features
            |
            v
    Saved preprocessing
            |
            v
    UMAP transform
            |
            v
    KMeans prediction
            |
            v
    Cluster assignment

Important:

The model is not retrained during projection.

------------------------------------------------------------------------

## 7. project_summary_input_to_fine_umap_ood_warning_only.py

Purpose:

Run projection with warning-only handling for out-of-distribution
samples.

Useful for exploratory visualization.

------------------------------------------------------------------------

## 8. audit_kmeans_random_state.py

Purpose:

Test KMeans clustering stability.

The script:

-   keeps UMAP coordinates fixed
-   reruns KMeans with different random states
-   compares clustering results

This checks whether the final clusters are reproducible.

------------------------------------------------------------------------

## 9. reference_model_io.py

Purpose:

Load and validate saved model files.

It checks that:

-   saved features match
-   UMAP coordinates are consistent
-   KMeans labels match
-   model artifacts are valid

------------------------------------------------------------------------

# Running Order

## Step 1: Build reference UMAP and KMeans model (make sure auto_umap_feature_set_search.py is in the same workspace)

python explore_reference_umap_kmeans.py


## Step 2: Refine the best candidates

python fine_search_reference_umap_kmeans.py


## Step 3: Project new samples

python project_summary_input_to_fine_umap.py


## Step 4: Audit clustering stability

python audit_kmeans_random_state.py


# File Relationship

    auto_umap_feature_set_search.py
                |
                v
    explore_reference_umap_kmeans.py
                |
                v
    fine_search_reference_umap_kmeans.py
                |
                +----------------+
                |                |
                v                v
    reference_model_io.py   project_summary_input_to_fine_umap.py
                                 |
                                 v
                        New sample clusters


    audit_kmeans_random_state.py
                |
                v
           Model stability check

------------------------------------------------------------------------

# Input Files

Main input:

    summary_11.xlsx

Reference morphology dataset.

Optional projection input:

    summary_input-all.xlsx

Contains samples to be projected into the reference UMAP space.

------------------------------------------------------------------------

# Output Files

Typical outputs:

    fine_search_results/

        best_reference_umap_model.joblib
        best_reference_umap_manifest.json
        run_status.json

The final model can be reused for future morphology projection without
retraining.

------------------------------------------------------------------------

# Summary

This project provides a complete workflow:

1.  Select morphology features.
2.  Optimize UMAP and KMeans parameters.
3.  Generate a frozen reference morphology map.
4.  Project new samples into the map.
5.  Validate clustering stability.

The final output is a reproducible UMAP based morphology clustering
model.