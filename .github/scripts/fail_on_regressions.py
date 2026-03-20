import json
from pathlib import Path

failures_path = Path("tmp/eval_failures.json")
if not failures_path.exists():
    raise SystemExit(0)

failures = json.loads(failures_path.read_text(encoding="utf-8"))
if not failures:
    raise SystemExit(0)

print("Regressions > 5% detected:")
for f in failures:
    if f.get("reason") == "no_current_metrics":
        print(f"- {f['eval']}: no current metrics")
    elif f.get("reason") == "no_baseline":
        print(f"- {f['eval']} / {f['metric']}: no baseline metric")
    else:
        print(
            f"- {f['eval']} / {f['metric']}: baseline={f['baseline']} current={f['current']} "
            f"delta={f['delta']}"
        )
raise SystemExit(1)
