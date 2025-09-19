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

    def _get_enhanced_contextual_schema(service, definition, completed_data):
        """Combina o schema base com o schema contextual específico do service"""
        base_schema = definition.get_contextual_schema(completed_data)

        # Enhancing each step with service-specific contextual schema
        for step_name, step_schema in base_schema.get("properties", {}).items():
            contextual_props = service.get_contextual_schema(step_name, completed_data)
            step_schema.update(contextual_props)

        return base_schema

    @tool
    def multi_step_service(
        service_name: str, payload: str, user_id: str
    ) -> Dict[str, Any]:
        """
        Sistema de serviços multi-step com schema dinâmico e estado transparente.

        Args:
            service_name: Nome do serviço (ex: "bank_account")
            payload: JSON string com campos (ex: '{"document_type":"CPF","account_type":"corrente"}')
            user_id: ID do agente, passar sempre 'agent'

        Returns:
            Estado completo: current_data, available_steps, schema dinâmico, progresso

        Exemplos:
            # Início - payload vazio
            payload = "{}"

            # Um campo
            payload = '{"document_type":"CPF"}'

            # Múltiplos campos
            payload = '{"document_number":"12345678901","account_type":"corrente"}'

            # Valores aninhados (se suportado pelo step)
            payload = '{"address":{"street":"Rua A","number":123},"contact":{"email":"test@example.com"}}'

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

        # Parse payload from JSON string
        try:
            if payload and payload.strip():
                payload_dict = json.loads(payload)
            else:
                payload_dict = {}
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "message": f"Invalid JSON payload: {str(e)}",
                "service_name": service_name,
            }

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
                response["next_steps_schema"] = _get_enhanced_contextual_schema(
                    service, definition, service.data
                )
                response["state_summary"] = definition.get_state_summary(service.data)
                response["next_action_suggestion"] = (
                    definition.get_next_action_suggestion(service.data)
                )

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
            or definition._is_conditionally_required(step, service.data)
        )

        if all_required_completed and not analysis["required_steps"]:
            status = "completed"
            response = {
                "status": status,
                "service_name": service_name,
                "current_data": dict(service.data),
                "completion_message": service.get_completion_message(),
            }
        else:
            status = "ready" if not service.data else "progress"
            response = {
                "status": status,
                "service_name": service_name,
                "current_data": dict(service.data),
                "next_steps_schema": _get_enhanced_contextual_schema(
                    service, definition, service.data
                ),
                "state_summary": definition.get_state_summary(service.data),
                "next_action_suggestion": definition.get_next_action_suggestion(
                    service.data
                ),
            }
            response.update(analysis)

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
