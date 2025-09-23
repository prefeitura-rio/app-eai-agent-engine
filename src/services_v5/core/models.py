from pydantic import BaseModel
from typing import Any, Dict, Literal, Optional


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
    status: Literal["running", "completed", "error"] = "running"
    data: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True


class AgentResponse(BaseModel):
    """
    Resposta enviada para o agente a cada step.
    """

    service_name: str
    status: str
    error_message: Optional[str] = None
    description: str = ""
    payload_schema: Optional[Dict[str, Any]] = None
    data: Dict[str, Any] = {}
