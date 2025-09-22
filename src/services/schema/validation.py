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
        # Build substep map with infinite nesting support
        self._substep_map = self._build_substep_map(steps)

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
        """Simple pass-through normalization - let services handle complex logic"""
        normalized = {}
        
        for field_name, field_value in payload.items():
            if field_name in self._steps_by_name:
                # Direct step
                normalized[field_name] = field_value
            else:
                # For now, pass through individual fields as-is
                # The service's execute_step method will handle the detection
                normalized[field_name] = field_value
        
        return normalized

    def _set_nested_value(self, parent_dict: dict, full_path: str, value: Any, parent_step: str):
        """Set value in nested dictionary using dot notation path"""
        # Remove parent step from path if present
        if full_path.startswith(f"{parent_step}."):
            path = full_path[len(parent_step)+1:]
        else:
            path = full_path
        
        parts = path.split(".")
        current = parent_dict
        
        # Navigate to the correct nesting level
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Set the final value
        current[parts[-1]] = value

    def _build_substep_map(self, steps: List[StepInfo]) -> Dict[str, str]:
        """Build substep map with infinite nesting support using dot notation"""
        substep_map = {}
        
        for step in steps:
            if step.substeps:
                self._add_substeps_to_map(step.substeps, step.name, substep_map)
        
        return substep_map

    def _add_substeps_to_map(self, substeps: List[StepInfo], parent_path: str, substep_map: Dict[str, str]):
        """Recursively add substeps to map with dot notation paths"""
        for substep in substeps:
            # Add dot notation mapping (full path)
            dot_path = f"{parent_path}.{substep.name}"
            substep_map[dot_path] = parent_path
            
            # Only add direct name mapping if it doesn't conflict with existing ones
            # Priority: more specific paths win over generic ones
            if substep.name not in substep_map:
                substep_map[substep.name] = parent_path
            
            # Recursively process sub-substeps
            if substep.substeps:
                self._add_substeps_to_map(substep.substeps, dot_path, substep_map)

    def validate_required_fields_complete(self, completed_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check if all required fields are completed"""
        missing = [
            step.name for step in self.steps 
            if step.required and step.name not in completed_data
        ]
        return len(missing) == 0, missing