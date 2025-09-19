import json
from typing import Dict, Any, List, Tuple
from src.services.schema.step_info import StepInfo
from src.services.schema.dependency_engine import DependencyEngine


class ValidationEngine:
    """Simplified validation engine with smart auto-detection"""

    def __init__(self, steps: List[StepInfo]):
        self.steps = steps
        self.dependency_engine = DependencyEngine(steps)
        
        # Pre-compute lookup tables for performance
        self._steps_by_name = {step.name: step for step in steps}
        self._substep_map = self._build_substep_map()

    def _build_substep_map(self) -> Dict[str, str]:
        """Build reverse lookup: substep_name -> parent_step_name"""
        substep_map = {}
        for step in self.steps:
            if step.substeps:
                for substep in step.substeps:
                    substep_map[substep.name] = step.name
        return substep_map

    def process_bulk_data(
        self, payload: Dict[str, Any], service_executor
    ) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
        """Simplified single-pass validation with smart field resolution"""
        valid_data = {}
        field_errors = {}
        dependency_errors = {}
        
        # Smart field resolution - auto-detect substeps and normalize
        normalized_payload = self._normalize_payload(payload)
        
        # Single pass: validate all fields with dependency checking
        existing_data = getattr(service_executor, "data", {})
        temp_data = dict(existing_data)
        
        for field_name, field_value in normalized_payload.items():
            # Skip if not a main step
            if field_name not in self._steps_by_name:
                continue
                
            # Validate the field
            is_valid, error_msg = self._validate_field(field_name, field_value, service_executor)
            
            if is_valid:
                # Check dependencies immediately
                temp_data[field_name] = getattr(service_executor, "data", {}).get(field_name, field_value)
                
                is_dep_valid, dep_error = self.dependency_engine.validate_dependencies_with_temp_data(
                    field_name, temp_data
                )
                
                if is_dep_valid:
                    valid_data[field_name] = temp_data[field_name]
                else:
                    dependency_errors[field_name] = dep_error
                    temp_data.pop(field_name, None)
            else:
                field_errors[field_name] = error_msg

        return valid_data, field_errors, dependency_errors

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Smart payload normalization with auto-detection"""
        normalized = {}
        
        for field_name, field_value in payload.items():
            # Check if it's a main step
            if field_name in self._steps_by_name:
                normalized[field_name] = field_value
                continue
            
            # Check if it's a substep (auto-detect parent)
            parent_step = self._substep_map.get(field_name)
            if parent_step:
                # Initialize parent step data if not exists
                if parent_step not in normalized:
                    normalized[parent_step] = {}
                
                # Ensure parent is a dict for substep accumulation
                if not isinstance(normalized[parent_step], dict):
                    normalized[parent_step] = {}
                
                # Add substep to parent
                normalized[parent_step][field_name] = field_value
            else:
                # Unknown field - keep as is for error handling
                normalized[field_name] = field_value
        
        return normalized

    def _validate_field(self, field_name: str, field_value: Any, service_executor) -> Tuple[bool, str]:
        """Simplified field validation"""
        # Convert complex objects to JSON strings for service validation
        if isinstance(field_value, (dict, list)):
            payload_str = json.dumps(field_value, ensure_ascii=False)
        else:
            payload_str = str(field_value)
        
        return service_executor.execute_step(field_name, payload_str)

    def validate_required_fields_complete(self, completed_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check if all required fields are completed"""
        missing = [
            step.name for step in self.steps 
            if (step.required or self.dependency_engine._is_conditionally_required(step, completed_data))
            and step.name not in completed_data
        ]
        return len(missing) == 0, missing