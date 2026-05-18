import json
import os
import re
import sys

comments = json.loads(os.environ["COMMENTS_JSON"])
for c in sorted(comments, key=lambda x: x.get("created_at", ""), reverse=True):
    body = c.get("body") or ""
    if "REASONING_ENGINE_ID" not in body:
        continue
    m_env = re.search(r"Environment[^a-zA-Z0-9]*([a-zA-Z0-9_-]+)", body, re.IGNORECASE)
    m_id = re.search(r"REASONING_ENGINE_ID\\s*:\\s*`?([^`\\s]+)`?", body, re.IGNORECASE)
    if not m_id:
        continue
    env = (m_env.group(1) if m_env else "").strip().lower()
    engine_id = m_id.group(1).strip()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write(f"env={env}\n")
        f.write(f"engine_id={engine_id}\n")
        f.write(f"should_run={'true' if env == 'staging' else 'false'}\n")
    sys.exit(0)

print("No deploy comment with REASONING_ENGINE_ID found.")
sys.exit(1)
