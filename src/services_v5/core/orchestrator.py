from typing import Dict, Type
from src.services_v5.core.models import ServiceRequest, ServiceState, AgentResponse
from src.services_v5.core.state import StateManager
from src.services_v5.workflows import workflows


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
        # Verifica se workflow existe
        if request.service_name not in self.workflows:
            available = ", ".join(self.list_workflows())
            return AgentResponse(
                service_name=request.service_name,
                status="error",
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
            # Cria novo state se não existir
            state = ServiceState(
                user_id=request.user_id,
                service_name=request.service_name,
                status="progress",
                data={},
            )

        # Instancia e executa workflow
        workflow_class = self.workflows[request.service_name]
        workflow = workflow_class()

        try:
            # Executa workflow passando state e payload separadamente
            # O workflow é responsável por validar e aplicar o payload
            response = workflow.execute(state, request.payload)

            # Salva state atualizado APÓS execução do workflow
            # O state foi modificado durante a execução
            state_manager.save_service_state(state)

            return response

        except Exception as e:
            # Em caso de erro, retorna resposta de erro
            return AgentResponse(
                service_name=request.service_name,
                status="error",
                error_message=f"Erro na execução do serviço: {str(e)}",
                description="Erro interno do serviço",
                payload_schema=None,
                data=state.data,
            )
