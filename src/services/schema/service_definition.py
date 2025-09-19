import json
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field, computed_field

from src.services.schema.step_info import StepInfo
from src.services.schema.dependency_engine import DependencyEngine
from src.services.schema.validation import ValidationEngine
from src.services.schema.visualization import VisualizationEngine


class ServiceDefinition(BaseModel):
    """
    Single source of truth for service configuration.
    Core ServiceDefinition with delegated responsibilities to specialized engines.
    """

    service_name: str = Field(..., description="Name of the service")
    description: str = Field(..., description="Service description")
    steps: List[StepInfo] = Field(..., description="Complete step definitions")

    def __init__(self, **data):
        super().__init__(**data)
        # Initialize engines after validation
        self._dependency_engine = DependencyEngine(self.steps)
        self._validation_engine = ValidationEngine(self.steps)
        self._visualization_engine = VisualizationEngine(
            self.service_name, self.description, self.steps
        )

    @computed_field
    @property
    def json_schema(self) -> Dict[str, Any]:
        """Auto-generated JSON schema from steps"""
        properties = {}
        required = []

        for step in self.steps:
            properties[step.name] = {"type": "string", "description": step.description}
            if step.example:
                properties[step.name]["example"] = step.example

            if step.required:
                required.append(step.name)

        return {"type": "object", "properties": properties, "required": required}

    @computed_field
    @property
    def step_names(self) -> List[str]:
        """List of all step names"""
        return [step.name for step in self.steps]

    # === Dependency Management (delegated to DependencyEngine) ===
    
    def get_available_steps(self, completed_data: Dict[str, Any]) -> List[str]:
        """Calculate available steps based on current state and dependencies"""
        return self._dependency_engine.get_available_steps(completed_data)

    def validate_dependencies(
        self, step_name: str, completed_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate if step dependencies are satisfied"""
        return self._dependency_engine.validate_dependencies(step_name, completed_data)

    def validate_dependencies_with_temp_data(
        self, step_name: str, temp_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate dependencies using temporary data state"""
        return self._dependency_engine.validate_dependencies_with_temp_data(step_name, temp_data)

    def get_processing_order(self, steps: List[str]) -> List[str]:
        """Get processing order based on dependencies (topological sort)"""
        return self._dependency_engine.get_processing_order(steps)

    def get_next_required_step(self, completed_data: Dict[str, Any]) -> Optional[str]:
        """Get the next required step based on dependencies"""
        return self._dependency_engine.get_next_required_step(completed_data)

    def is_service_completed(self, completed_data: Dict[str, Any]) -> bool:
        """Check if all required steps are completed"""
        return self._dependency_engine.is_service_completed(completed_data)

    # === Validation (delegated to ValidationEngine) ===
    
    def process_bulk_data(
        self, payload: Dict[str, Any], service_executor
    ) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
        """Process bulk payload with dependency validation"""
        return self._validation_engine.process_bulk_data(payload, service_executor)

    # === Visualization (delegated to VisualizationEngine) ===
    
    def get_steps_schematic(
        self, completed_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Retorna um esquemático visual dos steps do serviço"""
        return self._visualization_engine.get_steps_schematic(completed_data)

    def get_visual_schematic(
        self, completed_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Retorna representação visual em texto dos steps e dependências"""
        return self._visualization_engine.get_visual_schematic(completed_data)

    def get_state_analysis(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Análise completa do estado atual do serviço"""
        return self._visualization_engine.get_state_analysis(completed_data)

    def get_state_summary(self, completed_data: Dict[str, Any]) -> str:
        """Resumo em linguagem natural do estado atual"""
        return self._visualization_engine.get_state_summary(completed_data)

    def get_next_action_suggestion(self, completed_data: Dict[str, Any]) -> str:
        """Sugestão específica do que fazer a seguir"""
        return self._visualization_engine.get_next_action_suggestion(completed_data)

    # === Core Utility Methods ===

    def get_step_info(self, step_name: str) -> Optional[StepInfo]:
        """Get specific step information by name"""
        return self._dependency_engine.get_step_info(step_name)

    def get_contextual_schema(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Schema dinâmico baseado no estado atual - apenas steps principais com substeps estruturados"""
        available_steps = self.get_available_steps(completed_data)
        schema = {"type": "object", "properties": {}, "required": []}

        for step_name in available_steps:
            step_info = self.get_step_info(step_name)
            if step_info:
                # Criar schema para o step principal
                step_schema = {
                    "type": "string", 
                    "description": step_info.description,
                    "data_type": step_info.data_type
                }
                
                if step_info.example:
                    step_schema["example"] = step_info.example

                # Se tem substeps, adicionar informações dos substeps e instruções de formato
                if step_info.substeps:
                    # Substeps como objeto direto (não JSON string)
                    substeps_info = {}
                    for substep in step_info.substeps:
                        substeps_info[substep.name] = {
                            "description": substep.description,
                            "data_type": substep.data_type,
                        }
                        if substep.example:
                            substeps_info[substep.name]["example"] = substep.example
                    
                    step_schema["substeps"] = substeps_info
                    
                    # Gerar instruções de formato dinamicamente
                    step_schema["format_instructions"] = self._generate_format_instructions(step_info)

                schema["properties"][step_name] = step_schema
                
                # Para steps com substeps, adicionar substeps obrigatórios ao required
                if step_info.substeps:
                    for substep in step_info.substeps:
                        if substep.required:
                            schema["required"].append(substep.name)
                else:
                    # Para steps sem substeps, adicionar o step ao required se for obrigatório
                    if step_info.required or self._is_conditionally_required(
                        step_info, completed_data
                    ):
                        schema["required"].append(step_name)

        return schema

    def _generate_format_instructions(self, step_info: StepInfo) -> str:
        """Gera instruções de formato dinamicamente baseado nos substeps"""
        if not step_info.substeps:
            return ""
        
        # Gerar exemplo de payload estruturado
        example_payload = {}
        for substep in step_info.substeps:
            if substep.example:
                example_payload[substep.name] = substep.example
            else:
                example_payload[substep.name] = f"<{substep.name}>"
        
        # Formato para individual substeps
        individual_examples = []
        for substep in step_info.substeps:
            example_val = substep.example or f"<{substep.name}>"
            individual_examples.append(f'{{"{substep.name}": "{example_val}"}}')
        
        instructions = f"""
FORMATOS ACEITOS:

1. Individual substeps (detectados automaticamente):
   {' ou '.join(individual_examples)}

2. JSON completo:
   {{"{step_info.name}": {json.dumps(example_payload, ensure_ascii=False)}}}

3. Múltiplos substeps:
   {json.dumps(example_payload, ensure_ascii=False)}
"""
        return instructions.strip()

    def _is_conditionally_required(
        self, step: StepInfo, completed_data: Dict[str, Any]
    ) -> bool:
        """Verifica se um step se tornou obrigatório baseado em condições"""
        return self._dependency_engine._is_conditionally_required(step, completed_data)

    def to_dict(
        self,
        include_state: bool = False,
        completed_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convert to dictionary with optional state information"""
        result = {
            "service_name": self.service_name,
            "description": self.description,
            "steps": [step.model_dump() for step in self.steps],
            "schema": self.json_schema,
        }

        if include_state and completed_data is not None:
            result["available_steps"] = self.get_available_steps(completed_data)

        return result