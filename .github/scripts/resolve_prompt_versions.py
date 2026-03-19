import os
import re
import httpx


def fetch_unified_history(limit: int = 2):
    base_url = os.environ.get("EAI_AGENT_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("EAI_AGENT_URL is not set.")
    url = f"{base_url}/api/v1/unified-history?agent_type=agentic_search&limit={limit}"
    token = os.environ.get("EAI_AGENT_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


def extract_version_number(version_display: str) -> str:
    m = re.search(r"-v(\d+)$", version_display or "")
    return m.group(1) if m else ""


data = fetch_unified_history(limit=2)
items = data.get("items", [])
if not items:
    raise RuntimeError("Unified history is empty.")

current_display = items[0].get("version_display", "")
current_num = extract_version_number(current_display)

prev_display = items[1].get("version_display", "") if len(items) > 1 else ""
prev_num = extract_version_number(prev_display)

if not current_num:
    raise RuntimeError(f"Could not parse current version from '{current_display}'")

with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
    f.write(f"current_version_display={current_display}\n")
    f.write(f"current_version_num={current_num}\n")
    f.write(f"prev_version_display={prev_display}\n")
    f.write(f"prev_version_num={prev_num}\n")
