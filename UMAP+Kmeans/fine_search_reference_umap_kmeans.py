"""Refine archived feature sets with three hard guards and unchanged J_morph.

Default: 10 feature sets x 15 UMAP seeds x 10 neighbors x 10 min_dist,
with K=3..9. Each embedding is reused for all K values. SQLite checkpoints
allow exact-plan resume. Use --dry-run to inspect the plan before fitting.
"""

import argparse
import hashlib
import itertools
import json
import os
import sqlite3
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import joblib
import numpy as np
import pandas as pd
import sklearn
import umap
from sklearn.base import clone
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from fine_search_metrics import evaluate_partition
from fine_search_guards import (build_guard_context, combine_selection_eligibility,
                                evaluate_embedding_guards)
from reference_model_io import load_reference


HERE = Path(__file__).resolve().parent
OLD = HERE / "reference_umap_feature_search"
DEFAULT_NEIGHBORS = [3, 4, 5, 6, 7, 8, 10, 12, 14, 20]
DEFAULT_MIN_DIST = [0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20]
SCHEMA_VERSION = 2
WORKFLOW_STAGE = "hard_guard_fine_reference_exploration_and_model_fit"


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str),
                         encoding="utf-8")
    temporary.replace(path)


def parse_values(text, converter):
    values = [converter(value.strip()) for value in text.split(",") if value.strip()]
    if not values or len(set(values)) != len(values):
        raise argparse.ArgumentTypeError("Lists must be nonempty and contain unique values.")
    return sorted(values)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        default=OLD / "reference_umap_feature_search_all_results.csv")
    parser.add_argument("--model-artifact", type=Path,
                        default=OLD / "best_reference_umap_model.joblib")
    parser.add_argument("--reference", type=Path, default=HERE / "summary_11.xlsx")
    parser.add_argument("--guard-input", type=Path, default=HERE / "summary_input-all.xlsx")
    parser.add_argument("--guard-name", default="AirPulse")
    parser.add_argument("--top-feature-sets", type=int, default=10)
    parser.add_argument("--seeds", type=lambda s: parse_values(s, int), default=list(range(15)))
    parser.add_argument("--neighbors", type=lambda s: parse_values(s, int), default=DEFAULT_NEIGHBORS)
    parser.add_argument("--min-dist", type=lambda s: parse_values(s, float), default=DEFAULT_MIN_DIST)
    parser.add_argument("--k-values", type=lambda s: parse_values(s, int), default=list(range(3, 10)))
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Write plan only, with no model fitting.")
    parser.add_argument("--resume", action="store_true", help="Resume --output-dir with exactly the same plan.")
    parser.add_argument("--max-embeddings", type=int, default=None,
                        help="Stop after this many NEW embeddings, keeping a resumable partial run.")
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--compute-stability", action="store_true",
                        help="Also compute all pairwise seed ARIs per configuration after the search.")
    args = parser.parse_args()
    if args.top_feature_sets < 1 or args.progress_every < 1:
        parser.error("Feature-set count and progress interval must be positive.")
    if args.max_embeddings is not None and args.max_embeddings < 1:
        parser.error("--max-embeddings must be positive.")
    if args.resume and args.output_dir is None:
        parser.error("--resume requires --output-dir.")
    if any(seed < 0 or seed > np.iinfo(np.uint32).max for seed in args.seeds):
        parser.error("Seeds must be uint32 integers.")
    if any(not np.isfinite(v) or v < 0 for v in args.min_dist):
        parser.error("min_dist values must be finite and nonnegative.")
    return args


