from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import os

from langgraph.graph import StateGraph

from src.services.core.models import ServiceState, AgentResponse


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
    def build_graph(self) -> StateGraph[ServiceState]:
        """
        Constrói e retorna o grafo LangGraph para este workflow.
        Este método deve ser implementado por cada workflow filho.
        """
        pass

    def execute(self, state: ServiceState, payload: Dict[str, Any]) -> ServiceState:
        """
        Executa o workflow com o estado e payload fornecidos.

        Este método orquestra a execução do grafo LangGraph:
        1. Injeta payload no state (fonte única da verdade)
        2. Compila o grafo.
        3. Invoca o grafo, que executa em cascata até pausar ou terminar.
        4. Retorna o ServiceState atualizado.
        """

        # 1. Injeta payload no state - fonte única da verdade
        state.payload = payload or {}

        # 2. Compila o grafo definido no workflow específico
        graph = self.build_graph()
        compiled_graph = graph.compile()

        # 3. Invoca o grafo diretamente com ServiceState
        final_state_result = compiled_graph.invoke(state)

        # O LangGraph pode retornar o ServiceState diretamente ou como dict
        # Vamos garantir que sempre trabalhamos com ServiceState
        if isinstance(final_state_result, ServiceState):
            final_state = final_state_result
        else:
            # Se retornar dict, convertemos de volta para ServiceState
            final_state = ServiceState(**final_state_result)

        # Se o grafo terminou sem uma resposta explícita, significa que o serviço foi concluído.
        if final_state.agent_response is None:

            final_state.status = "completed"
            final_state.agent_response = AgentResponse(
                service_name=self.service_name,
                description="Serviço concluído com sucesso.",
                data=final_state.data,
            )

        # Limpa o payload para não persistir (dados temporários)
        temp_agent_response = final_state.agent_response
        final_state.payload = {}

        # Mantém a resposta para o orchestrator
        final_state.agent_response = temp_agent_response

        return final_state

    def save_graph_image(self) -> str:
        """
        Salva a imagem do grafo compilado na mesma pasta do workflow.

        Returns:
            Caminho para o arquivo de imagem salvo
        """
        try:
            # Constrói e compila o grafo
            graph = self.build_graph()
            compiled_graph = graph.compile()

            # Determina o diretório do arquivo do workflow
            workflow_file = self.__class__.__module__.replace(".", "/") + ".py"
            workflow_dir = os.path.dirname(workflow_file)

            # Se não conseguir determinar o diretório, usa o diretório atual
            if not workflow_dir or not os.path.exists(workflow_dir):
                workflow_dir = os.path.dirname(os.path.abspath(__file__))
                workflow_dir = os.path.join(workflow_dir, "..", "workflows")

            # Cria o caminho completo para a imagem
            image_filename = f"{self.service_name}.png"
            image_path = os.path.join(workflow_dir, image_filename)

            # diagram = compiled_graph.get_graph().draw_mermaid()

            # Gera e salva a imagem do grafo
            with open(image_path, "wb") as f:
                f.write(compiled_graph.get_graph().draw_mermaid_png(max_retries=10))

            return image_path

        except Exception as e:
            raise
