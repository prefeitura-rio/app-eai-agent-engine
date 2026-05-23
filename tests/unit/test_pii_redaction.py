"""Unit tests for ``engine.middleware.pii_redaction``.

Coverage targets:
- Each PT-BR pattern (CPF, CNPJ, CEP, RG, telefone, endereço heurístico)
  redacts the canonical mask and is restored byte-perfect.
- Same value inside one redactor gets the same token (stable identity).
- Non-PII text is untouched (no false positives in safe sentences).
- Idempotence: restore on text with no token is a no-op; restore is the
  perfect inverse of redact.
- Defensive: empty / None / non-string inputs do not raise.
"""

from __future__ import annotations

import pytest

from engine.middleware.pii_redaction import (
    CATEGORY_CEP,
    CATEGORY_CNPJ,
    CATEGORY_CPF,
    CATEGORY_ENDERECO,
    CATEGORY_RG,
    CATEGORY_TELEFONE,
    PIIRedactor,
    iter_known_categories,
    redact,
    restore,
)


# ---------- Per-category match + round-trip ----------


@pytest.mark.parametrize(
    "value, category",
    [
        ("123.456.789-09", CATEGORY_CPF),
        ("12.345.678/0001-95", CATEGORY_CNPJ),
        ("22041-001", CATEGORY_CEP),
        ("12.345.678-9", CATEGORY_RG),
        ("12.345.678-X", CATEGORY_RG),
        ("+55 21 99999-1234", CATEGORY_TELEFONE),
        ("(21) 99999-1234", CATEGORY_TELEFONE),
        ("(21) 2222-3333", CATEGORY_TELEFONE),
        ("Rua das Flores, 100", CATEGORY_ENDERECO),
        ("Av. Brasil, 2500", CATEGORY_ENDERECO),
        ("Avenida Atlântica, 1702", CATEGORY_ENDERECO),
    ],
)
def test_pattern_redacts_and_restores_round_trip(value, category):
    sentence = f"Meu dado: {value}, obrigado."
    redacted_text, mapping = redact(sentence)
    # Original PII must NOT appear in the redacted text.
    assert value not in redacted_text, (
        f"PII {category!r} leaked: {value!r} still in {redacted_text!r}"
    )
    # A token of the right shape must appear.
    assert f"[{category}_TOKEN_1]" in redacted_text
    # Mapping records the token → original value.
    assert mapping[f"[{category}_TOKEN_1]"] == value
    # Round-trip yields the original sentence.
    assert restore(redacted_text, mapping) == sentence


# ---------- Stable identity within one redactor ----------


def test_same_value_gets_same_token_within_redactor():
    redactor = PIIRedactor()
    first = redactor.redact("Meu CPF é 123.456.789-09.")
    second = redactor.redact("Confirmo, CPF 123.456.789-09 mesmo.")
    assert "[CPF_TOKEN_1]" in first
    assert "[CPF_TOKEN_1]" in second
    # No second token was minted for the same value.
    assert "[CPF_TOKEN_2]" not in second


def test_different_values_get_different_tokens():
    redactor = PIIRedactor()
    sentence = (
        "Um CPF é 123.456.789-09 e outro é 987.654.321-00, ambos válidos."
    )
    redacted = redactor.redact(sentence)
    assert "[CPF_TOKEN_1]" in redacted
    assert "[CPF_TOKEN_2]" in redacted
    assert "123.456.789-09" not in redacted
    assert "987.654.321-00" not in redacted


def test_multiple_categories_in_one_message_round_trip():
    sentence = (
        "Sou o cliente João, CPF 123.456.789-09, CEP 22041-001, "
        "fone (21) 99999-1234, moro na Av. Brasil, 2500."
    )
    redacted_text, mapping = redact(sentence)
    for piece in [
        "123.456.789-09",
        "22041-001",
        "(21) 99999-1234",
        "Av. Brasil, 2500",
    ]:
        assert piece not in redacted_text, f"PII leaked: {piece!r}"
    assert restore(redacted_text, mapping) == sentence


# ---------- No false positives on safe text ----------


@pytest.mark.parametrize(
    "safe_text",
    [
        "Bom dia, gostaria de saber sobre o IPTU.",
        "Tenho dúvida sobre o protocolo 12345.",
        "O número do meu pedido é 67890.",
        "Quero falar sobre poda de árvore na minha rua.",
        "1746 atende 24 horas por dia.",
        "O ano é 2026.",
    ],
)
def test_safe_text_is_not_redacted(safe_text):
    redacted_text, mapping = redact(safe_text)
    assert redacted_text == safe_text
    assert mapping == {}


