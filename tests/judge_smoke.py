"""Manual real-Gemini smoke for the Tier-0 judge-infra (ADR-038).

Run on demand (NOT collected by pytest — no ``test_`` functions, so it never
fires real Gemini calls during the unit suite or CI):

    uv run python tests/judge_smoke.py

Confirms ``LangChainJudgeModel`` + ``with_structured_output`` returns a
schema-valid ``JudgeVerdict`` from Gemini 2.5 Flash — i.e. that structured
output works on the real judge model. Imports only ``engine.judges`` (no global
Engine config), reads the key via ``os.getenv`` only, and prints verdict /
confidence / rationale — never the API key. Skips cleanly if no key is set.

DEV-ONLY capability confirmation, NOT accuracy validation (accuracy needs ≥50
human annotations — ADR-038 production gate).
"""

from __future__ import annotations

import os
import sys

from engine.judges.llm_judge import (
    JUDGE_DIMENSIONS,
    JudgeCase,
    JudgeVerdict,
    LangChainJudgeModel,
    judge_all,
)


def main() -> int:
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        print("SKIP: no GEMINI_API_KEY/GOOGLE_API_KEY in env — cannot run the real call.")
        return 0

    case = JudgeCase(
        prompt="Qual o prazo de pagamento do IPTU 2026?",
        bot_output="O prazo do IPTU 2026 é 31 de fevereiro de 2026.",
        source_context="O prazo de pagamento do IPTU 2026 é 10 de março de 2026.",
        prompt_id="smoke-iptu",
        category="smoke",
    )

    try:
        model = LangChainJudgeModel()
        panel = judge_all(case, model)
    except Exception as exc:  # never echo the key; print only type + message
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    ok = set(panel) == set(JUDGE_DIMENSIONS)
    for dimension, verdict in panel.items():
        valid = isinstance(verdict, JudgeVerdict) and 0.0 <= verdict.confidence <= 1.0 and bool(verdict.rationale)
        ok = ok and valid
        print(f"  {dimension:13} verdict={verdict.verdict!s:5} conf={verdict.confidence:.2f}  {verdict.rationale[:80]}")

    print("PASS: panel completo e schema-valid." if ok else "FAIL: panel incompleto ou verdict inválido.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
