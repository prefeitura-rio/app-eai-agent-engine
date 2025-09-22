from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

class StepInfo(BaseModel):
    """
    Defines a single step in the service flow.
    """
    name: str = Field(..., description="Unique name for the step, supporting dot notation for hierarchy (e.g., 'user_info.address').")
    description: str = Field(..., description="Instruction for the AI agent on what to ask the user. Can contain state variables like '{user.name}'.")
    payload_schema: Dict[str, Any] = Field({}, description="JSON Schema defining the expected payload for this step.")
    substeps: List[StepInfo] = Field([], description="List of nested steps to create a hierarchy.")
    depends_on: List[str] = Field([], description="List of step names that must be completed before this step can be activated.")
    condition: Optional[str] = Field(None, description='Logical expression to be evaluated against the service state (e.g., \'search_debts.outcome == "DEBTS_FOUND"\').')
    is_end: bool = Field(False, description="If true, marks this step as a successful end point of the flow.")
    required: bool = Field(True, description="Indicates if the step is mandatory.")
    action: Optional[str] = Field(None, description="Reference to a function/method that executes the step's business logic.")

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

class NextStepInfo(BaseModel):
    """
    Information about the next step that requires user input.
    """
    step_name: str = Field(..., description="The name of the step awaiting data.")
    description: str = Field(..., description="The instruction for the agent, from StepInfo.description.")
    payload_schema: Dict[str, Any] = Field(..., description="The JSON Schema for the required data input.")

class ExecutionSummary(BaseModel):
    """
    Provides a summary of the execution progress.
    """
    completed_data_schema: Dict[str, Any] = Field(..., description="A consolidated JSON Schema of all data collected so far.")
    dependency_tree_ascii: str = Field(..., description="A text representation of the service's dependency graph and its current state.")

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
