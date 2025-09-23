from abc import ABC, abstractmethod
from typing import Dict, Any
from langgraph.graph import StateGraph

from src.services_v5.core.models import ServiceState, ExecutionResult, AgentResponse


class BaseWorkflow(ABC):
    """
    Classe base para todos os workflows V5.

    Cada workflow deve herdar desta classe e implementar:
    - service_name: Nome do serviço
    - description: Descrição do serviço
    - build_graph(): Constrói o grafo LangGraph
    """

    service_name: str = ""
    description: str = ""

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """
        Constrói e retorna o grafo LangGraph para este workflow.

        Returns:
            StateGraph configurado com nodes e edges
        """
        pass

    def image(self) -> bytes:
        """
        Gera imagem compilada do grafo.

        Returns:
            Bytes da imagem do grafo
        """
        graph = self.build_graph()
        compiled = graph.compile()
        return compiled.get_graph().draw_mermaid_png()

    def _apply_dot_notation_payload(
        self, data: Dict[str, Any], payload: Dict[str, Any]
    ) -> None:
        """
        Aplica payload com dot notation ao estado.

        Ex: {"user_info.name": "João"} -> data["user_info"]["name"] = "João"
        """
        for key, value in payload.items():
            if "." in key:
                # Processa dot notation
                parts = key.split(".")
                current = data

                # Navega até o penúltimo nível, criando objetos se necessário
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

                # Define o valor no último nível
                current[parts[-1]] = value
            else:
                # Chave simples
                data[key] = value

    def execute(self, state: ServiceState, payload: Dict[str, Any]):
        """
        Executa o workflow com payload e estado fornecidos.

        Args:
            state: Estado atual do serviço
            payload: Dados enviados pelo agente

        Returns:
            ExecutionResult com estado atualizado e resposta
        """
