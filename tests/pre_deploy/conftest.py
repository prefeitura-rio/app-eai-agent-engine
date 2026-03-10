import asyncio
import pytest
import psycopg
from psycopg.rows import dict_row

from src.config import env
from src.tools import mcp_tools
from engine.agent import Agent
from src.prompt import prompt_data

# ---------------------------------------------------------------------------
# Shared accumulator: filled by tests, read by pytest_terminal_summary
# ---------------------------------------------------------------------------
_RESPONSES: list[tuple[str, str, str, str]] = []


@pytest.fixture(scope="session")
def record_response():
    """Record (scenario, thread_id, message_sent, agent_response) for the summary."""
    def _record(scenario: str, thread_id: str, sent: str, response: str) -> None:
        _RESPONSES.append((scenario, thread_id, sent, response))
    return _record


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not _RESPONSES:
        return
    terminalreporter.write_sep("=", "responses")
    for scenario, thread_id, sent, response in _RESPONSES:
        terminalreporter.write_line("")
        terminalreporter.write_line(f"  [{scenario}] {thread_id}")
        terminalreporter.write_line(f"  sent:     {sent}")
        terminalreporter.write_line(f"  response: {response}")
    terminalreporter.write_line("")


@pytest.fixture(scope="session")
def dsn():
    return (
        f"postgresql://{env.DATABASE_USER}:{env.DATABASE_PASSWORD}"
        f"@{env.DATABASE_HOST}:{env.DATABASE_PORT or '5432'}/{env.DATABASE}"
    )


@pytest.fixture(scope="session")
async def agent():
    """Single agent instance shared across all pre-deploy tests.

    thinking_budget=0 disables reasoning to keep test latency low.
    """
    prompt_version = prompt_data["version"]
    a = Agent(
        model="gemini-2.5-flash",
        system_prompt=prompt_data["prompt"],
        temperature=0.7,
        tools=mcp_tools,
        include_thoughts=False,
        thinking_budget=0,
        otpl_service=f"eai-langgraph-v{prompt_version}",
    )
    yield a
    try:
        await asyncio.wait_for(a.cleanup(), timeout=10.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass
