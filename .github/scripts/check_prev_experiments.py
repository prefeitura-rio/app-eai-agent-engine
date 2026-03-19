import os
from src.utils.bigquery import get_bigquery_result

EXPERIMENTS_TABLE = "rj-iplanrio.brutos_eai_logs.evaluations_experiments"

prev_version = os.environ.get("PREV_VERSION", "").strip()
evals_selected = [e.strip() for e in os.environ.get("EVALS_SELECTED", "").split(",") if e.strip()]

dataset_map = {
    "equipments": "Golden Equipment Test",
    "disaster": "Disaster Response Questions",
    "memory": "Multi-Turn Memory Test",
    "servicos": "EAí - Refactor Tests",
}
dataset_names = [dataset_map[e] for e in evals_selected if e in dataset_map]

if not prev_version or not dataset_names:
    has_prev = "false"
else:
    names_sql = ", ".join([f"'{n}'" for n in dataset_names])
    query = f"""
    WITH base AS (
      SELECT
        dataset_name,
        REGEXP_REPLACE(REGEXP_EXTRACT(experiment_name, r'([^-]+)$'), r'^v', '') AS version_norm
      FROM `{EXPERIMENTS_TABLE}`
    )
    SELECT COUNT(1) AS cnt
    FROM base
    WHERE version_norm = '{prev_version}'
      AND dataset_name IN ({names_sql})
    """
    rows = get_bigquery_result(query)
    cnt = int(rows[0].get("cnt", 0)) if rows else 0
    has_prev = "true" if cnt > 0 else "false"

with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
    f.write(f"has_prev_experiments={has_prev}\n")
