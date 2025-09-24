from typing import Any, Dict, Optional
from langchain_core.tools import tool

from src.services.core.orchestrator import Orchestrator
from src.services.core.models import ServiceRequest


@tool
def multi_step_service(
    service_name: str, user_id: str, payload: Optional[Dict[str, Any]] = None
) -> dict:
    """
    Sistema de serviços multi-step com schema dinâmico e estado transparente.

    Args:
        service_name: Nome do serviço (ex: "bank_account")
        payload: Dicionário com campos (ex: {"document_type":"CPF","account_type":"corrente"})
        user_id: ID do agente, passar sempre 'agent'
    Exemplos:
        # Início - payload vazio
        payload = {}

        # Um campo
        payload = {"document_type":"CPF"}

        # Múltiplos campos
        payload = {"document_number":"12345678901","account_type":"corrente"}

    Serviços disponíveis:
        - service_name: description

        __replace__available_services__
    """
    # Cria request agnóstico
    request = ServiceRequest(
        service_name=service_name, user_id=user_id, payload=payload or {}
    )

    # Executa via orquestrador agnóstico
    orchestrator = Orchestrator()
    response = orchestrator.execute_workflow(request)

    # Retorna resposta já formatada
    return response.model_dump()


def _get_workflow_descriptions():
    """Generate workflow descriptions for the tool docstring"""
    orchestrator = Orchestrator()
    workflow_dict = orchestrator.list_workflows()

    if not workflow_dict:
        return "- Nenhum workflow disponível"

    descriptions = []
    for service_name, description in workflow_dict.items():
        descriptions.append(f"- {service_name}: {description}")

    return "\n".join(descriptions)


# Update tool description with available workflows
multi_step_service.description = multi_step_service.description.replace(
    "__replace__available_services__", _get_workflow_descriptions()
)


def save_workflow_graphs():
    """
    Função de conveniência para salvar imagens dos grafos de todos os workflows.

    Returns:
        Dicionário com os resultados da operação
    """
    orchestrator = Orchestrator()
    return orchestrator.save_all_workflow_graphs()


def save_single_workflow_graph(service_name: str):
    """
    Função de conveniência para salvar imagem do grafo de um workflow específico.

    Args:
        service_name: Nome do serviço/workflow

    Returns:
        Caminho para o arquivo de imagem salvo
    """
    orchestrator = Orchestrator()
    return orchestrator.save_workflow_graph_image(service_name)
