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
            if step.payload_example:
                properties[step.name]["payload_example"] = step.payload_example

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
        return self._dependency_engine.validate_dependencies_with_temp_data(
            step_name, temp_data
        )

    def get_processing_order(self, steps: List[str]) -> List[str]:
        """Get processing order based on dependencies (topological sort)"""
        return self._dependency_engine.get_processing_order(steps)

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
                    "description": step_info.description,
                    "data_type": step_info.data_type,
                }
                # Usar exemplo de payload direto do StepInfo (obrigatório para todos os steps)
                if step_info.payload_example:
                    step_schema["payload_example"] = step_info.payload_example

                # Adicionar substeps se existirem
                if step_info.substeps:
                    # Substeps como objeto direto (não JSON string)
                    substeps_info = {}
                    for substep in step_info.substeps:
                        substeps_info[substep.name] = {
                            "description": substep.description,
                            "data_type": substep.data_type,
                        }
                        if substep.payload_example:
                            substeps_info[substep.name][
                                "payload_example"
                            ] = substep.payload_example

                    step_schema["substeps"] = substeps_info

                schema["properties"][step_name] = step_schema

                # Para steps com substeps, adicionar substeps obrigatórios ao required
                if step_info.substeps:
                    for substep in step_info.substeps:
                        if substep.required:
                            schema["required"].append(substep.name)
                else:
                    # Para steps sem substeps, adicionar o step ao required se for obrigatório
                    if step_info.required:
                        schema["required"].append(step_name)

        return schema


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
