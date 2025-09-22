from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

class StepInfo(BaseModel):
    """
    Defines a single step in the service flow.
    Simplified: Actions control the flow, no more complex conditions!
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., description="Unique name for the step, supporting dot notation for hierarchy (e.g., 'user_info.address').")
    description: str = Field("", description="Instruction for the AI agent on what to ask the user. Can contain state variables like '{user.name}'.")
    payload_schema: Dict[str, Any] = Field({}, description="JSON Schema defining the expected payload for this step.")
    substeps: List['StepInfo'] = Field([], description="List of nested steps to create a hierarchy.")
    
    # Simplified: Only basic dependencies, actions control the rest!
    depends_on: List[str] = Field([], description="List of step names that must be completed before this step can be activated.")
    required: bool = Field(True, description="Indicates if the step is mandatory.")
    action: Optional[Callable[[Dict[str, Any]], 'ExecutionResult']] = Field(None, description="A callable method that executes the step's business logic and controls flow.")
    
    # Lifecycle management - determines when step data should be reset
    persistence_level: str = Field("permanent", description="Data persistence level: 'permanent' (never reset), 'session' (reset on session end), 'operation' (reset after each complete operation), 'transient' (reset immediately after use)")
    
    # Removed: condition (actions decide), is_end (actions decide)


class ServiceDefinition(BaseModel):
    """
    The immutable blueprint of a service.
    """
    service_name: str = Field(..., description="Unique string identifier for the service (e.g., 'iptu_payment').")
    description: str = Field(..., description="General description of what the service does.")
    steps: List[StepInfo] = Field(..., description="The list of top-level steps for the service.")

class ExecutionResult(BaseModel):
    """
    Internal return contract for every action executed by the Orchestrator.
    """
    success: bool
    outcome: str = Field(..., description="Semantic outcome of the action (e.g., 'DEBTS_FOUND', 'USER_NOT_FOUND').")
    updated_data: Dict[str, Any] = Field({}, description="Data to be merged into the ServiceState.")
    error_message: Optional[str] = None
    
    # New: Actions control the flow
    next_steps: List[str] = Field([], description="List of step names that should be available next. Action decides the flow!")
    is_complete: bool = Field(False, description="If true, marks the service as completed. Action decides when to end!")
    completion_message: Optional[str] = Field(None, description="Message to display when service is complete.")

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
    final_output: Optional[Dict[str, Any]] = Field(None, description="The final result data, if status is 'COMPLETED'.")
