"""PT-BR PII redaction middleware for outbound LLM calls.

Scope
~~~~~
- **Input side:** turn citizen-supplied free text into a redacted form
  whose tokens (``[CPF_TOKEN_1]``, ``[CEP_TOKEN_2]``, …) are stable inside
  a single ``PIIRedactor`` instance so the LLM can refer back to the same
  value across a turn.
- **Output side:** restore the LLM's response by substituting the tokens
  back to the original PII values.

The redactor is **per-thread / per-turn**. Callers are expected to build
one ``PIIRedactor`` per LLM invocation, hold it across the round-trip,
then discard. Memory lifetime is bounded by the caller (the plan calls
out a ~10 min TTL for the mapping; this module does not implement that
TTL — it just refuses to leak across redactor instances).

Tools that *legitimately* need PII (e.g. consulting IPTU by CPF) must
operate on the **restored** text — i.e. after the agent's response has
been run through ``restore``. Document any such flow at the call-site.

Patterns covered
~~~~~~~~~~~~~~~~
The patterns are intentionally conservative: PT-BR formatted CPF/CNPJ/CEP
must use their canonical separators (``999.999.999-99`` etc.); we do not
try to match every loose digit sequence because false positives are worse
than misses for compliance — the threat model is "PII pasted by the
citizen in obvious form", not "PII reconstructed from spans of digits".

Order of redaction matters: longer/more specific patterns run first so
they are not partially consumed by shorter patterns. Rua/Av prefixes are
matched before phone numbers since street addresses can contain digit
runs.

Categories (in match order):
1. CNPJ — ``00.000.000/0000-00``
2. CPF — ``000.000.000-00``
3. CEP — ``00000-000``
4. RG — variable digit/separator (Brazilian RG has no canonical mask;
   we match the most common ``XX.XXX.XXX-X`` / ``XX.XXX.XXX`` shapes)
5. Endereço heurístico — ``Rua|Av|Avenida|Travessa|Alameda|Praça|Estrada
   <Nome>, <num>``
6. Telefone E.164 / formato BR — ``+55 21 9XXXX-XXXX`` and common
   variants

Non-PII text is untouched. The redactor is idempotent on already-redacted
input: running ``redact(text_with_tokens)`` again is a no-op for the
tokens themselves.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Mapping, MutableMapping, Pattern


# Token category labels — kept in one place so callers can introspect.
CATEGORY_CNPJ: str = "CNPJ"
CATEGORY_CPF: str = "CPF"
CATEGORY_CEP: str = "CEP"
CATEGORY_RG: str = "RG"
CATEGORY_ENDERECO: str = "ENDERECO"
CATEGORY_TELEFONE: str = "TELEFONE"


# Pattern definitions. Order matters — longer/more specific first.
# Each tuple is (category, compiled-pattern). Patterns must match the
# entire formatted PII (no partial matches) to keep restore unambiguous.
_PATTERNS: list[tuple[str, Pattern[str]]] = [
    # CNPJ: 00.000.000/0000-00
    (
        CATEGORY_CNPJ,
        re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),
    ),
    # CPF: 000.000.000-00
    (
        CATEGORY_CPF,
        re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    ),
    # CEP: 00000-000
    (
        CATEGORY_CEP,
        re.compile(r"\b\d{5}-\d{3}\b"),
    ),
    # RG (PT-BR conventions vary by state — match the two common masks).
    # Matches: 12.345.678-9, 12.345.678-X, 12.345.678
    (
        CATEGORY_RG,
        re.compile(r"\b\d{2}\.\d{3}\.\d{3}(?:-[\dXx])?\b"),
    ),
    # Endereço heurístico: <Rua|Av|...> <Nome capitalizado>, <num>[ ...]
    # Caveat: this is intentionally narrow — only catches obvious form;
    # bots seeing free-form "moro na rua das flores 10" miss on purpose
    # to keep false-positive surface manageable.
    (
        CATEGORY_ENDERECO,
        re.compile(
            r"\b(?:Rua|Av\.?|Avenida|Travessa|Tv\.?|Alameda|Pra[çc]a|Estrada|Rod\.?|Rodovia)"
            r"\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\.\- ]*?,\s*\d+[A-Za-z]?\b",
        ),
    ),
    # Telefone E.164 BR completo: +55 21 9XXXX-XXXX, +5521 9XXXX-XXXX,
    # +55 21 9 XXXX-XXXX, (21) 9XXXX-XXXX, (21) 9 XXXX-XXXX, also
    # supports landline (8-digit) variants.
    # Caveat: we intentionally require either +55 or (DDD) so loose
    # numeric runs like dates ("0800 282 8181") don't trip.
    (
        CATEGORY_TELEFONE,
        re.compile(
            r"(?:"
            r"\+55\s?\d{2}\s?9?\s?\d{4}[- ]?\d{4}"  # +55 21 9XXXX-XXXX
            r"|"
            r"\(\d{2}\)\s?9?\s?\d{4}[- ]?\d{4}"  # (21) 9XXXX-XXXX
            r")"
        ),
    ),
]


@dataclass
class PIIRedactor:
    """Stateful redactor for one LLM round-trip.

    Attributes
    ----------
    mapping:
        ``token → original_value`` map used by :meth:`restore`. Exposed
        for callers that need to persist or inspect the mapping (audit
        log, debugging). Treat as read-only after construction; the
        redactor mutates it during :meth:`redact`.
    counters:
        Internal per-category counter so tokens are numbered
        deterministically (``[CPF_TOKEN_1]``, ``[CPF_TOKEN_2]``).
    reverse_mapping:
        ``original_value → token`` cache so the same PII inside a turn
        gets the same token (the LLM can reason about it as one entity).
    """

    mapping: MutableMapping[str, str] = field(default_factory=dict)
    counters: MutableMapping[str, int] = field(default_factory=dict)
    reverse_mapping: MutableMapping[str, str] = field(default_factory=dict)

    def redact(self, text: str) -> str:
        """Return ``text`` with every recognised PII span replaced by a token.

        Stable within the redactor instance: identical PII gets the same
        token across multiple ``redact`` calls. Empty or non-string input
        is returned unchanged.
        """
        if not text or not isinstance(text, str):
            return text
        redacted = text
        for category, pattern in _PATTERNS:
            redacted = pattern.sub(
                lambda match, category=category: self._token_for(category, match.group(0)),
                redacted,
            )
        return redacted

    def restore(self, text: str) -> str:
        """Inverse of :meth:`redact`: token → original PII.

        Idempotent on text with no tokens. Tokens whose mapping is missing
        are left intact (defensive — never leak a wrong PII because a
        token got malformed).
        """
        if not text or not isinstance(text, str):
            return text
        restored = text
        # Replace longest tokens first so e.g. ``[CPF_TOKEN_10]`` is not
        # partially consumed by ``[CPF_TOKEN_1]``.
        for token in sorted(self.mapping.keys(), key=len, reverse=True):
            if token in restored:
                restored = restored.replace(token, self.mapping[token])
        return restored

    def _token_for(self, category: str, value: str) -> str:
        """Allocate (or reuse) a token for ``value`` under ``category``."""
        existing = self.reverse_mapping.get(value)
        if existing is not None:
            return existing
        counter = self.counters.get(category, 0) + 1
        self.counters[category] = counter
        token = f"[{category}_TOKEN_{counter}]"
        self.mapping[token] = value
        self.reverse_mapping[value] = token
        return token


def redact(text: str) -> tuple[str, dict[str, str]]:
    """Single-shot redact: build a fresh ``PIIRedactor``, return text + mapping.

    Use this when you do not need to redact a follow-up across more than
    one string. For multi-string flows (e.g. multiple messages in one
    turn that should share tokens) instantiate :class:`PIIRedactor` and
    call ``redact`` per string.
    """
    redactor = PIIRedactor()
    redacted = redactor.redact(text)
    # Return a *plain* dict so the caller can serialise without surprises.
    return redacted, dict(redactor.mapping)


def restore(text: str, mapping: Mapping[str, str]) -> str:
    """Single-shot restore from a token→PII mapping.

    The mapping does not have to come from the same ``PIIRedactor`` that
    produced it; any dict-like with the right shape works.
    """
    if not text or not isinstance(text, str) or not mapping:
        return text
    restored = text
    for token in sorted(mapping.keys(), key=len, reverse=True):
        if token in restored:
            restored = restored.replace(token, mapping[token])
    return restored


def iter_known_categories() -> Iterable[str]:
    """Iterate the categories the current pattern set redacts.

    Useful for tests/dashboards that want to enumerate coverage.
    """
    seen: set[str] = set()
    for category, _ in _PATTERNS:
        if category not in seen:
            seen.add(category)
            yield category


# --- Per-thread mapping cache --------------------------------------------------
#
# The agent runtime needs the *same* token→value mapping to survive across a
# single LangGraph invocation (redact happens at pre-invoke, restore happens at
# post-model + worker-callback) and ideally across follow-up turns inside the
# short-term-memory window so the LLM keeps reasoning about the same entity
# token if the user references it again.
#
# Implementation
# ~~~~~~~~~~~~~~
# - Keyed by ``thread_id`` (LangGraph thread = WhatsApp conversation).
# - Each entry holds an immutable copy of the mapping + last-access timestamp.
# - TTL is configurable per cache instance (the caller sets it to align with
#   the project's short-term memory window — default ``600`` seconds = 10 min).
# - Thread-safe; the underlying lock is fine-grained (one lock per cache; the
#   throughput target is hundreds of conversations / hour, not microservice
#   levels, so a single mutex is enough).
# - Eviction is lazy: ``get``/``update`` purges expired entries before reading.

_DEFAULT_PII_CACHE_TTL_SECONDS: int = 600


@dataclass
class _PIICacheEntry:
    """Internal cache row: mapping + last-access wall-clock seconds."""

    mapping: dict[str, str]
    last_access: float


class PIIThreadCache:
    """TTL-bounded per-thread token→PII mapping store.

    The cache is process-local. Multi-replica deployments lose mapping
    continuity across replicas; that is acceptable because (a) the redactor
    is deterministic on stable token numbering inside one turn, and (b) cross-
    turn restoration is a best-effort UX nicety, not a correctness invariant
    (the underlying PII is also stored in the LangGraph checkpoint, redacted
    only for the LLM call — the citizen-visible response is reconstructed
    inside the same Engine process that just talked to the LLM).
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_PII_CACHE_TTL_SECONDS) -> None:
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._lock = threading.Lock()
        self._entries: dict[str, _PIICacheEntry] = {}

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def get(self, thread_id: str) -> dict[str, str]:
        """Return the live mapping for ``thread_id`` (empty dict if absent/expired)."""
        if not thread_id:
            return {}
        with self._lock:
            self._evict_expired_locked()
            entry = self._entries.get(thread_id)
            if entry is None:
                return {}
            entry.last_access = time.monotonic()
            # Return a copy so callers can iterate without holding the lock.
            return dict(entry.mapping)

    def update(self, thread_id: str, new_pairs: Mapping[str, str]) -> dict[str, str]:
        """Merge ``new_pairs`` into the thread's mapping, return the full mapping.

        Existing tokens keep their original values (the redactor is
        deterministic on the per-instance counter; if the same PII appears
        across turns it gets a *new* token from the fresh redactor, but the
        old token still maps to the same value, so both keep resolving).
        """
        if not thread_id:
            return dict(new_pairs)
        with self._lock:
            self._evict_expired_locked()
            entry = self._entries.get(thread_id)
            if entry is None:
                entry = _PIICacheEntry(mapping={}, last_access=time.monotonic())
                self._entries[thread_id] = entry
            for token, value in new_pairs.items():
                # First-writer-wins: if a token already maps to a value we
                # keep that one — a fresh redactor in a later turn might
                # collide on a counter but the user-visible PII is what we
                # care about preserving.
                entry.mapping.setdefault(token, value)
            entry.last_access = time.monotonic()
            return dict(entry.mapping)

    def redact_and_merge(
        self, thread_id: str, text: str
    ) -> tuple[str, dict[str, str]]:
        """Atomically redact ``text`` against the thread's mapping and merge new tokens.

        Holds the cache lock for the *entire* duration of the redact + merge
        cycle so two concurrent requests for the same ``thread_id`` cannot
        both mint ``[CPF_TOKEN_1]`` for different PII values. Without this
        atomicity the read-snapshot / mint / write-back sequence has a race
        window equal to the regex pass — short, but observable under load
        (Engine workers serve hundreds of concurrent threads via the same
        process).

        Returns ``(redacted_text, full_mapping)``. The full mapping always
        contains every token the thread carries (including ones minted by
        other concurrent calls before this one).

        Memory shape: a thread entry is only persisted in the cache when the
        redaction produced at least one token. Non-PII text on a brand-new
        ``thread_id`` does not create a zero-length row, so workers serving
        thousands of unique threads with mostly non-PII traffic do not pay
        for empty cache rows.
        """
        if not thread_id or not text or not isinstance(text, str):
            existing = self._entries.get(thread_id) if thread_id else None
            return text, (dict(existing.mapping) if existing else {})
        with self._lock:
            self._evict_expired_locked()
            entry = self._entries.get(thread_id)
            existing_mapping = entry.mapping if entry is not None else {}
            redactor = _build_seeded_redactor(existing_mapping)
            redacted = redactor.redact(text)
            new_tokens = {
                token: value
                for token, value in redactor.mapping.items()
                if token not in existing_mapping
            }
            if entry is None and not new_tokens:
                # No prior mapping AND no fresh PII → do NOT persist an empty
                # row. Keeps the cache size proportional to the number of
                # threads that actually saw redacted spans.
                return redacted, {}
            if entry is None:
                entry = _PIICacheEntry(mapping={}, last_access=time.monotonic())
                self._entries[thread_id] = entry
            for token, value in new_tokens.items():
                entry.mapping.setdefault(token, value)
            entry.last_access = time.monotonic()
            return redacted, dict(entry.mapping)

    def drop(self, thread_id: str) -> None:
        """Forget the mapping for ``thread_id`` (used by tests/manual reset)."""
        if not thread_id:
            return
        with self._lock:
            self._entries.pop(thread_id, None)

    def size(self) -> int:
        """Number of thread entries currently held (post-eviction)."""
        with self._lock:
            self._evict_expired_locked()
            return len(self._entries)

    def _evict_expired_locked(self) -> None:
        """Drop entries whose ``last_access`` is older than ``ttl_seconds``.

        Must be called with ``_lock`` already held.
        """
        deadline = time.monotonic() - self._ttl_seconds
        expired = [tid for tid, entry in self._entries.items() if entry.last_access < deadline]
        for tid in expired:
            self._entries.pop(tid, None)


