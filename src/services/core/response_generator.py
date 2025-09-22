from typing import Any, Dict, List, Optional

from src.services.core.state import ServiceState
from src.services.schema.models import (
    ExecutionSummary,
    NextStepInfo,
    ServiceDefinition,
    StepInfo,
)


class ResponseGenerator:
    """
    Generates the rich AgentResponse object.
    """

    def __init__(self, service_def: ServiceDefinition, state_manager: ServiceState, service_state: Dict[str, Any]):
        self.service_def = service_def
        self.state_manager = state_manager
        self.service_state = service_state

    def _generate_dependency_tree_ascii(self) -> str:
        """Creates a visual text representation of the service's progress."""
        tree_lines = ["🌳 DEPENDENCY TREE:"]
        pending_step = self.state_manager.get("_internal.pending_step", self.service_state)

        def build_tree(steps: List[StepInfo], prefix: str = ""):
            for i, step in enumerate(steps):
                is_last = i == len(steps) - 1
                connector = "└── " if is_last else "├── "
                
                # Determine status icon
                if self.state_manager.get(f"_internal.completed_steps.{step.name}", self.service_state):
                    icon = "🟢"
                elif step.name == pending_step:
                    icon = "🟡"
                else:
                    # A more complex check could be done here to see if it's blocked vs. just pending
                    icon = "🔴"

                line = f"{prefix}{connector}{icon} {step.name}"
                if step.required:
                    line += " (required)"
                if step.name == pending_step:
                    line += "   <-- CURRENT STEP"
                
                tree_lines.append(line)

                if step.substeps:
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    build_tree(step.substeps, new_prefix)

        build_tree(self.service_def.steps)
        return "\n".join(tree_lines)

    def _consolidate_schemas(self) -> Dict[str, Any]:
        """Merges the JSON schemas of all completed steps into a single schema."""
        consolidated_schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        def find_and_merge(steps: List[StepInfo]):
            for step in steps:
                if self.state_manager.get(f"_internal.completed_steps.{step.name}", self.service_state):
                    if step.payload_schema and "properties" in step.payload_schema:
                        props = step.payload_schema.get("properties", {})
                        consolidated_schema["properties"].update(props)
                        
                        # Add required fields from the step's schema
                        required_fields = step.payload_schema.get("required", [])
                        for req_field in required_fields:
                            if req_field not in consolidated_schema["required"]:
                                consolidated_schema["required"].append(req_field)
                
                if step.substeps:
                    find_and_merge(step.substeps)

        find_and_merge(self.service_def.steps)
        return consolidated_schema

    def get_next_step_info(self) -> Optional[NextStepInfo]:
        """Constructs the NextStepInfo object if a step is pending user input."""
        pending_step_name = self.state_manager.get("_internal.pending_step", self.service_state)
        if not pending_step_name:
            return None

        def find_step(steps: List[StepInfo]) -> Optional[StepInfo]:
            for step in steps:
                if step.name == pending_step_name:
                    return step
                if step.substeps:
                    found = find_step(step.substeps)
                    if found:
                        return found
            return None

        step = find_step(self.service_def.steps)
        if step:
            return NextStepInfo(
                step_name=step.name,
                description=step.description.format(**self.service_state), # Basic templating
                payload_schema=step.payload_schema
            )
        return None

    def get_execution_summary(self) -> ExecutionSummary:
        """Constructs the ExecutionSummary object."""
        return ExecutionSummary(
            completed_data_schema=self._consolidate_schemas(),
            dependency_tree_ascii=self._generate_dependency_tree_ascii()
        )
