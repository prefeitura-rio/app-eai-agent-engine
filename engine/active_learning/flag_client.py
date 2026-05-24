"""Low-privilege HTTP client for Gateway flag assignment endpoint.

Scope
~~~~~
Consumes ``GET /api/v1/flags/:name/assign?user=<id>`` exposed by the Gateway
(see ``study-sf-whatsapp-poc1`` ADR-032 for the security split). The endpoint
is read-only and gated by a separate ``FLAGS_READ_TOKEN`` — never the
``ADMIN_API_TOKEN``. Gateway enforces fail-closed token isolation at
construction time: if both tokens resolve to the same value the endpoint
returns 503 before any compare runs.

Failure model
~~~~~~~~~~~~~
- **Network/timeout failure** → returns ``None``. Caller treats absence of
  assignment as *no experiment active* (degrades to baseline behaviour);
  never blocks LLM call on Gateway availability.
- **HTTP 4xx (config error)** → raises ``FlagClientError``. Misconfigured
  token / unknown flag is a deploy-time bug, not a runtime degradation.
- **HTTP 5xx (Gateway internal error)** → returns ``None``; logs warning.
  Same rationale: never block the citizen on Gateway hiccups.

The fail-open default is deliberate for Iter 2.5 — variant assignment is
an *experiment* layer, not a safety gate. When Iter 3 introduces
calibrated refusal, those decisions get a separate client with fail-closed
semantics.

Lifecycle
~~~~~~~~~
``FlagClient`` owns no shared state. Each ``assign()`` call opens a fresh
``httpx.AsyncClient`` with a short timeout (default 1s). Concurrency
safety is delegated to httpx; the surrounding Engine turn is already async.

Tokens are read from env **at construction** — not per call — so
constructing a module-level singleton at import time is unsafe if env
loading (e.g. dotenv) runs later in startup. Prefer constructing per
request scope or after explicit env bootstrapping. Rotate credentials
by recreating the client.

Cross-repo contract: the Gateway side (study-sf-whatsapp-poc1
``internal/handlers/flags_read.go`` and ``flags_read_test.go``,
specifically ``TestFlagsRead_FailClosedOnTokenOverlap``) asserts the
fail-closed token-isolation behaviour referenced here. Update both
sides when the contract changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final
from urllib.parse import quote

import httpx

from engine.log import logger

DEFAULT_TIMEOUT_SECONDS: Final[float] = 1.0
ENV_GATEWAY_BASE_URL: Final[str] = "GATEWAY_BASE_URL"
ENV_FLAGS_READ_TOKEN: Final[str] = "FLAGS_READ_TOKEN"
HEADER_FLAGS_READ_TOKEN: Final[str] = "X-Flags-Read-Token"


class FlagClientError(Exception):
    """Configuration error: bad token, unknown flag, or invalid request."""


class FlagClientTimeout(Exception):
    """Gateway did not respond within the timeout budget.

    Reserved for the Iter 3 fail-closed surface (uncertainty / refusal
    decisions). The current ``FlagClient`` swallows timeouts and returns
    ``None`` because variant assignment is an experiment layer, not a
    safety gate.
    """


@dataclass(frozen=True)
class FlagAssignment:
    """Resolved variant for a given (flag, user) pair.

    Attributes:
        flag: Flag name as registered in Gateway (e.g. ``active_learning_v1``).
        variant: Bucket the user landed in. Convention: ``control`` or
            ``treatment``; flag definitions may extend this.
        user_id: Echo of the user identifier passed to ``assign()``; useful
            for log correlation.
    """

    flag: str
    variant: str
    user_id: str


class FlagClient:
    """HTTP client for the Gateway flag-assignment endpoint.

    Construction does not perform I/O; it captures credentials and base
    URL. ``assign()`` is the only network-touching method.
    """

    def __init__(
        self,
        base_url: str | None = None,
        read_token: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = (base_url or os.getenv(ENV_GATEWAY_BASE_URL, "")).rstrip("/")
        self._read_token = read_token or os.getenv(ENV_FLAGS_READ_TOKEN, "")
        self._timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        """True iff base URL and token are both set."""

        return bool(self._base_url and self._read_token)

    async def assign(self, flag_name: str, user_id: str) -> FlagAssignment | None:
        """Resolve the variant for ``user_id`` under ``flag_name``.

        Returns:
            ``FlagAssignment`` on a successful 200 response.
            ``None`` if the client is not configured, the Gateway times
            out, or the Gateway returns a 5xx.

        Raises:
            FlagClientError: On 4xx responses (configuration error).
        """

        if not self.is_configured:
            logger.debug(
                "FlagClient skipped — missing GATEWAY_BASE_URL or FLAGS_READ_TOKEN"
            )
            return None

        escaped_flag = quote(flag_name, safe="")
        url = f"{self._base_url}/api/v1/flags/{escaped_flag}/assign"
        headers = {HEADER_FLAGS_READ_TOKEN: self._read_token}
        params = {"user": user_id}

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.TimeoutException:
            logger.warning(
                f"FlagClient timeout after {self._timeout_seconds}s "
                f"flag={flag_name} user={user_id}"
            )
            return None
        except httpx.HTTPError as exc:
            logger.warning(
                f"FlagClient transport error flag={flag_name} user={user_id}: {exc}"
            )
            return None

        if 500 <= response.status_code < 600:
            logger.warning(
                f"FlagClient Gateway 5xx flag={flag_name} user={user_id} "
                f"status={response.status_code}"
            )
            return None

        if 400 <= response.status_code < 500:
            # Body intentionally omitted from the error: a misconfigured
            # auth middleware echoing the submitted token back would
            # leak credentials into upstream logs / exception sinks.
            # AGENTS.md § Secrets — never echo token material.
            raise FlagClientError(
                f"FlagClient configuration error flag={flag_name} "
                f"status={response.status_code}"
            )

        if response.status_code != 200:
            logger.warning(
                f"FlagClient unexpected status flag={flag_name} "
                f"status={response.status_code}"
            )
            return None

        try:
            payload = response.json()
        except ValueError as exc:
            raise FlagClientError(
                f"FlagClient invalid JSON flag={flag_name}: {exc}"
            ) from exc

        try:
            return FlagAssignment(
                flag=str(payload["flag"]),
                variant=str(payload["variant"]),
                user_id=str(payload.get("user_id", user_id)),
            )
        except KeyError as exc:
            raise FlagClientError(
                f"FlagClient missing key in response flag={flag_name}: {exc}"
            ) from exc