def redact_with_cache(
    text: str,
    cache: PIIThreadCache,
    thread_id: str,
) -> tuple[str, dict[str, str]]:
    """Redact ``text`` and merge the new tokens into ``cache`` for ``thread_id``.

    Returns ``(redacted_text, full_mapping)`` where ``full_mapping`` includes
    both the freshly-minted tokens for this call and any prior tokens that the
    same thread carries from earlier turns within the TTL window.

    Cross-call continuity
    ~~~~~~~~~~~~~~~~~~~~~
    Each call creates a *new* :class:`PIIRedactor`, but we seed its counters
    and reverse-mapping from the cache so:

    1. Re-encountering a PII value across calls reuses its existing token
       (e.g. CPF 123.456.789-09 mentioned on turn 1 and again on turn 5
       both resolve to ``[CPF_TOKEN_1]``).
    2. A brand-new PII value on a later turn gets the *next* unused number
       in that category (so we never collide ``[CPF_TOKEN_1]`` across two
       different CPFs).

    Concurrency
    ~~~~~~~~~~~
    Uses :meth:`PIIThreadCache.redact_and_merge` so the entire snapshot →
    mint → merge sequence runs under the cache lock; two concurrent calls
    for the same ``thread_id`` can therefore never assign the same token
    number to different PII values.
    """
    if not thread_id:
        return _redact_without_cache(text)
    if not text or not isinstance(text, str):
        return text, cache.get(thread_id)
    return cache.redact_and_merge(thread_id, text)


