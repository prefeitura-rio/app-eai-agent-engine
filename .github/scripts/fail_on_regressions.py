import json
from pathlib import Path

failures_path = Path("tmp/eval_failures.json")
if not failures_path.exists():
    raise SystemExit(0)

failures = json.loads(failures_path.read_text(encoding="utf-8"))
if not failures:
    raise SystemExit(0)

print("Regressions detected:")

for f in failures:
    eval_name = f.get("eval")
    metric = f.get("metric")

    if f.get("reason") == "no_current_metrics":
        print(f"- {eval_name}: no current metrics")
        continue

    if f.get("reason") == "no_baseline":
        print(f"- {eval_name} / {metric}: no baseline metric")
        continue

    base = f.get("baseline")
    cur = f.get("current")
    reason = f.get("reason", "")

    print(
        f"- {eval_name} / {metric}: baseline={base} current={cur} -> {reason}"
    )

raise SystemExit(1)
