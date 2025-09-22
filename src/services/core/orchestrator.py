from typing import Any, Dict, List, Optional

from src.services.core.actions import get_action
from src.services.core.evaluator import ConditionEvaluator
from src.services.core.response_generator import ResponseGenerator
from src.services.core.state import ServiceState
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
        Finds all next valid steps, prioritizing parallel data collection steps.
        If no data collection steps are found, it returns the next single action/end step.
        """
        
        def is_step_valid(step: StepInfo) -> bool:
            return (
                state.get(f"_internal.completed_steps.{step.name}", service_state_data) is not True
                and all(
                    state.get(f"_internal.completed_steps.{dep}", service_state_data) is True
                    for dep in step.depends_on
                )
                and (not step.condition or self.evaluator.evaluate(step.condition, service_state_data.get("data", {})))
            )

        # First, find all possible parallel data steps
        pending_data_steps = []
        
        def find_data_steps(steps: List[StepInfo]):
            # Find valid steps at the current level
            valid_steps_at_level = [s for s in steps if is_step_valid(s)]
            
            # If any valid step at this level is a data request, collect it
            level_data_steps = [s for s in valid_steps_at_level if not s.action and s.payload_schema]
            if level_data_steps:
                pending_data_steps.extend(level_data_steps)

            # If we found data steps, we don't need to go deeper or check for actions yet
            if not pending_data_steps:
                for step in valid_steps_at_level:
                    if step.substeps:
                        find_data_steps(step.substeps)

        find_data_steps(self.service_def.steps)
        if pending_data_steps:
            return pending_data_steps

        # If no data steps are pending, find the single next actionable step
        def find_action_step(steps: List[StepInfo]) -> Optional[StepInfo]:
            for step in steps:
                if not is_step_valid(step):
                    continue
                if step.substeps:
                    found = find_action_step(step.substeps)
                    if found:
                        return found
                # If it's a leaf (action or end step), return it
                if not step.substeps or step.action or step.is_end:
                    return step
            return None

        action_step = find_action_step(self.service_def.steps)
        return [action_step] if action_step else []

    def execute_turn(
        self, user_id: str, payload: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        Executes a single turn of the conversation.
        """
        state_manager = ServiceState(user_id)
        service_state = state_manager.get_service_state(self.service_def.service_name)
        error_message = None

        if payload:
            pending_step_names = state_manager.get("_internal.pending_steps", service_state) or []
            if pending_step_names:
                for step_name, value in payload.items():
                    if step_name in pending_step_names:
                        step_to_update = self._find_step(step_name)
                        if step_to_update:
                            # Construct the full path for the data, e.g., data.user_info.name
                            # The value from the payload is the raw value (e.g., "John Doe")
                            # The key in the state should be the last part of the step name
                            parent_key = step_name.rsplit('.', 1)[0]
                            data_key = step_name.split('.')[-1]
                            
                            state_manager.set(f"data.{parent_key}.{data_key}", value, service_state)
                            state_manager.set(f"_internal.completed_steps.{step_name}", True, service_state)
                            self._check_and_complete_parent(step_to_update, state_manager, service_state)

                state_manager.set("_internal.pending_steps", None, service_state)

        # Main execution loop
        while True:
            next_steps = self._find_next_steps(state_manager, service_state)

            if not next_steps:
                break

            # If there are data steps, we need user input
            if not next_steps[0].action and not next_steps[0].is_end:
                state_manager.set("_internal.pending_steps", [s.name for s in next_steps], service_state)
                break

            # Handle single action/end step
            next_step = next_steps[0]
            if next_step.action:
                try:
                    result = get_action(next_step.action)(service_state)
                    state_manager.merge_data(result.updated_data, service_state)
                    state_manager.set(f"_internal.outcomes.{next_step.name}", result.outcome, service_state)
                    if not result.success:
                        error_message = result.error_message or f"Action '{next_step.action}' failed."
                        break
                    state_manager.set(f"_internal.completed_steps.{next_step.name}", True, service_state)
                    self._check_and_complete_parent(next_step, state_manager, service_state)
                except Exception as e:
                    error_message = f"Unexpected error in action '{next_step.action}': {e}"
                    break
            elif next_step.is_end:
                state_manager.set(f"_internal.completed_steps.{next_step.name}", True, service_state)
                self._check_and_complete_parent(next_step, state_manager, service_state)
        
        state_manager.save()

        response_gen = ResponseGenerator(self.service_def, state_manager, service_state)
        next_step_info = response_gen.get_next_step_info()
        
        status = "IN_PROGRESS"
        final_output = None
        if error_message:
            status = "FAILED"
        elif not next_step_info:
            def is_end_step_complete(steps: List[StepInfo]) -> bool:
                for step in steps:
                    if step.is_end and state_manager.get(f"_internal.completed_steps.{step.name}", service_state):
                        return True
                    if step.substeps and is_end_step_complete(step.substeps):
                        return True
                return False

            if is_end_step_complete(self.service_def.steps):
                status = "COMPLETED"
                final_output = service_state.get("data", {})
            else:
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