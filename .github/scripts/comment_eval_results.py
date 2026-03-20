import json
import os
from pathlib import Path

DATASET_TO_EVAL = {
    "Golden Equipment Test": "equipments",
    "Disaster Response Questions": "disaster",
    "Multi-Turn Memory Test": "memory",
    "EAí - Refactor Tests": "servicos",
}

LOWER_IS_BETTER = {
    "search_calls_after_second_question",
    "hallucination_flag",
}

def load_bq_metrics(path: Path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    averages = {}
    for dataset_name, metrics in data.get("averages", {}).items():
        eval_name = DATASET_TO_EVAL.get(dataset_name, "unknown")
        rounded = {}
        for key, val in metrics.items():
            if isinstance(val, (int, float)):
                rounded[key] = round(val, 2)
            else:
                rounded[key] = val
        averages[eval_name] = rounded
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
lines.append(f"**Baseline:** `v{prev_version}`")
lines.append(f"**Versão atual:** `v{current_version}`")
lines.append("")

failures = []

for eval_name in evals_selected:
    cur = current.get(eval_name, {})
    base = baseline.get(eval_name, {})
    lines.append(f"**Eval {eval_name}**")
    lines.append("")
    lines.append(
        f"| métrica | v{prev_version} | v{current_version} | diferença (abs) | variação % |"
    )
    lines.append("|---|---|---|---|---|")
    if not cur:
        lines.append("| _sem métricas_ | - | - | - | - |")
        failures.append({"eval": eval_name, "metric": "_sem métricas_", "reason": "no_current_metrics"})
    else:
        for metric, cur_val in sorted(cur.items()):
            base_val = base.get(metric)
            if base_val is None:
                lines.append(f"| {metric} | NA | {cur_val} | NA | NA |")
                failures.append({"eval": eval_name, "metric": metric, "reason": "no_baseline"})
            else:
                is_percent_metric = metric in {"token_usage_total", "search_calls_after_second_question", "equipments_speed"}
                delta = round(cur_val - base_val, 2)
                variation_str = pct_change_str(base_val, cur_val) if is_percent_metric else "NA"
                lines.append(
                    f"| {metric} | {base_val} | {cur_val} | {delta} | {variation_str} |"
                )
                if is_percent_metric:
                    variation = pct_change_value(base_val, cur_val)
                    if variation is not None:
                        if metric in LOWER_IS_BETTER:
                            # piora = aumento
                            if variation > 5.0:
                                failures.append(
                                    {
                                        "eval": eval_name,
                                        "metric": metric,
                                        "baseline": base_val,
                                        "current": cur_val,
                                        "variation_pct": variation,
                                    }
                                )
                        else:
                            # piora = diminuição
                            if variation < -5.0:
                                failures.append(
                                    {
                                        "eval": eval_name,
                                        "metric": metric,
                                        "baseline": base_val,
                                        "current": cur_val,
                                        "variation_pct": variation,
                                    }
                                )
                else:
                    if delta <= -0.05:
                        failures.append(
                            {
                                "eval": eval_name,
                                "metric": metric,
                                "baseline": base_val,
                                "current": cur_val,
                                "delta": delta,
                            }
                        )
    lines.append("")

if failures:
    lines.append(
        f"❌ **Resultado final:** Reprovado ({len(failures)} uma ou mais métricas ficaram abaixo do limite de 5% em relação à baseline)"
    )
else:
    lines.append("✅ **Resultado final:** Aprovado (todas as métricas dentro do limite)")

comment = "\n".join(lines).strip() + "\n"
Path("tmp/pr_comment.md").write_text(comment, encoding="utf-8")
Path("tmp/eval_failures.json").write_text(
    json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8"
)
