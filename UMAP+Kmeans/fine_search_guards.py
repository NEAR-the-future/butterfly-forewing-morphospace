"""Hard guards using reference-only full-feature calibration and frozen queries.

The global threshold preserves the supplied baseline model; it is not an
independently established universal cutoff. Query rank checks use the selected
2D nearest reference row's rank in full feature space, never cluster labels.
"""

import json

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.manifold import trustworthiness
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import StandardScaler


def full_space_rank(distances, index):
    """One plus the count of strictly closer references; ties share rank."""
    values = np.asarray(distances, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all() or not 0 <= index < len(values):
        raise ValueError("Rank requires finite 1D distances and a valid reference index.")
    return int(1 + np.count_nonzero(values < values[index]))


def trustworthiness_passes(value, baseline, tolerance=1e-12):
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Numerical tolerance must be finite and nonnegative.")
    return bool(np.isfinite(value) and np.isfinite(baseline) and value + tolerance >= baseline)


def combine_selection_eligibility(score, guard_results):
    """A finite single-run score is eligible only after every hard guard passes."""
    return bool(np.isfinite(score) and all(guard_results.get(key) is True for key in (
        "exact_neighbor_guard_passed", "rank_guard_passed", "trustworthiness_guard_passed")))


def build_guard_context(reference, inputs, full_features, name_col, baseline_z,
                        exact_guard_name="AirPulse", ood_quantile=0.985, max_rank=50,
                        trust_neighbors=10, numerical_tolerance=1e-12):
    """Fit calibration on references only, select OOD-passing input rows once."""
    if not 0 < ood_quantile < 1 or not isinstance(max_rank, int) or max_rank < 1:
        raise ValueError("OOD quantile must be in (0,1); maximum rank must be a positive integer.")
    if not isinstance(trust_neighbors, int) or not 0 < trust_neighbors < len(reference) / 2:
        raise ValueError("Trustworthiness neighbors must be a positive integer below n_reference/2.")
    trustworthiness_passes(1, 1, numerical_tolerance)
    ref_raw = reference.loc[:, full_features].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    query_raw = inputs.loc[:, full_features].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    ref_raw[~np.isfinite(ref_raw)] = np.nan
    query_raw[~np.isfinite(query_raw)] = np.nan
    if np.any(np.all(np.isnan(ref_raw), axis=0)):
        raise ValueError("A full-space reference feature is entirely missing.")
    imputer, scaler = SimpleImputer(strategy="median"), StandardScaler()
    full_x = np.asarray(scaler.fit_transform(imputer.fit_transform(ref_raw)), dtype=np.float64)
    full_queries = np.asarray(scaler.transform(imputer.transform(query_raw)), dtype=np.float64)
    ref_distances = pairwise_distances(full_x)
    np.fill_diagonal(ref_distances, np.inf)
    loo_nn = np.min(ref_distances, axis=1)
    threshold = float(np.quantile(loo_nn, ood_quantile))
    # Direct Euclidean norm matches the original exact-neighbor guard.
    distances = np.linalg.norm(full_queries[:, None, :] - full_x[None, :, :], axis=2)
    closest = np.argmin(distances, axis=1)
    nearest_distances = distances[np.arange(len(inputs)), closest]
    selected = np.flatnonzero(nearest_distances <= threshold)
    names = inputs[name_col].astype(str).str.strip().tolist()
    exact_matches = [i for i, name in enumerate(names) if name == exact_guard_name]
    if len(exact_matches) != 1:
        raise ValueError(f"Expected exactly one exact guard input named {exact_guard_name!r}.")
    exact_input_index = exact_matches[0]
    if exact_input_index not in selected:
        raise ValueError("The exact guard input must pass the reference-only OOD calibration.")
    if len({names[i] for i in selected}) != len(selected):
        raise ValueError("OOD-passing guard input names must be unique.")
    z = np.asarray(baseline_z, dtype=np.float64)
    if z.ndim != 2 or len(z) != len(reference) or not np.isfinite(z).all():
        raise ValueError("Baseline coordinates must align with all finite reference rows.")
    baseline = float(trustworthiness(full_x, z, n_neighbors=trust_neighbors))
    reference_names = reference[name_col].astype(str).tolist()
    assessments = []
    query_neighbors = []
    for i, name in enumerate(names):
        assessment = {"input_row_index": i, "input_name": name,
                      "input_missing_feature_count": int(np.isnan(query_raw[i]).sum()),
                      "nearest_reference_index": int(closest[i]),
                      "nearest_reference_name": reference_names[closest[i]],
                      "nearest_full11_distance": float(nearest_distances[i]),
                      "ood_passed": bool(nearest_distances[i] <= threshold)}
        assessments.append(assessment)
        if i in selected:
            # All references, not merely top50: ties at the boundary are auditable.
            order = np.argsort(distances[i], kind="stable")
            query_neighbors.append({"input_row_index": i, "input_name": name,
                                    "reference_indices_by_distance": order.tolist(),
                                    "full11_distances_by_reference_index": distances[i].tolist(),
                                    "top50_reference_names": [reference_names[j] for j in order[:max_rank]]})
    exact_position = int(np.flatnonzero(selected == exact_input_index)[0])
    exact_reference = int(closest[exact_input_index])
    spec = {
        "guard_version": "exact_input_plus_ood_query_rank_plus_baseline_trustworthiness_v1",
        "ood_quantile": ood_quantile, "ood_distance_threshold": threshold,
        "ood_fit_population": "all reference rows only; input rows never used for fitting or calibration",
        "ood_distance": "Euclidean after reference-only median imputation and StandardScaler",
        "reference_loo_nearest_distances": loo_nn.tolist(),
        "full_features": list(full_features), "reference_names_by_index": reference_names,
        "reference_imputer_medians": imputer.statistics_.tolist(),
        "reference_scaler_means": scaler.mean_.tolist(), "reference_scaler_scales": scaler.scale_.tolist(),
        "ood_assessments": assessments, "query_names": [names[i] for i in selected],
        "query_row_indices": selected.tolist(), "query_count": len(selected),
        "query_full11_neighbors": query_neighbors,
        "exact_input_name": exact_guard_name, "exact_input_row_index": exact_input_index,
        "exact_query_position": exact_position, "exact_reference_index": exact_reference,
        "exact_reference_name": reference_names[exact_reference],
        "exact_reference_distance": float(nearest_distances[exact_input_index]),
        "max_rank_inclusive": max_rank, "rank_definition": "1 + count(distance < chosen_reference_distance); ties share rank",
        "trustworthiness_neighbors": trust_neighbors, "trustworthiness_baseline": baseline,
        "trustworthiness_numerical_tolerance": numerical_tolerance,
        "trustworthiness_baseline_policy": "Preserve the supplied saved baseline's full-feature reference trustworthiness; not a universal cutoff",
        "transform_mode": "row_wise_independent_transform",
        "evaluation_order": "trustworthiness and exact input always; remaining queries only if both pass",
    }
    return {"full_x": full_x, "query_full_distances": distances[selected],
            "query_indices": selected, "query_names": spec["query_names"],
            "exact_query_position": exact_position, "exact_reference_index": exact_reference,
            "reference_names": reference_names, "spec": spec}


def evaluate_embedding_guards(reducer, z, selected_queries, context, force_all=False):
    """Evaluate once per embedding; return JSON-safe metrics shared by every K."""
    spec = context["spec"]
    z = np.asarray(z, dtype=np.float64)
    selected_queries = np.asarray(selected_queries, dtype=np.float64)
    if len(selected_queries) != len(context["query_names"]):
        raise ValueError("Selected query rows do not match the fixed guard context.")
    if not np.isfinite(z).all() or not np.isfinite(selected_queries).all():
        raise ValueError("Guard coordinates and processed queries must be finite.")
    before = np.asarray(reducer.embedding_).copy()
    if not np.array_equal(z, np.asarray(before, dtype=np.float64)):
        raise RuntimeError("Reference coordinates differ from reducer before guard transforms.")
    score = float(trustworthiness(context["full_x"], z, n_neighbors=spec["trustworthiness_neighbors"]))
    t_pass = trustworthiness_passes(score, spec["trustworthiness_baseline"],
                                   spec["trustworthiness_numerical_tolerance"])
    details = [{"input_name": name, "input_row_index": int(index), "status": "not_evaluated"}
               for name, index in zip(context["query_names"], context["query_indices"])]

    def evaluate_query(position):
        query_z = np.asarray(reducer.transform(selected_queries[position:position + 1]), dtype=np.float64)
        if query_z.shape != (1, z.shape[1]) or not np.isfinite(query_z).all():
            raise RuntimeError("A row-wise query transform returned malformed coordinates.")
        if not np.array_equal(before, reducer.embedding_):
            raise RuntimeError("Guard transform changed frozen reference coordinates.")
        distances = np.linalg.norm(z - query_z[0], axis=1)
        nearest = int(np.argmin(distances))
        rank = full_space_rank(context["query_full_distances"][position], nearest)
        details[position].update(status="evaluated", nearest_reference_index=nearest,
                                 nearest_reference_name=context["reference_names"][nearest],
                                 nearest_2d_distance=float(distances[nearest]), full11_rank=rank,
                                 chosen_reference_full11_distance=float(context["query_full_distances"][position, nearest]),
                                 rank_passed=bool(rank <= spec["max_rank_inclusive"]))

    exact_position = context["exact_query_position"]
    evaluate_query(exact_position)
    exact_detail = details[exact_position]
    exact_pass = exact_detail["nearest_reference_index"] == context["exact_reference_index"]
    if force_all or (t_pass and exact_pass):
        for position in range(len(details)):
            if position != exact_position:
                evaluate_query(position)
    all_evaluated = all(row["status"] == "evaluated" for row in details)
    rank_pass = bool(all(row["rank_passed"] for row in details)) if all_evaluated else None
    rank_status = ("passed" if rank_pass else "failed") if all_evaluated else "not_evaluated"
    return {
        "hard_guards_passed": bool(t_pass and exact_pass and rank_pass is True),
        "exact_neighbor_guard_passed": bool(exact_pass), "neighbor_preserved": bool(exact_pass),
        "rank_guard_passed": rank_pass, "rank_guard_status": rank_status,
        "rank_guard_max_rank_inclusive": spec["max_rank_inclusive"],
        "rank_guard_max_observed_rank": max(row["full11_rank"] for row in details) if all_evaluated else None,
        "rank_guard_query_count": len(details),
        "trustworthiness_guard_passed": t_pass, "trustworthiness_full11_k10": score,
        "trustworthiness_baseline": spec["trustworthiness_baseline"],
        "trustworthiness_numerical_tolerance": spec["trustworthiness_numerical_tolerance"],
        "guard_transform_count": sum(row["status"] == "evaluated" for row in details),
        "guard_reference_coordinates_unchanged": True,
        "guard_query_diagnostics_json": json.dumps(details, ensure_ascii=False, sort_keys=True),
        "umap_space_nearest_names": exact_detail["nearest_reference_name"],
        "umap_space_nearest_original_indices": exact_detail["nearest_reference_index"],
        "umap_space_nearest_distances": exact_detail["nearest_2d_distance"],
    }
