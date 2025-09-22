from typing import Any, Dict, Optional
from langchain_core.tools import tool

# --- Service and Action Imports ---
# This section dynamically loads all services and actions.
# In a real application, you might use a more robust discovery mechanism.
from src.services.repository.bank_account_service import bank_account_service_def
from src.services.repository.bank_account_actions import *
from src.services.core.orchestrator import ServiceOrchestrator
from src.services.schema.models import AgentResponse, ServiceDefinition

# --- Service Registry ---
# A simple dictionary to hold all loaded service definitions.
_services: Dict[str, ServiceDefinition] = {
    bank_account_service_def.service_name: bank_account_service_def
}


def get_service_definition(service_name: str) -> Optional[ServiceDefinition]:
    """Retrieves a service definition from the registry."""
    return _services.get(service_name)


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

        # Valores aninhados (se suportado pelo step)
        payload = {"address":{"street":"Rua A","number":123},"contact":{"email":"test@example.com"}}

    Serviços disponíveis:
        - service_name: description

        __replace__available_services__
    """
    service_def = get_service_definition(service_name)
    if not service_def:
        response = AgentResponse(
            service_name=service_name,
            status="FAILED",
            error_message=f"Service '{service_name}' not found. Available services: {list(_services.keys())}",
            current_data={},
        )
        return response.model_dump()

    orchestrator = ServiceOrchestrator(service_def)
    response = orchestrator.execute_turn(user_id, payload)

    return response.model_dump()


def _get_service_descriptions():
    """Generate service descriptions for the tool docstring"""
    descriptions = []
    for name, cls in _services.items():
        desc = f"- {name}: {cls.description or 'No description'}"
        descriptions.append(desc)
    return "\n".join(descriptions)


multi_step_service.description = multi_step_service.description.replace(
    "__replace__available_services__", _get_service_descriptions()
)
