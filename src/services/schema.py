import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator, computed_field


class ConditionalDependency(BaseModel):
    """Model for conditional dependencies between steps"""
    if_condition: Dict[str, Any] = Field(..., description="Condition that must be met")
    then_required: List[str] = Field(default_factory=list, description="Steps required if condition is met")
    else_required: List[str] = Field(default_factory=list, description="Steps required if condition is not met")


class StepInfo(BaseModel):
    """Pydantic model for step information with dependencies"""
    name: str = Field(..., description="Unique step name", min_length=1)
    description: str = Field(..., description="Step description", min_length=1)
    example: Optional[str] = Field(None, description="Example input")
    required: bool = Field(True, description="Whether this step is required")
    
    # Dependency system (all optional)
    depends_on: List[str] = Field(default_factory=list, description="Steps that must be completed before this one")
    conflicts_with: List[str] = Field(default_factory=list, description="Steps that cannot coexist with this one")
    conditional: Optional[ConditionalDependency] = Field(default=None, description="Conditional dependency rules")
    validation_depends_on: List[str] = Field(default_factory=list, description="Steps whose data is needed for validation")
    
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', v):
            raise ValueError('Step name must be a valid identifier')
        return v
    
    @field_validator('depends_on', 'conflicts_with', 'validation_depends_on')
    @classmethod
    def validate_step_lists(cls, v: List[str]) -> List[str]:
        for step in v:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', step):
                raise ValueError(f'Invalid step name: {step}')
        return v


class ServiceDefinition(BaseModel):
    """
    Single source of truth for service configuration.
    Eliminates redundancy between schema, steps_info, and available_steps.
    """
    service_name: str = Field(..., description="Name of the service")
    description: str = Field(..., description="Service description")
    steps: List[StepInfo] = Field(..., description="Complete step definitions")
    
    @computed_field
    @property
    def json_schema(self) -> Dict[str, Any]:
        """Auto-generated JSON schema from steps"""
        properties = {}
        required = []
        
        for step in self.steps:
            properties[step.name] = {
                "type": "string",
                "description": step.description
            }
            if step.example:
                properties[step.name]["example"] = step.example
            
            if step.required:
                required.append(step.name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    @computed_field
    @property
    def step_names(self) -> List[str]:
        """List of all step names"""
        return [step.name for step in self.steps]
    
    def get_available_steps(self, completed_data: Dict[str, Any]) -> List[str]:
        """Calculate available steps based on current state and dependencies"""
        completed_steps = set(completed_data.keys())
        available = []
        
        for step in self.steps:
            # Check if already completed
            if step.name in completed_steps:
                continue
                
            # Check basic dependencies
            if step.depends_on and not all(dep in completed_steps for dep in step.depends_on):
                continue
                
            # Check conflicts
            if step.conflicts_with and any(conflict in completed_steps for conflict in step.conflicts_with):
                continue
                
            # Check conditional dependencies
            if step.conditional:
                condition_met = self._evaluate_condition(step.conditional.if_condition, completed_data)
                required_deps = step.conditional.then_required if condition_met else step.conditional.else_required
                
                if required_deps and not all(dep in completed_steps for dep in required_deps):
                    continue
            
            available.append(step.name)
        
        return available
    
    def _evaluate_condition(self, condition: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """Evaluate a condition against current data"""
        for field, expected_value in condition.items():
            if field not in data or data[field] != expected_value:
                return False
        return True
    
    def get_step_info(self, step_name: str) -> Optional[StepInfo]:
        """Get specific step information by name"""
        for step in self.steps:
            if step.name == step_name:
                return step
        return None
    
    def to_dict(self, include_state: bool = False, completed_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Convert to dictionary with optional state information"""
        result = {
            "service_name": self.service_name,
            "description": self.description,
            "steps": [step.model_dump() for step in self.steps],
            "schema": self.json_schema
        }
        
        if include_state and completed_data is not None:
            result["available_steps"] = self.get_available_steps(completed_data)
            
        return result