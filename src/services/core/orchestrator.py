from typing import Any, Dict, List, Optional

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

    def _get_active_steps(
        self, state_manager: ServiceState, service_state_data: Dict[str, Any]
    ) -> List[StepInfo]:
        """
        V3: Calculates which steps are currently active (valid for processing).
        This is the core of the Strict Graph Executor - only active steps can be processed.

        Returns:
            List of StepInfo objects that are currently valid for data collection or action execution
        """
        active_steps = []

        def check_step_activity(steps: List[StepInfo]):
            for step in steps:
                # Skip if step is already completed
                is_completed = (
                    state_manager.get(
                        f"_internal.completed_steps.{step.name}", service_state_data
                    )
                    is True
                )

                if is_completed:
                    # Process substeps even if parent is complete (for hierarchical validation)
                    if step.substeps:
                        check_step_activity(step.substeps)
                    continue

                # Check if dependencies are met
                dependencies_met = all(
                    self._is_dependency_met(dep_name, state_manager, service_state_data)
                    for dep_name in step.depends_on
                )

                if dependencies_met:
                    # This step is active
                    active_steps.append(step)

                # Always check substeps for hierarchical structures
                if step.substeps:
                    check_step_activity(step.substeps)

        check_step_activity(self.service_def.steps)
        return active_steps

    def _find_next_steps(
        self, state_manager: ServiceState, service_state_data: Dict[str, Any]
    ) -> List[StepInfo]:
        """
        Finds next valid steps. Simplified: actions control the flow!
        """
        # Check if we have action-driven next steps from previous actions
        action_next_steps = state_manager.get(
            "_internal.action_next_steps", service_state_data
        )
        if action_next_steps:
            # Find steps by name from action decisions
            available_steps = []
            for step_name in action_next_steps:
                step = self._find_step(step_name)
                if step and self._is_step_valid(
                    step, state_manager, service_state_data
                ):
                    available_steps.append(step)

            if available_steps:
                # Clear action next steps after using them
                state_manager.set(
                    "_internal.action_next_steps", None, service_state_data
                )
                return available_steps

        # Default behavior: find data collection steps first, then actions
        def is_step_valid(step: StepInfo) -> bool:
            return self._is_step_valid(step, state_manager, service_state_data)

        # Find data collection steps
        data_steps = []
        action_steps = []

        def find_steps(steps: List[StepInfo]):
            for step in steps:
                is_step_complete = (
                    state_manager.get(
                        f"_internal.completed_steps.{step.name}", service_state_data
                    )
                    is True
                )

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

    def _is_step_valid(
        self,
        step: StepInfo,
        state_manager: ServiceState,
        service_state_data: Dict[str, Any],
    ) -> bool:
        """Check if a step is valid (not completed and dependencies met)."""
        is_self_complete = (
            state_manager.get(
                f"_internal.completed_steps.{step.name}", service_state_data
            )
            is True
        )

        # Special case: If step has an action, check if the action has been executed (has outcome)
        if step.action:
            action_outcome = state_manager.get(
                f"_internal.outcomes.{step.name}", service_state_data
            )
            # If outcome exists and is not None (i.e., not reset), action was executed
            if action_outcome is not None:
                return False  # Action already executed, step is truly complete
            # If action not executed or was reset (None), continue to check dependencies
        elif is_self_complete:
            return False  # Data-only step that's complete

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
                            self._is_dependency_met(
                                s.name, state_manager, service_state
                            )
                            for s in required_substeps
                        ):
                            state_manager.set(
                                f"_internal.completed_steps.{step.name}",
                                True,
                                service_state,
                            )

        traverse_and_hydrate(self.service_def.steps)

    def _apply_persistence_resets(
        self, state_manager: ServiceState, service_state: Dict[str, Any]
    ):
        """
        Applies data resets based on persistence_level of completed steps.
        This is called when a service completes an operation.
        """

        def reset_step_data(steps: List[StepInfo], current_path: str = ""):
            for step in steps:
                # Build the full path for this step
                step_path = f"{current_path}.{step.name}" if current_path else step.name

                # Check if this step was completed
                is_completed = (
                    state_manager.get(
                        f"_internal.completed_steps.{step.name}", service_state
                    )
                    is True
                )

                if is_completed and hasattr(step, "persistence_level"):
                    if step.persistence_level == "operation":
                        # Reset data for this step after operation completes
                        # Only reset if the step actually has payload_schema (is a data collection step)
                        if step.payload_schema:
                            if "." in step_path:
                                # Handle nested data (e.g., user_info.name)
                                parent_path = step_path.rsplit(".", 1)[0]
                                field_name = step_path.split(".")[-1]
                                parent_data = state_manager.get(
                                    f"data.{parent_path}", service_state
                                )
                                if (
                                    isinstance(parent_data, dict)
                                    and field_name in parent_data
                                ):
                                    del parent_data[field_name]
                            else:
                                # Handle top-level data - only delete the specific field from payload_schema
                                data = service_state.get("data", {})
                                # Look at the payload schema to see which fields to reset
                                schema = step.get_json_schema()
                                if schema.get("properties"):
                                    for field_name in schema["properties"].keys():
                                        if field_name in data:
                                            del data[field_name]

                        # Reset completion status for operation-level steps
                        state_manager.set(
                            f"_internal.completed_steps.{step.name}",
                            None,
                            service_state,
                        )

                        # Reset action outcomes for operation-level steps with actions
                        if step.action:
                            state_manager.set(
                                f"_internal.outcomes.{step.name}",
                                None,
                                service_state,
                            )

                    elif step.persistence_level == "transient":
                        # Transient data is reset immediately after use
                        # (This would typically be handled right after step execution,
                        # but we include it here for completeness)
                        if "." in step_path:
                            parent_path = step_path.rsplit(".", 1)[0]
                            field_name = step_path.split(".")[-1]
                            parent_data = state_manager.get(
                                f"data.{parent_path}", service_state
                            )
                            if (
                                isinstance(parent_data, dict)
                                and field_name in parent_data
                            ):
                                del parent_data[field_name]
                        else:
                            data = service_state.get("data", {})
                            if step.name in data:
                                del data[step.name]

                # Recursively process substeps
                if step.substeps:
                    reset_step_data(step.substeps, step_path)

        reset_step_data(self.service_def.steps)

    def _execute_transition_loop(
        self, state_manager: ServiceState, service_state: Dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        V3: Executes actions in cascade until no more actions are available.
        This is the heart of the Strict Graph Executor's action execution.

        Returns:
            tuple[service_completed, error_message, complete_tree]
        """
        while True:
            # Get currently active steps
            active_steps = self._get_active_steps(state_manager, service_state)

            # Find action steps that are ready to execute
            action_steps = [step for step in active_steps if step.action]

            if not action_steps:
                # No more actions to execute - transition loop complete
                break

            # Execute the first available action
            next_action = action_steps[0]

            try:
                print(f"🎬 V3: Executing action '{next_action.name}'")
                result = next_action.action(service_state)

                # Merge updated data into the data section
                if not service_state.get("data"):
                    service_state["data"] = {}
                state_manager.merge_data(result.updated_data, service_state["data"])

                # Store action outcome
                state_manager.set(
                    f"_internal.outcomes.{next_action.name}",
                    result.outcome,
                    service_state,
                )

                if not result.success:
                    error_message = (
                        result.error_message
                        or f"Action '{next_action.action.__name__}' failed."
                    )
                    return False, error_message

                # Mark the action step as completed
                state_manager.set(
                    f"_internal.completed_steps.{next_action.name}",
                    True,
                    service_state,
                )

                # V3: Action controls the flow
                if result.next_steps:
                    state_manager.set(
                        "_internal.action_next_steps",
                        result.next_steps,
                        service_state,
                    )

                # V3: Action decides when service is complete
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
                    
                    # Clear pending steps when service completes
                    state_manager.set(
                        "_internal.pending_steps",
                        None,
                        service_state,
                    )

                    # Capture the complete execution tree BEFORE applying persistence resets
                    response_gen = ResponseGenerator(self.service_def, state_manager, service_state)
                    complete_tree = response_gen._generate_dependency_tree_ascii()

                    # Apply persistence-based resets when service completes
                    self._apply_persistence_resets(state_manager, service_state)

                    return True, None, complete_tree  # Service completed successfully

                # Continue the loop to check for more actions
                print(
                    f"✅ V3: Action '{next_action.name}' completed with outcome: {result.outcome}"
                )

            except Exception as e:
                error_message = (
                    f"Unexpected error in action '{next_action.action.__name__}': {e}"
                )
                return False, error_message, None

        # Transition loop completed without service completion
        return False, None, None

    def execute_turn(
        self, user_id: str, payload: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        V3: Executes a single turn using the Strict Graph Executor approach.

        This method implements the core V3 improvements:
        1. Strict step validation (only active steps are processed)
        2. Cascade action execution via transition loop
        3. Enhanced error handling and recovery
        """
        print(
            f"🚀 V3: Starting execute_turn for service '{self.service_def.service_name}'"
        )

        state_manager = ServiceState(user_id)
        service_state = state_manager.get_service_state(self.service_def.service_name)
        error_message = None
        complete_tree = None

        # 1. LOAD STATE: Handle service completion resets
        is_completed = state_manager.get("_internal.service_completed", service_state)
        if is_completed:
            print("🔄 V3: Service was completed, resetting for new operation")
            # Reset service completion flags to allow new operations
            state_manager.set("_internal.service_completed", None, service_state)
            state_manager.set("_internal.completion_message", None, service_state)
            state_manager.set("_internal.action_next_steps", None, service_state)
            state_manager.set("_internal.pending_steps", None, service_state)
            # Apply persistence-based resets for new operation
            self._apply_persistence_resets(state_manager, service_state)

        # 2. IDENTIFY ACTIVE NODES: Calculate which steps are currently valid
        if payload:
            print(f"📝 V3: Processing payload with {len(payload)} fields")
            active_steps = self._get_active_steps(state_manager, service_state)
            active_step_names = {step.name for step in active_steps}

            print(f"✅ V3: Active steps: {active_step_names}")

            # 3. PROCESS PAYLOAD (Only for Active Nodes): Strict validation
            processed_fields = []
            ignored_fields = []

            for step_name, value in payload.items():
                if step_name in active_step_names:
                    # Find the step for validation
                    step = self._find_step(step_name)
                    if step:
                        # V3: Validate payload using new method
                        # For dotted notation steps, extract the field name for validation
                        if "." in step_name:
                            field_name = step_name.split(".")[-1]
                            validation_payload = {field_name: value}
                        else:
                            validation_payload = {step_name: value}

                        is_valid, validation_error, validated_data = (
                            step.validate_payload(validation_payload)
                        )

                        if is_valid:
                            # Handle dotted notation (e.g., "user_info.name")
                            if "." in step_name:
                                parent_key = step_name.rsplit(".", 1)[0]
                                data_key = step_name.split(".")[-1]
                                state_manager.set(
                                    f"data.{parent_key}.{data_key}",
                                    value,
                                    service_state,
                                )
                            else:
                                # Handle top-level step
                                state_manager.set(
                                    f"data.{step_name}", value, service_state
                                )

                            # Mark step as completed
                            state_manager.set(
                                f"_internal.completed_steps.{step_name}",
                                True,
                                service_state,
                            )
                            processed_fields.append(step_name)
                            print(f"✅ V3: Processed field '{step_name}' = {value}")
                        else:
                            error_message = f"Validation error for '{step_name}': {validation_error}"
                            print(f"❌ V3: {error_message}")
                            break
                else:
                    ignored_fields.append(step_name)
                    print(f"🚫 V3: Ignored field '{step_name}' (not in active steps)")

            if ignored_fields:
                print(
                    f"⚠️  V3: Ignored {len(ignored_fields)} fields due to dependency requirements: {ignored_fields}"
                )

        # 4. UPDATE STATE AND EXECUTE ACTIONS (Transition Loop)
        if not error_message:
            # Hydrate state from existing data
            self._hydrate_state(state_manager, service_state)

            # Execute the transition loop (cascade action execution)
            print("🔄 V3: Starting transition loop")
            service_completed, loop_error, complete_tree = self._execute_transition_loop(
                state_manager, service_state
            )

            if loop_error:
                error_message = loop_error
            elif service_completed:
                print("🎉 V3: Service completed via transition loop")

        # 5. DETERMINE NEXT STEP: Only after transition loop is complete
        if not error_message and not state_manager.get(
            "_internal.service_completed", service_state
        ):
            # Calculate next pending steps for data collection
            next_steps = self._find_next_steps(state_manager, service_state)
            data_collection_steps = [
                step.name
                for step in next_steps
                if not step.action and step.payload_schema
            ]
            if data_collection_steps:
                state_manager.set(
                    "_internal.pending_steps", data_collection_steps, service_state
                )

        state_manager.save()

        response_gen = ResponseGenerator(self.service_def, state_manager, service_state)
        next_step_info = response_gen.get_next_step_info()

        status = "IN_PROGRESS"

        if error_message:
            status = "FAILED"
            print(f"❌ V3: Execution failed: {error_message}")
        elif state_manager.get("_internal.service_completed", service_state):
            status = "COMPLETED"
            print("🎉 V3: Service execution completed successfully")
        elif not next_step_info:
            # Check if we have any available steps
            active_steps = self._get_active_steps(state_manager, service_state)
            if not active_steps:
                status = "FAILED"
                error_message = (
                    "Service flow ended without completion or available next steps."
                )
                print(f"❌ V3: {error_message}")

        print(f"🏁 V3: Execution completed with status: {status}")

        # Use the complete tree if service was completed and we have it
        execution_summary = response_gen.get_execution_summary(complete_tree)

        return AgentResponse(
            service_name=self.service_def.service_name,
            status=status,
            error_message=error_message,
            current_data=service_state,
            next_step_info=next_step_info,
            execution_summary=execution_summary,
        )
