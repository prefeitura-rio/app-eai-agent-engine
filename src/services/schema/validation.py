import json
from typing import Dict, Any, List, Tuple, Optional
from src.services.schema.step_info import StepInfo
from src.services.schema.dependency_engine import DependencyEngine


class ValidationEngine:
    """Engine for validating step data and processing bulk payloads"""

    def __init__(self, steps: List[StepInfo]):
        self.steps = steps
        self.dependency_engine = DependencyEngine(steps)
        self._steps_by_name = {step.name: step for step in steps}
        self.step_names = [step.name for step in steps]

    def process_bulk_data(
        self, payload: Dict[str, Any], service_executor
    ) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
        """Process bulk payload with dependency validation - returns (valid_data, field_errors, dependency_errors)"""
        valid_data = {}
        field_errors = {}
        dependency_errors = {}

        # First pass: validate individual steps without dependencies
        # Process both main steps and substeps
        all_possible_steps = set(self.step_names)
        
        # Add substep names to the processing list (com prefixo)
        for step_info in self.steps:
            if step_info.substeps:
                for substep in step_info.substeps:
                    substep_key = f"{step_info.name}_{substep.name}"
                    all_possible_steps.add(substep_key)
        
        # Detectar substeps sem prefixo automaticamente
        payload_to_process = {}
        for field_name, field_value in payload.items():
            if field_name in all_possible_steps:
                # Campo já mapeado (main step ou substep com prefixo)
                payload_to_process[field_name] = field_value
            else:
                # Tentar detectar se é um substep sem prefixo
                detected_substep = self._detect_substep_parent(field_name)
                if detected_substep:
                    # Converter para formato com prefixo
                    prefixed_key = f"{detected_substep}_{field_name}"
                    payload_to_process[prefixed_key] = field_value
                    all_possible_steps.add(prefixed_key)
                else:
                    # Campo não reconhecido - manter original para gerar erro apropriado
                    payload_to_process[field_name] = field_value
        
        for step_name in all_possible_steps:
            if step_name in payload_to_process:
                # Para objetos complexos, usar json.dumps; para strings simples, usar como está
                value = payload_to_process[step_name]
                if isinstance(value, (dict, list)):
                    payload_str = json.dumps(value, ensure_ascii=False)
                else:
                    payload_str = str(value)
                
                is_valid, error_msg = service_executor.execute_step(step_name, payload_str)
                if is_valid:
                    # Substeps não devem ser salvos em valid_data, apenas processados
                    # (eles são gerenciados internamente pelo service)
                    if "_" in step_name and step_name not in self.step_names:
                        # É um substep - não salvar em valid_data
                        pass
                    else:
                        # É um step principal - salvar normalmente
                        if (
                            hasattr(service_executor, "data")
                            and step_name in service_executor.data
                        ):
                            valid_data[step_name] = service_executor.data[step_name]
                        else:
                            valid_data[step_name] = str(payload_to_process[step_name]).strip()
                else:
                    field_errors[step_name] = error_msg

        # Second pass: validate dependencies with combined data (existing + new)
        # Only validate dependencies for main steps, not substeps
        main_steps_to_validate = [step for step in valid_data.keys() if step in self.step_names]
        
        # Get existing service data
        existing_data = getattr(service_executor, "data", {})
        temp_data = dict(existing_data)  # Start with existing data
        processing_order = self.dependency_engine.get_processing_order(main_steps_to_validate)

        for step in processing_order:
            if step in valid_data:
                # Add new step to combined data
                temp_data[step] = valid_data[step]
                # Validate dependencies with combined state (existing + new)
                is_dep_valid, dep_error = self.dependency_engine.validate_dependencies_with_temp_data(
                    step, temp_data
                )
                if not is_dep_valid:
                    dependency_errors[step] = dep_error
                    # Remove from valid data if dependencies fail
                    valid_data.pop(step, None)
                    temp_data.pop(step, None)  # Remove from temp as well

        return valid_data, field_errors, dependency_errors

    def _detect_substep_parent(self, field_name: str) -> Optional[str]:
        """Detecta qual step principal contém o substep especificado"""
        for step_info in self.steps:
            if step_info.substeps:
                for substep in step_info.substeps:
                    if substep.name == field_name:
                        return step_info.name
        return None

    def validate_step_exists(self, step_name: str) -> bool:
        """Check if step exists in the service definition"""
        return step_name in self._steps_by_name

    def get_step_validation_context(self, step_name: str, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get validation context for a specific step"""
        step_info = self._steps_by_name.get(step_name)
        if not step_info:
            return {}

        context = {
            "step_info": step_info,
            "completed_data": completed_data,
            "validation_depends_on": step_info.validation_depends_on,
        }

        # Add contextual data from validation dependencies
        validation_data = {}
        for dep_step in step_info.validation_depends_on:
            if dep_step in completed_data:
                validation_data[dep_step] = completed_data[dep_step]
        
        context["validation_data"] = validation_data
        return context

    def validate_required_fields_complete(self, completed_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate that all required fields are completed"""
        missing_required = []
        
        for step in self.steps:
            if step.required or self.dependency_engine._is_conditionally_required(step, completed_data):
                if step.name not in completed_data:
                    missing_required.append(step.name)

        return len(missing_required) == 0, missing_required

    def get_validation_errors_summary(
        self, field_errors: Dict[str, str], dependency_errors: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create a summary of validation errors"""
        return {
            "field_errors": field_errors,
            "dependency_errors": dependency_errors,
            "total_errors": len(field_errors) + len(dependency_errors),
            "has_field_errors": len(field_errors) > 0,
            "has_dependency_errors": len(dependency_errors) > 0,
        }