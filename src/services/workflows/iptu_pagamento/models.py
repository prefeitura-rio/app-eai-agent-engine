"""
Modelos Pydantic para validação do workflow IPTU Ano Vigente
"""

from typing import Literal, Optional, List, Dict
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


class EscolhaAnoPayload(BaseModel):
    """Payload para escolha do ano de exercício."""

    ano_exercicio: Literal[2024, 2025, 2026] = Field(
        ..., description="Ano de exercício para consulta do IPTU"
    )

    @classmethod
    def validate_inscricao(cls, v):
        """Valida formato da inscrição imobiliária."""
        # Remove espaços e caracteres especiais
        clean_inscricao = re.sub(r"[^0-9]", "", v)

        if len(clean_inscricao) < 8 or len(clean_inscricao) > 15:
            raise ValueError("Inscrição imobiliária deve ter entre 14 e 15 dígitos")

        return clean_inscricao


class EscolhaGuiasIPTUPayload(BaseModel):
    """Payload para escolher qual guia de IPTU o usuário quer pagar."""

    guia_escolhida: str = Field(
        ..., description="Número da guia escolhida para pagamento (ex: '00', '01')"
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

    cotas_escolhidas: List[str] = Field(
        ..., description="Lista das cotas escolhidas para pagamento"
    )


class ConfirmacaoDadosPayload(BaseModel):
    """Payload para confirmação dos dados coletados."""

    confirmacao: bool = Field(..., description="Confirmação se os dados estão corretos")


# Modelos de dados para estruturas internas


class Guia(BaseModel):
    """Dados completos de uma guia conforme retornado pela API ConsultarGuias."""

    # Campos retornados pela API
    situacao: Dict = Field(
        alias="Situacao"
    )  # {codigo: "01|02", descricao: "EM ABERTO|QUITADA"}
    inscricao: str = Field(alias="Inscricao")
    exercicio: str = Field(alias="Exercicio")
    numero_guia: str = Field(alias="NGuia")
    tipo: str = Field(alias="Tipo")  # "ORDINÁRIA" ou "EXTRAORDINÁRIA"
    valor_iptu_original_guia: str = Field(
        alias="ValorIPTUOriginalGuia"
    )  # Formato brasileiro "2.878,00"
    data_vencto_desc_cota_unica: str = Field(
        alias="DataVenctoDescCotaUnica"
    )  # Formato "07/02/2024" ou ""
    quant_dias_em_atraso: str = Field(alias="QuantDiasEmAtraso")  # "1390"
    percentual_desc_cota_unica: str = Field(alias="PercentualDescCotaUnica")  # "00007"
    valor_iptu_desconto_avista: str = Field(
        alias="ValorIPTUDescontoAvista"
    )  # Formato brasileiro "0,00"
    valor_parcelas: str = Field(alias="ValorParcelas")  # Formato brasileiro "86,00"
    credito_nota_carioca: str = Field(
        alias="CreditoNotaCarioca"
    )  # Formato brasileiro "0,00"
    credito_decad: str = Field(alias="CreditoDECAD")  # Formato brasileiro "0,00"
    credito_isencao: str = Field(alias="CreditoIsencao")  # Formato brasileiro "0,00"
    credito_cota_unica: str = Field(
        alias="CreditoCotaUnica"
    )  # Formato brasileiro "201,46"
    valor_quitado: str = Field(alias="ValorQuitado")  # Formato brasileiro "2.676,54"
    data_quitacao: str = Field(alias="DataQuitacao")  # Formato "28/01/2021" ou ""
    deposito: str = Field(alias="Deposito")  # "N" ou "S"

    # Campos calculados/processados localmente
    valor_numerico: Optional[float] = None
    valor_desconto_numerico: Optional[float] = None
    valor_parcelas_numerico: Optional[float] = None
    esta_quitada: Optional[bool] = None
    esta_em_aberto: Optional[bool] = None

    class Config:
        validate_by_name = True


class DadosGuias(BaseModel):
    """Dados das guias consultadas."""

    inscricao_imobiliaria: str
    exercicio: str
    guias: List[Guia] = []
    total_guias: int = 0


class Cota(BaseModel):
    """Dados completos de uma cota conforme retornado pela API ConsultarCotas."""

    # Campos retornados pela API
    situacao: Dict = Field(
        alias="Situacao"
    )  # {codigo: "01|02|03", descricao: "PAGA|EM ABERTO|VENCIDA"}
    numero_cota: str = Field(alias="NCota")
    valor_cota: str = Field(alias="ValorCota")  # Formato brasileiro "89,44"
    data_vencimento: str = Field(alias="DataVencimento")  # Formato "07/11/2024"
    valor_pago: str = Field(alias="ValorPago")  # Formato brasileiro "0,00"
    data_pagamento: str = Field(alias="DataPagamento")  # Pode estar vazio ""
    quantidade_dias_atraso: str = Field(alias="QuantDiasEmAtraso")

    # Campos calculados/processados localmente
    valor_numerico: Optional[float] = None
    valor_pago_numerico: Optional[float] = None
    dias_atraso_numerico: Optional[int] = None
    esta_paga: Optional[bool] = None
    esta_vencida: Optional[bool] = None
    codigo_barras: Optional[str] = None
    linha_digitavel: Optional[str] = None
    darf_data: Optional[dict] = None

    class Config:
        validate_by_name = True


class DadosCotas(BaseModel):
    """Dados das cotas disponíveis para uma guia específica."""

    inscricao_imobiliaria: str
    exercicio: str
    numero_guia: str
    tipo_guia: str
    cotas: List[Cota] = []
    total_cotas: int = 0
    valor_total: float = 0.0


class CotaDarm(BaseModel):
    """Cota dentro do DARM."""

    ncota: str = Field(alias="ncota")
    valor: str = Field(alias="valor")  # Formato brasileiro "89,44"

    class Config:
        validate_by_name = True


class Darm(BaseModel):
    """Dados completos de um DARM conforme retornado pela API ConsultarDARM."""

    # Campos retornados pela API
    cotas: List[CotaDarm] = Field(alias="Cotas")
    inscricao: str = Field(alias="Inscricao")
    exercicio: str = Field(alias="Exercicio")
    numero_guia: str = Field(alias="NGuia")
    tipo: str = Field(alias="Tipo")  # "ORDINÁRIA" ou "EXTRAORDINÁRIA"
    data_vencimento: str = Field(alias="DataVencimento")  # Formato "29/11/2024"
    valor_iptu_original: str = Field(
        alias="ValorIPTUOriginal"
    )  # Formato brasileiro "860,00"
    valor_darm: str = Field(alias="ValorDARM")  # Formato brasileiro "261,44"
    valor_desc_cota_unica: str = Field(
        alias="ValorDescCotaUnica"
    )  # Formato brasileiro "0,00"
    credito_nota_carioca: str = Field(
        alias="CreditoNotaCarioca"
    )  # Formato brasileiro "0,00"
    credito_decad: str = Field(alias="CreditoDECAD")  # Formato brasileiro "0,00"
    credito_isencao: str = Field(alias="CreditoIsencao")  # Formato brasileiro "0,00"
    credito_emissao: str = Field(alias="CreditoEmissao")  # Formato brasileiro "0,00"
    valor_a_pagar: str = Field(alias="ValorAPagar")  # Formato brasileiro "261,44"
    sequencia_numerica: str = Field(alias="SequenciaNumerica")  # Linha digitável
    descricao_darm: str = Field(
        alias="DescricaoDARM"
    )  # "DARM por cota ref.cotas 01,02,03"
    cod_receita: str = Field(alias="CodReceita")  # "310-7"
    des_receita: str = Field(alias="DesReceita")  # "RECEITA DE PAGAMENTO"
    endereco: Optional[str] = Field(alias="Endereco")  # Pode ser null
    nome: Optional[str] = Field(alias="Nome")  # Pode ser null

    # Campos calculados/processados localmente
    valor_numerico: Optional[float] = None
    codigo_barras: Optional[str] = None  # Derivado da sequencia_numerica

    class Config:
        validate_by_name = True


class DadosDarm(BaseModel):
    """Dados do DARM consultado."""

    inscricao_imobiliaria: str
    exercicio: str
    numero_guia: str
    cotas_selecionadas: List[str]
    darm: Optional[Darm] = None
    pdf_base64: Optional[str] = None


class EscolhaMaisCotasPayload(BaseModel):
    """Payload para pergunta sobre pagar mais cotas da mesma guia."""

    mais_cotas: bool = Field(
        ..., description="Se deseja pagar mais cotas da mesma guia"
    )


class EscolhaOutrasGuiasPayload(BaseModel):
    """Payload para pergunta sobre pagar outras guias do mesmo imóvel."""

    outras_guias: bool = Field(
        ..., description="Se deseja pagar outras guias do mesmo imóvel"
    )


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

    dados_guias: DadosGuias
    guia_escolhida: Optional[str] = None
    dados_cotas: Optional[DadosCotas] = None
    dados_darm: Optional[DadosDarm] = None
    tipo_cobranca_escolhido: Optional[str] = None
    formato_pagamento_escolhido: Optional[str] = None
