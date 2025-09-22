import random
from typing import Dict
from src.services.core.actions import action
from src.services.schema.models import ExecutionResult

@action("create_bank_account")
def create_bank_account(state: Dict) -> ExecutionResult:
    """
    A dummy action that simulates creating a bank account.
    It randomly succeeds or fails.
    """
    user_data = state.get("data", {})
    print("--- Executing action: create_bank_account ---")
    print(f"--- State data received: {user_data} ---")

    # Simulate some business logic
    if random.random() > 0.2: # 80% success rate
        account_number = random.randint(100000000, 999999999)
        return ExecutionResult(
            success=True,
            outcome="ACCOUNT_CREATED",
            updated_data={"account_details": {"account_number": account_number}}
        )
    else:
        return ExecutionResult(
            success=False,
            outcome="ERROR",
            error_message="Failed to create account due to a simulated internal error."
        )
