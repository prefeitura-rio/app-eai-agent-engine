import json
import os
from pathlib import Path

DATASET_TO_EVAL = {
    "Golden Equipment Test": "equipments",
    "Disaster Response Questions": "disaster",
    "Multi-Turn Memory Test": "memory",
    "EAí - Refactor Tests": "servicos",
}

# -------------------------
# CONFIG DE MÉTRICAS
# -------------------------

# usa % (escala grande)
PERCENT_METRICS = {
    "token_usage_total",
}

# usa delta absoluto (escala pequena)
ABSOLUTE_METRICS = {
    "search_calls_after_second_question",
    "equipments_speed",
}

# direção da métrica
LOWER_IS_BETTER = {
    "search_calls_after_second_question",
    "hallucination_flag",
    "token_usage_total",
    "equipments_speed",
}

# thresholds específicos
ABS_THRESHOLDS = {
    "search_calls_after_second_question": 0.1,
    "equipments_speed": 0.25,
}

PERCENT_THRESHOLD = 5.0
DEFAULT_SCORE_DELTA = -0.05


# -------------------------
# HELPERS
# -------------------------

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


def is_regression(metric, base_val, cur_val):
    delta = cur_val - base_val

    # -------------------------
    # REGRA CRÍTICA (casos especiais)
    # -------------------------
    if metric == "search_calls_after_second_question":
        if base_val == 0 and cur_val > 0:
            return True, "baseline_zero_regression"

    if metric == "equipments_speed":
        if base_val != 0 and cur_val == 0:
            return True, "equipment_missing"

    # -------------------------
    # MÉTRICAS DE %
    # -------------------------
    if metric in PERCENT_METRICS:
        variation = pct_change_value(base_val, cur_val)
        if variation is None:
            return False, None

        if metric in LOWER_IS_BETTER:
            if variation > PERCENT_THRESHOLD:
                return True, f"variation {variation:.2f}% > {PERCENT_THRESHOLD}%"
        else:
            if variation < -PERCENT_THRESHOLD:
                return True, f"variation {variation:.2f}% < -{PERCENT_THRESHOLD}%"

        return False, None

    # -------------------------
    # MÉTRICAS ABSOLUTAS
    # -------------------------
    if metric in ABSOLUTE_METRICS:
        threshold = ABS_THRESHOLDS.get(metric, 0.1)

        if metric in LOWER_IS_BETTER:
            if delta > threshold:
                return True, f"delta {delta:.2f} > {threshold}"
        else:
            if delta < -threshold:
                return True, f"delta {delta:.2f} < -{threshold}"

        return False, None

    # -------------------------
    # MÉTRICAS PADRÃO (0–1)
    # -------------------------
    if delta < DEFAULT_SCORE_DELTA:
        return True, f"delta {delta:.2f} < {DEFAULT_SCORE_DELTA}"

    return False, None


# -------------------------
# MAIN
# -------------------------

current = load_bq_metrics(Path("tmp/bq_current_metrics.json"))
baseline = load_bq_metrics(Path("tmp/bq_prev_metrics.json"))

evals_selected = [
    e.strip() for e in os.environ.get("EVALS_SELECTED", "").split(",") if e.strip()
]

current_version = os.environ.get("CURRENT_VERSION", "")
prev_version = os.environ.get("PREV_VERSION", "") or "baseline (no RE)"

lines = []
lines.append("✅ **Evals finalizados**\n")
lines.append(f"**Baseline:** `v{prev_version}`")
lines.append(f"**Versão atual:** `v{current_version}`\n")

failures = []

for eval_name in evals_selected:
    cur = current.get(eval_name, {})
    base = baseline.get(eval_name, {})

    lines.append(f"**Eval {eval_name}**\n")
    lines.append(f"| métrica | v{prev_version} | v{current_version} | delta | variação % |")
    lines.append("|---|---|---|---|---|")

    if not cur:
        lines.append("| _sem métricas_ | - | - | - | - |")
        failures.append({"eval": eval_name, "reason": "no_current_metrics"})
        continue

    for metric, cur_val in sorted(cur.items()):
        base_val = base.get(metric)

        if base_val is None:
            lines.append(f"| {metric} | NA | {cur_val} | NA | NA |")
            failures.append({"eval": eval_name, "metric": metric, "reason": "no_baseline"})
            continue

        delta = round(cur_val - base_val, 2)
        variation_str = (
            pct_change_str(base_val, cur_val)
            if metric in PERCENT_METRICS
            else "NA"
        )

        lines.append(
            f"| {metric} | {base_val} | {cur_val} | {delta} | {variation_str} |"
        )

        is_fail, reason = is_regression(metric, base_val, cur_val)

        if is_fail:
            failures.append(
                {
                    "eval": eval_name,
                    "metric": metric,
                    "baseline": base_val,
                    "current": cur_val,
                    "reason": reason,
                }
            )

    lines.append("")

# -------------------------
# RESULTADO FINAL
# -------------------------

if failures:
    failed_metrics = sorted(set(f["metric"] for f in failures if "metric" in f))
    lines.append(
        f"❌ **Resultado final:** Reprovado — métricas com regressão: `{', '.join(failed_metrics)}`"
    )
else:
    lines.append("✅ **Resultado final:** Aprovado")

comment = "\n".join(lines)
Path("tmp/pr_comment.md").write_text(comment, encoding="utf-8")
Path("tmp/eval_failures.json").write_text(
    json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8"
)
