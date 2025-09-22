from typing import Any, Dict, List, Optional

from src.services.core.evaluator import ConditionEvaluator
from src.services.core.response_generator import ResponseGenerator
from src.services.core.state import ServiceState
from src.services.schema.models import (
    AgentResponse,
    ExecutionResult,
    ServiceDefinition,
    StepInfo,
)


class ServiceOrchestrator:
    """
    The brain of the framework, orchestrating the execution of a service.
    """

    def __init__(self, service_definition: ServiceDefinition):
        self.service_def = service_definition
        self.evaluator = ConditionEvaluator()

    def _find_step(self, step_name: str) -> Optional[StepInfo]:
        """Finds a step by its name in the service definition tree."""

        def search(steps: List[StepInfo]) -> Optional[StepInfo]:
            for step in steps:
                if step.name == step_name:
                    return step
                if step.substeps:
                    found = search(step.substeps)
                    if found:
                        return found
            return None

        return search(self.service_def.steps)

    def _is_dependency_met(
        self, step_name: str, state_manager: ServiceState, service_state: Dict[str, Any]
    ) -> bool:
        """
        Recursively checks if a step or a container's required children are complete.
        """
        # First, check the state directly
        completion_status = state_manager.get(
            f"_internal.completed_steps.{step_name}", service_state
        )
        if completion_status is True:
            return True

        # If not explicitly complete, check if it's a container whose children are complete
        dep_step = self._find_step(step_name)
        if dep_step and dep_step.substeps:
            required_substeps = [s for s in dep_step.substeps if s.required]
            if not required_substeps:
                return True  # A container with no required children is implicitly complete for dependency purposes

            # Recursively check if all required children are met
            return all(
                self._is_dependency_met(s.name, state_manager, service_state)
                for s in required_substeps
            )

        return False

    def _find_next_steps(
        self, state_manager: ServiceState, service_state_data: Dict[str, Any]
    ) -> List[StepInfo]:
        """
        Finds next valid steps. Simplified: actions control the flow!
        """
        # Check if we have action-driven next steps from previous actions
        action_next_steps = state_manager.get("_internal.action_next_steps", service_state_data)
        if action_next_steps:
            # Find steps by name from action decisions
            available_steps = []
            for step_name in action_next_steps:
                step = self._find_step(step_name)
                if step and self._is_step_valid(step, state_manager, service_state_data):
                    available_steps.append(step)
            
            if available_steps:
                # Clear action next steps after using them
                state_manager.set("_internal.action_next_steps", None, service_state_data)
                return available_steps

        # Default behavior: find data collection steps first, then actions
        def is_step_valid(step: StepInfo) -> bool:
            return self._is_step_valid(step, state_manager, service_state_data)

        # Find data collection steps
        data_steps = []
        action_steps = []
        
        def find_steps(steps: List[StepInfo]):
            for step in steps:
                is_step_complete = state_manager.get(f"_internal.completed_steps.{step.name}", service_state_data) is True
                
                if not is_step_valid(step):
                    # Only process substeps if the parent step is not complete
                    if step.substeps and not is_step_complete:
                        find_steps(step.substeps)
                    continue
                
                if step.action:
                    action_steps.append(step)
                elif step.payload_schema:
                    data_steps.append(step)
                
                # Only process substeps if the parent step is not complete
                if step.substeps and not is_step_complete:
                    find_steps(step.substeps)

        find_steps(self.service_def.steps)
        
        # Prioritize actions first (they control the flow), then data collection
        if action_steps:
            return action_steps[:1]  # Execute one action at a time
        elif data_steps:
            return data_steps
            
        return []

    def _is_step_valid(self, step: StepInfo, state_manager: ServiceState, service_state_data: Dict[str, Any]) -> bool:
        """Check if a step is valid (not completed and dependencies met)."""
        is_self_complete = (
            state_manager.get(f"_internal.completed_steps.{step.name}", service_state_data) is True
        )
        if is_self_complete:
            return False

        all_deps_met = all(
            self._is_dependency_met(dep_name, state_manager, service_state_data)
            for dep_name in step.depends_on
        )
        return all_deps_met

    def _hydrate_state(
        self, state_manager: ServiceState, service_state: Dict[str, Any]
    ):
        """
        Scans the service definition and automatically completes any steps
        for which data already exists in the state.
        """

        def traverse_and_hydrate(steps: List[StepInfo]):
            for step in steps:
                is_complete = (
                    state_manager.get(
                        f"_internal.completed_steps.{step.name}", service_state
                    )
                    is True
                )
                if is_complete:
                    continue

                # Check if it's a data collection step
                if not step.action and step.payload_schema:
                    # Check if all required data points for this step exist in the state
                    parent_key = (
                        step.name.rsplit(".", 1)[0] if "." in step.name else None
                    )
                    data_key = step.name.split(".")[-1]

                    if (
                        parent_key
                        and state_manager.get(
                            f"data.{parent_key}.{data_key}", service_state
                        )
                        is not None
                    ):
                        state_manager.set(
                            f"_internal.completed_steps.{step.name}",
                            True,
                            service_state,
                        )
                    elif (
                        not parent_key
                        and state_manager.get(f"data.{data_key}", service_state)
                        is not None
                    ):
                        state_manager.set(
                            f"_internal.completed_steps.{step.name}",
                            True,
                            service_state,
                        )

                if step.substeps:
                    # Process substeps first
                    traverse_and_hydrate(step.substeps)
                    
                    # After processing substeps, check if this container step should be marked complete
                    if not step.action and not step.payload_schema and step.substeps:
                        required_substeps = [s for s in step.substeps if s.required]
                        if required_substeps and all(
                            self._is_dependency_met(s.name, state_manager, service_state)
                            for s in required_substeps
                        ):
                            state_manager.set(
                                f"_internal.completed_steps.{step.name}",
                                True,
                                service_state,
                            )

        traverse_and_hydrate(self.service_def.steps)

    def execute_turn(
        self, user_id: str, payload: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        Executes a single turn of the conversation.
        """
        state_manager = ServiceState(user_id)
        service_state = state_manager.get_service_state(
            self.service_def.service_name
        )
        error_message = None

        # If the service was complete and a new payload is provided, reset internal state.
        is_completed = state_manager.get("_internal.service_completed", service_state)
        if is_completed and payload:
            # Preserve data, reset progress
            data = service_state.get("data", {})
            service_state.clear()
            service_state["data"] = data

        if payload:
            pending_step_names = (
                state_manager.get("_internal.pending_steps", service_state) or []
            )
            
            # Process payload data regardless of pending_steps
            # This allows filling data even when no specific steps are pending
            for step_name, value in payload.items():
                # Check if this step exists in the service definition
                step_exists = self._find_step(step_name) is not None
                
                if step_exists or step_name in pending_step_names:
                    # Handle dotted notation (e.g., "user_info.name")
                    if "." in step_name:
                        parent_key = step_name.rsplit(".", 1)[0]
                        data_key = step_name.split(".")[-1]
                        state_manager.set(
                            f"data.{parent_key}.{data_key}", value, service_state
                        )
                    else:
                        # Handle top-level step
                        state_manager.set(f"data.{step_name}", value, service_state)
                    
                    # Mark step as completed
                    state_manager.set(
                        f"_internal.completed_steps.{step_name}",
                        True,
                        service_state,
                    )

            state_manager.set("_internal.pending_steps", None, service_state)

        # Hydrate state from existing data before running the loop
        self._hydrate_state(state_manager, service_state)
        
        # Hydrate again after processing payload to ensure substeps are marked complete
        if payload:
            self._hydrate_state(state_manager, service_state)

        # Main execution loop
        while True:
            next_steps = self._find_next_steps(state_manager, service_state)

            if not next_steps:
                break

            if not next_steps[0].action:
                state_manager.set(
                    "_internal.pending_steps",
                    [s.name for s in next_steps],
                    service_state,
                )
                break

            next_step = next_steps[0]
            if next_step.action:
                try:
                    result = next_step.action(service_state)
                    
                    # Merge updated data into the data section
                    if not service_state.get("data"):
                        service_state["data"] = {}
                    state_manager.merge_data(result.updated_data, service_state["data"])
                    
                    # Store action outcome
                    state_manager.set(
                        f"_internal.outcomes.{next_step.name}",
                        result.outcome,
                        service_state,
                    )
                    
                    if not result.success:
                        error_message = (
                            result.error_message
                            or f"Action '{next_step.action.__name__}' failed."
                        )
                        break
                    
                    # NEW: Action controls the flow!
                    if result.next_steps:
                        state_manager.set(
                            "_internal.action_next_steps",
                            result.next_steps,
                            service_state,
                        )
                    
                    # NEW: Action decides when service is complete
                    if result.is_complete:
                        state_manager.set(
                            "_internal.service_completed",
                            True,
                            service_state,
                        )
                        if result.completion_message:
                            state_manager.set(
                                "_internal.completion_message", 
                                result.completion_message,
                                service_state,
                            )
                    
                    state_manager.set(
                        f"_internal.completed_steps.{next_step.name}",
                        True,
                        service_state,
                    )
                except Exception as e:
                    error_message = f"Unexpected error in action '{next_step.action.__name__}': {e}"
                    break

        state_manager.save()

        response_gen = ResponseGenerator(
            self.service_def, state_manager, service_state
        )
        next_step_info = response_gen.get_next_step_info()

        status = "IN_PROGRESS"
        final_output = None
        
        if error_message:
            status = "FAILED"
        elif state_manager.get("_internal.service_completed", service_state):
            # NEW: Action decided the service is complete!
            status = "COMPLETED"
            final_output = service_state.get("data", {})
            for key, value in service_state.items():
                if key not in ["data", "_internal"]:
                    final_output[key] = value
        elif not next_step_info:
            # No next steps and no action-driven completion - check if we're stuck
            next_steps = self._find_next_steps(state_manager, service_state)
            if not next_steps:
                status = "FAILED"
                error_message = "Service flow ended without completion or available next steps."
        return AgentResponse(
            service_name=self.service_def.service_name,
            status=status,
            error_message=error_message,
            current_data=service_state,
            next_step_info=next_step_info,
            execution_summary=response_gen.get_execution_summary(),
            final_output=final_output,
        )
