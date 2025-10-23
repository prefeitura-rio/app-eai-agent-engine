"""
Funções utilitárias para o workflow IPTU.

Este módulo contém funções auxiliares para processamento de dados,
formatação e lógica reutilizável do workflow.
"""

from typing import Dict, List, Any, Optional
from src.services.core.models import ServiceState
from src.services.workflows.iptu_pagamento.models import DadosCotas


def preparar_dados_guias_para_template(
    dados_guias: Dict[str, Any],
    api_service
) -> List[Dict[str, Any]]:
    """
    Prepara dados das guias no formato esperado pelo template.

    Args:
        dados_guias: Dicionário com dados brutos das guias
        api_service: Instância do serviço de API para parsing de moeda

    Returns:
        Lista de dicionários com dados formatados das guias
    """
    guias_formatadas = []
    guias_disponiveis = dados_guias.get("guias", [])

    for guia in guias_disponiveis:
        valor_original = api_service._parse_brazilian_currency(
            guia.get("valor_iptu_original_guia", "0,00")
        )
        situacao = guia.get("situacao", {}).get("descricao", "EM ABERTO")

        guias_formatadas.append({
            "numero_guia": guia.get("numero_guia", "N/A"),
            "tipo": guia.get("tipo", "IPTU").upper(),
            "valor_original": valor_original,
            "situacao": situacao,
        })

    return guias_formatadas


def preparar_dados_cotas_para_template(dados_cotas: DadosCotas) -> List[Dict[str, Any]]:
    """
    Prepara dados das cotas no formato esperado pelo template.

    Args:
        dados_cotas: Objeto DadosCotas com as cotas disponíveis

    Returns:
        Lista de dicionários com dados formatados das cotas
    """
    cotas_formatadas = []
    cotas_em_aberto = [c for c in dados_cotas.cotas if not c.esta_paga]

    for cota in cotas_em_aberto:
        cotas_formatadas.append({
            "numero_cota": cota.numero_cota,
            "data_vencimento": cota.data_vencimento,
            "valor_cota": cota.valor_cota,
            "esta_vencida": cota.esta_vencida,
            "valor_numerico": cota.valor_numerico or 0.0,
        })

    return cotas_formatadas


def preparar_dados_boletos_para_template(
    guias_geradas: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Prepara dados dos boletos gerados no formato esperado pelo template.

    Args:
        guias_geradas: Lista de guias geradas pelo sistema

    Returns:
        Lista formatada para exibição
    """
    # Já está no formato correto, apenas garante que campos necessários existem
    for guia in guias_geradas:
        if "pdf" not in guia:
            guia["pdf"] = "Não disponível"

    return guias_geradas


def tem_mais_cotas_disponiveis(state: ServiceState) -> bool:
    """
    Verifica se há mais cotas disponíveis da guia atual para pagar.

    Args:
        state: Estado do serviço

    Returns:
        True se há mais cotas disponíveis, False caso contrário
    """
    dados_cotas_dict = state.data.get("dados_cotas")
    cotas_escolhidas = state.data.get("cotas_escolhidas", [])

    if not dados_cotas_dict or not cotas_escolhidas:
        return False

    cotas_disponiveis = dados_cotas_dict.get("cotas", [])
    total_cotas = len(cotas_disponiveis)
    cotas_selecionadas = len(cotas_escolhidas)

    return cotas_selecionadas < total_cotas


def tem_outras_guias_disponiveis(state: ServiceState) -> bool:
    """
    Verifica se há outras guias disponíveis no imóvel.

    Args:
        state: Estado do serviço

    Returns:
        True se há outras guias disponíveis, False caso contrário
    """
    dados_guias_dict = state.data.get("dados_guias")

    if not dados_guias_dict:
        return False

    guias_disponiveis = dados_guias_dict.get("guias", [])
    total_guias = len(guias_disponiveis)

    # Se há mais de uma guia disponível, significa que há outras além da atual
    return total_guias > 1


def reset_campos_seletivo(
    state: ServiceState,
    fields: Dict[str, List[str]],
    manter_inscricao: bool = False,
) -> None:
    """
    Faz reset seletivo dos campos especificados.

    Args:
        state: Estado do serviço
        fields: Dict com 'data' e 'internal' contendo listas de campos para resetar
        manter_inscricao: Se True, mantém a inscrição imobiliária atual
    """
    inscricao_atual = (
        state.data.get("inscricao_imobiliaria") if manter_inscricao else None
    )

    # Reset seletivo do data
    if "data" in fields:
        for field in fields["data"]:
            state.data.pop(field, None)

    # Reset seletivo do internal
    if "internal" in fields:
        for field in fields["internal"]:
            state.internal.pop(field, None)

    # Restaura inscrição se necessário e não foi removida no reset
    if inscricao_atual and "inscricao_imobiliaria" not in fields.get("data", []):
        state.data["inscricao_imobiliaria"] = inscricao_atual


def reset_completo(
    state: ServiceState,
    manter_inscricao: bool = False,
) -> None:
    """
    Faz reset completo dos dados e flags internas.

    Args:
        state: Estado do serviço
        manter_inscricao: Se True, mantém a inscrição imobiliária atual
    """
    inscricao_atual = (
        state.data.get("inscricao_imobiliaria") if manter_inscricao else None
    )

    # Reset completo do data
    state.data.clear()

    # Reset completo do internal
    state.internal.clear()

    # Restaura inscrição se necessário
    if inscricao_atual:
        state.data["inscricao_imobiliaria"] = inscricao_atual


def calcular_numero_boletos(darm_separado: bool, num_cotas: int) -> int:
    """
    Calcula o número de boletos que serão gerados.

    Args:
        darm_separado: Se True, gera um boleto por cota
        num_cotas: Número de cotas selecionadas

    Returns:
        Número de boletos a serem gerados
    """
    if darm_separado:
        return num_cotas
    return 1
