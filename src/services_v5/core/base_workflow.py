from abc import ABC, abstractmethod
from typing import Dict, Any

from src.services_v5.core.models import ServiceState


class BaseWorkflow(ABC):
    """
    Classe base para todos os workflows V5.

    Cada workflow deve herdar desta classe e implementar:
    - service_name: Nome do serviço
    - description: Descrição do serviço
    """

    service_name: str = ""
    description: str = ""

    @abstractmethod
    def build_graph(self):
        """
        Constrói e retorna o grafo compilado LangGraph para este workflow.

        """
        pass

    def execute(self, state: ServiceState, payload: Dict[str, Any]):
        """
        Executa o workflow com payload e estado fornecidos.

        Args:
            state: Estado atual do serviço
            payload: Dados enviados pelo agente
        """
