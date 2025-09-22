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
        Creates an enhanced dependency tree visualization with improved formatting and information.
        100% service-agnostic - works with any service definition.
        """
        tree_lines = []
        tree_lines.append("═" * 60)
        tree_lines.append(f"🌳 SERVICE EXECUTION TREE: {self.service_def.service_name.upper()}")
        tree_lines.append("═" * 60)
        tree_lines.append("")
        
        # Get service completion status for enhanced messaging
        is_service_completed = self.state_manager.get("_internal.service_completed", self.service_state)
        completion_message = self.state_manager.get("_internal.completion_message", self.service_state)
        
        def get_step_status_enhanced(step_name: str) -> tuple[str, str]:
            """Returns (emoji, description) for enhanced status display"""
            # If service is completed, show all steps that were part of the execution path as completed
            if is_service_completed:
                # Check if this step has an outcome (was executed) or has data (was provided)
                has_outcome = self.state_manager.get(f"_internal.outcomes.{step_name}", self.service_state) is not None
                has_data = self.state_manager.get(f"data.{step_name}", self.service_state) is not None
                if "." in step_name:
                    # Handle nested data like user_info.name
                    parent_key = step_name.rsplit(".", 1)[0]
                    data_key = step_name.split(".")[-1]
                    parent_data = self.state_manager.get(f"data.{parent_key}", self.service_state)
                    has_data = isinstance(parent_data, dict) and data_key in parent_data
                
                # If step was executed/used or explicitly completed, show as completed
                is_explicitly_completed = self.state_manager.get(f"_internal.completed_steps.{step_name}", self.service_state) is True
                if has_outcome or has_data or is_explicitly_completed:
                    return "✅", "COMPLETED"
                else:
                    return "⭕", "PENDING"  # Not used in this execution path
            
            # Normal logic for non-completed services
            if self.state_manager.get(f"_internal.completed_steps.{step_name}", self.service_state) is True:
                return "✅", "COMPLETED"
            # If service is not completed, check for pending steps
            pending_steps = self.state_manager.get("_internal.pending_steps", self.service_state) or []
            if step_name in pending_steps:
                return "⏳", "CURRENT"
            return "⭕", "PENDING"
        
        def get_outcome(step_name: str) -> str:
            return self.state_manager.get(f"_internal.outcomes.{step_name}", self.service_state)
        
        def get_data_value(step_name: str) -> str:
            """Get the actual data value for completed data collection steps"""
            if "." in step_name:
                # Handle nested data like user_info.name
                parent_key = step_name.rsplit(".", 1)[0]
                data_key = step_name.split(".")[-1]
                parent_data = self.state_manager.get(f"data.{parent_key}", self.service_state)
                if isinstance(parent_data, dict) and data_key in parent_data:
                    value = parent_data[data_key]
                    # Truncate long values for display
                    if isinstance(value, str) and len(value) > 30:
                        return f'"{value[:27]}..."'
                    elif isinstance(value, str):
                        return f'"{value}"'
                    return str(value)
            else:
                # Handle top-level data
                value = self.state_manager.get(f"data.{step_name}", self.service_state)
                if value is not None:
                    if isinstance(value, str) and len(value) > 30:
                        return f'"{value[:27]}..."'
                    elif isinstance(value, str):
                        return f'"{value}"'
                    return str(value)
            return ""
        
        # Build enhanced hierarchical dependency tree 
        def render_dependency_hierarchy():
            """Renders steps with enhanced hierarchical indentation based on dependencies."""
            rendered = set()
            
            def render_step_and_dependents(step: StepInfo, prefix: str = "", is_last_at_level: bool = True):
                if step.name in rendered:
                    return
                rendered.add(step.name)
                
                # Render current step with enhanced information
                connector = "└──" if is_last_at_level else "├──"
                status_emoji, status_text = get_step_status_enhanced(step.name)
                
                # Build enhanced step description
                step_desc = f"{step.name}"
                
                # Add step type indicator with better icons
                if step.action:
                    step_desc += " 🎬(action)"
                elif step.payload_schema:
                    step_desc += " 📝(data)"
                elif step.substeps:
                    step_desc += " 📁(container)"
                
                # Add data value for completed data steps
                if not step.action and status_text == "COMPLETED":
                    data_value = get_data_value(step.name)
                    if data_value:
                        step_desc += f" = {data_value}"
                
                # Add outcome if it's an action step
                outcome = get_outcome(step.name)
                if outcome:
                    step_desc += f" → {outcome}"
                
                tree_lines.append(f"{prefix}{connector} {status_emoji} {step_desc}")
                
                # Render substeps with enhanced information
                if step.substeps:
                    for i, substep in enumerate(step.substeps):
                        is_last_substep = i == len(step.substeps) - 1
                        substep_connector = "└──" if is_last_substep else "├──"
                        
                        substep_status_emoji, substep_status_text = get_step_status_enhanced(substep.name)
                        # If parent is complete, substeps should be complete too
                        if status_text == "COMPLETED":
                            substep_status_emoji = "✅"
                        
                        substep_prefix = prefix + ("    " if is_last_at_level else "│   ")
                        
                        # Enhanced substep description
                        substep_desc = substep.name
                        if substep.action:
                            substep_desc += " 🎬(action)"
                        elif substep.payload_schema:
                            substep_desc += " 📝(data)"
                            
                        # Add data value for completed substeps
                        if not substep.action and substep_status_text == "COMPLETED":
                            substep_data_value = get_data_value(substep.name)
                            if substep_data_value:
                                substep_desc += f" = {substep_data_value}"
                        
                        tree_lines.append(f"{substep_prefix}{substep_connector} {substep_status_emoji} {substep_desc}")
                
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
        
        # Enhanced footer with comprehensive status information
        tree_lines.append("")
        tree_lines.append("─" * 60)
        
        # Service completion status
        if is_service_completed:
            tree_lines.append("🎉 SERVICE COMPLETED SUCCESSFULLY!")
            if completion_message:
                tree_lines.append(f"📝 Result: {completion_message}")
        else:
            # Current status and next steps
            pending_steps = self.state_manager.get("_internal.pending_steps", self.service_state) or []
            if pending_steps:
                tree_lines.append(f"⏳ AWAITING INPUT: {', '.join(pending_steps)}")
            else:
                tree_lines.append("🔄 PROCESSING...")
        
        # Statistics summary
        all_steps = []
        def collect_all_steps(steps):
            for step in steps:
                if step.payload_schema or step.action:  # Only count actual executable steps
                    all_steps.append(step)
                if step.substeps:
                    collect_all_steps(step.substeps)
        collect_all_steps(self.service_def.steps)
        
        # If service is completed, show 100% progress regardless of individual step states
        if is_service_completed:
            total_count = len(all_steps)
            tree_lines.append(f"📊 Progress: {total_count}/{total_count} steps (100%)")
        else:
            completed_count = sum(1 for step in all_steps 
                                 if self.state_manager.get(f"_internal.completed_steps.{step.name}", self.service_state) is True)
            total_count = len(all_steps)
            progress_percentage = int((completed_count / total_count) * 100) if total_count > 0 else 0
            
            tree_lines.append(f"📊 Progress: {completed_count}/{total_count} steps ({progress_percentage}%)")
        
        # Enhanced legend
        tree_lines.append("")
        tree_lines.append("Legend: ✅=Completed ⏳=Current ⭕=Pending")
        tree_lines.append("Types:  🎬=Action 📝=Data 📁=Container")
        tree_lines.append("═" * 60)
        
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
        # If service is completed, return None regardless of pending steps
        is_service_completed = self.state_manager.get("_internal.service_completed", self.service_state)
        if is_service_completed:
            return None
            
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
            
            # V3: Use the new get_json_schema method for better schema handling
            step_schema = step.get_json_schema()
            
            # The payload schema properties should be keyed by the full step name
            properties = {
                step.name: step_schema.get("properties", {}).get(step.name, {"type": "string"})
            }

            return NextStepInfo(
                step_name=step.name,
                description=step.description,
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

        for step in pending_steps:
            # Add child substep info only if the parent is a true container
            if parent_step_info.name != step.name:
                child_next_step = NextStepInfo(
                    step_name=step.name,
                    description=step.description,
                    payload_schema=step.get_json_schema()
                )
                parent_next_step.substeps.append(child_next_step)

            # V3: Consolidate schema into parent using new method
            step_schema = step.get_json_schema()
            for prop_name, prop_schema in step_schema.get("properties", {}).items():
                # Use the full step name as the key in the parent schema
                parent_next_step.payload_schema["properties"][step.name] = prop_schema
                if step.required:
                     parent_next_step.payload_schema["required"].append(step.name)

        return parent_next_step

    def get_execution_summary(self, complete_tree: Optional[str] = None) -> ExecutionSummary:
        """Constructs the ExecutionSummary object using current state."""
        # If we have a complete tree passed as parameter (from service completion), use it
        if complete_tree:
            return ExecutionSummary(tree=complete_tree)
        
        # Otherwise, generate current tree
        return ExecutionSummary(
            tree=self._generate_dependency_tree_ascii()
        )
