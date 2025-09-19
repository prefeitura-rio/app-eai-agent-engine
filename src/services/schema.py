import re
from typing import Dict, Any, List, Optional, Tuple
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
    
    def get_state_analysis(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Análise completa do estado atual do serviço"""
        all_steps = {step.name: step for step in self.steps}
        completed_steps = list(completed_data.keys())
        available_steps = self.get_available_steps(completed_data)
        
        # Classificar steps disponíveis
        required_available = []
        optional_available = []
        for step_name in available_steps:
            step = all_steps[step_name]
            if step.required or self._is_conditionally_required(step, completed_data):
                required_available.append(step_name)
            else:
                optional_available.append(step_name)
        
        # Steps ainda pendentes (não disponíveis por dependências)
        pending_steps = []
        for step in self.steps:
            if step.name not in completed_steps and step.name not in available_steps:
                pending_steps.append(step.name)
        
        total_steps = len(self.steps)
        completed_count = len(completed_steps)
        
        return {
            "completed_steps": completed_steps,
            "available_steps": available_steps,
            "required_steps": required_available,
            "optional_steps": optional_available, 
            "pending_steps": pending_steps,
            "progress": {
                "completed": completed_count,
                "available": len(available_steps),
                "pending": len(pending_steps),
                "total": total_steps,
                "percentage": round((completed_count / total_steps) * 100, 1) if total_steps > 0 else 0,
                "completion_estimate": self._estimate_completion(completed_count, total_steps)
            }
        }
    
    def get_contextual_schema(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Schema dinâmico baseado no estado atual"""
        available_steps = self.get_available_steps(completed_data)
        schema = {"type": "object", "properties": {}, "required": []}
        
        for step_name in available_steps:
            step_info = self.get_step_info(step_name)
            if step_info:
                step_schema = {
                    "type": "string",
                    "description": step_info.description
                }
                
                if step_info.example:
                    step_schema["example"] = step_info.example
                
                # Add to required array if this step is required
                if step_info.required or self._is_conditionally_required(step_info, completed_data):
                    schema["required"].append(step_name)
                
                # Schema contextual será adicionado pela tool que tem acesso ao service
                # This is where service.get_contextual_schema() will enhance the step_schema
                
                schema["properties"][step_name] = step_schema
        
        return schema
    
    def get_state_summary(self, completed_data: Dict[str, Any]) -> str:
        """Resumo em linguagem natural do estado atual"""
        analysis = self.get_state_analysis(completed_data)
        
        if not completed_data:
            return f"Iniciando {self.service_name}. Escolha os primeiros campos disponíveis."
        
        completed_desc = ", ".join(analysis["completed_steps"])
        required_desc = ", ".join(analysis["required_steps"]) 
        
        summary = f"Concluído: {completed_desc}. "
        if required_desc:
            summary += f"Próximos obrigatórios: {required_desc}. "
        if analysis["optional_steps"]:
            summary += f"Opcionais disponíveis: {len(analysis['optional_steps'])}. "
        
        return summary
    
    def get_next_action_suggestion(self, completed_data: Dict[str, Any]) -> str:
        """Sugestão específica do que fazer a seguir"""
        analysis = self.get_state_analysis(completed_data)
        
        if analysis["required_steps"]:
            if len(analysis["required_steps"]) == 1:
                step_name = analysis["required_steps"][0]
                step_info = self.get_step_info(step_name)
                if step_info:
                    base_desc = step_info.description.lower()
                    example_part = f" (ex: {step_info.example})" if step_info.example else ""
                    return f"Forneça {base_desc}{example_part}"
                else:
                    return f"Forneça {step_name}"
            else:
                return f"Forneça qualquer um dos campos obrigatórios: {', '.join(analysis['required_steps'])}"
        elif analysis["optional_steps"]:
            return f"Todos campos obrigatórios concluídos. Opcionalmente: {', '.join(analysis['optional_steps'])}"
        else:
            return "Pronto para finalizar o serviço."
    
    def _is_conditionally_required(self, step: StepInfo, completed_data: Dict[str, Any]) -> bool:
        """Verifica se um step se tornou obrigatório baseado em condições"""
        if not step.conditional:
            return False
        
        # Para initial_deposit: se account_type = "corrente", então é obrigatório
        condition_met = self._evaluate_condition(step.conditional.if_condition, completed_data)
        
        # Se a condição é atendida e o step está na lista then_required, é obrigatório
        # Ou se a condição não é atendida e está na lista else_required, é obrigatório
        required_steps = step.conditional.then_required if condition_met else step.conditional.else_required
        is_in_required_list = step.name in required_steps
        
        # Para steps como initial_deposit, se a condição é "account_type: corrente"
        # e está atendida, o step se torna obrigatório mesmo se não estiver na lista
        if step.name == "initial_deposit" and condition_met:
            return True
            
        return is_in_required_list
    
    def _estimate_completion(self, completed: int, total: int) -> str:
        """Estimativa de conclusão baseada no progresso"""
        if total == 0:
            return "Concluído"
        
        remaining = total - completed
        if remaining == 0:
            return "Concluído"
        elif remaining == 1:
            return "1 campo restante"
        elif remaining <= 3:
            return f"{remaining} campos restantes"
        else:
            return f"{remaining} campos restantes"
    
    def _get_step_contextual_schema(self, step_name: str, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Schema específico baseado no contexto atual - pode ser sobrescrito pelos services"""
        # Implementação base - services podem sobrescrever para contexto específico
        # Base implementation doesn't use parameters, but subclasses might need them
        return {}
    
    def validate_dependencies(self, step_name: str, completed_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate if step dependencies are satisfied"""
        step_info = self.get_step_info(step_name)
        if not step_info:
            return False, f"Step '{step_name}' not found"
        
        # Check direct dependencies
        for dep in step_info.depends_on:
            if dep not in completed_data:
                return False, f"Step '{step_name}' requires '{dep}' to be completed first"
        
        # Check conflicts
        for conflict in step_info.conflicts_with:
            if conflict in completed_data:
                return False, f"Step '{step_name}' conflicts with already completed step '{conflict}'"
        
        # Check conditional dependencies
        if step_info.conditional:
            condition_met = self._evaluate_condition(step_info.conditional.if_condition, completed_data)
            required_steps = (step_info.conditional.then_required if condition_met 
                            else step_info.conditional.else_required)
            
            for req_step in required_steps:
                if req_step not in completed_data:
                    return False, f"Step '{step_name}' requires '{req_step}' based on current conditions"
        
        return True, ""
    
    def get_next_required_step(self, completed_data: Dict[str, Any]) -> Optional[str]:
        """Get the next required step based on dependencies"""
        available = self.get_available_steps(completed_data)
        
        # Filter for required steps only
        for step in self.steps:
            if step.name in available and (step.required or self._is_conditionally_required(step, completed_data)):
                return step.name
        
        # If no required steps, return first available
        return available[0] if available else None
    
    def get_processing_order(self, steps: List[str]) -> List[str]:
        """Get processing order based on dependencies (topological sort)"""
        # Simple implementation - can be enhanced with proper topological sort
        ordered = []
        remaining = list(steps)
        
        while remaining:
            # Find steps with no unmet dependencies in remaining list
            ready = []
            for step in remaining:
                step_info = self.get_step_info(step)
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
    
    def validate_dependencies_with_temp_data(self, step_name: str, temp_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate dependencies using temporary data state"""
        step_info = self.get_step_info(step_name)
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
    
    def process_bulk_data(self, payload: Dict[str, Any], service_executor) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
        """Process bulk payload with dependency validation - returns (valid_data, field_errors, dependency_errors)"""
        valid_data = {}
        field_errors = {}
        dependency_errors = {}

        # First pass: validate individual steps without dependencies
        for step_name in self.step_names:
            if step_name in payload:
                is_valid, error_msg = service_executor.execute_step(step_name, str(payload[step_name]))
                if is_valid:
                    valid_data[step_name] = str(payload[step_name]).strip()
                else:
                    field_errors[step_name] = error_msg

        # Second pass: validate dependencies with temporary data
        temp_data = {}
        processing_order = self.get_processing_order(list(valid_data.keys()))
        
        for step in processing_order:
            if step in valid_data:
                # Check dependencies with current state
                temp_data[step] = valid_data[step]
                is_dep_valid, dep_error = self.validate_dependencies_with_temp_data(step, temp_data)
                if not is_dep_valid:
                    dependency_errors[step] = dep_error
                    # Remove from valid data if dependencies fail
                    valid_data.pop(step, None)
                    temp_data.pop(step, None)
        
        return valid_data, field_errors, dependency_errors
    
    def is_service_completed(self, completed_data: Dict[str, Any]) -> bool:
        """Check if all required steps are completed"""
        required_steps = [
            step.name for step in self.steps 
            if step.required or self._is_conditionally_required(step, completed_data)
        ]
        return all(step in completed_data for step in required_steps)

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