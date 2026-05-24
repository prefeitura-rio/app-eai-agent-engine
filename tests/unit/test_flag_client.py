"""Unit tests for ``engine.active_learning.flag_client``.

Coverage targets:
- ``is_configured`` reflects presence of base URL + token (both required).
- Successful 200 yields a populated ``FlagAssignment``.
- 4xx responses raise ``FlagClientError`` (config bug, not runtime fault).
- 5xx responses degrade to ``None`` (fail-open for experiment layer).
- Timeout returns ``None`` and does not raise.
- Token header and ``user`` query parameter are wired correctly.
- Unconfigured client returns ``None`` without touching the network.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from engine.active_learning.flag_client import (
    DEFAULT_TIMEOUT_SECONDS,
    HEADER_FLAGS_READ_TOKEN,
    FlagAssignment,
    FlagClient,
    FlagClientError,
)


def _patch_async_client(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """Replace httpx.AsyncClient inside flag_client with one that uses MockTransport."""

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return real_async_client(transport=transport, **kwargs)

    monkeypatch.setattr(
        "engine.active_learning.flag_client.httpx.AsyncClient", factory
    )


@pytest.mark.asyncio
async def test_is_configured_requires_both_base_and_token():
    assert FlagClient(base_url="", read_token="t").is_configured is False
    assert FlagClient(base_url="http://x", read_token="").is_configured is False
    assert FlagClient(base_url="http://x", read_token="t").is_configured is True


@pytest.mark.asyncio
async def test_assign_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("GATEWAY_BASE_URL", raising=False)
    monkeypatch.delenv("FLAGS_READ_TOKEN", raising=False)
    client = FlagClient()
    assert await client.assign("active_learning_v1", "user-1") is None


@pytest.mark.asyncio
async def test_assign_200_returns_assignment(monkeypatch):
    received: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        received["token"] = request.headers.get(HEADER_FLAGS_READ_TOKEN)
        return httpx.Response(
            200,
            json={
                "flag": "active_learning_v1",
                "variant": "treatment",
                "user_id": "user-1",
            },
        )

    _patch_async_client(monkeypatch, handler)

    client = FlagClient(base_url="http://gateway.test", read_token="tok")
    result = await client.assign("active_learning_v1", "user-1")

    assert isinstance(result, FlagAssignment)
    assert result.flag == "active_learning_v1"
    assert result.variant == "treatment"
    assert result.user_id == "user-1"
    # Lock the wire contract: full path template + query param + auth header.
    received_url = received["url"] or ""
    assert "/api/v1/flags/active_learning_v1/assign" in received_url
    assert "user=user-1" in received_url
    assert received["token"] == "tok"


@pytest.mark.asyncio
async def test_assign_user_id_with_plus_is_url_encoded(monkeypatch):
    """BR phone numbers prefix with `+55`; httpx must percent-encode."""

    received: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"flag": "active_learning_v1", "variant": "control", "user_id": "+5521999"},
        )

    _patch_async_client(monkeypatch, handler)

    client = FlagClient(base_url="http://gateway.test", read_token="tok")
    await client.assign("active_learning_v1", "+5521999")

    # httpx must percent-encode `+` in query values (RFC 3986).
    received_url = received["url"] or ""
    assert "%2B5521999" in received_url


@pytest.mark.asyncio
async def test_assign_flag_name_path_is_escaped(monkeypatch):
    """Flag name with reserved chars must not break the URL path."""

    received: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"flag": "weird/flag", "variant": "control", "user_id": "user-1"},
        )

    _patch_async_client(monkeypatch, handler)

    client = FlagClient(base_url="http://gateway.test", read_token="tok")
    await client.assign("weird/flag", "user-1")

    received_url = received["url"] or ""
    # `/` inside the flag name must be percent-encoded as `%2F`.
    assert "/api/v1/flags/weird%2Fflag/assign" in received_url


@pytest.mark.asyncio
async def test_assign_4xx_raises_flag_client_error(monkeypatch):
    _patch_async_client(monkeypatch, lambda req: httpx.Response(401, text="unauthorized"))
    client = FlagClient(base_url="http://gateway.test", read_token="wrong")
    with pytest.raises(FlagClientError):
        await client.assign("active_learning_v1", "user-1")


@pytest.mark.asyncio
async def test_assign_4xx_error_does_not_leak_response_body(monkeypatch):
    """AGENTS.md § Secrets — 4xx error must not echo response body (could contain echoed token)."""

    leaky_body = "submitted token was 'super-secret-tok' — invalid"
    _patch_async_client(
        monkeypatch, lambda req: httpx.Response(401, text=leaky_body)
    )
    client = FlagClient(base_url="http://gateway.test", read_token="super-secret-tok")
    with pytest.raises(FlagClientError) as excinfo:
        await client.assign("active_learning_v1", "user-1")

    assert "super-secret-tok" not in str(excinfo.value)
    assert leaky_body not in str(excinfo.value)
    # But status and flag should still be there for ops to triage.
    assert "401" in str(excinfo.value)
    assert "active_learning_v1" in str(excinfo.value)


@pytest.mark.asyncio
async def test_assign_5xx_returns_none(monkeypatch):
    _patch_async_client(
        monkeypatch, lambda req: httpx.Response(503, text="service unavailable")
    )
    client = FlagClient(base_url="http://gateway.test", read_token="tok")
    assert await client.assign("active_learning_v1", "user-1") is None


@pytest.mark.asyncio
async def test_assign_timeout_returns_none(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    _patch_async_client(monkeypatch, handler)
    client = FlagClient(base_url="http://gateway.test", read_token="tok")
    assert await client.assign("active_learning_v1", "user-1") is None


@pytest.mark.asyncio
async def test_assign_invalid_json_raises_flag_client_error(monkeypatch):
    _patch_async_client(
        monkeypatch, lambda req: httpx.Response(200, text="not json at all")
    )
    client = FlagClient(base_url="http://gateway.test", read_token="tok")
    with pytest.raises(FlagClientError):
        await client.assign("active_learning_v1", "user-1")


@pytest.mark.asyncio
async def test_assign_missing_required_key_raises(monkeypatch):
    _patch_async_client(
        monkeypatch, lambda req: httpx.Response(200, json={"flag": "x"})
    )
    client = FlagClient(base_url="http://gateway.test", read_token="tok")
    with pytest.raises(FlagClientError):
        await client.assign("active_learning_v1", "user-1")


@pytest.mark.asyncio
async def test_assign_unexpected_2xx_returns_none(monkeypatch):
    _patch_async_client(monkeypatch, lambda req: httpx.Response(204))
    client = FlagClient(base_url="http://gateway.test", read_token="tok")
    assert await client.assign("active_learning_v1", "user-1") is None


@pytest.mark.asyncio
async def test_default_timeout_constant_matches_doc():
    assert DEFAULT_TIMEOUT_SECONDS == 1.0


@pytest.mark.asyncio
async def test_env_var_construction_strips_slash_and_uses_token(monkeypatch):
    """Construction reads env; trailing slash on base URL must be stripped
    so the path template does not produce a double slash."""

    received: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        received["token"] = request.headers.get(HEADER_FLAGS_READ_TOKEN)
        return httpx.Response(
            200,
            json={"flag": "f", "variant": "control", "user_id": "u"},
        )

    monkeypatch.setenv("GATEWAY_BASE_URL", "http://from-env.test/")
    monkeypatch.setenv("FLAGS_READ_TOKEN", "env-tok")
    _patch_async_client(monkeypatch, handler)

    client = FlagClient()
    assert client.is_configured is True
    await client.assign("f", "u")

    received_url = received["url"] or ""
    # No double slash between host and `/api/v1/...`.
    assert "//api/v1" not in received_url
    assert "/api/v1/flags/f/assign" in received_url
    assert received["token"] == "env-tok"
