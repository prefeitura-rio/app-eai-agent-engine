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
