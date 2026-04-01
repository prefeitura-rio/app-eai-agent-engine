import json
import os
from collections import defaultdict

from src.utils.bigquery import get_bigquery_result

EXPERIMENTS_TABLE = "rj-iplanrio.brutos_eai_logs.evaluations_experiments"

current_version = os.environ.get("CURRENT_VERSION", "").strip()
evals_selected = [e.strip() for e in os.environ.get("EVALS_SELECTED", "").split(",") if e.strip()]
current_start = os.environ.get("CURRENT_START")
current_end = os.environ.get("CURRENT_END")

dataset_map = {
    "equipments": "Golden Equipment Test",
    "disaster": "Disaster Response Questions",
    "memory": "Multi-Turn Memory Test",
    "servicos": "EAí - Refactor Tests",
}

dataset_names = [dataset_map[e] for e in evals_selected if e in dataset_map]
if not dataset_names:
    raise RuntimeError("No dataset names resolved from EVALS_SELECTED.")
if not current_start or not current_end:
    raise RuntimeError("Current time window is missing.")

names_sql = ", ".join([f"'{n}'" for n in dataset_names])

query = f"""
WITH base AS (
  SELECT
    experiment_name,
    experiment_timestamp,
    dataset_name,
    aggregate_metrics,
    runs,
    REGEXP_REPLACE(REGEXP_EXTRACT(experiment_name, r'([^-]+)$'), r'^v', '') AS version_norm
  FROM `{EXPERIMENTS_TABLE}`
  WHERE dataset_name IN ({names_sql})
    AND experiment_timestamp >= TIMESTAMP_SECONDS({current_start})
    AND experiment_timestamp <= TIMESTAMP_SECONDS({current_end})
)
SELECT experiment_name, experiment_timestamp, dataset_name, aggregate_metrics, runs
FROM (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY dataset_name ORDER BY experiment_timestamp ASC) AS rn
  FROM base
  WHERE version_norm = '{current_version}'
)
WHERE rn <= 3
ORDER BY dataset_name, experiment_timestamp ASC
"""

rows = get_bigquery_result(query)


def avg_metrics(runs):
    agg = defaultdict(list)
    for run in runs:
        for k, v in run.items():
            agg[k].append(v)
    return {k: round(sum(vs) / len(vs), 4) for k, vs in agg.items()}


def extract_metric_averages(row):
    metrics = {}
    for m in row.get("aggregate_metrics", []):
        stats = m.get("score_statistics") or {}
        if "average" in stats:
            metrics[m.get("metric_name")] = stats["average"]
    return metrics


def count_general_errors(experiment_runs):
    total = 0
    for run in experiment_runs or []:
        one_turn = run.get("one_turn_analysis") or {}
        multi_turn = run.get("multi_turn_analysis") or {}
        if one_turn.get("has_error") or multi_turn.get("has_error"):
            total += 1
    return total


def count_metric_errors(experiment_runs):
    counts = defaultdict(int)
    for run in experiment_runs or []:
        for analysis_key in ["one_turn_analysis", "multi_turn_analysis"]:
            analysis = run.get(analysis_key) or {}
            if analysis.get("has_error"):
                continue
            for evaluation in analysis.get("evaluations", []) or []:
                if evaluation.get("has_error"):
                    counts[evaluation.get("metric_name", "unknown")] += 1
    return dict(counts)


by_dataset_metric_runs = defaultdict(list)
by_dataset_general_errors = defaultdict(int)
by_dataset_total_examples = defaultdict(int)
by_dataset_metric_errors = defaultdict(lambda: [dict(), dict(), dict()])
by_dataset_run_index = defaultdict(int)

for row in rows:
    dataset_name = row.get("dataset_name")
    if not dataset_name:
        continue

    metrics = extract_metric_averages(row)
    if metrics:
        by_dataset_metric_runs[dataset_name].append(metrics)

    experiment_runs = row.get("runs", []) or []
    by_dataset_general_errors[dataset_name] += count_general_errors(experiment_runs)
    by_dataset_total_examples[dataset_name] += len(experiment_runs)

    run_index = by_dataset_run_index[dataset_name]
    if run_index < 3:
        by_dataset_metric_errors[dataset_name][run_index] = count_metric_errors(
            experiment_runs
        )
        by_dataset_run_index[dataset_name] += 1

payload = {
    "current_version": current_version,
    "averages": {k: avg_metrics(v) for k, v in by_dataset_metric_runs.items()},
    "metric_errors_by_run": dict(by_dataset_metric_errors),
    "general_errors": dict(by_dataset_general_errors),
    "total_examples": dict(by_dataset_total_examples),
}

os.makedirs("tmp", exist_ok=True)
with open("tmp/bq_current_metrics.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)
