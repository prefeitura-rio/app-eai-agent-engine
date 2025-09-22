from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Union, Type
from pydantic import BaseModel, Field, ConfigDict

class StepInfo(BaseModel):
    """
    Defines a single step in the service flow.
    Simplified: Actions control the flow, no more complex conditions!
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., description="Unique name for the step, supporting dot notation for hierarchy (e.g., 'user_info.address').")
    description: str = Field("", description="Instruction for the AI agent on what to ask the user.")
    payload_schema: Union[Dict[str, Any], Type[BaseModel]] = Field({}, description="JSON Schema dict OR Pydantic model class defining the expected payload structure.")
    substeps: List['StepInfo'] = Field([], description="List of nested steps to create a hierarchy.")
    
    # Simplified: Only basic dependencies, actions control the rest!
    depends_on: List[str] = Field([], description="List of step names that must be completed before this step can be activated.")
    required: bool = Field(True, description="Indicates if the step is mandatory.")
    action: Optional[Callable[[Dict[str, Any]], 'ExecutionResult']] = Field(None, description="A callable method that executes the step's business logic and controls flow.")
    
    # Lifecycle management - determines when step data should be reset
    persistence_level: str = Field("permanent", description="Data persistence level: 'permanent' (never reset), 'session' (reset on session end), 'operation' (reset after each complete operation), 'transient' (reset immediately after use)")
    
    # Removed: condition (actions decide), is_end (actions decide)
    
    def get_json_schema(self) -> Dict[str, Any]:
        """
        V3: Gets the JSON Schema for this step, handling both dict and Pydantic model formats.
        
        Returns:
            JSON Schema dict that can be sent to the LLM agent
        """
        if isinstance(self.payload_schema, dict):
            # V2 compatibility: already a JSON Schema dict
            return self.payload_schema
        elif hasattr(self.payload_schema, 'model_json_schema') and callable(self.payload_schema):
            # V3: Pydantic model class - extract the schema
            return self.payload_schema.model_json_schema()
        else:
            # Fallback: empty schema
            return {}
    
    def validate_payload(self, payload: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        V3: Validates payload data using the appropriate method.
        
        Args:
            payload: Raw payload data to validate
            
        Returns:
            tuple[is_valid, error_message, validated_data]
        """
        try:
            if isinstance(self.payload_schema, dict):
                # V2 compatibility: basic validation (could be enhanced with jsonschema lib)
                return True, None, payload
            elif hasattr(self.payload_schema, 'model_validate') and callable(self.payload_schema):
                # V3: Pydantic model validation
                validated = self.payload_schema.model_validate(payload)
                return True, None, validated.model_dump()
            else:
                # No validation available
                return True, None, payload
        except Exception as e:
            return False, str(e), None


class ServiceDefinition(BaseModel):
    """
    The immutable blueprint of a service.
    """
    service_name: str = Field(..., description="Unique string identifier for the service (e.g., 'iptu_payment').")
    description: str = Field(..., description="General description of what the service does.")
    steps: List[StepInfo] = Field(..., description="The list of top-level steps for the service.")

class ExecutionResult(BaseModel):
    """
    V3: Enhanced execution result with improved error handling and recovery guidance.
    """
    success: bool
    outcome: str = Field(..., description="Semantic outcome of the action (e.g., 'DEBTS_FOUND', 'USER_NOT_FOUND').")
    updated_data: Dict[str, Any] = Field({}, description="Data to be merged into the ServiceState.")
    
    # V3: Enhanced error handling
    error_message: Optional[str] = Field(None, description="Human-readable error message that helps the agent understand what went wrong.")
    error_code: Optional[str] = Field(None, description="Machine-readable error code for programmatic handling.")
    valid_choices: Optional[List[str]] = Field(None, description="When validation fails, provide valid options to guide the agent.")
    
    # Actions control the flow
    next_steps: List[str] = Field([], description="List of step names that should be available next. Action decides the flow!")
    is_complete: bool = Field(False, description="If true, marks the service as completed. Action decides when to end!")
    completion_message: Optional[str] = Field(None, description="Message to display when service is complete.")
    
    @classmethod
    def success_result(
        cls,
        outcome: str,
        updated_data: Optional[Dict[str, Any]] = None,
        next_steps: Optional[List[str]] = None,
        is_complete: bool = False,
        completion_message: Optional[str] = None
    ) -> 'ExecutionResult':
        """V3: Helper method to create successful execution results."""
        return cls(
            success=True,
            outcome=outcome,
            updated_data=updated_data or {},
            next_steps=next_steps or [],
            is_complete=is_complete,
            completion_message=completion_message,
            error_message=None,
            error_code=None,
            valid_choices=None
        )
    
    @classmethod
    def validation_error(
        cls,
        error_message: str,
        valid_choices: Optional[List[str]] = None,
        error_code: str = "VALIDATION_ERROR",
        retry_step: Optional[str] = None
    ) -> 'ExecutionResult':
        """V3: Helper method to create validation error results with recovery guidance."""
        return cls(
            success=False,
            outcome="VALIDATION_ERROR",
            error_message=error_message,
            error_code=error_code,
            valid_choices=valid_choices,
            next_steps=[retry_step] if retry_step else [],
            updated_data={},
            is_complete=False,
            completion_message=None
        )

class NextStepInfo(BaseModel):
    """
    Information about the next step(s) that require user input.
    Can be nested to represent a hierarchy.
    """
    step_name: str = Field(..., description="The name of the step or parent group awaiting data.")
    description: str = Field(..., description="The consolidated instruction for the agent.")
    payload_schema: Dict[str, Any] = Field(..., description="The consolidated JSON Schema for the required data.")
    substeps: List[NextStepInfo] = Field([], description="A list of child steps, if this is a parent group.")

class ExecutionSummary(BaseModel):
    """
    Provides a summary of the execution progress.
    """
    tree: str = Field(..., description="A text representation of the service's dependency graph and its current state.")

class AgentResponse(BaseModel):
    """
    The comprehensive response object sent to the AI agent after each turn.
    """
    service_name: str
    status: str = Field(..., description="The overall status of the flow ('IN_PROGRESS', 'COMPLETED', 'FAILED').")
    error_message: Optional[str] = None
    current_data: Dict[str, Any] = Field(..., description="The complete, current ServiceState object.")
    next_step_info: Optional[NextStepInfo] = Field(None, description="Information about the next step, if status is 'IN_PROGRESS'.")
    execution_summary: Optional[ExecutionSummary] = None
