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
    metric_errors_by_run = {}
    general_errors = {}
    total_examples = {}

    for dataset_name, metrics in data.get("averages", {}).items():
        eval_name = DATASET_TO_EVAL.get(dataset_name, "unknown")
        rounded = {}
        for key, val in metrics.items():
            if isinstance(val, (int, float)):
                rounded[key] = round(val, 2)
            else:
                rounded[key] = val
        averages[eval_name] = rounded

    for dataset_name, run_errors in data.get("metric_errors_by_run", {}).items():
        eval_name = DATASET_TO_EVAL.get(dataset_name, "unknown")
        metric_errors_by_run[eval_name] = run_errors

    for dataset_name, error_count in data.get("general_errors", {}).items():
        eval_name = DATASET_TO_EVAL.get(dataset_name, "unknown")
        general_errors[eval_name] = int(error_count)

    for dataset_name, example_count in data.get("total_examples", {}).items():
        eval_name = DATASET_TO_EVAL.get(dataset_name, "unknown")
        total_examples[eval_name] = int(example_count)

    return {
        "averages": averages,
        "metric_errors_by_run": metric_errors_by_run,
        "general_errors": general_errors,
        "total_examples": total_examples,
    }


def pct_change_value(baseline, current):
    if baseline == 0:
        return None
    return ((current - baseline) / baseline) * 100.0


def pct_change_str(baseline, current):
    if baseline == 0:
        return "NA"
    return f"{pct_change_value(baseline, current):.2f}%"


def is_regression(metric, base_val, cur_val):
    # Compare using the same 2-decimal precision shown in the report so
    # threshold-edge values do not fail because of floating-point noise.
    delta = round(cur_val - base_val, 2)

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
        variation = round(variation, 2)

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
    if metric in LOWER_IS_BETTER:
        if delta > abs(DEFAULT_SCORE_DELTA):
            return True, f"delta {delta:.2f} > {abs(DEFAULT_SCORE_DELTA)}"
    else:
        if delta < DEFAULT_SCORE_DELTA:
            return True, f"delta {delta:.2f} < {DEFAULT_SCORE_DELTA}"

    return False, None


def metric_error_for_run(run_error_list, run_index, metric_name):
    if run_index >= len(run_error_list):
        return 0
    return int((run_error_list[run_index] or {}).get(metric_name, 0))


def general_error_rate_str(error_count, total_examples):
    if total_examples <= 0:
        return "NA"
    return f"{(error_count / total_examples) * 100:.1f}%"


# -------------------------
# MAIN
# -------------------------

current_data = load_bq_metrics(Path("tmp/bq_current_metrics.json"))
baseline_data = load_bq_metrics(Path("tmp/bq_prev_metrics.json"))

current = current_data["averages"]
baseline = baseline_data["averages"]
current_metric_errors = current_data["metric_errors_by_run"]
current_general_errors = current_data["general_errors"]
current_total_examples = current_data["total_examples"]

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
    run_errors = current_metric_errors.get(eval_name, [{}, {}, {}])
    general_errors = int(current_general_errors.get(eval_name, 0))
    total_examples = int(current_total_examples.get(eval_name, 0))
    general_error_rate = general_error_rate_str(general_errors, total_examples)

    lines.append(
        f"**Eval {eval_name} | erros gerais v{current_version}: {general_errors} ({general_error_rate} dos {total_examples} exemplos)**\n"
    )
    lines.append(
        f"| métrica | v{prev_version} | v{current_version} | delta | variação % | err r1 | err r2 | err r3 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")

    if not cur:
        lines.append("| _sem métricas_ | - | - | - | - | - | - | - |")
        failures.append({"eval": eval_name, "reason": "no_current_metrics"})
        lines.append("")
        continue

    for metric, cur_val in sorted(cur.items()):
        base_val = base.get(metric)
        err_r1 = metric_error_for_run(run_errors, 0, metric)
        err_r2 = metric_error_for_run(run_errors, 1, metric)
        err_r3 = metric_error_for_run(run_errors, 2, metric)

        if base_val is None:
            lines.append(
                f"| {metric} | NA | {cur_val} | NA | NA | {err_r1} | {err_r2} | {err_r3} |"
            )
            failures.append({"eval": eval_name, "metric": metric, "reason": "no_baseline"})
            continue

        delta = round(cur_val - base_val, 2)
        variation_str = (
            pct_change_str(base_val, cur_val)
            if metric in PERCENT_METRICS
            else "NA"
        )

        lines.append(
            f"| {metric} | {base_val} | {cur_val} | {delta} | {variation_str} | {err_r1} | {err_r2} | {err_r3} |"
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
