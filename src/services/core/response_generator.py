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
        """
        Creates a visual representation of the service's structure and execution flow.
        """
        tree_lines = ["🌳 EXECUTION GRAPH:"]
        pending_steps_names = self.state_manager.get("_internal.pending_steps", self.service_state) or []

        memo_is_complete = {}
        def is_step_complete(step: StepInfo) -> bool:
            step_name = step.name
            if step_name in memo_is_complete: return memo_is_complete[step_name]
            
            if self.state_manager.get(f"_internal.completed_steps.{step_name}", self.service_state) is True:
                memo_is_complete[step_name] = True
                return True
            
            if step.substeps:
                required = [s for s in step.substeps if s.required]
                if required and all(is_step_complete(s) for s in required):
                    memo_is_complete[step_name] = True
                    return True

            memo_is_complete[step_name] = False
            return False

        def build_tree(steps: List[StepInfo], prefix: str = ""):
            for i, step in enumerate(steps):
                is_last = i == len(steps) - 1
                connector = "└── " if is_last else "├── "
                
                icon = "🔴"
                if is_step_complete(step): icon = "🟢"
                elif step.name in pending_steps_names: icon = "🟡"

                line = f"{prefix}{connector}{icon} {step.name}"
                
                annotations = []
                if step.depends_on:
                    annotations.append(f"deps: {', '.join(step.depends_on)}")
                if step.action:
                    annotations.append("action")
                if annotations:
                    line += f" [{'; '.join(annotations)}]"

                if step.name in pending_steps_names:
                    line += "   <-- CURRENT"
                
                tree_lines.append(line)

                if step.substeps:
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    build_tree(step.substeps, new_prefix)

        build_tree(self.service_def.steps, "")
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
        # Helper to find the actual StepInfo objects from their names
        def find_steps_by_names(steps: List[StepInfo]):
            for step in steps:
                if step.name in pending_step_names:
                    pending_steps.append(step)
                if step.substeps:
                    find_steps_by_names(step.substeps)
        
        find_steps_by_names(self.service_def.steps)
        if not pending_steps:
            return None

        # If there's only one pending step and it's a leaf, handle it simply.
        if len(pending_steps) == 1 and not pending_steps[0].substeps:
            step = pending_steps[0]
            
            # The payload schema properties should be keyed by the full step name
            properties = {
                step.name: {
                    "type": "string" # Assuming string for simplicity, schema could be copied
                }
                for prop_name in step.payload_schema.get("properties", {}).keys()
            }

            return NextStepInfo(
                step_name=step.name,
                description=step.description.format(**self.service_state.get("data", {})),
                payload_schema={
                    "type": "object",
                    "properties": properties,
                    "required": [step.name] if step.required else []
                }
            )

        # Find the common parent StepInfo object for all pending steps
        step_paths = [s.name.replace('.', '/') for s in pending_steps]
        common_path_prefix = os.path.commonpath(step_paths).replace('/', '.')
        
        parent_step_info = None
        def find_parent_step(steps: List[StepInfo]):
            nonlocal parent_step_info
            for step in steps:
                if step.name == common_path_prefix:
                    parent_step_info = step
                    return
                if step.substeps:
                    find_parent_step(step.substeps)
        
        find_parent_step(self.service_def.steps)
        if not parent_step_info:
            parent_step_info = StepInfo(name="root", description="Please provide the following information.")

        # Build the hierarchical response
        parent_next_step = NextStepInfo(
            step_name=parent_step_info.name,
            description=parent_step_info.description,
            payload_schema={"type": "object", "properties": {}, "required": []}
        )

        data_context = self.service_state.get("data", {})
        for step in pending_steps:
            # Add child substep info only if the parent is a true container
            if parent_step_info.name != step.name:
                child_next_step = NextStepInfo(
                    step_name=step.name,
                    description=step.description.format(**data_context),
                    payload_schema=step.payload_schema
                )
                parent_next_step.substeps.append(child_next_step)

            # Consolidate schema into parent
            for prop_name, prop_schema in step.payload_schema.get("properties", {}).items():
                # Use the full step name as the key in the parent schema
                parent_next_step.payload_schema["properties"][step.name] = prop_schema
                if step.required:
                     parent_next_step.payload_schema["required"].append(step.name)

        return parent_next_step

    def get_execution_summary(self) -> ExecutionSummary:
        """Constructs the ExecutionSummary object."""
        return ExecutionSummary(
            tree=self._generate_dependency_tree_ascii()
        )
