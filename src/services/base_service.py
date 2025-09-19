from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional, Type

from src.services.schema import StepInfo, ServiceDefinition


class BaseService(ABC):
    """Base class for all multi-step services"""
    
    # Service identifier - must be defined in each service class
    service_name: Optional[str] = None

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.data = {}
        self.created_at = datetime.now()
        
        # Ensure service_name is defined
        if self.__class__.service_name is None:
            raise ValueError(f"Service {self.__class__.__name__} must define service_name")

    @abstractmethod
    def get_service_definition(self) -> ServiceDefinition:
        """Return the complete service definition - single source of truth"""
        pass

    def get_steps(self) -> list:
        """Return list of step names in order"""
        definition = self.get_service_definition()
        return definition.step_names

    @abstractmethod
    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """Validate input for a step. Returns (is_valid, error_message)"""
        pass

    @abstractmethod
    def get_completion_message(self) -> str:
        """Get message when service is completed"""
        pass
    
    def _validate_dependencies(self, step_name: str) -> Tuple[bool, str]:
        """Validate if step dependencies are satisfied"""
        step_info = self._get_step_info(step_name)
        if not step_info:
            return False, f"Step '{step_name}' not found"
        
        # Check direct dependencies
        for dep in step_info.depends_on:
            if dep not in self.data:
                return False, f"Step '{step_name}' requires '{dep}' to be completed first"
        
        # Check conflicts
        for conflict in step_info.conflicts_with:
            if conflict in self.data:
                return False, f"Step '{step_name}' conflicts with already completed step '{conflict}'"
        
        # Check conditional dependencies
        if step_info.conditional:
            condition_met = self._evaluate_condition(step_info.conditional.if_condition)
            required_steps = (step_info.conditional.then_required if condition_met 
                            else step_info.conditional.else_required)
            
            for req_step in required_steps:
                if req_step not in self.data:
                    return False, f"Step '{step_name}' requires '{req_step}' based on current conditions"
        
        return True, ""
    
    def _evaluate_condition(self, condition: Dict[str, Any]) -> bool:
        """Evaluate conditional dependency"""
        for step_name, expected_value in condition.items():
            if step_name not in self.data:
                return False
            if self.data[step_name] != expected_value:
                return False
        return True
    
    def _get_step_info(self, step_name: str) -> Optional[StepInfo]:
        """Get StepInfo for a specific step"""
        definition = self.get_service_definition()
        return definition.get_step_info(step_name)
    
    def get_available_steps(self) -> List[str]:
        """Get list of steps that can be executed based on current state"""
        definition = self.get_service_definition()
        return definition.get_available_steps(self.data)
    
    def get_next_required_step(self) -> Optional[str]:
        """Get the next required step based on dependencies"""
        available = self.get_available_steps()
        definition = self.get_service_definition()
        
        # Filter for required steps only
        for step in definition.steps:
            if step.name in available and step.required:
                return step.name
        
        # If no required steps, return first available
        return available[0] if available else None
    
    def _get_processing_order(self, steps: List[str]) -> List[str]:
        """Get processing order based on dependencies (topological sort)"""
        # Simple implementation - can be enhanced with proper topological sort
        ordered = []
        remaining = list(steps)
        
        while remaining:
            # Find steps with no unmet dependencies in remaining list
            ready = []
            for step in remaining:
                step_info = self._get_step_info(step)
                if step_info:
                    deps_in_remaining = [dep for dep in step_info.depends_on if dep in remaining]
                    if not deps_in_remaining:
                        ready.append(step)
            
            if not ready:
                # Circular dependency or missing dependency - add remaining in original order
                ordered.extend(remaining)
                break
            
            # Add ready steps and remove from remaining
            ordered.extend(ready)
            for step in ready:
                remaining.remove(step)
        
        return ordered
    
    def _validate_dependencies_with_temp_data(self, step_name: str, temp_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate dependencies using temporary data state"""
        step_info = self._get_step_info(step_name)
        if not step_info:
            return False, f"Step '{step_name}' not found"
        
        # Check direct dependencies
        for dep in step_info.depends_on:
            if dep not in temp_data:
                return False, f"Step '{step_name}' requires '{dep}' to be completed first"
        
        # Check conflicts
        for conflict in step_info.conflicts_with:
            if conflict in temp_data:
                return False, f"Step '{step_name}' conflicts with step '{conflict}'"
        
        return True, ""

    def process_bulk(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process bulk payload with dependency validation"""
        valid_data = {}
        field_errors = {}
        dependency_errors = {}

        # First pass: validate individual steps without dependencies
        for step in self.get_steps():
            if step in payload:
                is_valid, error_msg = self.execute_step(step, str(payload[step]))
                if is_valid:
                    valid_data[step] = str(payload[step]).strip()
                else:
                    field_errors[step] = error_msg

        # Second pass: validate dependencies with temporary data
        temp_data = self.data.copy()
        processing_order = self._get_processing_order(list(valid_data.keys()))
        
        for step in processing_order:
            if step in valid_data:
                # Check dependencies with current state
                temp_data[step] = valid_data[step]
                is_dep_valid, dep_error = self._validate_dependencies_with_temp_data(step, temp_data)
                if not is_dep_valid:
                    dependency_errors[step] = dep_error
                    # Remove from valid data if dependencies fail
                    valid_data.pop(step, None)
                    temp_data.pop(step, None)

        # If no valid data, return error with schema
        if not valid_data:
            return {
                "status": "bulk_validation_error",
                "message": "Nenhum campo válido encontrado",
                "field_errors": field_errors,
                "dependency_errors": dependency_errors,
                "schema": self.get_schema(),
            }

        # Store valid data
        self.data.update(valid_data)

        # If all steps completed, return success
        steps = self.get_steps()
        if all(step in self.data for step in steps):
            return {
                "status": "bulk_success",
                "completed": True,
                "data": self.data,
                "completion_message": self.get_completion_message(),
            }

        # Partial success - determine next step needed
        next_step = self.get_next_required_step()

        return {
            "status": "partial_success",
            "next_step_info": self.get_next_step_info(next_step) if next_step else {},
            "field_errors": field_errors,
            "dependency_errors": dependency_errors,
            "valid_fields": list(valid_data.keys()),
            "available_steps": self.get_available_steps(),
            "completed": False,
            "schema": self.get_schema(),
        }

    def get_schema(self) -> Dict[str, Any]:
        """Generate schema from service definition"""
        definition = self.get_service_definition()
        return definition.json_schema
    
    def get_steps_info(self) -> List[StepInfo]:
        """Return detailed information about all steps - compatibility method"""
        definition = self.get_service_definition()
        return definition.steps

    def get_next_step_info(self, step: str) -> Dict[str, Any]:
        """Get complete info for next step"""
        step_info = self._get_step_info(step)
        if step_info:
            return step_info.model_dump()
        return {}

    def process_step(self, step: str, payload: str) -> Dict[str, Any]:
        """Process a step and return result with dependency validation"""
        # First validate dependencies
        is_dep_valid, dep_error = self._validate_dependencies(step)
        if not is_dep_valid:
            return {
                "status": "dependency_error",
                "message": dep_error,
                "next_step_info": self.get_next_step_info(step),
                "available_steps": self.get_available_steps(),
                "completed": False,
                "schema": self.get_schema(),
            }
        
        # Then validate input
        is_valid, error_msg = self.execute_step(step, payload)
        if not is_valid:
            return {
                "status": "validation_error",
                "message": error_msg,
                "next_step_info": self.get_next_step_info(step),
                "completed": False,
                "schema": self.get_schema(),
            }

        # Store valid data
        self.data[step] = payload

        # Check if all required steps are completed
        definition = self.get_service_definition()
        required_steps = [s.name for s in definition.steps if s.required]
        if all(step in self.data for step in required_steps):
            return {
                "status": "completed",
                "completed": True,
                "data": self.data,
                "completion_message": self.get_completion_message(),
            }
        
        # Get next step based on dependencies
        next_step = self.get_next_required_step()
        return {
            "status": "success",
            "next_step_info": self.get_next_step_info(next_step) if next_step else {},
            "available_steps": self.get_available_steps(),
            "completed": False,
            "schema": self.get_schema(),
        }


def build_service_registry(*service_classes: Type[BaseService]) -> Dict[str, Type[BaseService]]:
    """
    Build SERVICE_REGISTRY dynamically from service classes.
    
    Args:
        *service_classes: Service classes that inherit from BaseService
        
    Returns:
        Dict mapping service_name to service class
        
    Raises:
        ValueError: If service_name is not defined or duplicated
    """
    registry = {}
    
    for service_class in service_classes:
        if not issubclass(service_class, BaseService):
            raise ValueError(f"{service_class.__name__} must inherit from BaseService")
        
        if service_class.service_name is None:
            raise ValueError(f"{service_class.__name__} must define service_name")
        
        service_name = service_class.service_name
        
        if service_name in registry:
            existing_class = registry[service_name]
            raise ValueError(
                f"Duplicate service_name '{service_name}' found in "
                f"{existing_class.__name__} and {service_class.__name__}"
            )
        
        registry[service_name] = service_class
    
    return registry