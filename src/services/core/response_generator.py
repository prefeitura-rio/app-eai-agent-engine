import os
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
        """
        Constructs a hierarchical NextStepInfo object based on all pending data collection steps.
        """
        pending_step_names = self.state_manager.get("_internal.pending_steps", self.service_state)
        if not pending_step_names:
            return None

        pending_steps: List[StepInfo] = []
        def find_steps_by_names(steps: List[StepInfo]):
            for step in steps:
                if step.name in pending_step_names:
                    pending_steps.append(step)
                if step.substeps:
                    find_steps_by_names(step.substeps)
        
        find_steps_by_names(self.service_def.steps)
        if not pending_steps:
            return None

        # Find the common parent of all pending steps using path logic
        if not pending_steps:
            return None
        
        step_paths = [s.name.replace('.', '/') for s in pending_steps]
        common_path_prefix = os.path.commonpath(step_paths).replace('/', '.')
        
        # Find the actual StepInfo for the common parent
        parent_step = None
        def find_parent_step(steps: List[StepInfo]):
            nonlocal parent_step
            for step in steps:
                if step.name == common_path_prefix:
                    parent_step = step
                    return
                if step.substeps:
                    find_parent_step(step.substeps)
        
        find_parent_step(self.service_def.steps)

        if not parent_step:
            parent_step = StepInfo(name="root", description="Please provide the following information.")

        # Build the hierarchical response
        parent_next_step = NextStepInfo(
            step_name=parent_step.name,
            description=parent_step.description,
            payload_schema={"type": "object", "properties": {}, "required": []}
        )

        data_context = self.service_state.get("data", {})
        for step in pending_steps:
            # Add child substep info
            child_next_step = NextStepInfo(
                step_name=step.name,
                description=step.description.format(**data_context),
                payload_schema=step.payload_schema
            )
            parent_next_step.substeps.append(child_next_step)

            # Consolidate schema into parent, using full step name as key
            for prop_name, prop_schema in step.payload_schema.get("properties", {}).items():
                parent_next_step.payload_schema["properties"][step.name] = prop_schema # e.g., "user_info.name": {...}
                if step.payload_schema.get("required"):
                     parent_next_step.payload_schema["required"].append(step.name)

        return parent_next_step

    def get_execution_summary(self) -> ExecutionSummary:
        """Constructs the ExecutionSummary object."""
        return ExecutionSummary(
            completed_data_schema=self._consolidate_schemas(),
            dependency_tree_ascii=self._generate_dependency_tree_ascii()
        )
