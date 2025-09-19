"""
Multi-step service tool for LangChain integration.
Isolated tool that can be easily migrated to MCP repository.
"""

from typing import Dict, Any
from langchain_core.tools import tool
import json

from src.services.state import save_service_state, get_or_create_service


def create_multi_step_service_tool(service_registry):
    """Factory function to create the multi_step_service tool with dependency injection"""

    def _get_schema_from_definition(definition, completed_data):
        """Gera schema diretamente do ServiceDefinition - sem dependências externas"""
        return definition.get_contextual_schema(completed_data)

    @tool
    def multi_step_service(
        service_name: str, payload: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """
        Sistema de serviços multi-step com schema dinâmico e estado transparente.

        Args:
            service_name: Nome do serviço (ex: "bank_account")
            payload: Dicionário com campos (ex: {"document_type":"CPF","account_type":"corrente"})
            user_id: ID do agente, passar sempre 'agent'

        Returns:
            Estado completo: current_data, available_steps, schema dinâmico, progresso

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
        {__replace__available_services__}
        """
        
        # Load or create service instance
        service = get_or_create_service(
            service_name=service_name,
            user_id=user_id,
            service_registry=service_registry,
        )

        if not service:
            return {
                "status": "error",
                "message": f"Serviço '{service_name}' não encontrado",
                "available_services": list(service_registry.keys()),
            }

        # Get service definition for all logic
        definition = service.get_service_definition()

        # Payload já vem como dicionário
        payload_dict = payload if payload else {}

        # Process the payload - sempre dict, pode estar vazio para início
        if payload_dict:
            # Use ServiceDefinition for bulk processing logic
            valid_data, field_errors, dependency_errors = definition.process_bulk_data(
                payload_dict, service
            )

            # Update service data with valid fields only
            service.data.update(valid_data)

            # If there are any errors, return error response
            all_errors = {**field_errors, **dependency_errors}
            if all_errors:
                analysis = definition.get_state_analysis(service.data)

                response = {
                    "status": "validation_error",
                    "service_name": service_name,
                    "current_data": dict(service.data),
                    "errors": all_errors,
                }
                response.update(analysis)
                response["next_steps_schema"] = _get_schema_from_definition(
                    definition, service.data
                )
                response["visual_schematic"] = definition.get_visual_schematic(service.data)

                # Save state even on validation error
                save_service_state(
                    service=service, service_name=service_name, user_id=user_id
                )
                return response

        # Get current state and build response
        definition = service.get_service_definition()
        analysis = definition.get_state_analysis(service.data)

        # Check if service is completed
        all_required_completed = all(
            step.name in service.data
            for step in definition.steps
            if step.required
        )

        if all_required_completed and not analysis["required_steps"]:
            status = "completed"
            response = {
                "status": status,
                "service_name": service_name,
                "current_data": dict(service.data),
                "completion_message": service.get_completion_message(),
            }
            response["visual_schematic"] = definition.get_visual_schematic(service.data)
        else:
            status = "ready" if not service.data else "progress"
            response = {
                "status": status,
                "service_name": service_name,
                "current_data": dict(service.data),
                "next_steps_schema": _get_schema_from_definition(
                    definition, service.data
                ),
            }
            response.update(analysis)
            response["visual_schematic"] = definition.get_visual_schematic(service.data)

        # Save state after processing
        save_service_state(service=service, service_name=service_name, user_id=user_id)

        return response

    def _get_service_descriptions():
        """Generate service descriptions for the tool docstring"""
        descriptions = []
        for name, cls in service_registry.items():
            desc = f"- {name}: {cls.__doc__ or 'No description'}"
            descriptions.append(desc)
        return "\n".join(descriptions)

    # Update the tool description with available services
    multi_step_service.description = multi_step_service.description.replace(
        "__replace__available_services__", _get_service_descriptions()
    )

    return multi_step_service
