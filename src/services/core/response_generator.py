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
        Creates a generic dependency tree visualization based purely on ServiceDefinition structure.
        100% service-agnostic - works with any service definition.
        """
        tree_lines = [f"🌳 DEPENDENCY TREE: {self.service_def.service_name}"]
        tree_lines.append("│")
        
        def get_step_status(step_name: str) -> str:
            if self.state_manager.get(f"_internal.completed_steps.{step_name}", self.service_state) is True:
                return "🟢"
            pending_steps = self.state_manager.get("_internal.pending_steps", self.service_state) or []
            if step_name in pending_steps:
                return "🟡"
            return "🔴"
        
        def get_outcome(step_name: str) -> str:
            return self.state_manager.get(f"_internal.outcomes.{step_name}", self.service_state)
        
        def render_step(step: StepInfo, prefix: str = "", is_last: bool = True):
            """Renders a step and all its substeps recursively."""
            connector = "└──" if is_last else "├──"
            status = get_step_status(step.name)
            
            # Build step description
            step_desc = step.name
            if step.action:
                step_desc += f" (action)"
            
            # Add outcome if it's an action step
            outcome = get_outcome(step.name)
            if outcome:
                step_desc += f" → {outcome}"
            
            tree_lines.append(f"{prefix}{connector} {status} {step_desc}")
            
            # Render substeps if any
            if step.substeps:
                for i, substep in enumerate(step.substeps):
                    is_last_substep = i == len(step.substeps) - 1
                    substep_connector = "└──" if is_last_substep else "├──"
                    
                    # Fix substep status: if parent is complete, substeps should be complete too
                    substep_status = get_step_status(substep.name)
                    if status == "🟢":  # Parent is complete
                        substep_status = "🟢"
                    
                    # Correct indentation for substeps
                    substep_prefix = prefix + ("    " if is_last else "│   ")
                    tree_lines.append(f"{substep_prefix}{substep_connector} {substep_status} {substep.name}")
                    
                    # Handle nested substeps recursively
                    if substep.substeps:
                        nested_prefix = substep_prefix + ("    " if is_last_substep else "│   ")
                        for j, nested_step in enumerate(substep.substeps):
                            is_last_nested = j == len(substep.substeps) - 1
                            render_step(nested_step, nested_prefix, is_last_nested)
        
        # Find root steps (steps with no dependencies or dependencies outside current service)
        def find_root_steps():
            all_step_names = set()
            def collect_names(steps):
                for step in steps:
                    all_step_names.add(step.name)
                    if step.substeps:
                        collect_names(step.substeps)
            collect_names(self.service_def.steps)
            
            root_steps = []
            for step in self.service_def.steps:
                # A step is root if it has no dependencies or all dependencies are external
                if not step.depends_on or not any(dep in all_step_names for dep in step.depends_on):
                    root_steps.append(step)
            return root_steps
        
        # Build hierarchical dependency tree with proper indentation
        def render_dependency_hierarchy():
            """Renders steps with hierarchical indentation based on dependencies."""
            rendered = set()
            
            def render_step_and_dependents(step: StepInfo, prefix: str = "", is_last_at_level: bool = True):
                if step.name in rendered:
                    return
                rendered.add(step.name)
                
                # Render current step
                connector = "└──" if is_last_at_level else "├──"
                status = get_step_status(step.name)
                
                step_desc = step.name
                if step.action:
                    step_desc += " (action)"
                
                outcome = get_outcome(step.name)
                if outcome:
                    step_desc += f" → {outcome}"
                
                tree_lines.append(f"{prefix}{connector} {status} {step_desc}")
                
                # Render substeps first
                if step.substeps:
                    for i, substep in enumerate(step.substeps):
                        is_last_substep = i == len(step.substeps) - 1
                        substep_connector = "└──" if is_last_substep else "├──"
                        
                        substep_status = get_step_status(substep.name)
                        if status == "🟢":
                            substep_status = "🟢"
                        
                        substep_prefix = prefix + ("    " if is_last_at_level else "│   ")
                        tree_lines.append(f"{substep_prefix}{substep_connector} {substep_status} {substep.name}")
                
                # Find direct dependents (steps that depend on this step)
                dependents = []
                for s in self.service_def.steps:
                    if step.name in s.depends_on and s.name not in rendered:
                        dependents.append(s)
                
                # Render dependents with proper indentation
                if dependents:
                    # Add flow arrow
                    flow_prefix = prefix + ("    " if is_last_at_level else "│   ")
                    tree_lines.append(f"{flow_prefix}│")
                    tree_lines.append(f"{flow_prefix}▼")
                    
                    # Render each dependent
                    for i, dependent in enumerate(dependents):
                        is_last_dependent = i == len(dependents) - 1
                        render_step_and_dependents(
                            dependent, 
                            flow_prefix,
                            is_last_dependent
                        )
            
            # Start with root steps (no dependencies)
            root_steps = []
            all_step_names = {s.name for s in self.service_def.steps}
            
            for step in self.service_def.steps:
                if not step.depends_on or not any(dep in all_step_names for dep in step.depends_on):
                    root_steps.append(step)
            
            # Render from roots
            for i, root_step in enumerate(root_steps):
                is_last_root = i == len(root_steps) - 1
                render_step_and_dependents(root_step, "", is_last_root)
        
        render_dependency_hierarchy()
        
        # Add current status indicator
        pending_steps = self.state_manager.get("_internal.pending_steps", self.service_state) or []
        if pending_steps:
            tree_lines.append("")
            tree_lines.append(f"◄── NEXT: {', '.join(pending_steps)}")
        
        # Add legend
        tree_lines.append("")
        tree_lines.append("Legend: 🟢=Complete 🟡=Current 🔴=Pending")
        
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
        # If service is completed, use the pre-reset tree to show complete execution path
        service_completed = self.state_manager.get("_internal.service_completed", self.service_state)
        if service_completed:
            complete_tree = self.state_manager.get("_internal.execution_tree_complete", self.service_state)
            if complete_tree:
                return ExecutionSummary(tree=complete_tree)
        
        # Otherwise, use current state tree
        return ExecutionSummary(
            tree=self._generate_dependency_tree_ascii()
        )