# ---------- Idempotence + restore robustness ----------


def test_restore_is_noop_on_text_without_tokens():
    assert restore("Olá, tudo bem?", {"[CPF_TOKEN_1]": "999.999.999-99"}) == "Olá, tudo bem?"


def test_restore_with_empty_mapping_is_noop():
    text = "Olá [CPF_TOKEN_1], tudo bem?"
    assert restore(text, {}) == text


def test_restore_unknown_token_left_intact():
    text = "Olá [CPF_TOKEN_99], tudo bem?"
    assert restore(text, {"[CPF_TOKEN_1]": "111.111.111-11"}) == text


def test_redact_then_restore_is_identity():
    sentence = (
        "Sou o cliente, CPF 123.456.789-09, fone (21) 99999-1234, "
        "endereço Rua das Flores, 100, CEP 22041-001."
    )
    redacted_text, mapping = redact(sentence)
    assert restore(redacted_text, mapping) == sentence


def test_restore_handles_double_digit_token_numbers():
    """Token ``[CPF_TOKEN_10]`` must not be partially restored as
    ``[CPF_TOKEN_1]0``. The mapping iterates longest-first.
    """
    redactor = PIIRedactor()
    # Force 10+ tokens by feeding 11 distinct CPFs.
    cpfs = [f"{i:03d}.456.789-09" for i in range(100, 111)]
    sentence = " ".join(f"CPF {c}." for c in cpfs)
    redacted = redactor.redact(sentence)
    restored = redactor.restore(redacted)
    assert restored == sentence
    # And the highest-numbered token actually got minted.
    assert "[CPF_TOKEN_11]" in redacted


# ---------- Defensive: bad inputs do not raise ----------


@pytest.mark.parametrize("bad_input", ["", None, 12345, [], {}])
def test_redact_handles_non_string_input(bad_input):
    redacted_text, mapping = redact(bad_input)  # type: ignore[arg-type]
    assert redacted_text == bad_input
    assert mapping == {}


@pytest.mark.parametrize("bad_input", ["", None, 12345, [], {}])
def test_restore_handles_non_string_input(bad_input):
    assert restore(bad_input, {"[CPF_TOKEN_1]": "111.111.111-11"}) == bad_input  # type: ignore[arg-type]


# ---------- Introspection ----------


def test_iter_known_categories_covers_expected_set():
    assert set(iter_known_categories()) == {
        CATEGORY_CNPJ,
        CATEGORY_CPF,
        CATEGORY_CEP,
        CATEGORY_RG,
        CATEGORY_ENDERECO,
        CATEGORY_TELEFONE,
    }


# ---------- Pattern boundary cases ----------


def test_phone_does_not_match_loose_digit_runs():
    """Year, protocol numbers, plain numbers must not match the phone pattern."""
    sentence = "Em 2026 abri protocolo 0800 282 8181 sobre rua das flores."
    redacted_text, mapping = redact(sentence)
    # No telefone token must be created from this — the loose-digits should be ignored.
    assert "[TELEFONE_TOKEN_1]" not in redacted_text
    # "Rua das Flores" lowercase shouldn't match the address heuristic
    # because it requires a capitalised street name and a number after a
    # comma. Without comma+digits, it shouldn't.
    assert "[ENDERECO_TOKEN_1]" not in redacted_text


def test_cnpj_matched_before_cpf():
    """A CNPJ string ``00.000.000/0000-00`` must not be partially redacted as a
    CPF (which would leave the ``/0000-00`` fragment dangling)."""
    sentence = "Minha empresa é CNPJ 12.345.678/0001-95, registrada."
    redacted_text, mapping = redact(sentence)
    assert "[CNPJ_TOKEN_1]" in redacted_text
    assert "12.345.678/0001-95" not in redacted_text
    # No CPF token was leaked.
    assert "[CPF_TOKEN_1]" not in redacted_text


def test_redactor_mapping_is_externalisable():
    """The redactor's ``mapping`` is a plain dict-like that callers can
    serialise / store with TTL outside this module.
    """
    redactor = PIIRedactor()
    redactor.redact("Meu CPF é 123.456.789-09.")
    serialised = dict(redactor.mapping)
    assert serialised == {"[CPF_TOKEN_1]": "123.456.789-09"}
    # And the same dict can be used by the free function `restore` later.
    assert restore("Olá [CPF_TOKEN_1]!", serialised) == "Olá 123.456.789-09!"
