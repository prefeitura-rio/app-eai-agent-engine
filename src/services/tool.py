"""
Multi-step service tool for LangChain integration.
Isolated tool that can be easily migrated to MCP repository.
"""

import json
from typing import Dict, Any
from langchain_core.tools import tool

from src.services.state import save_service_state, get_or_create_service


def create_multi_step_service_tool(service_registry):
    """Factory function to create the multi_step_service tool with dependency injection"""
    
    @tool
    def multi_step_service(
        service_name: str, step: str, payload: str, user_id: str
    ) -> Dict[str, Any]:
        """
        Universal multi-step service tool with dependency management.
        
        IMPORTANTE - Quando solicitar dados ao usuario siga essas instruções:
        - Suas mensagens de solicitação devem ser claras, objetivas e seguindo sua Persona original.
        - Apresente os campos necessários em formato de lista.
        - Exemplo:
            Para iniciar seu cadastro, por favor forneça as seguintes informações:
            - CPF
            - Nome completo
            - E-mail

        
        Serviços disponíveis:
        {available_services}

        Args:
            service_name: Nome do serviço a ser executado
            step: Passo atual ('start' para a primeira interação, 'bulk' para múltiplos passos em um único request, ou o nome específico do passo a ser executado.)
            payload: Resposta do usuário (string para passos específicos, JSON string para bulk)
            user_id: Identificador do usuário

        Returns:
            Dict com status, next_step_info (detalhes completos do próximo passo), schema, available_steps e outros dados relevantes.
        """

        # Check if this is not a start and session doesn't exist
        if step != "start":
            from src.services.state import STATE_DIR
            state_file = STATE_DIR / f"{user_id}__{service_name}.json"
            if not state_file.exists():
                return {
                    "status": "error",
                    "message": f"Nenhuma sessão ativa encontrada para {service_name}. Use step='start' para iniciar.",
                    "available_services": list(service_registry.keys()),
                }

        # Load or create service instance
        service = get_or_create_service(service_name=service_name, user_id=user_id, service_registry=service_registry)

        if not service:
            return {
                "status": "error",
                "message": f"Serviço '{service_name}' não encontrado",
                "available_services": list(service_registry.keys()),
            }

        # Handle start step - sempre solicita todos os dados de uma vez
        if step == "start":
            result = {
                "status": "bulk_request",
                "schema": service.get_schema(),
                "steps_info": [step_info.model_dump() for step_info in service.get_steps_info()],
                "available_steps": service.get_available_steps(),
                "completed": False,
            }

            # Save initial state
            save_service_state(service=service, service_name=service_name, user_id=user_id)
            return result

        # Auto-detect bulk vs step-by-step based on payload
        is_bulk = False
        bulk_payload = None

        try:
            bulk_payload = json.loads(payload)
            # If JSON parsing succeeds and it's a dict, it's bulk mode
            if isinstance(bulk_payload, dict):
                is_bulk = True
        except (json.JSONDecodeError, TypeError):
            # Not JSON or not a dict, treat as step-by-step
            is_bulk = False

        # Process accordingly
        if is_bulk and bulk_payload is not None:
            result = service.process_bulk(bulk_payload)
        else:
            result = service.process_step(step, payload)

        # Save state after processing
        save_service_state(service=service, service_name=service_name, user_id=user_id)

        return result

    def _get_service_descriptions():
        """Generate service descriptions for the tool docstring"""
        descriptions = []
        for name, cls in service_registry.items():
            desc = f"- {name}: {cls.__doc__ or 'No description'}"
            descriptions.append(desc)
        return "\n".join(descriptions)

    # Update the tool description with available services
    multi_step_service.description = multi_step_service.description.format(
        available_services=_get_service_descriptions()
    )
    
    return multi_step_service