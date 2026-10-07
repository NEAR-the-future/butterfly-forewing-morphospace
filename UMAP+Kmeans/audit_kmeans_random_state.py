"""Audit K-means random-state sensitivity on the frozen UMAP embedding.

The audit refits only K-means.  It never refits UMAP or changes the saved
two-dimensional reference coordinates.  Partition equality is evaluated up
to a permutation of numeric cluster identifiers.
"""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.metrics import (
    adjusted_rand_score,
    davies_bouldin_score,
    silhouette_score,
)
from threadpoolctl import threadpool_limits


HERE = Path(__file__).resolve().parent
DEFAULT_LABELS = (
    HERE
    / "fine_search_results"
    / "20260926_234406_930698"
    / "best_reference_labels.csv"
)
DEFAULT_OUTPUT = HERE / "kmeans_random_state_audit"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS,
        help="Frozen-reference CSV containing UMAP coordinates and cluster labels.",
    )
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-count", type=int, default=100)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--require-identical",
        action="store_true",
        help="Exit non-zero if any tested seed changes the saved partition.",
    )
    args = parser.parse_args()
    if args.seed_start < 0 or args.seed_count < 1:
        parser.error("--seed-start must be nonnegative and --seed-count positive.")
    return args


def same_partition(left: np.ndarray, right: np.ndarray) -> bool:
    """Return True when two partitions differ at most by label numbering."""

    if left.shape != right.shape:
        return False
    return bool(
        np.array_equal(
            left[:, np.newaxis] == left[np.newaxis, :],
            right[:, np.newaxis] == right[np.newaxis, :],
        )
    )


def align_to_reference(reference: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    

    reference_values = np.unique(reference)
    candidate_values = np.unique(candidate)
    overlap = np.zeros(
        (len(reference_values), len(candidate_values)), dtype=np.int64
    )
    for row, reference_value in enumerate(reference_values):
        for column, candidate_value in enumerate(candidate_values):
            overlap[row, column] = np.count_nonzero(
                (reference == reference_value) & (candidate == candidate_value)
            )
    rows, columns = linear_sum_assignment(-overlap)
    mapping = {
        candidate_values[column]: reference_values[row]
        for row, column in zip(rows, columns)
    }
    return np.asarray([mapping[value] for value in candidate], dtype=reference.dtype)


def main() -> None:
    args = parse_args()
    frame = pd.read_csv(args.labels)
    required = {
        "Reference_UMAP1",
        "Reference_UMAP2",
        "Reference_KMeans_Cluster",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    coordinates = frame.loc[:, ["Reference_UMAP1", "Reference_UMAP2"]].to_numpy(
        dtype=np.float64
    )
    baseline_labels = frame["Reference_KMeans_Cluster"].to_numpy(dtype=int)
    if not np.isfinite(coordinates).all():
        raise ValueError("Frozen UMAP coordinates must all be finite.")
    cluster_count = int(np.unique(baseline_labels).size)
    if cluster_count < 2:
        raise ValueError("The saved partition must contain at least two clusters.")

    baseline_silhouette = float(silhouette_score(coordinates, baseline_labels))
    baseline_dbi = float(davies_bouldin_score(coordinates, baseline_labels))
    records: list[dict[str, float | int | bool | str]] = []
    seeds = range(args.seed_start, args.seed_start + args.seed_count)

    with threadpool_limits(limits=1):
        for seed in seeds:
            model = KMeans(
                n_clusters=cluster_count,
                init="k-means++",
                n_init=20,
                max_iter=300,
                random_state=seed,
            )
            labels = model.fit_predict(coordinates)
            aligned_labels = align_to_reference(baseline_labels, labels)
            changed_rows = np.flatnonzero(aligned_labels != baseline_labels)
            changed_original_indices = (
                frame.iloc[changed_rows]["Reference_Original_Index"].astype(int).tolist()
                if "Reference_Original_Index" in frame.columns
                else changed_rows.astype(int).tolist()
            )
            changed_names = (
                frame.iloc[changed_rows]["Name"].astype(str).tolist()
                if "Name" in frame.columns
                else []
            )
            records.append(
                {
                    "random_state": seed,
                    "same_partition_up_to_label_permutation": same_partition(
                        baseline_labels, labels
                    ),
                    "adjusted_rand_index_vs_saved": float(
                        adjusted_rand_score(baseline_labels, labels)
                    ),
                    "changed_reference_count_after_label_matching": int(
                        len(changed_rows)
                    ),
                    "changed_reference_original_indices": "; ".join(
                        str(value) for value in changed_original_indices
                    ),
                    "changed_reference_names": "; ".join(changed_names),
                    "silhouette": float(silhouette_score(coordinates, labels)),
                    "davies_bouldin_index": float(
                        davies_bouldin_score(coordinates, labels)
                    ),
                    "inertia": float(model.inertia_),
                    "iterations": int(model.n_iter_),
                }
            )

    results = pd.DataFrame.from_records(records)
    all_same = bool(results["same_partition_up_to_label_permutation"].all())
    summary = {
        "input": str(args.labels.resolve()),
        "reference_sample_count": int(len(frame)),
        "cluster_count": cluster_count,
        "tested_seed_start": int(args.seed_start),
        "tested_seed_count": int(args.seed_count),
        "tested_seed_end_inclusive": int(args.seed_start + args.seed_count - 1),
        "kmeans_protocol": {
            "init": "k-means++",
            "n_init": 20,
            "max_iter": 300,
        },
        "all_partitions_match_saved_up_to_label_permutation": all_same,
        "matching_partition_count": int(
            results["same_partition_up_to_label_permutation"].sum()
        ),
        "maximum_changed_reference_count_after_label_matching": int(
            results["changed_reference_count_after_label_matching"].max()
        ),
        "changed_reference_names_across_tested_seeds": sorted(
            {
                name
                for names in results["changed_reference_names"]
                for name in str(names).split("; ")
                if name
            }
        ),
        "adjusted_rand_index_min": float(
            results["adjusted_rand_index_vs_saved"].min()
        ),
        "adjusted_rand_index_max": float(
            results["adjusted_rand_index_vs_saved"].max()
        ),
        "saved_partition_silhouette": baseline_silhouette,
        "tested_silhouette_min": float(results["silhouette"].min()),
        "tested_silhouette_max": float(results["silhouette"].max()),
        "saved_partition_davies_bouldin_index": baseline_dbi,
        "tested_davies_bouldin_index_min": float(
            results["davies_bouldin_index"].min()
        ),
        "tested_davies_bouldin_index_max": float(
            results["davies_bouldin_index"].max()
        ),
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output_dir / "per_seed_results.csv", index=False)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.require_identical and not all_same:
        raise SystemExit(
            "At least one tested random state changed the saved partition; "
            "inspect per_seed_results.csv."
        )


if __name__ == "__main__":
    main()
