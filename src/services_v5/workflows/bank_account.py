import random
from typing import Literal, Union, Dict, Any
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END

from src.services_v5.core.base_workflow import BaseWorkflow
from src.services_v5.core.models import ServiceState


# Pydantic models for payload validation
class UserNamePayload(BaseModel):
    """User name input payload"""

    name: str = Field(
        ..., description="Full name of the user", min_length=2, max_length=100
    )


class UserEmailPayload(BaseModel):
    """User email input payload"""

    email: str = Field(
        ..., description="Valid email address", pattern=r"^[^@]+@[^@]+\.[^@]+$"
    )


class AccountTypePayload(BaseModel):
    """Account type selection payload"""

    account_type: Literal["checking", "savings"] = Field(
        ..., description="Type of bank account"
    )


class ActionChoicePayload(BaseModel):
    """User action choice payload"""

    ask_action: Literal["deposit", "balance"] = Field(
        ..., description="Action to perform on the account"
    )


class DepositAmountPayload(BaseModel):
    """Deposit amount input payload"""

    deposit_amount: float = Field(..., description="Amount to deposit", gt=0, le=10000)


class BankAccountWorkflow(BaseWorkflow):
    """
    Bank account opening workflow with dot notation support.
    """

    service_name = "bank_account"
    description = "Bank account opening and operations workflow"

    def build_graph(self) -> StateGraph:
        """
        Constr�i o grafo LangGraph para abertura de conta banc�ria.
        """
        graph = StateGraph(ServiceState)

        # Adiciona nodes
        # graph.add_node("user_info", self._collect_user_info)
        # graph.add_node("check_account", self._check_account_exists)
        # graph.add_node("account_type", self._collect_account_type)
        # graph.add_node("create_account", self._create_account)
        # graph.add_node("ask_action", self._ask_action)
        # graph.add_node("process_action_choice", self._process_action_choice)
        # graph.add_node("deposit_amount", self._collect_deposit_amount)
        # graph.add_node("execute_deposit", self._make_deposit)

        # # Define fluxo
        # graph.set_entry_point("user_info")
        # graph.add_edge("user_info", "check_account")

        # # Conditional edges baseadas no resultado de check_account
        # graph.add_conditional_edges(
        #     "check_account",
        #     self._route_after_check_account,
        #     {"account_type": "account_type", "ask_action": "ask_action"},
        # )

        # graph.add_edge("account_type", "create_account")
        # graph.add_edge("create_account", "ask_action")
        # graph.add_edge("ask_action", "process_action_choice")

        # # Conditional edges baseadas na escolha da a��o
        # graph.add_conditional_edges(
        #     "process_action_choice",
        #     self._route_after_action_choice,
        #     {"deposit_amount": "deposit_amount", "completed": END},
        # )

        # graph.add_edge("deposit_amount", "execute_deposit")
        # graph.add_edge("execute_deposit", END)

        return graph