def shortlist_archive(path, count):
    frame = pd.read_csv(path)
    required = {"selected_features", "feature_set_id", "selection_valid", "score",
                "umap_n_neighbors", "umap_min_dist", "kmeans_n_clusters", "silhouette"}
    if missing := required.difference(frame.columns):
        raise ValueError(f"Archive columns missing: {sorted(missing)}")
    frame["feature_signature"] = frame["selected_features"].map(
        lambda s: "; ".join(sorted(part.strip() for part in s.split(";"))))
    frame["score"] = pd.to_numeric(frame["score"], errors="raise")
    valid = frame["selection_valid"].astype(str).str.lower().eq("true")
    eligible = frame.loc[valid & np.isfinite(frame["score"])].copy()
    # Distinct feature sets, not the first N parameter/seed rows.
    selected = (eligible.sort_values(
        ["score", "silhouette", "feature_signature", "umap_n_neighbors", "umap_min_dist",
         "kmeans_n_clusters"], ascending=[False, False, True, True, True, True],
        kind="stable").drop_duplicates("feature_signature").head(count).copy())
    if len(selected) != count:
        raise ValueError(f"Only {len(selected)} eligible distinct feature sets, requested {count}.")
    selected.insert(0, "fine_feature_rank", range(1, count + 1))
    return selected, {
        "archived_feature_sets": int(frame["feature_signature"].nunique()),
        "eligible_feature_sets": int(eligible["feature_signature"].nunique()),
        "shortlist_rule": "max archived score per distinct feature set among selection_valid=True rows",
    }


