import random
import logging
from typing import Literal
from pydantic import BaseModel, Field, ValidationError

from langgraph.graph import StateGraph, END

from src.services_v5.core.base_workflow import BaseWorkflow
from src.services_v5.core.models import ServiceState, AgentResponse

# Configure logging
logger = logging.getLogger(__name__)


# Modelos Pydantic para validação de payload


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

    # --- Nós do Grafo ---
    def _collect_user_info(self, state: ServiceState) -> ServiceState:
        # state.data = dados persistidos
        # state.payload = input atual

        if "name" not in state.data or "email" not in state.data:
            error_message = None
            try:
                validated_data = UserInfoPayload.model_validate(state.payload)
                state.data.update(validated_data.model_dump())
                # Se validação foi bem-sucedida e dados foram adicionados, não precisa de agent_response
                if "name" in state.data and "email" in state.data:
                    state.agent_response = None
                else:
                    state.agent_response = AgentResponse(
                        service_name=self.service_name,
                        error_message=error_message,
                        description="Por favor, forneça seu nome completo e email.",
                        payload_schema=UserInfoPayload.model_json_schema(),
                        data=state.data,
                    )
            except ValidationError as e:
                error_message = str(e)
                state.agent_response = AgentResponse(
                    service_name=self.service_name,
                    error_message=error_message,
                    description="Por favor, forneça seu nome completo e email.",
                    payload_schema=UserInfoPayload.model_json_schema(),
                    data=state.data,
                )
        else:
            state.agent_response = None

        return state

    def _check_account_exists(self, state: ServiceState) -> ServiceState:
        if state.data.get("account_number"):
            state.data["_internal_account_exists"] = True
        else:
            state.data["_internal_account_exists"] = False
        return state

    def _collect_account_type(self, state: ServiceState) -> ServiceState:
        if "account_type" not in state.data:
            error_message = None
            try:
                validated_data = AccountTypePayload.model_validate(state.payload)
                state.data.update(validated_data.model_dump())
            except ValidationError as e:
                error_message = str(e)

            state.agent_response = AgentResponse(
                service_name=self.service_name,
                error_message=error_message,
                description="Qual tipo de conta você gostaria de abrir: 'checking' (corrente) ou 'savings' (poupança)?",
                payload_schema=AccountTypePayload.model_json_schema(),
                data=state.data,
            )
        else:
            state.agent_response = None

        return state

    def _create_account(self, state: ServiceState) -> ServiceState:
        state.data["account_number"] = random.randint(10000, 99999)
        state.data["balance"] = 0.0
        return state

    def _ask_action(self, state: ServiceState) -> ServiceState:
        # Processar ação se veio no payload
        action = state.payload.get("ask_action")
        if action == "balance":
            # Limpar ação para evitar loop e mostrar saldo
            state.data.pop("ask_action", None)
            state.agent_response = AgentResponse(
                service_name=self.service_name,
                description=f"💰 Saldo atual da conta {state.data['account_number']}: R$ {state.data.get('balance', 0.0):.2f}. O que você gostaria de fazer agora? 'deposit' (depositar) ou 'balance' (ver saldo novamente)?",
                payload_schema=ActionChoicePayload.model_json_schema(),
                data=state.data,
            )
            return state

        # Lógica original para coletar ação
        if "ask_action" not in state.data:
            error_message = None
            try:
                validated_data = ActionChoicePayload.model_validate(state.payload)
                state.data.update(validated_data.model_dump())
            except ValidationError as e:
                error_message = str(e)
            state.agent_response = AgentResponse(
                service_name=self.service_name,
                error_message=error_message,
                description=f"Conta {state.data['account_number']} pronta. Saldo atual: R$ {state.data.get('balance', 0.0):.2f}. O que você gostaria de fazer? 'deposit' (depositar) ou 'balance' (ver saldo)?",
                payload_schema=ActionChoicePayload.model_json_schema(),
                data=state.data,
            )
        else:
            state.agent_response = None

        return state

    def _collect_deposit_amount(self, state: ServiceState) -> ServiceState:
        try:
            validated_data = DepositAmountPayload.model_validate(state.payload)
            state.data.update(validated_data.model_dump())
        except ValidationError as e:
            state.agent_response = AgentResponse(
                service_name=self.service_name,
                description=f"Valor de depósito inválido. Por favor, forneça um número positivo. Erro: {e.errors()[0]['msg']}",
                payload_schema=DepositAmountPayload.model_json_schema(),
                data=state.data,
            )
            return state

        if "deposit_amount" not in state.data:
            state.agent_response = AgentResponse(
                service_name=self.service_name,
                description="Qual valor você gostaria de depositar?",
                payload_schema=DepositAmountPayload.model_json_schema(),
                data=state.data,
            )
        else:
            state.agent_response = None

        return state

    def _make_deposit(self, state: ServiceState) -> ServiceState:
        amount = state.data.get("deposit_amount", 0)
        current_balance = state.data.get("balance", 0)
        state.data["balance"] = current_balance + amount

        state.data.pop("ask_action", None)
        state.data.pop("deposit_amount", None)
        return state

    # --- Roteadores Condicionais (Lógica de roteamento e pausa) ---

    def _decide_after_data_collection(self, state: ServiceState):
        # Roteador genérico para nós de coleta de dados.
        # Se o nó pediu input, a execução para. Senão, continua.
        if state.agent_response is not None:
            return END
        return "continue"

    def _route_after_check_account(self, state: ServiceState) -> str:
        exists = state.data.get("_internal_account_exists", False)
        return "ask_action" if exists else "account_type"

    def _route_after_action_choice(self, state: ServiceState) -> str:
        # Roteador que decide próximo nó baseado na ação escolhida
        action = state.data.get("ask_action")
        if action == "deposit":
            return "collect_deposit_amount"
        # Para "balance" ou qualquer outra ação, volta para ask_action
        # mas a lógica de balance já foi processada no nó ask_action
        return "ask_action"

    # --- Construção do Grafo ---

    def build_graph(self) -> StateGraph[ServiceState]:
        graph = StateGraph(ServiceState)

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