def _redact_without_cache(text: str) -> tuple[str, dict[str, str]]:
    """Fallback when no thread_id was supplied — behaves like :func:`redact`."""
    if not text or not isinstance(text, str):
        return text, {}
    return redact(text)


def _build_seeded_redactor(existing_mapping: Mapping[str, str]) -> PIIRedactor:
    """Construct a redactor whose counters / reverse-mapping resume from
    ``existing_mapping``.

    The shape of the tokens is ``[<CATEGORY>_TOKEN_<N>]``; we parse N back out
    so the next token minted for the same category continues at N+1 instead
    of restarting at 1.
    """
    redactor = PIIRedactor()
    if not existing_mapping:
        return redactor
    counters: dict[str, int] = {}
    for token, value in existing_mapping.items():
        redactor.mapping[token] = value
        redactor.reverse_mapping[value] = token
        # Token shape: "[<CATEGORY>_TOKEN_<N>]"
        # Strip the bracketed wrapper, split, take the last segment as N.
        bare = token.strip("[]")
        if "_TOKEN_" not in bare:
            continue
        category, _, number_str = bare.rpartition("_TOKEN_")
        try:
            number = int(number_str)
        except ValueError:
            continue
        current = counters.get(category, 0)
        if number > current:
            counters[category] = number
    redactor.counters.update(counters)
    return redactor


def restore_with_cache(
    text: str,
    cache: PIIThreadCache,
    thread_id: str,
) -> str:
    """Restore PII tokens in ``text`` using the cached mapping for ``thread_id``.

    Returns ``text`` unchanged if the cache holds no mapping for the thread
    (typical for replies that contain no redacted spans).
    """
    if not text or not isinstance(text, str) or not thread_id:
        return text
    mapping = cache.get(thread_id)
    if not mapping:
        return text
    return restore(text, mapping)


_PII_MARKER_RE: Pattern[str] = re.compile(r"\[[A-Z_]+_TOKEN_\d+\]")


def text_contains_token(text: str) -> bool:
    """Cheap predicate: does ``text`` carry any redaction token?

    Useful for short-circuiting restore on payloads that obviously hold no
    redactor output (most non-PII responses).
    """
    if not text or not isinstance(text, str):
        return False
    return bool(_PII_MARKER_RE.search(text))
