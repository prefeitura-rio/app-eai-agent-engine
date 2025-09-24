import random
from typing import Literal, Dict, Any
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END

from src.services_v5.core.base_workflow import BaseWorkflow
from src.services_v5.core.models import ServiceState, AgentResponse


# (Modelos Pydantic e GraphState permanecem os mesmos)
class GraphState(TypedDict):
    state: ServiceState
    payload: Dict[str, Any]


class UserInfoPayload(BaseModel):
    name: str = Field(..., min_length=2)
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")


class AccountTypePayload(BaseModel):
    account_type: Literal["checking", "savings"]


class ActionChoicePayload(BaseModel):
    ask_action: Literal["deposit", "balance"]


class DepositAmountPayload(BaseModel):
    deposit_amount: float = Field(..., gt=0)


class BankAccountWorkflow(BaseWorkflow):
    service_name = "bank_account"
    description = (
        "Abre uma conta bancária e permite operações como depósito e consulta de saldo."
    )

    # --- Nós do Grafo (Lógica Interna dos Nós está OK) ---
    # ... (os métodos _collect_user_info, _check_account_exists, etc. não precisam mudar)
    def _collect_user_info(self, state: GraphState) -> GraphState:
        service_state = state["state"]
        payload = state["payload"]

        try:
            validated_data = UserInfoPayload.model_validate(payload)
            service_state.data.update(validated_data.model_dump())
        except ValidationError:
            pass

        if "name" not in service_state.data or "email" not in service_state.data:
            service_state.agent_response = AgentResponse(
                service_name=self.service_name,
                description="Por favor, forneça seu nome completo e email.",
                payload_schema=UserInfoPayload.model_json_schema(),
            )
        else:
            service_state.agent_response = None

        return {"state": service_state, "payload": {}}

    def _check_account_exists(self, state: GraphState) -> GraphState:
        service_state = state["state"]
        if service_state.data.get("account_number"):
            service_state.data["_internal_account_exists"] = True
        else:
            service_state.data["_internal_account_exists"] = False
        return state

    def _collect_account_type(self, state: GraphState) -> GraphState:
        service_state = state["state"]
        payload = state["payload"]

        try:
            validated_data = AccountTypePayload.model_validate(payload)
            service_state.data.update(validated_data.model_dump())
        except ValidationError:
            pass

        if "account_type" not in service_state.data:
            service_state.agent_response = AgentResponse(
                service_name=self.service_name,
                description="Qual tipo de conta você gostaria de abrir: 'checking' (corrente) ou 'savings' (poupança)?",
                payload_schema=AccountTypePayload.model_json_schema(),
            )
        else:
            service_state.agent_response = None

        return {"state": service_state, "payload": {}}

    def _create_account(self, state: GraphState) -> GraphState:
        service_state = state["state"]
        service_state.data["account_number"] = random.randint(10000, 99999)
        service_state.data["balance"] = 0.0
        return state

    def _ask_action(self, state: GraphState) -> GraphState:
        service_state = state["state"]
        payload = state["payload"]

        # Limpa ações antigas para permitir que o usuário faça outra operação
        if "ask_action" in payload:
            service_state.data.pop("ask_action", None)
            service_state.data.pop("deposit_amount", None)

        try:
            validated_data = ActionChoicePayload.model_validate(payload)
            service_state.data.update(validated_data.model_dump())
        except ValidationError:
            pass

        if "ask_action" not in service_state.data:
            service_state.agent_response = AgentResponse(
                service_name=self.service_name,
                description=f"Conta {service_state.data['account_number']} pronta. Saldo atual: R$ {service_state.data.get('balance', 0.0):.2f}. O que você gostaria de fazer? 'deposit' (depositar) ou 'balance' (ver saldo)?",
                payload_schema=ActionChoicePayload.model_json_schema(),
            )
        else:
            service_state.agent_response = None

        return {"state": service_state, "payload": {}}

    def _collect_deposit_amount(self, state: GraphState) -> GraphState:
        service_state = state["state"]
        payload = state["payload"]

        try:
            validated_data = DepositAmountPayload.model_validate(payload)
            service_state.data.update(validated_data.model_dump())
        except ValidationError as e:
            service_state.agent_response = AgentResponse(
                service_name=self.service_name,
                status="progress",
                description=f"Valor de depósito inválido. Por favor, forneça um número positivo. Erro: {e.errors()[0]['msg']}",
                payload_schema=DepositAmountPayload.model_json_schema(),
            )
            return {"state": service_state, "payload": {}}

        if "deposit_amount" not in service_state.data:
            service_state.agent_response = AgentResponse(
                service_name=self.service_name,
                description="Qual valor você gostaria de depositar?",
                payload_schema=DepositAmountPayload.model_json_schema(),
            )
        else:
            service_state.agent_response = None

        return {"state": service_state, "payload": {}}

    def _make_deposit(self, state: GraphState) -> GraphState:
        service_state = state["state"]
        amount = service_state.data.get("deposit_amount", 0)
        current_balance = service_state.data.get("balance", 0)
        service_state.data["balance"] = current_balance + amount

        service_state.data.pop("ask_action", None)
        service_state.data.pop("deposit_amount", None)
        return state

    # --- Roteadores Condicionais (Lógica de roteamento e pausa) ---

    def _decide_after_data_collection(
        self, state: GraphState
    ) -> Literal["continue", END]:
        # Roteador genérico para nós de coleta de dados.
        # Se o nó pediu input, a execução para. Senão, continua.
        if state["state"].agent_response is not None:
            return END
        return "continue"

    def _route_after_check_account(self, state: GraphState) -> str:
        exists = state["state"].data.get("_internal_account_exists", False)
        return "ask_action" if exists else "account_type"

    def _route_after_action_choice(self, state: GraphState) -> str:
        # <-- MUDANÇA: Lógica de pausa movida para o roteador genérico.
        # Este roteador agora só se preocupa com a lógica de negócio.
        action = state["state"].data.get("ask_action")
        if action == "deposit":
            return "collect_deposit_amount"
        elif action == "balance":
            return "ask_action"  # Volta para ask_action para mostrar o saldo atualizado e perguntar de novo
        return "ask_action"

    # --- Construção do Grafo ---

    def build_graph(self) -> StateGraph:
        graph = StateGraph(GraphState)

        graph.add_node("collect_user_info", self._collect_user_info)
        graph.add_node("check_account", self._check_account_exists)
        graph.add_node("account_type", self._collect_account_type)
        graph.add_node("create_account", self._create_account)
        graph.add_node("ask_action", self._ask_action)
        graph.add_node("collect_deposit_amount", self._collect_deposit_amount)
        graph.add_node("make_deposit", self._make_deposit)

        graph.set_entry_point("collect_user_info")

        # <-- MUDANÇA: Arestas após nós de coleta de dados agora são condicionais
        graph.add_conditional_edges(
            "collect_user_info",
            self._decide_after_data_collection,
            {"continue": "check_account", END: END},
        )

        graph.add_conditional_edges(
            "check_account",
            self._route_after_check_account,
            {"account_type": "account_type", "ask_action": "ask_action"},
        )

        # <-- MUDANÇA: Aresta condicional aqui também
        graph.add_conditional_edges(
            "account_type",
            self._decide_after_data_collection,
            {"continue": "create_account", END: END},
        )

        graph.add_edge("create_account", "ask_action")

        # <-- MUDANÇA: Roteamento após 'ask_action' agora é um processo de duas etapas
        # 1. Verifica se precisa pausar
        graph.add_conditional_edges(
            "ask_action",
            self._decide_after_data_collection,
            {
                # 2. Se não pausar, decide para onde ir com base na ação
                "continue": "route_action_choice",
                END: END,
            },
        )

        # Adicionamos um nó "invisível" que apenas roteia
        graph.add_node("route_action_choice", lambda state: state)
        graph.add_conditional_edges(
            "route_action_choice",
            self._route_after_action_choice,
            {
                "collect_deposit_amount": "collect_deposit_amount",
                "ask_action": "ask_action",
            },
        )

        # <-- MUDANÇA: Aresta condicional para a coleta de valor
        graph.add_conditional_edges(
            "collect_deposit_amount",
            self._decide_after_data_collection,
            {"continue": "make_deposit", END: END},
        )

        graph.add_edge("make_deposit", "ask_action")

        return graph
