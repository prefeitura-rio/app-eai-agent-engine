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
    REGEXP_REPLACE(REGEXP_EXTRACT(experiment_name, r'([^-]+)$'), r'^v', '') AS version_norm
  FROM `{EXPERIMENTS_TABLE}`
  WHERE dataset_name IN ({names_sql})
    AND experiment_timestamp >= TIMESTAMP_SECONDS({current_start})
    AND experiment_timestamp <= TIMESTAMP_SECONDS({current_end})
)
SELECT experiment_name, experiment_timestamp, dataset_name, aggregate_metrics
FROM (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY dataset_name ORDER BY experiment_timestamp DESC) AS rn
  FROM base
  WHERE version_norm = '{current_version}'
)
WHERE rn <= 3
ORDER BY dataset_name, experiment_timestamp DESC
"""

rows = get_bigquery_result(query)


def avg_metrics(runs):
    agg = defaultdict(list)
    for run in runs:
        for k, v in run.items():
            agg[k].append(v)
    return {k: round(sum(vs) / len(vs), 4) for k, vs in agg.items()}


by_dataset = defaultdict(list)
for row in rows:
    metrics = {}
    for m in row.get("aggregate_metrics", []):
        stats = m.get("score_statistics") or {}
        if "average" in stats:
            metrics[m.get("metric_name")] = stats["average"]
    if metrics:
        by_dataset[row.get("dataset_name")].append(metrics)

averages = {k: avg_metrics(v) for k, v in by_dataset.items()}

os.makedirs("tmp", exist_ok=True)
with open("tmp/bq_current_metrics.json", "w", encoding="utf-8") as f:
    json.dump({"current_version": current_version, "averages": averages}, f, indent=2, ensure_ascii=False)
