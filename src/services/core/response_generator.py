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
        Creates a decision tree style visualization showing the flow and possible outcomes.
        """
        tree_lines = [f"🌳 DECISION TREE: {self.service_def.service_name}"]
        tree_lines.append("│")
        
        # Helper functions
        def get_step_status(step_name: str) -> str:
            if self.state_manager.get(f"_internal.completed_steps.{step_name}", self.service_state) is True:
                return "🟢"
            pending_steps = self.state_manager.get("_internal.pending_steps", self.service_state) or []
            if step_name in pending_steps:
                return "🟡"
            return "🔴"
        
        def get_outcome(step_name: str) -> str:
            return self.state_manager.get(f"_internal.outcomes.{step_name}", self.service_state)
        
        def add_step_with_substeps(step: StepInfo, prefix: str = ""):
            status = get_step_status(step.name)
            tree_lines.append(f"{prefix}└── {status} {step.name}")
            
            if step.substeps:
                for i, substep in enumerate(step.substeps):
                    is_last_substep = i == len(step.substeps) - 1
                    substep_connector = "└──" if is_last_substep else "├──"
                    substep_status = "🟢" if status == "🟢" else get_step_status(substep.name)
                    tree_lines.append(f"{prefix}    {substep_connector} {substep_status} {substep.name}")
        
        def add_flow_arrow(prefix: str = ""):
            tree_lines.append(f"{prefix}    │")
            tree_lines.append(f"{prefix}    ▼")
        
        def add_outcome_branch(step_name: str, outcome: str, next_steps: List[str], prefix: str = ""):
            tree_lines.append(f"{prefix}    ├── outcome: {outcome}")
            for next_step in next_steps:
                tree_lines.append(f"{prefix}    │       ▼")
                tree_lines.append(f"{prefix}    │   {get_step_status(next_step)} {next_step}")
        
        # Build the decision tree flow
        def build_flow():
            # 1. Start with user_info collection
            user_info_step = None
            check_account_step = None
            
            for step in self.service_def.steps:
                if step.name == "user_info":
                    user_info_step = step
                elif step.name == "check_account":
                    check_account_step = step
            
            if user_info_step:
                add_step_with_substeps(user_info_step)
                add_flow_arrow()
            
            # 2. Check account action with branching outcomes
            if check_account_step:
                status = get_step_status("check_account")
                tree_lines.append(f"└── {status} check_account (action: _check_account_exists)")
                
                outcome = get_outcome("check_account")
                if outcome:
                    if outcome == "ACCOUNT_EXISTS":
                        tree_lines.append("    ├── outcome: ACCOUNT_EXISTS")
                        tree_lines.append("    │       ▼")
                        add_action_flow("ask_action", "    │   ")
                    elif outcome == "ACCOUNT_NOT_FOUND":
                        tree_lines.append("    └── outcome: ACCOUNT_NOT_FOUND")
                        tree_lines.append("            ▼")
                        add_new_account_flow("        ")
                else:
                    # Show both possible paths
                    tree_lines.append("    ├── outcome: ACCOUNT_EXISTS")
                    tree_lines.append("    │       ▼")
                    tree_lines.append("    │   🔴 ask_action")
                    tree_lines.append("    │       │")
                    tree_lines.append("    │       ▼")
                    tree_lines.append("    │   🔴 process_action_choice → [operations...]")
                    tree_lines.append("    │")
                    tree_lines.append("    └── outcome: ACCOUNT_NOT_FOUND")
                    tree_lines.append("            ▼")
                    tree_lines.append("        🔴 account_type")
                    tree_lines.append("            │")
                    tree_lines.append("            ▼")
                    tree_lines.append("        🔴 create_account → ask_action → [operations...]")
        
        def add_action_flow(step_name: str, prefix: str):
            status = get_step_status(step_name)
            tree_lines.append(f"{prefix}{status} {step_name}")
            
            if step_name == "ask_action":
                tree_lines.append(f"{prefix}    │")
                tree_lines.append(f"{prefix}    ▼")
                process_status = get_step_status("process_action_choice")
                tree_lines.append(f"{prefix}{process_status} process_action_choice (action: _process_action_choice)")
                
                process_outcome = get_outcome("process_action_choice")
                if process_outcome:
                    if process_outcome == "DEPOSIT_CHOSEN":
                        tree_lines.append(f"{prefix}    ├── outcome: DEPOSIT_CHOSEN")
                        tree_lines.append(f"{prefix}    │       ▼")
                        deposit_status = get_step_status("deposit_amount")
                        tree_lines.append(f"{prefix}    │   {deposit_status} deposit_amount")
                        tree_lines.append(f"{prefix}    │       │")
                        tree_lines.append(f"{prefix}    │       ▼")
                        execute_status = get_step_status("execute_deposit")
                        tree_lines.append(f"{prefix}    │   {execute_status} execute_deposit (action: _make_deposit) → [Fim]")
                    elif process_outcome == "BALANCE_CALCULATED":
                        tree_lines.append(f"{prefix}    └── outcome: BALANCE_CALCULATED → [Fim]")
                else:
                    # Show both possible paths
                    tree_lines.append(f"{prefix}    ├── outcome: DEPOSIT_CHOSEN")
                    tree_lines.append(f"{prefix}    │       ▼")
                    tree_lines.append(f"{prefix}    │   🔴 deposit_amount")
                    tree_lines.append(f"{prefix}    │       │")
                    tree_lines.append(f"{prefix}    │       ▼")
                    tree_lines.append(f"{prefix}    │   🔴 execute_deposit → [Fim]")
                    tree_lines.append(f"{prefix}    │")
                    tree_lines.append(f"{prefix}    └── outcome: BALANCE_CALCULATED → [Fim]")
        
        def add_new_account_flow(prefix: str):
            account_type_status = get_step_status("account_type")
            tree_lines.append(f"{prefix}{account_type_status} account_type")
            tree_lines.append(f"{prefix}    │")
            tree_lines.append(f"{prefix}    ▼")
            create_status = get_step_status("create_account")
            tree_lines.append(f"{prefix}{create_status} create_account (action: _create_account)")
            tree_lines.append(f"{prefix}    │")
            tree_lines.append(f"{prefix}    ▼")
            add_action_flow("ask_action", prefix)
        
        build_flow()
        
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
        return ExecutionSummary(
            tree=self._generate_dependency_tree_ascii()
        )
