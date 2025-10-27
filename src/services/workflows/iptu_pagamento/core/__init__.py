"""
Core components do workflow IPTU.

Contém modelos, validadores e constantes.
"""

from src.services.workflows.iptu_pagamento.core.models import (
    InscricaoImobiliariaPayload,
    EscolhaAnoPayload,
    EscolhaGuiasIPTUPayload,
    EscolhaCotasParceladasPayload,
    EscolhaMaisCotasPayload,
    EscolhaOutrasGuiasPayload,
    EscolhaOutroImovelPayload,
    EscolhaFormatoDarmPayload,
    ConfirmacaoDadosPayload,
    DadosGuias,
    Guia,
    DadosCotas,
    Cota,
    DadosDarm,
    Darm,
    CotaDarm,
    DadosDividaAtiva,
    CDA,
    EF,
    Parcelamento,
)

from src.services.workflows.iptu_pagamento.core.constants import (
    MAX_TENTATIVAS_ANO,
    STATE_FAILED_ATTEMPTS_PREFIX,
    STATE_HAS_CONSULTED_GUIAS,
    STATE_NEXT_QUESTION_TYPE,
    QUESTION_TYPE_MORE_QUOTAS,
    QUESTION_TYPE_OTHER_GUIAS,
    QUESTION_TYPE_OTHER_PROPERTY,
    FAKE_API_ENV_VAR,
)

__all__ = [
    # Models - Payloads
    "InscricaoImobiliariaPayload",
    "EscolhaAnoPayload",
    "EscolhaGuiasIPTUPayload",
    "EscolhaCotasParceladasPayload",
    "EscolhaMaisCotasPayload",
    "EscolhaOutrasGuiasPayload",
    "EscolhaOutroImovelPayload",
    "EscolhaFormatoDarmPayload",
    "ConfirmacaoDadosPayload",
    # Models - Data
    "DadosGuias",
    "Guia",
    "DadosCotas",
    "Cota",
    "DadosDarm",
    "Darm",
    "CotaDarm",
    "DadosDividaAtiva",
    "CDA",
    "EF",
    "Parcelamento",
    # Constants
    "MAX_TENTATIVAS_ANO",
    "STATE_FAILED_ATTEMPTS_PREFIX",
    "STATE_HAS_CONSULTED_GUIAS",
    "STATE_NEXT_QUESTION_TYPE",
    "QUESTION_TYPE_MORE_QUOTAS",
    "QUESTION_TYPE_OTHER_GUIAS",
    "QUESTION_TYPE_OTHER_PROPERTY",
    "FAKE_API_ENV_VAR",
]
