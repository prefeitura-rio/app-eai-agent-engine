"""
Modelos Pydantic para validação do workflow IPTU Ano Vigente
"""

from typing import Literal, Optional, List
from pydantic import BaseModel, Field
import re


class InscricaoImobiliariaPayload(BaseModel):
    """Payload para coleta da inscrição imobiliária."""

    inscricao_imobiliaria: str = Field(
        ...,
        min_length=8,
        max_length=15,
        description="Inscrição imobiliária (8-16 dígitos)",
    )

    @classmethod
    def validate_inscricao(cls, v):
        """Valida formato da inscrição imobiliária."""
        # Remove espaços e caracteres especiais
        clean_inscricao = re.sub(r"[^0-9]", "", v)

        if len(clean_inscricao) < 8 or len(clean_inscricao) > 15:
            raise ValueError("Inscrição imobiliária deve ter entre 14 e 15 dígitos")

        return clean_inscricao


class EscolhaGuiaPayload(BaseModel):
    """Payload para escolher qual guia o usuário quer pagar."""

    guia_escolhida: str = Field(
        ..., description="Guia escolhida pelo usuário para pagamento"
    )


class EscolhaCobrancaPayload(BaseModel):
    """Payload para escolha do tipo de cobrança."""

    tipo_cobranca: Literal["cota_unica", "cota_parcelada"] = Field(
        ..., description="Tipo de cobrança: cota única ou parcelada"
    )


class EscolhaFormatoPagamentoPayload(BaseModel):
    """Payload para escolha do formato de pagamento."""

    formato_pagamento: Literal["darf", "codigo_barras"] = Field(
        ..., description="Formato de pagamento: DARF separado ou código de barras"
    )


class EscolhaCotasParceladasPayload(BaseModel):
    """Payload para escolher quais cotas parceladas pagar."""

    inscricao_imobiliaria: str = Field(
        None,
        min_length=14,
        max_length=16,
        description="Inscrição imobiliária (14-16 dígitos) - opcional se já informada",
    )
    cotas_escolhidas: List[str] = Field(
        ..., description="Lista das cotas escolhidas para pagamento"
    )


class ConfirmacaoDadosPayload(BaseModel):
    """Payload para confirmação dos dados coletados."""

    inscricao_imobiliaria: str = Field(
        ...,
        min_length=14,
        max_length=16,
        description="Inscrição imobiliária (14-16 dígitos)",
    )
    confirmacao: bool = Field(..., description="Confirmação se os dados estão corretos")


# Modelos de dados para estruturas internas


class DadosIPTU(BaseModel):
    """Dados do IPTU consultado."""

    inscricao_imobiliaria: str
    endereco: str
    proprietario: str
    valor_iptu: float
    ano_vigente: int = 2024


class GuiaIPTU(BaseModel):
    """Dados de uma guia de IPTU."""

    numero_guia: str
    valor: float
    vencimento: str
    codigo_barras: Optional[str] = None
    linha_digitavel: Optional[str] = None
    darf_data: Optional[dict] = None


class EscolhaGuiaMesmoImovelPayload(BaseModel):
    """Payload para pergunta sobre gerar mais guias para o mesmo imóvel."""

    mesma_guia: bool = Field(
        ..., description="Se deseja emitir mais guias para o mesmo imóvel"
    )


class EscolhaOutroImovelPayload(BaseModel):
    """Payload para pergunta sobre gerar guias para outro imóvel."""

    outro_imovel: bool = Field(
        ..., description="Se deseja emitir guias para outro imóvel"
    )


class DadosConsulta(BaseModel):
    """Dados completos da consulta de IPTU."""

    dados_iptu: DadosIPTU
    guias_disponiveis: List[GuiaIPTU] = []
    tipo_cobranca_escolhido: Optional[str] = None
    formato_pagamento_escolhido: Optional[str] = None
