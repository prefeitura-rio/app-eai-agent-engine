from typing import Any, Dict, Optional
from langchain_core.tools import tool

from src.services.core.base_service import BaseService
from src.services.core.orchestrator import ServiceOrchestrator
from src.services.repository.bank_account_service_v2 import BankAccountServiceV2
from src.services.repository.order_service import OrderService
from src.services.schema.models import AgentResponse, ServiceDefinition

# --- Service Registry ---
# Register all service classes.
_service_classes = [BankAccountServiceV2, OrderService]
_services: Dict[str, type[BaseService]] = {
    service.service_name: service for service in _service_classes
}


def get_service_definition(service_name: str) -> Optional[ServiceDefinition]:
    """Retrieves a service definition from the registry."""
    service_class = _services.get(service_name)
    if service_class:
        service_instance = service_class()
        return service_instance.get_definition()
    return None


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
    service_def = get_service_definition(service_name)
    if not service_def:
        response = AgentResponse(
            service_name=service_name,
            status="FAILED",
            error_message=f"Service '{service_name}' not found. Available services: {list(_services.keys())}",
            current_data={},
            next_step_info=None,
            execution_summary=None,
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
