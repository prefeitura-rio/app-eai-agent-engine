import json
import os
from pathlib import Path

DATASET_TO_EVAL = {
    "Golden Equipment Test": "equipments",
    "Disaster Response Questions": "disaster",
    "Multi-Turn Memory Test": "memory",
    "EAí - Refactor Tests": "servicos",
}


def load_bq_metrics(path: Path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    averages = {}
    for dataset_name, metrics in data.get("averages", {}).items():
        eval_name = DATASET_TO_EVAL.get(dataset_name, "unknown")
        averages[eval_name] = metrics
    return averages


evals_selected = [e.strip() for e in os.environ.get("EVALS_SELECTED", "").split(",") if e.strip()]

current = load_bq_metrics(Path("tmp/bq_current_metrics.json"))
prev = load_bq_metrics(Path("tmp/bq_prev_metrics.json"))

lines = []
lines.append(f"**Current prompt version:** `{os.environ.get('CURRENT_VERSION', '')}`")
prev_label = os.environ.get("PREV_VERSION", "") or "baseline (no RE)"
lines.append(f"**Previous reference:** `{prev_label}`")
lines.append("")

for eval_name in evals_selected:
    cur = current.get(eval_name, {})
    prv = prev.get(eval_name, {})
    lines.append(f"### {eval_name}")
    if not cur:
        lines.append("- No current metrics found.")
        continue
    for metric, cur_val in sorted(cur.items()):
        if metric in prv:
            diff = round(cur_val - prv[metric], 4)
            lines.append(f"- {metric}: current={cur_val} previous={prv[metric]} diff={diff}")
        else:
            lines.append(f"- {metric}: current={cur_val} previous=NA diff=NA")
    lines.append("")

summary = "\n".join(lines).strip() or "No comparable metrics found."
with open(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/stdout"), "a", encoding="utf-8") as f:
    f.write("\n## Eval comparison (current vs previous)\n")
    f.write(summary + "\n")
