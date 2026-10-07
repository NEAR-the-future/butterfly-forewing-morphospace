import numpy as np
from sklearn.metrics import davies_bouldin_score, silhouette_score


EPS = 1e-12
SCORE_WEIGHTS = {
    "silhouette_weight": 1.4,
    "dbi_weight": 0.12,
    "smallest_cluster_ratio_weight": 2.0,
    "second_smallest_cluster_ratio_weight": 1.0,
    "cluster_size_entropy_weight": 1.0,
    "max_cluster_ratio_penalty_weight": 5.0,
    "spatial_occupancy_entropy_weight": 1.5,
}


def _size_summary(unique, counts):
    sorted_counts = np.sort(counts)
    n_samples = int(np.sum(counts))
    smallest = float(sorted_counts[0] / n_samples) if n_samples else np.nan
    second = float(sorted_counts[1] / n_samples) if len(counts) >= 2 else 0.0
    ratios = counts / n_samples if n_samples else np.array([], dtype=float)
    positive = ratios[ratios > EPS]
    entropy = -float(np.sum(positive * np.log(positive))) if len(positive) else 0.0
    if len(counts) > 1:
        entropy = entropy / float(np.log(len(counts)))
    return {
        "class_count": int(len(unique)),
        "cluster_count": int(len(unique)),
        "min_cluster_size": int(counts.min()) if len(counts) else 0,
        "max_cluster_size": int(counts.max()) if len(counts) else 0,
        "smallest_cluster_ratio": smallest,
        "second_smallest_cluster_ratio": second,
        "smallest_two_cluster_ratio": smallest + second if np.isfinite(smallest) else np.nan,
        "max_cluster_ratio": float(np.max(ratios)) if len(ratios) else np.nan,
        "cluster_size_entropy": float(np.clip(entropy, 0.0, 1.0)),
        "cluster_sizes": "; ".join(f"{label}:{count}" for label, count in zip(unique, counts)),
    }


def _occupancy_summary(z, labels, unique):
    volumes = []
    for label in unique:
        points = z[labels == label]
        if len(points) < 4:
            volumes.append(0.0)
            continue
        low = np.nanpercentile(points, 10, axis=0)
        high = np.nanpercentile(points, 90, axis=0)
        side = np.maximum(high - low, 0.0)
        volume = float(np.prod(side))
        volumes.append(volume if np.isfinite(volume) else 0.0)
    volumes = np.asarray(volumes, dtype=float)
    volume_sum = float(np.sum(volumes))
    if volume_sum > EPS:
        ratios = volumes / volume_sum
        positive = ratios[ratios > EPS]
        entropy = -float(np.sum(positive * np.log(positive))) if len(positive) else 0.0
        if len(unique) > 1:
            entropy = entropy / float(np.log(len(unique)))
    else:
        ratios = np.zeros_like(volumes)
        entropy = 0.0
    return {
        "spatial_occupancy_entropy": float(np.clip(entropy, 0.0, 1.0)),
        "spatial_occupancy_min_ratio": float(np.min(ratios)) if len(ratios) else np.nan,
        "spatial_occupancy_max_ratio": float(np.max(ratios)) if len(ratios) else np.nan,
        "spatial_occupancy_ratios": "; ".join(
            f"{label}:{ratio:.6f}" for label, ratio in zip(unique, ratios)
        ),
        "spatial_occupancy_volumes": "; ".join(
            f"{label}:{volume:.6g}" for label, volume in zip(unique, volumes)
        ),
    }


def evaluate_partition(
    Z,
    labels,
    silhouette_threshold=0.5,
    min_cluster_size_abs=10,
    min_cluster_size_frac=0.03,
    target_range=(3, 9),
):

    z = np.asarray(Z, dtype=np.float64)
    labels = np.asarray(labels)
    if z.ndim != 2 or z.shape[1] == 0 or labels.ndim != 1 or len(z) != len(labels):
        raise ValueError("Z must be a 2D coordinate array aligned with 1D labels.")
    if not np.isfinite(z).all():
        raise ValueError("Partition coordinates must be finite.")
    if labels.dtype.kind in "biufc" and not np.isfinite(labels).all():
        raise ValueError("Partition labels must be finite.")
    if (not isinstance(min_cluster_size_abs, (int, np.integer))
            or min_cluster_size_abs < 0
            or not np.isfinite(min_cluster_size_frac)
            or not 0 <= min_cluster_size_frac <= 1):
        raise ValueError("Minimum cluster size requires a nonnegative integer and a fraction in [0, 1].")
    if not np.isfinite(silhouette_threshold):
        raise ValueError("silhouette_threshold must be finite.")
    if (len(target_range) != 2
            or any(not isinstance(value, (int, np.integer)) for value in target_range)
            or target_range[0] < 2 or target_range[0] > target_range[1]):
        raise ValueError("target_range must be an ordered pair of integer cluster counts >= 2.")

    unique, counts = np.unique(labels, return_counts=True)
    row = _size_summary(unique, counts)
    row.update(_occupancy_summary(z, labels, unique))
    n_samples, n_groups = len(labels), len(unique)
    valid = bool(2 <= n_groups < n_samples)
    min_required = max(int(min_cluster_size_abs), int(np.ceil(min_cluster_size_frac * n_samples)))
    in_target = bool(target_range[0] <= n_groups <= target_range[1])
    size_valid = bool(n_groups > 0 and row["min_cluster_size"] >= min_required)
    silhouette = float(silhouette_score(z, labels)) if valid else np.nan
    dbi = float(davies_bouldin_score(z, labels)) if valid else np.nan
    silhouette_valid = bool(np.isfinite(silhouette) and silhouette >= silhouette_threshold)
    score = np.nan
    if valid and np.isfinite(silhouette):

        score = float(
            SCORE_WEIGHTS["silhouette_weight"] * silhouette
            - SCORE_WEIGHTS["dbi_weight"] * (dbi if np.isfinite(dbi) else 0.0)
            + SCORE_WEIGHTS["smallest_cluster_ratio_weight"] * row["smallest_cluster_ratio"]
            + SCORE_WEIGHTS["second_smallest_cluster_ratio_weight"] * row["second_smallest_cluster_ratio"]
            + SCORE_WEIGHTS["cluster_size_entropy_weight"] * row["cluster_size_entropy"]
            - SCORE_WEIGHTS["max_cluster_ratio_penalty_weight"] * row["max_cluster_ratio"]
            + SCORE_WEIGHTS["spatial_occupancy_entropy_weight"] * row["spatial_occupancy_entropy"]
        )
    row.update({
        "partition_valid": valid,
        "partition_status": "ok" if valid else "requires_2_to_n_minus_1_groups",
        "class_count_valid": valid,
        "in_target_cluster_range": in_target,
        "cluster_size_valid": size_valid,
        "required_min_cluster_size": min_required,
        "raw_silhouette": silhouette,
        "silhouette": silhouette,
        "silhouette_threshold_valid": silhouette_valid,
        "davies_bouldin": dbi,
        "score": score,
        "selection_valid": bool(valid and in_target and size_valid and silhouette_valid),
    })
    return row
