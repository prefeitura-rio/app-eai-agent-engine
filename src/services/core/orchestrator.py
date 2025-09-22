from typing import Any, Dict, List, Optional, Tuple

from src.services.core.actions import get_action
from src.services.core.evaluator import ConditionEvaluator
from src.services.core.state import ServiceState
from src.services.core.response_generator import ResponseGenerator
from src.services.schema.models import (AgentResponse, ExecutionResult,
                                        ServiceDefinition, StepInfo)


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

    def _find_next_step(
        self, state: ServiceState, service_state_data: Dict[str, Any]
    ) -> Optional[StepInfo]:
        """
        Finds the next valid leaf step (action or data request) using a DFS approach.
        """
        def is_step_valid(step: StepInfo) -> bool:
            if state.get(f"_internal.completed_steps.{step.name}", service_state_data) is True:
                return False

            if not all(
                state.get(f"_internal.completed_steps.{dep}", service_state_data) is True
                for dep in step.depends_on
            ):
                return False

            if step.condition and not self.evaluator.evaluate(step.condition, service_state_data):
                return False
            
            return True

        def search(steps: List[StepInfo]) -> Optional[StepInfo]:
            for step in steps:
                if not is_step_valid(step):
                    continue

                if step.substeps:
                    found_in_substeps = search(step.substeps)
                    if found_in_substeps:
                        return found_in_substeps

                is_leaf = not step.substeps or step.action or step.payload_schema
                if is_leaf:
                    return step

            return None

        return search(self.service_def.steps)

    def _find_parent(self, child_name: str) -> Optional[StepInfo]:
        """Finds the parent of a step by the child's name."""
        
        def search(steps: List[StepInfo], parent: Optional[StepInfo]) -> Optional[StepInfo]:
            for step in steps:
                if step.name == child_name:
                    return parent
                if step.substeps:
                    found = search(step.substeps, step)
                    if found:
                        return found
            return None

        return search(self.service_def.steps, None)

    def _check_and_complete_parent(self, step: StepInfo, state_manager: ServiceState, service_state: Dict[str, Any]):
        """Checks if a completed step's parent container can also be marked as complete."""
        parent = self._find_parent(step.name)
        if not parent:
            return

        required_substeps = [s for s in parent.substeps if s.required]
        if not required_substeps:
            return

        all_required_done = all(
            state_manager.get(f"_internal.completed_steps.{s.name}", service_state) is True
            for s in required_substeps
        )

        if all_required_done and state_manager.get(f"_internal.completed_steps.{parent.name}", service_state) is not True:
            state_manager.set(f"_internal.completed_steps.{parent.name}", True, service_state)
            self._check_and_complete_parent(parent, state_manager, service_state)

    def _find_next_steps(
        self, state: ServiceState, service_state_data: Dict[str, Any]
    ) -> List[StepInfo]:
        """
        Finds all valid, parallel steps that require user input.
        This allows grouping questions (e.g., asking for name and email at once).
        """
        
        def is_step_valid(step: StepInfo) -> bool:
            # Simplified check for this specific logic
            return (
                state.get(f"_internal.completed_steps.{step.name}", service_state_data) is not True
                and all(
                    state.get(f"_internal.completed_steps.{dep}", service_state_data) is True
                    for dep in step.depends_on
                )
                and (not step.condition or self.evaluator.evaluate(step.condition, service_state_data))
            )

        def search(steps: List[StepInfo]) -> List[StepInfo]:
            pending_steps = []
            for step in steps:
                if not is_step_valid(step):
                    continue

                # If it's a container, search its children.
                if step.substeps:
                    found_in_substeps = search(step.substeps)
                    if found_in_substeps:
                        # If we find pending steps in a container, we don't need to look further at this level
                        return found_in_substeps

                # If it's a leaf that needs data, add it to our list.
                is_data_request = not step.action and step.payload_schema
                if is_data_request:
                    pending_steps.append(step)
            
            return pending_steps

        # We also need to find the first actionable step if no data steps are pending
        action_step = self._find_first_actionable_step(state, service_state_data)
        
        # Prioritize data collection
        data_steps = search(self.service_def.steps)
        if data_steps:
            return data_steps
        
        return [action_step] if action_step else []

    def _find_first_actionable_step(
        self, state: ServiceState, service_state_data: Dict[str, Any]
    ) -> Optional[StepInfo]:
        """Finds the very first valid step that is a leaf node (action or end step)."""
        # Re-using the original logic for finding a single step.
        return self._find_next_step(state, service_state_data)

    def execute_turn(
        self, user_id: str, payload: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        Executes a single turn of the conversation.
        """
        state_manager = ServiceState(user_id)
        service_state = state_manager.get_service_state(self.service_def.service_name)
        error_message = None

        # Process incoming payload
        if payload:
            # When a payload is received, we assume it satisfies all pending steps
            # that were sent to the user in the last turn.
            pending_steps_names = state_manager.get("_internal.pending_steps", service_state) or []
            if pending_steps_names:
                state_manager.merge_data(payload, service_state)
                for step_name in pending_steps_names:
                    state_manager.set(f"_internal.completed_steps.{step_name}", True, service_state)
                    completed_step = self._find_step(step_name)
                    if completed_step:
                        self._check_and_complete_parent(completed_step, state_manager, service_state)
                state_manager.set("_internal.pending_steps", None, service_state)

        # Main execution loop
        while True:
            next_steps = self._find_next_steps(state_manager, service_state)

            if not next_steps:
                break

            next_step = next_steps[0] # For now, we handle one action at a time

            if next_step.action:
                try:
                    action_func = get_action(next_step.action)
                    result: ExecutionResult = action_func(service_state)
                    state_manager.merge_data(result.updated_data, service_state)
                    state_manager.set(f"_internal.outcomes.{next_step.name}", result.outcome, service_state)
                    
                    if not result.success:
                        error_message = result.error_message or f"Action '{next_step.action}' failed."
                        break 
                    
                    state_manager.set(f"_internal.completed_steps.{next_step.name}", True, service_state)
                    self._check_and_complete_parent(next_step, state_manager, service_state)
                except Exception as e:
                    error_message = f"An unexpected error occurred during action '{next_step.action}': {e}"
                    break
            elif next_step.is_end:
                state_manager.set(f"_internal.completed_steps.{next_step.name}", True, service_state)
                self._check_and_complete_parent(next_step, state_manager, service_state)
                continue
            else: # Step(s) require user input
                state_manager.set("_internal.pending_steps", [s.name for s in next_steps], service_state)
                break
        
        state_manager.save()

        # Generate the rich response
        response_gen = ResponseGenerator(self.service_def, state_manager, service_state)
        next_step_info = response_gen.get_next_step_info()
        
        status = "IN_PROGRESS"
        final_output = None
        if error_message:
            status = "FAILED"
        elif not next_step_info:
            def find_end_step_completed(steps: List[StepInfo]) -> bool:
                for step in steps:
                    if step.is_end and state_manager.get(f"_internal.completed_steps.{step.name}", service_state):
                        return True
                    if step.substeps and find_end_step_completed(step.substeps):
                        return True
                return False

            if find_end_step_completed(self.service_def.steps):
                status = "COMPLETED"
                final_output = {k: v for k, v in service_state.items() if not k.startswith('_')}
            elif self._find_first_actionable_step(state_manager, service_state) is None:
                status = "FAILED"
                error_message = "Service flow ended without reaching a designated end step."


        return AgentResponse(
            service_name=self.service_def.service_name,
            status=status,
            error_message=error_message,
            current_data=service_state,
            next_step_info=next_step_info,
            execution_summary=response_gen.get_execution_summary(),
            final_output=final_output,
        )