def preprocess(frame, features):
    values = frame.loc[:, features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    values[~np.isfinite(values)] = np.nan
    if np.any(np.all(np.isnan(values), axis=0)):
        raise ValueError("A selected feature has no finite reference observations.")
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    x = scaler.fit_transform(imputer.fit_transform(values))
    return {"imputer": imputer, "scaler": scaler}, np.asarray(x, dtype=np.float64)


def transform(frame, features, preprocessor):
    values = frame.loc[:, features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    values[~np.isfinite(values)] = np.nan
    return preprocessor["scaler"].transform(preprocessor["imputer"].transform(values))


def prepare(args):
    artifact, _, old_z, old_labels, reducer, kmeans = load_reference(args.model_artifact)
    expected_hash = artifact["metadata"].get("reference_source_sha256")
    if not expected_hash or sha256_file(args.reference) != expected_hash:
        raise ValueError("Reference workbook differs from the archived search dataset. "
                         "Do not reuse its feature ranking with changed data.")
    reference = pd.read_excel(args.reference)
    if len(reference) != len(old_labels) or not np.asarray(artifact["reference_keep_mask"]).all():
        raise ValueError("This refinement requires the complete, unfiltered archived reference rows.")
    for values, label in ((args.neighbors, "neighbors"), (args.k_values, "K")):
        if any(value < 2 or value >= len(reference) for value in values):
            raise ValueError(f"Each {label} must be >=2 and smaller than the reference sample count.")
    if any(value > reducer.spread for value in args.min_dist):
        raise ValueError("min_dist cannot exceed the saved UMAP spread.")
    # Numerically verify the reconstructed scorer against the frozen baseline.
    baseline_metrics = evaluate_partition(old_z, old_labels,
                                         target_range=(min(args.k_values), max(args.k_values)))
    if not np.isclose(baseline_metrics["score"], artifact["best_result"]["score"],
                      rtol=0, atol=1e-10):
        raise ValueError("Reconstructed J_morph does not reproduce the saved baseline score.")
    shortlist, audit = shortlist_archive(args.archive, args.top_feature_sets)
    name_col = artifact["name_col"]
    label_col = artifact["label_col"]
    if reference[name_col].tolist() != artifact["reference_table"][name_col].tolist():
        raise ValueError("Reference row order differs from the saved baseline model.")
    full_features = [s.strip() for s in
                     artifact["best_result"]["feature_space_reference_features"].split(";")]
    guard_table = pd.read_excel(args.guard_input)
    guard_context = build_guard_context(reference, guard_table, full_features, name_col,
                                        old_z, exact_guard_name=args.guard_name)
    guard_spec = guard_context["spec"]
    guard_index = guard_spec["exact_input_row_index"]
    nearest = guard_context["exact_reference_index"]
    guard_rows = guard_table.iloc[guard_context["query_indices"]].copy()
    sets = []
    for row in shortlist.to_dict("records"):
        features = [s.strip() for s in row["selected_features"].split(";")]
        preprocessor, x = preprocess(reference, features)
        sets.append({"rank": int(row["fine_feature_rank"]), "features": features,
                     "old_feature_set_id": row["feature_set_id"],
                     "old_best_score": float(row["score"]), "preprocessor": preprocessor,
                     "x": x, "queries": transform(guard_rows, features, preprocessor),
                     "guard_context": guard_context})
    n_fits = len(sets) * len(args.seeds) * len(args.neighbors) * len(args.min_dist)
    plan = {
        "schema_version": SCHEMA_VERSION, "workflow_stage": WORKFLOW_STAGE,
        "ranking": "single_run_max_score",
        "selection_rule": "finite score AND exact-input nearest index preserved AND all OOD-passing query ranks <=50 AND full11 trustworthiness@10 >= measured baseline minus 1e-12; quality flags diagnostic only",
        "hard_guard_spec": guard_spec,
        "score_formula": "1.4*S - 0.12*DBI + 2*p_min + p_second + H_size - 5*p_max + 1.5*H_occupancy",
        "target_range_bonus": 0, "n_reference_samples": len(reference),
        "reference": str(args.reference.resolve()), "reference_sha256": sha256_file(args.reference),
        "archive": str(args.archive.resolve()), "archive_sha256": sha256_file(args.archive),
        "base_model": str(args.model_artifact.resolve()), "base_model_sha256": sha256_file(args.model_artifact),
        "guard_input": str(args.guard_input.resolve()), "guard_input_sha256": sha256_file(args.guard_input),
        "guard_name": args.guard_name, "guard_row_index": guard_index,
        "guard_feature_nearest_index": nearest,
        "guard_feature_nearest_name": str(reference.iloc[nearest][name_col]),
        "guard_feature_nearest_distance": guard_spec["exact_reference_distance"],
        "full_guard_features": full_features, "label_col": label_col, "name_col": name_col,
        "seeds": args.seeds, "neighbors": args.neighbors, "min_dist": args.min_dist,
        "k_values": args.k_values, "expected_umap_fits": n_fits,
        "expected_kmeans_evaluations": n_fits * len(args.k_values),
        "umap_parameters": reducer.get_params(), "kmeans_parameters": kmeans.get_params(),
        "fixed_transform_seed": int(reducer.transform_seed),
        "fixed_kmeans_seed": int(kmeans.random_state),
        "compute_stability": args.compute_stability,
        "versions": {"sklearn": sklearn.__version__, "umap": umap.__version__,
                     "numpy": np.__version__, "pandas": pd.__version__},
        "code_sha256": {name: sha256_file(HERE / name) for name in
                        ("fine_search_reference_umap_kmeans.py", "fine_search_metrics.py",
                         "fine_search_guards.py", "reference_model_io.py")},
        "shortlist_audit": audit,
        "feature_sets": [{key: entry[key] for key in
                          ("rank", "features", "old_feature_set_id", "old_best_score")} for entry in sets],
        "grid_design": "Shared nonuniform discrete grid; retains all old values and adds local refinement points.",
        "baseline_score_reproduced": baseline_metrics["score"],
    }
    return plan, shortlist, reference, sets, reducer, kmeans


def fit_embedding(template, entry, neighbors, min_dist, seed, force_all_guards=False):
    reducer = clone(template).set_params(n_neighbors=neighbors, min_dist=min_dist,
                                        random_state=seed, n_jobs=1)
    z = np.asarray(reducer.fit_transform(entry["x"]), dtype=np.float64)
    guards = evaluate_embedding_guards(reducer, z, entry["queries"], entry["guard_context"],
                                      force_all=force_all_guards)
    return reducer, z, guards


def run_key(rank, neighbors, min_dist, seed):
    return json.dumps([rank, neighbors, min_dist, seed], separators=(",", ":"))


def connect_checkpoint(path, plan):
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY, plan TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS runs (key TEXT PRIMARY KEY, rows_json TEXT NOT NULL, labels BLOB NOT NULL)")
    canonical = json.dumps(plan, sort_keys=True, default=str)
    stored = connection.execute("SELECT plan FROM metadata WHERE id=1").fetchone()
    if stored and stored[0] != canonical:
        connection.close()
        raise ValueError("Resume plan differs from checkpoint: inputs, parameters, seeds, or software versions changed.")
    if not stored:
        connection.execute("INSERT INTO metadata VALUES (1,?)", (canonical,))
        connection.commit()
    return connection


def read_results(connection):
    records = []
    for (payload,) in connection.execute("SELECT rows_json FROM runs ORDER BY rowid"):
        records.extend(json.loads(payload))
    return pd.DataFrame.from_records(records)


def rank_results(frame):
    return frame.sort_values(
        ["selection_valid", "score", "silhouette", "fine_feature_rank", "umap_n_neighbors",
         "umap_min_dist", "umap_seed", "kmeans_n_clusters"],
        ascending=[False, False, False, True, True, True, True, True], kind="stable")


def export_results(connection, output, plan, complete):
    frame = read_results(connection)
    if frame.empty:
        return frame
    ranked = rank_results(frame)
    ranked.to_csv(output / "fine_search_all_results.csv", index=False, encoding="utf-8-sig")
    eligible = ranked.loc[ranked["selection_valid"]]
    eligible.head(1000).to_csv(output / "top_single_runs.csv", index=False, encoding="utf-8-sig")
    eligible.drop_duplicates("fine_feature_rank").to_csv(
        output / "best_per_feature_set.csv", index=False, encoding="utf-8-sig")
    group_cols = ["fine_feature_rank", "selected_features", "umap_n_neighbors",
                  "umap_min_dist", "kmeans_n_clusters"]
    summary = (frame.groupby(group_cols, sort=False, dropna=False).agg(
        seeds_completed=("umap_seed", "size"), score_max=("score", "max"),
        score_median=("score", "median"), score_mean=("score", "mean"),
        score_min=("score", "min"), exact_guard_pass_rate=("exact_neighbor_guard_passed", "mean"),
        trustworthiness_guard_pass_rate=("trustworthiness_guard_passed", "mean"),
        rank_guard_evaluated_count=("rank_guard_passed", "count"),
        rank_guard_pass_rate_among_evaluated=("rank_guard_passed", "mean"),
        hard_guard_pass_rate=("hard_guards_passed", "mean"),
        quality_pass_rate=("quality_valid", "mean"), eligible_rate=("selection_valid", "mean"))
        .reset_index())
    summary["expected_seeds"] = len(plan["seeds"])
    summary["all_seeds_completed"] = summary["seeds_completed"].eq(len(plan["seeds"]))
    summary.to_csv(output / "seed_summary.csv", index=False, encoding="utf-8-sig")
    if complete and plan["compute_stability"]:
        # Compute pairwise ARI within each fixed (features, neighbors, min_dist, K).
        labels_by_group = {}
        for payload, packed in connection.execute("SELECT rows_json, labels FROM runs"):
            rows = json.loads(payload)
            labels = np.frombuffer(zlib.decompress(packed), dtype=np.int32).reshape(
                len(plan["k_values"]), plan["n_reference_samples"])
            for index, row in enumerate(rows):
                key = (row["fine_feature_rank"], row["umap_n_neighbors"], row["umap_min_dist"],
                       row["kmeans_n_clusters"])
                labels_by_group.setdefault(key, []).append(labels[index])
        stability = []
        for key, labels in labels_by_group.items():
            scores = [adjusted_rand_score(a, b) for a, b in itertools.combinations(labels, 2)]
            stability.append({"fine_feature_rank": key[0], "umap_n_neighbors": key[1],
                              "umap_min_dist": key[2], "kmeans_n_clusters": key[3],
                              "ARI_pairs": len(scores),
                              "ARI_mean": float(np.mean(scores)) if scores else np.nan,
                              "ARI_median": float(np.median(scores)) if scores else np.nan,
                              "ARI_min": float(np.min(scores)) if scores else np.nan})
        ari_frame = pd.DataFrame(stability)
        summary = summary.merge(ari_frame, on=["fine_feature_rank", "umap_n_neighbors",
                                              "umap_min_dist", "kmeans_n_clusters"], validate="one_to_one")
        summary.to_csv(output / "seed_summary.csv", index=False, encoding="utf-8-sig")
    return eligible


def save_winner(winner, connection, output, plan, reference, sets, reducer_template, kmeans_template):
    entry = next(entry for entry in sets if entry["rank"] == int(winner["fine_feature_rank"]))
    seed, neighbors, k = (int(winner[key]) for key in
                          ("umap_seed", "umap_n_neighbors", "kmeans_n_clusters"))
    distance = float(winner["umap_min_dist"])
    reducer, z, guards = fit_embedding(reducer_template, entry, neighbors, distance, seed,
                                       force_all_guards=True)
    kmeans = clone(kmeans_template).set_params(n_clusters=k)
    with threadpool_limits(limits=2):
        labels = kmeans.fit_predict(z)
        metrics = evaluate_partition(z, labels, target_range=(min(plan["k_values"]), max(plan["k_values"])))
    packed = connection.execute("SELECT labels FROM runs WHERE key=?", (winner["embedding_key"],)).fetchone()[0]
    saved_labels = np.frombuffer(zlib.decompress(packed), dtype=np.int32).reshape(
        len(plan["k_values"]), len(reference))[plan["k_values"].index(k)]
    if (adjusted_rand_score(saved_labels, labels) != 1
            or not np.isclose(metrics["score"], winner["score"], rtol=0, atol=1e-10)
            or not combine_selection_eligibility(metrics["score"], guards)
            or not guards["hard_guards_passed"]):
        raise RuntimeError("Winning trial did not reproduce during final model fitting; checkpoint retained.")
    old_guard_details = json.loads(winner["guard_query_diagnostics_json"])
    new_guard_details = json.loads(guards["guard_query_diagnostics_json"])
    for old_detail, new_detail in zip(old_guard_details, new_guard_details, strict=True):
        if any(old_detail[key] != new_detail[key] for key in
               ("input_row_index", "nearest_reference_index", "full11_rank", "rank_passed")):
            raise RuntimeError("Winning query guard results changed during reproduction.")
    if not np.isclose(guards["trustworthiness_full11_k10"], winner["trustworthiness_full11_k10"],
                      rtol=0, atol=1e-12):
        raise RuntimeError("Winning trustworthiness did not reproduce.")
    table = reference.copy()
    table.insert(0, "Reference_Original_Index", np.arange(len(reference)))
    table["Reference_Used_For_UMAP_Fit"] = True
    table["Reference_Initial_Edge_Distance"] = 0.0
    table["Reference_UMAP1"], table["Reference_UMAP2"] = z[:, 0], z[:, 1]
    table["Reference_KMeans_Cluster"] = labels
    metadata = {
        "workflow_stage": WORKFLOW_STAGE, "artifact_schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "reference_source": plan["reference"], "reference_source_sha256": plan["reference_sha256"],
        "reference_sample_count": len(reference), "reference_umap_fit_count": len(reference),
        "selected_features": entry["features"], "name_col": plan["name_col"], "label_col": plan["label_col"],
        "umap_n_neighbors": neighbors, "umap_min_dist": distance, "umap_init": reducer.init,
        "umap_n_epochs": reducer.n_epochs, "umap_seed": seed, "kmeans_n_clusters": k,
        "reference_coordinates_sha256": hashlib.sha256(np.ascontiguousarray(z).tobytes()).hexdigest(),
        "unseen_rows_used_during_fit": 0, "guard_input_used_during_fit": False,
        "guard_input_source": plan["guard_input"], "guard_input_source_sha256": plan["guard_input_sha256"],
        "guard_input_name": plan["guard_name"], "guard_input_source_row_index": plan["guard_row_index"],
        "neighbor_guard_required": True, "neighbor_guard_passed": True,
        "hard_guards_passed": True,
        "exact_neighbor_guard_passed": guards["exact_neighbor_guard_passed"],
        "rank_guard_passed": guards["rank_guard_passed"],
        "trustworthiness_guard_passed": guards["trustworthiness_guard_passed"],
        "trustworthiness_full11_k10": guards["trustworthiness_full11_k10"],
        "trustworthiness_baseline": guards["trustworthiness_baseline"],
        "trustworthiness_numerical_tolerance": guards["trustworthiness_numerical_tolerance"],
        "rank_guard_max_rank_inclusive": guards["rank_guard_max_rank_inclusive"],
        "rank_guard_max_observed_rank": guards["rank_guard_max_observed_rank"],
        "guard_query_names": plan["hard_guard_spec"]["query_names"],
        "guard_transform_count": guards["guard_transform_count"],
        "ood_reference_quantile": plan["hard_guard_spec"]["ood_quantile"],
        "ood_distance_threshold": plan["hard_guard_spec"]["ood_distance_threshold"],
        "feature_space_nearest_name": plan["guard_feature_nearest_name"],
        "umap_space_nearest_name": guards["umap_space_nearest_names"],
        "guard_reference_coordinates_unchanged": True,
        "selection_method": "highest single-run J_morph among trials passing all three hard guards",
        "baseline_policy": plan["hard_guard_spec"]["trustworthiness_baseline_policy"],
        "search_code_sha256": plan["code_sha256"],
        "winner_score_reproduction_absolute_error": float(abs(metrics["score"] - winner["score"])),
        "winner_label_reproduction_ARI": float(adjusted_rand_score(saved_labels, labels)),
    }
    best_result = dict(winner)
    best_result.update(guards)
    best_result["feature_space_reference_features"] = "; ".join(plan["full_guard_features"])
    artifact = {"schema_version": 1, "workflow": "reference_fit_then_unseen_transform",
                "selected_features": entry["features"], "label_col": plan["label_col"],
                "name_col": plan["name_col"], "preprocessor": entry["preprocessor"],
                "umap_reducer": reducer, "kmeans_model": kmeans, "reference_coordinates": z,
                "reference_processed_features": entry["x"], "reference_clusters": labels,
                "reference_table": table, "reference_keep_mask": np.ones(len(reference), dtype=bool),
                "metadata": metadata, "best_result": best_result}
    joblib.dump(artifact, output / "best_reference_umap_model.joblib", compress=3)
    write_json(output / "best_reference_umap_manifest.json", metadata)
    write_json(output / "best_result.json", best_result)
    table.to_csv(output / "best_reference_labels.csv", index=False, encoding="utf-8-sig")


def main():
    args = parse_args()
    plan, shortlist, reference, sets, reducer_template, kmeans_template = prepare(args)
    output = args.output_dir or (HERE / "fine_search_results" /
                                datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    if args.resume:
        if not (output / "checkpoint.sqlite3").is_file():
            raise ValueError("No checkpoint in the requested resume directory.")
    else:
        output.mkdir(parents=True, exist_ok=False)
    if not args.resume:
        write_json(output / "search_plan.json", plan)
        shortlist.to_csv(output / "selected_feature_sets.csv", index=False, encoding="utf-8-sig")
    print(f"Output: {output.resolve()}", flush=True)
    print(f"Planned: {plan['expected_umap_fits']:,} UMAP fits; "
          f"{plan['expected_kmeans_evaluations']:,} KMeans evaluations. "
          "Final winner export adds one verification refit.", flush=True)
    print(f"neighbors={args.neighbors}; min_dist={args.min_dist}; seeds={args.seeds}; K={args.k_values}", flush=True)
    if args.dry_run:
        print("Dry run complete; no UMAP/KMeans fitting performed.", flush=True)
        return
    connection = connect_checkpoint(output / "checkpoint.sqlite3", plan)
    done = {row[0] for row in connection.execute("SELECT key FROM runs")}
    initial_done = len(done)
    new_count = 0
    start = time.perf_counter()
    state = {"status": "running", "complete": False, "completed_umap_fits": len(done),
             "planned_umap_fits": plan["expected_umap_fits"], "resumed": args.resume}
    write_json(output / "run_status.json", state)
    try:
        for entry, neighbors, distance, seed in itertools.product(sets, args.neighbors, args.min_dist, args.seeds):
            key = run_key(entry["rank"], neighbors, distance, seed)
            if key in done:
                continue
            if args.max_embeddings is not None and new_count >= args.max_embeddings:
                break
            fit_start = time.perf_counter()
            _, z, guards = fit_embedding(reducer_template, entry, neighbors, distance, seed)
            umap_guard_seconds = time.perf_counter() - fit_start
            guard_passed = guards["hard_guards_passed"]
            rows, all_labels = [], []
            km_start = time.perf_counter()
            with threadpool_limits(limits=2):
                for k in args.k_values:
                    model = clone(kmeans_template).set_params(n_clusters=k)
                    labels = model.fit_predict(z)
                    metrics = evaluate_partition(z, labels, target_range=(min(args.k_values), max(args.k_values)))
                    quality_valid = bool(metrics["selection_valid"])
                    metrics.update(guards)
                    metrics.update({
                        "embedding_key": key, "fine_feature_rank": entry["rank"],
                        "feature_set_id": entry["old_feature_set_id"],
                        "selected_features": "; ".join(entry["features"]),
                        "selected_feature_count": len(entry["features"]),
                        "umap_n_neighbors": neighbors, "umap_min_dist": distance, "umap_seed": seed,
                        "kmeans_seed": int(kmeans_template.random_state), "kmeans_n_clusters": k,
                        "reference_sample_count": len(reference),
                        "quality_valid": quality_valid,
                        "selection_valid": combine_selection_eligibility(metrics["score"], guards),
                        "guard_input_name": plan["guard_name"], "guard_input_source_row_index": plan["guard_row_index"],
                        "feature_space_nearest_names": plan["guard_feature_nearest_name"],
                        "feature_space_nearest_original_indices": plan["guard_feature_nearest_index"],
                        "feature_space_nearest_distances": plan["guard_feature_nearest_distance"],
                        "unseen_rows_used_in_umap_fit": 0,
                        "umap_fit_and_guard_seconds": umap_guard_seconds,
                    })
                    rows.append(metrics)
                    all_labels.append(np.asarray(labels, dtype=np.int32))
            km_seconds = time.perf_counter() - km_start
            for row in rows:
                row["embedding_kmeans_batch_seconds"] = km_seconds
            packed = zlib.compress(np.stack(all_labels).tobytes())
            with connection:
                connection.execute("INSERT INTO runs VALUES (?,?,?)", (key, json.dumps(rows), packed))
            done.add(key)
            new_count += 1
            if new_count == 1 or new_count % args.progress_every == 0 or len(done) == plan["expected_umap_fits"]:
                elapsed = time.perf_counter() - start
                eta = (plan["expected_umap_fits"] - len(done)) * elapsed / new_count
                state.update(completed_umap_fits=len(done),
                             completed_kmeans_evaluations=len(done) * len(args.k_values),
                             current_session_seconds=elapsed)
                write_json(output / "run_status.json", state)
                print(f"[{len(done):,}/{plan['expected_umap_fits']:,}] feature={entry['rank']} "
                      f"nn={neighbors} min_dist={distance:g} seed={seed} guard={guard_passed} "
                      f"fit+guard={umap_guard_seconds:.2f}s Kbatch={km_seconds:.2f}s "
                      f"ETA={eta/3600:.2f}h", flush=True)
        complete = len(done) == plan["expected_umap_fits"]
        print("Exporting result tables" + (" and seed ARI summaries..." if complete and plan["compute_stability"]
                                           else "..." if complete else " (partial)..."), flush=True)
        eligible = export_results(connection, output, plan, complete)
        if complete and not eligible.empty:
            print("Reproducing the highest-score eligible trial for model export...", flush=True)
            save_winner(eligible.iloc[0].to_dict(), connection, output, plan, reference,
                        sets, reducer_template, kmeans_template)
        state.update(status="complete" if complete else "partial", complete=complete,
                     completed_umap_fits=len(done), completed_kmeans_evaluations=len(done) * len(args.k_values),
                     new_umap_fits_this_session=new_count, initial_completed_umap_fits=initial_done,
                     winner_available=bool(complete and not eligible.empty),
                     current_session_seconds=time.perf_counter() - start)
        write_json(output / "run_status.json", state)
        print(f"Status: {state['status']}; {len(done):,} completed embeddings. Results: {output.resolve()}", flush=True)
        if complete and eligible.empty:
            print("No trial passed all hard guards; no best model was exported.", flush=True)
    except BaseException as error:
        state.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                     error=str(error), completed_umap_fits=len(done), complete=False)
        write_json(output / "run_status.json", state)
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
