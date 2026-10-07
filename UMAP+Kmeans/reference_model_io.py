
import hashlib

import joblib
import numpy as np


def load_reference(path):
    artifact = joblib.load(path)
    if artifact.get("schema_version") != 1:
        raise ValueError("Expected schema_version=1 in the reference model artifact.")
    if artifact.get("workflow") != "reference_fit_then_unseen_transform":
        raise ValueError("Expected a reference_fit_then_unseen_transform artifact.")
    x = np.asarray(artifact["reference_processed_features"], dtype=np.float64)
    z = np.asarray(artifact["reference_coordinates"], dtype=np.float64)
    labels = np.asarray(artifact["reference_clusters"], dtype=int)
    reducer = artifact["umap_reducer"]
    kmeans = artifact["kmeans_model"]
    if (x.ndim != 2 or z.ndim != 2 or labels.ndim != 1
            or x.shape[0] != z.shape[0] or len(labels) != len(x)
            or len(artifact["reference_table"]) != len(x)
            or x.shape[1] != len(artifact["selected_features"])):
        raise ValueError("Reference features, coordinates, labels, and rows are not aligned.")
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("The saved processed reference arrays must be finite.")
    if not np.array_equal(z, np.asarray(reducer.embedding_, dtype=np.float64)):
        raise ValueError("Reference coordinates differ from the saved UMAP embedding.")
    raw = np.asarray(reducer._raw_data)
    if not np.array_equal(x.astype(raw.dtype), raw):
        raise ValueError("Processed reference rows differ from UMAP's original fit input.")
    if not np.array_equal(labels, np.asarray(kmeans.labels_)):
        raise ValueError("Reference labels differ from the saved KMeans labels.")
    expected_hash = artifact.get("metadata", {}).get("reference_coordinates_sha256")
    if expected_hash and hashlib.sha256(z.tobytes()).hexdigest() != expected_hash:
        raise ValueError("Reference coordinate hash does not match the artifact metadata.")
    return artifact, x, z, labels, reducer, kmeans
