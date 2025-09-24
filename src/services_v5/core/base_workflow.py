from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

from langgraph.graph import StateGraph

from src.services_v5.core.models import ServiceState, AgentResponse

# Configure logging
logger = logging.getLogger(__name__)


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
        logger.info(f"🔧 BASE_WORKFLOW: Compilando grafo para '{self.service_name}'")
        
        # 1. Injeta payload no state - fonte única da verdade
        state.payload = payload or {}
        logger.info(f"🎯 BASE_WORKFLOW: State data: {state.data}")
        logger.info(f"🎯 BASE_WORKFLOW: Payload: {state.payload}")

        # 2. Compila o grafo definido no workflow específico
        graph = self.build_graph()
        compiled_graph = graph.compile()

        # 3. Invoca o grafo diretamente com ServiceState
        logger.info(f"🚀 BASE_WORKFLOW: Iniciando execução do grafo LangGraph")
        final_state_result = compiled_graph.invoke(state)
        logger.info(f"🏁 BASE_WORKFLOW: Execução do grafo concluída")

        # O LangGraph pode retornar o ServiceState diretamente ou como dict
        # Vamos garantir que sempre trabalhamos com ServiceState
        if isinstance(final_state_result, ServiceState):
            final_state = final_state_result
        else:
            # Se retornar dict, convertemos de volta para ServiceState
            final_state = ServiceState(**final_state_result)

        logger.info(f"📊 BASE_WORKFLOW: Estado final: {final_state.data}")
        logger.info(f"📝 BASE_WORKFLOW: Agent response: {final_state.agent_response is not None}")

        # Se o grafo terminou sem uma resposta explícita, significa que o serviço foi concluído.
        if final_state.agent_response is None:
            logger.info(f"✅ BASE_WORKFLOW: Serviço concluído - criando resposta de conclusão")
            final_state.status = "completed"
            final_state.agent_response = AgentResponse(
                service_name=self.service_name,
                description="Serviço concluído com sucesso.",
                data=final_state.data,
            )
        else:
            logger.info(f"⏸️  BASE_WORKFLOW: Serviço pausado - aguardando input: {final_state.agent_response.description}")

        # Limpa o payload para não persistir (dados temporários)
        temp_agent_response = final_state.agent_response
        final_state.payload = {}
        
        # Mantém a resposta para o orchestrator
        final_state.agent_response = temp_agent_response

        return final_state
