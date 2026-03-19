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


def extract_version_number(value: str) -> str:
    if not value:
        return ""
    m = re.search(r"(?:^|[-_])v(\d+)$", value)
    return m.group(1) if m else ""


data = fetch_unified_history(limit=2)
items = data.get("items", [])
if not items:
    raise RuntimeError("Unified history is empty.")

def resolve_version(item):
    candidates = [
        item.get("version_display", ""),
        item.get("version", ""),
        item.get("prompt_version", ""),
        item.get("version_id", ""),
        item.get("id", ""),
    ]
    for val in candidates:
        if isinstance(val, str):
            num = extract_version_number(val)
            if num:
                return val, num
    return "", ""


current_display, current_num = resolve_version(items[0])
prev_display, prev_num = ("", "")
if len(items) > 1:
    prev_display, prev_num = resolve_version(items[1])

if not current_num:
    keys = ", ".join(sorted(items[0].keys()))
    raise RuntimeError(
        f"Could not parse current version from unified history item. keys=[{keys}] item={items[0]}"
    )

with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
    f.write(f"current_version_display={current_display}\n")
    f.write(f"current_version_num={current_num}\n")
    f.write(f"prev_version_display={prev_display}\n")
    f.write(f"prev_version_num={prev_num}\n")
