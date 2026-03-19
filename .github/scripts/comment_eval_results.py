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


def pct_change_value(baseline, current):
    if baseline == 0:
        return None
    return ((current - baseline) / baseline) * 100.0


def pct_change_str(baseline, current):
    if baseline == 0:
        return "NA"
    return f"{pct_change_value(baseline, current):.2f}%"


current = load_bq_metrics(Path("tmp/bq_current_metrics.json"))
baseline = load_bq_metrics(Path("tmp/bq_prev_metrics.json"))

evals_selected = [e.strip() for e in os.environ.get("EVALS_SELECTED", "").split(",") if e.strip()]
current_version = os.environ.get("CURRENT_VERSION", "")
prev_version = os.environ.get("PREV_VERSION", "") or "baseline (no RE)"

lines = []
lines.append("✅ **Evals finalizados**")
lines.append("")
lines.append(f"**Baseline:** `{prev_version}`")
lines.append(f"**Versão atual:** `{current_version}`")
lines.append("")

failures = []

for eval_name in evals_selected:
    cur = current.get(eval_name, {})
    base = baseline.get(eval_name, {})
    lines.append(f"**Eval {eval_name}**")
    lines.append("")
    lines.append("| métrica | baseline | versão atual | variacao % |")
    lines.append("|---|---|---|---|")
    if not cur:
        lines.append("| _sem métricas_ | - | - | - |")
        failures.append({"eval": eval_name, "metric": "_sem métricas_", "reason": "no_current_metrics"})
    else:
        for metric, cur_val in sorted(cur.items()):
            base_val = base.get(metric)
            if base_val is None:
                lines.append(f"| {metric} | NA | {cur_val} | NA |")
                failures.append({"eval": eval_name, "metric": metric, "reason": "no_baseline"})
            else:
                variation = pct_change_value(base_val, cur_val)
                lines.append(
                    f"| {metric} | {base_val} | {cur_val} | {pct_change_str(base_val, cur_val)} |"
                )
                if variation is not None and variation < -5.0:
                    failures.append(
                        {
                            "eval": eval_name,
                            "metric": metric,
                            "baseline": base_val,
                            "current": cur_val,
                            "variation_pct": variation,
                        }
                    )
    lines.append("")

if failures:
    lines.append("❌ **Resultado final:** Reprovado (métricas > 5% pior)")
else:
    lines.append("✅ **Resultado final:** Aprovado (todas as métricas dentro de 5%)")

comment = "\n".join(lines).strip() + "\n"
Path("tmp/pr_comment.md").write_text(comment, encoding="utf-8")
Path("tmp/eval_failures.json").write_text(
    json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8"
)
