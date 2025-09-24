from pydantic import BaseModel
from typing import Any, Dict, Literal, Optional, List


class ServiceRequest(BaseModel):
    """
    Estrutura da requisição para um serviço.
    """

    service_name: str
    user_id: str
    payload: Dict[str, Any] = {}


class ServiceState(BaseModel):
    """
    Estado completo de um serviço - onde ficam guardadas todas as informações.
    """

    user_id: str
    service_name: str
    status: Literal["progress", "completed", "error"] = "progress"
    data: Dict[str, Any] = {}
    pending_steps: List[str] = []
    completed_steps: Dict[str, bool] = {}

    class Config:
        arbitrary_types_allowed = True


class AgentResponse(BaseModel):
    """
    Resposta enviada para o agente a cada step.
    """

    service_name: str
    status: Literal["progress", "completed", "error"] = "progress"
    error_message: Optional[str] = None
    description: str = ""
    payload_schema: Optional[Dict[str, Any]] = None
    data: Dict[str, Any] = {}


class ExecutionResult(BaseModel):
    """
    Resultado da execução de um workflow.
    """

    state: ServiceState
    response: AgentResponse
