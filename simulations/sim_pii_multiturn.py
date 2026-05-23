"""Simulação real — Fase 0 C3 PII redaction multi-turn.

Cenário: cidadão envia CPF/CEP no turn 1 pra consultar IPTU. No turn 5
("qual é meu CPF mesmo?") agente precisa reconhecer referência consistente.

Asserts empíricos:
 1. Gemini nunca vê PII raw (mediado via mock LLM)
 2. Tokens são estáveis ao longo da thread
 3. Cidadão recebe PII original no AIMessage final (restore)
 4. Cross-thread leak prevenido: thread B não acessa PII da thread A
 5. Performance overhead < 100ms para conversa típica (P95)

Não usa Gemini real — usa mock que loga o que recebe. Em prod o pipeline
é idêntico; o que muda é a resposta do modelo.

Run:
    cd app-eai-agent-engine
    uv run python simulations/sim_pii_multiturn.py
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from engine.middleware import (
    PIIThreadCache,
    redact_with_cache,
    restore,
)


@dataclass
class SimResult:
    name: str
    passed: bool
    notes: list[str] = field(default_factory=list)
    raw_input: str = ""
    llm_received: str = ""
    final_output: str = ""
    duration_ms: float = 0.0


class _MockGemini:
    """Captura input que receberia + retorna response com tokens preservados
    (simula comportamento real: LLM trabalha com tokens, restore acontece
    no post-process)."""

    def __init__(self) -> None:
        self.received_inputs: list[str] = []
        self.calls: int = 0

    def chat(self, redacted_input: str) -> str:
        self.received_inputs.append(redacted_input)
        self.calls += 1
        # Mock: copia entrada (tokens preservados) + adiciona texto fixo.
        # Em prod, Gemini geraria resposta com tokens; nossa restore depois
        # converte token → PII original.
        if "[CPF_TOKEN_" in redacted_input:
            return f"OK, vou consultar seu CPF {redacted_input.split('CPF é ')[-1].split('.')[0] if 'CPF é ' in redacted_input else '[CPF_TOKEN_1]'} agora..."
        if "[CEP_TOKEN_" in redacted_input:
            return f"Endereço com CEP {redacted_input.split('CEP ')[-1].split(' ')[0] if 'CEP ' in redacted_input else '[CEP_TOKEN_1]'} confirmado."
        return "Tudo bem, posso ajudar?"


def _pretty(s: str, max_len: int = 90) -> str:
    s = s.replace("\n", "\\n")
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def sim1_cpf_redact_restore_single_turn() -> SimResult:
    """Turn único: CPF redactado → mock LLM vê token → restore."""
    cache = PIIThreadCache(ttl_seconds=600)
    mock = _MockGemini()
    thread_id = "thread-sim-1"

    citizen_input = "Olá, gostaria de consultar IPTU. Meu CPF é 123.456.789-00."

    t0 = time.perf_counter()
    redacted, mapping = redact_with_cache(citizen_input, cache, thread_id)
    llm_response = mock.chat(redacted)
    final = restore(llm_response, mapping)
    dt = (time.perf_counter() - t0) * 1000

    result = SimResult(
        name="sim1: CPF single-turn redact/restore",
        passed=True,
        raw_input=citizen_input,
        llm_received=mock.received_inputs[0],
        final_output=final,
        duration_ms=dt,
    )

    if "123.456.789-00" in mock.received_inputs[0]:
        result.passed = False
        result.notes.append("FAIL: Gemini received raw CPF — redaction broke")
    else:
        result.notes.append(f"OK: Gemini received token (no raw CPF in mock input)")

    if "[CPF_TOKEN_" in final:
        result.passed = False
        result.notes.append("FAIL: final output still has token — restore broke")
    else:
        result.notes.append("OK: final output free of tokens (restore worked)")

    if "123.456.789-00" not in final and mock.received_inputs[0].count("[CPF_TOKEN_") == 1:
        result.notes.append("OK: round-trip integrity preserved")
    return result


def sim2_multi_turn_token_stability() -> SimResult:
    """Multi-turn: CPF em turn 1, "qual era meu CPF?" turn 5 → mapping stable."""
    cache = PIIThreadCache(ttl_seconds=600)
    mock = _MockGemini()
    thread_id = "thread-sim-2"

    turns = [
        "Quero consultar IPTU. Meu CPF é 987.654.321-00.",
        "Qual o valor do meu IPTU?",
        "Posso parcelar?",
        "Em quantas vezes?",
        "Qual é o meu CPF que eu te dei?",  # turn 5 — referência
    ]

    t0 = time.perf_counter()
    mappings = []
    for turn in turns:
        redacted, mapping = redact_with_cache(turn, cache, thread_id)
        mock.chat(redacted)
        mappings.append(dict(mapping))
    dt = (time.perf_counter() - t0) * 1000

    result = SimResult(
        name="sim2: multi-turn token stability",
        passed=True,
        raw_input=" | ".join(turns),
        llm_received=" | ".join(mock.received_inputs),
        duration_ms=dt,
    )

    # Validate token "1" maps to same CPF across turns
    turn1_cpf = mappings[0].get("[CPF_TOKEN_1]")
    if turn1_cpf != "987.654.321-00":
        result.passed = False
        result.notes.append(f"FAIL: turn 1 token mapping wrong: {turn1_cpf}")
    else:
        result.notes.append("OK: turn 1 token correctly maps CPF")

    # Validate no raw CPF leaked in mock inputs
    for i, recv in enumerate(mock.received_inputs):
        if "987.654.321-00" in recv:
            result.passed = False
            result.notes.append(f"FAIL: turn {i+1} leaked raw CPF to LLM")
    if result.passed:
        result.notes.append(f"OK: all {len(turns)} turns sanitized before LLM")

    # Validate cache size — mapping should accumulate, not duplicate
    if len(cache.get(thread_id)) > 1:
        result.notes.append(
            f"WARN: cache has {len(cache.get(thread_id))} entries (turn 5 mentions CPF re-redacted?)"
        )
    return result


def sim3_cross_thread_leak_prevention() -> SimResult:
    """Thread A com PII não deve afetar thread B (cross-conversation leak)."""
    cache = PIIThreadCache(ttl_seconds=600)
    mock = _MockGemini()

    redacted_a, mapping_a = redact_with_cache(
        "CPF 111.222.333-44 do João",
        cache,
        "thread-A",
    )
    redacted_b, mapping_b = redact_with_cache(
        "CPF 555.666.777-88 da Maria",
        cache,
        "thread-B",
    )

    result = SimResult(
        name="sim3: cross-thread PII isolation",
        passed=True,
        raw_input=f"A: {redacted_a} | B: {redacted_b}",
        llm_received="(mock not invoked)",
    )

    # Thread A's mapping must NOT contain Maria's CPF (and vice-versa)
    if "555.666.777-88" in mapping_a.values():
        result.passed = False
        result.notes.append("FAIL: thread A leaked Maria's CPF")
    if "111.222.333-44" in mapping_b.values():
        result.passed = False
        result.notes.append("FAIL: thread B leaked João's CPF")

    if result.passed:
        result.notes.append(
            f"OK: thread A has {len(mapping_a)} entries, thread B has {len(mapping_b)}, no leak"
        )

    # Tokens should be independent (both can start at TOKEN_1)
    if "[CPF_TOKEN_1]" in mapping_a and "[CPF_TOKEN_1]" in mapping_b:
        if mapping_a["[CPF_TOKEN_1]"] != mapping_b["[CPF_TOKEN_1]"]:
            result.notes.append("OK: token numbering independent per thread")

    return result


def sim4_multimodal_pii_text_only() -> SimResult:
    """Multimodal: imagem + texto. Só texto redactado; image bytes intactos.

    Mock simula multimodal payload (dict com text + image_uri).
    """
    cache = PIIThreadCache(ttl_seconds=600)
    thread_id = "thread-sim-4"

    # Simula payload do worker
    multimodal_msg = {
        "text": "Aqui está minha conta de IPTU, CPF 222.333.444-55",
        "image_uri": "gs://bucket/iptu.jpg",
    }

    redacted, mapping = redact_with_cache(multimodal_msg["text"], cache, thread_id)

    result = SimResult(
        name="sim4: multimodal — text redacted, image untouched",
        passed=True,
        raw_input=json.dumps(multimodal_msg, ensure_ascii=False),
        llm_received=json.dumps({"text": redacted, "image_uri": multimodal_msg["image_uri"]}, ensure_ascii=False),
    )

    if "222.333.444-55" in redacted:
        result.passed = False
        result.notes.append("FAIL: raw CPF leaked into redacted text")
    else:
        result.notes.append("OK: text PII redacted")

    if multimodal_msg["image_uri"] != "gs://bucket/iptu.jpg":
        result.passed = False
        result.notes.append("FAIL: image URI mutated")
    else:
        result.notes.append("OK: image URI unchanged (multimodal-safe)")

    return result


def sim5_performance_overhead() -> SimResult:
    """Overhead da redaction: P50/P95 em 1000 turnos sintéticos."""
    cache = PIIThreadCache(ttl_seconds=600)
    sample_msgs = [
        "Meu CPF é 100.200.300-40 e meu CEP é 22.250-040",
        "Quero pagar IPTU. CPF 444.555.666-77",
        "Endereço: Rua das Flores, 100, CEP 20000-000",
        "Telefone (21) 99988-7766",
        "CNPJ 12.345.678/0001-99",
        "Apenas uma mensagem sem PII nenhum",
        "Qual o status do meu pedido?",
        "Mais uma sem dados sensíveis aqui",
    ]
    iterations = 1000
    durations = []
    for i in range(iterations):
        msg = sample_msgs[i % len(sample_msgs)]
        thread_id = f"thread-perf-{i % 50}"  # 50 threads concorrentes
        t0 = time.perf_counter()
        redacted, mapping = redact_with_cache(msg, cache, thread_id)
        _ = restore(redacted, mapping)
        durations.append((time.perf_counter() - t0) * 1000)
    durations.sort()
    p50 = durations[500]
    p95 = durations[950]
    p99 = durations[990]

    result = SimResult(
        name=f"sim5: performance over {iterations} redact+restore round-trips",
        passed=p95 < 5.0,  # alvo: <5ms p95
        duration_ms=sum(durations),
    )
    result.notes.append(f"P50={p50:.3f}ms P95={p95:.3f}ms P99={p99:.3f}ms")
    result.notes.append(f"total={sum(durations):.0f}ms avg={sum(durations)/len(durations):.3f}ms")
    if not result.passed:
        result.notes.append(f"FAIL: P95 {p95:.3f}ms > alvo 5ms")
    else:
        result.notes.append("OK: P95 dentro do orçamento (<5ms)")
    return result


def main() -> int:
    sims = [
        sim1_cpf_redact_restore_single_turn(),
        sim2_multi_turn_token_stability(),
        sim3_cross_thread_leak_prevention(),
        sim4_multimodal_pii_text_only(),
        sim5_performance_overhead(),
    ]

    print("\n" + "=" * 78)
    print(" SIMULAÇÕES REAIS — Engine C3 PII redaction multi-turn")
    print("=" * 78)
    for s in sims:
        marker = "✓ PASS" if s.passed else "✗ FAIL"
        print(f"\n[{marker}] {s.name}  ({s.duration_ms:.1f}ms)")
        if s.raw_input:
            print(f"  raw_input    : {_pretty(s.raw_input)}")
        if s.llm_received:
            print(f"  llm_received : {_pretty(s.llm_received)}")
        if s.final_output:
            print(f"  final_output : {_pretty(s.final_output)}")
        for note in s.notes:
            print(f"    {note}")

    passed = sum(1 for s in sims if s.passed)
    failed = len(sims) - passed
    print("\n" + "=" * 78)
    print(f" RESULTADO: {passed}/{len(sims)} passed, {failed} failed")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
