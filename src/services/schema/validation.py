import json
from typing import Dict, Any, List, Tuple
from src.services.schema.step_info import StepInfo
from src.services.schema.dependency_engine import DependencyEngine


class ValidationEngine:
    """Simple validation engine with auto-detection"""

    def __init__(self, steps: List[StepInfo]):
        self.steps = steps
        self.dependency_engine = DependencyEngine(steps)
        self._steps_by_name = {step.name: step for step in steps}
        self._substep_map = {
            substep.name: step.name
            for step in steps if step.substeps
            for substep in step.substeps
        }

    def process_bulk_data(
        self, payload: Dict[str, Any], service_executor
    ) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
        """Single-pass validation with auto-detection"""
        valid_data = {}
        field_errors = {}
        dependency_errors = {}
        
        # Normalize payload (auto-detect substeps)
        normalized = self._normalize_payload(payload)
        
        # Validate each field
        existing_data = getattr(service_executor, "data", {})
        temp_data = dict(existing_data)
        
        for field_name, field_value in normalized.items():
            if field_name not in self._steps_by_name:
                continue
                
            # Validate field
            payload_str = json.dumps(field_value, ensure_ascii=False) if isinstance(field_value, (dict, list)) else str(field_value)
            is_valid, error_msg = service_executor.execute_step(field_name, payload_str)
            
            if is_valid:
                # Check dependencies
                temp_data[field_name] = getattr(service_executor, "data", {}).get(field_name, field_value)
                is_dep_valid, dep_error = self.dependency_engine.validate_dependencies_with_temp_data(field_name, temp_data)
                
                if is_dep_valid:
                    valid_data[field_name] = temp_data[field_name]
                else:
                    dependency_errors[field_name] = dep_error
                    temp_data.pop(field_name, None)
            else:
                field_errors[field_name] = error_msg

        return valid_data, field_errors, dependency_errors

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-detect substeps and normalize"""
        normalized = {}
        
        for field_name, field_value in payload.items():
            if field_name in self._steps_by_name:
                normalized[field_name] = field_value
            elif field_name in self._substep_map:
                # Substep - group under parent
                parent_step = self._substep_map[field_name]
                if parent_step not in normalized:
                    normalized[parent_step] = {}
                if not isinstance(normalized[parent_step], dict):
                    normalized[parent_step] = {}
                normalized[parent_step][field_name] = field_value
            else:
                normalized[field_name] = field_value
        
        return normalized

    def validate_required_fields_complete(self, completed_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check if all required fields are completed"""
        missing = [
            step.name for step in self.steps 
            if step.required and step.name not in completed_data
        ]
        return len(missing) == 0, missing