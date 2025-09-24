from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from langgraph.graph import StateGraph

from src.services_v5.core.models import ServiceState, ExecutionResult, AgentResponse


class BaseWorkflow(ABC):
    """
    Classe base para todos os workflows V5.

    Cada workflow deve herdar desta classe e implementar:
    - service_name: Nome do serviço
    - description: Descrição do serviço
    - build_graph(): Método que constrói o StateGraph.
    """

    service_name: str = ""
    description: str = ""

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """
        Constrói e retorna o grafo LangGraph para este workflow.
        Este método deve ser implementado por cada workflow filho.
        """
        pass

    def execute(self, state: ServiceState, payload: Dict[str, Any]) -> ExecutionResult:
        """
        Executa o workflow com o estado e payload fornecidos.

        Este método orquestra a execução do grafo LangGraph:
        1. Compila o grafo.
        2. Prepara o dicionário de entrada para o grafo.
        3. Invoca o grafo, que executa em cascata até pausar ou terminar.
        4. Processa o estado final para construir o ExecutionResult.
        """
        # 1. Compila o grafo definido no workflow específico
        graph = self.build_graph()
        compiled_graph = graph.compile()

        # 2. Prepara o input para a invocação do grafo
        graph_input = {"state": state, "payload": payload or {}}

        # 3. Invoca o grafo. A execução em cascata acontece aqui dentro.
        final_graph_state = compiled_graph.invoke(graph_input)

        # 4. Extrai o estado final e a resposta para o agente
        final_service_state = final_graph_state["state"]
        agent_response = final_service_state.agent_response

        # Se o grafo terminou sem uma resposta explícita, significa que o serviço foi concluído.
        if agent_response is None:
            final_service_state.status = "completed"
            agent_response = AgentResponse(
                service_name=self.service_name,
                status="completed",
                description="Serviço concluído com sucesso.",
                data=final_service_state.data,
            )

        # Limpa a resposta do agente do estado para não persistir entre chamadas
        final_service_state.agent_response = None

        return ExecutionResult(state=final_service_state, response=agent_response)
