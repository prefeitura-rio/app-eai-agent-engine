from typing import Dict, Type
import logging
from src.services_v5.core.models import ServiceRequest, ServiceState, AgentResponse
from src.services_v5.core.state import StateManager
from src.services_v5.workflows import workflows

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Orquestrador responsável por gerenciar workflows:
    - Listar workflows existentes
    - Executar workflows
    - Auto-inicializa com state manager e workflows
    """

    def __init__(self):
        self.workflows: Dict[str, Type] = {}

        # Importa workflows automaticamente usando service_name
        for workflow_class in workflows:
            if hasattr(workflow_class, "service_name"):
                self.workflows[workflow_class.service_name] = workflow_class

    def list_workflows(self) -> Dict[str, str]:
        """
        Lista todos os workflows registrados.

        Returns:
            Dicionário com {service_name: description} dos workflows disponíveis
        """
        result = {}
        for service_name, workflow_class in self.workflows.items():
            # Pega description do workflow (atributo description ou __doc__)
            description = getattr(workflow_class, "description", None)
            if not description:
                description = getattr(
                    workflow_class, "__doc__", "Sem descrição"
                ).strip()
                description = (
                    description.split("\n")[0] if description else "Sem descrição"
                )

            result[service_name] = description

        return result

    def execute_workflow(self, request: ServiceRequest) -> AgentResponse:
        """
        Executa um workflow com base na requisição do agente.

        Args:
            request: Requisição contendo service_name, user_id e payload

        Returns:
            Resposta formatada para o agente

        Raises:
            ValueError: Se workflow não for encontrado
        """
        logger.info(
            f"🚀 ORCHESTRATOR: Executando workflow '{request.service_name}' para user '{request.user_id}'"
        )
        logger.info(f"📦 ORCHESTRATOR: Payload recebido: {request.payload}")

        # Verifica se workflow existe
        if request.service_name not in self.workflows:
            available = ", ".join(self.list_workflows())
            return AgentResponse(
                service_name=request.service_name,
                error_message=f"Serviço '{request.service_name}' não encontrado. Disponíveis: {available}",
                description="Erro: Serviço não encontrado",
                payload_schema=None,
                data={},
            )

        # Cria StateManager específico para este user_id
        state_manager = StateManager(user_id=request.user_id)

        # Carrega ou cria state do serviço
        state = state_manager.load_service_state(request.service_name)

        if state is None:
            logger.info("📝 ORCHESTRATOR: Criando novo estado (primeiro uso)")
            # Cria novo state se não existir
            state = ServiceState(
                user_id=request.user_id,
                service_name=request.service_name,
                status="progress",
                data={},
            )
        else:
            logger.info(f"📖 ORCHESTRATOR: Estado carregado: {state.data}")
            logger.info(f"📊 ORCHESTRATOR: Status atual: {state.status}")

        # Instancia e executa workflow
        workflow_class = self.workflows[request.service_name]
        workflow = workflow_class()

        try:
            logger.info(f"⚡ ORCHESTRATOR: Iniciando execução do workflow")
            # Executa workflow passando state e payload
            # O workflow retorna ServiceState com agent_response integrado
            final_state = workflow.execute(state, request.payload)

            logger.info(f"✅ ORCHESTRATOR: Workflow executado")
            logger.info(f"💾 ORCHESTRATOR: Estado final: {final_state.data}")
            logger.info(f"📊 ORCHESTRATOR: Status final: {final_state.status}")
            logger.info(
                f"📤 ORCHESTRATOR: Resposta: {final_state.agent_response.description if final_state.agent_response else 'Nenhuma resposta'}"
            )

            # Salva state atualizado APÓS execução do workflow
            # O state foi modificado durante a execução
            state_manager.save_service_state(final_state)
            logger.info(f"💾 ORCHESTRATOR: Estado salvo no arquivo")

            # Retorna a resposta do agente que está integrada no ServiceState
            return final_state.agent_response

        except Exception as e:
            # Em caso de erro, retorna resposta de erro
            return AgentResponse(
                service_name=request.service_name,
                error_message=f"Erro na execução do serviço: {str(e)}",
                description="Erro interno do serviço",
                payload_schema=None,
                data=state.data,
            )
