import random
from typing import Dict, Any, Literal
from pydantic import BaseModel, Field
from src.services.core.base_service import BaseService
from src.services.schema.models import ExecutionResult, ServiceDefinition, StepInfo

# V3: Pydantic models for type-safe payload validation
class UserNamePayload(BaseModel):
    """User name input payload"""
    name: str = Field(..., description="Full name of the user", min_length=2, max_length=100)

class UserEmailPayload(BaseModel):
    """User email input payload"""
    email: str = Field(..., description="Valid email address", pattern=r'^[^@]+@[^@]+\.[^@]+$')

class AccountTypePayload(BaseModel):
    """Account type selection payload"""
    account_type: Literal["checking", "savings"] = Field(..., description="Type of bank account")

class ActionChoicePayload(BaseModel):
    """User action choice payload"""
    ask_action: Literal["deposit", "balance"] = Field(..., description="Action to perform on the account")

class DepositAmountPayload(BaseModel):
    """Deposit amount input payload"""
    deposit_amount: float = Field(..., description="Amount to deposit", gt=0, le=10000)


class BankAccountServiceV2(BaseService):
    """
    V3: Enhanced bank account service with Strict Graph Executor and Pydantic validation.
    Features strict dependency validation and enhanced error recovery.
    """

    service_name = "bank_account_opening_v2"
    description = "V3: Enhanced bank account service with strict validation and error recovery"

    # --- Service Definition (Much cleaner!) ---

    def get_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description=self.description,
            steps=[
                # 1. User Info Collection - V3: Using Pydantic models
                StepInfo(
                    name="user_info",
                    description="Collect basic user information",
                    substeps=[
                        StepInfo(
                            name="user_info.name",
                            description="Please provide your full name",
                            payload_schema=UserNamePayload,
                        ),
                        StepInfo(
                            name="user_info.email",
                            description="What is your email address?",
                            payload_schema=UserEmailPayload,
                        ),
                    ],
                ),
                # 2. Check Account (Action controls what's next!)
                StepInfo(
                    name="check_account",
                    action=self._check_account_exists,
                    depends_on=["user_info"],
                ),
                # 3. Account Type (Only if needed - controlled by action) - V3: Using Pydantic
                StepInfo(
                    name="account_type",
                    description="What type of account? (checking/savings)",
                    depends_on=["check_account"],
                    payload_schema=AccountTypePayload,
                ),
                # 4. Create Account (Action controls flow)
                StepInfo(
                    name="create_account",
                    action=self._create_account,
                    depends_on=["account_type"],
                ),
                # 5. Ask Action (Available when actions decide) - V3: Using Pydantic
                # persistence_level="operation" - resets after each operation so user can do multiple operations
                StepInfo(
                    name="ask_action",
                    description="Would you like to make a deposit or check your balance?",
                    payload_schema=ActionChoicePayload,
                    depends_on=["check_account"],  # Only available after account check
                    persistence_level="operation",  # Reset after each operation
                ),
                # 5b. Process Action Choice (Processes the user's choice)
                StepInfo(
                    name="process_action_choice",
                    action=self._process_action_choice,  # Action processes choice
                    depends_on=["ask_action"],  # Only available after action is chosen
                    persistence_level="operation",  # Reset after each operation
                ),
                # 6. Deposit Amount Collection (Only if deposit chosen) - V3: Using Pydantic
                # persistence_level="operation" - resets so user can make multiple deposits
                StepInfo(
                    name="deposit_amount",
                    description="How much would you like to deposit?",
                    payload_schema=DepositAmountPayload,
                    depends_on=[
                        "process_action_choice"
                    ],  # Only available after action choice processed
                    persistence_level="operation",  # Reset after each operation
                ),
                # 7. Execute Deposit (Action step)
                StepInfo(
                    name="execute_deposit",
                    action=self._make_deposit,  # Action completes deposit
                    depends_on=[
                        "deposit_amount"
                    ],  # Only available after amount is collected
                    persistence_level="operation",  # Reset after each operation
                ),
            ],
        )

    # --- Actions (Now control the flow!) ---

    def _check_account_exists(self, state: Dict[str, Any]) -> ExecutionResult:
        """V3: Action that decides what happens next based on account existence."""
        data = state.get("data", {})

        # Check if user already has an account (from previous service execution)
        existing_account_number = data.get("account_number")
        existing_deposits = data.get("deposits", [])

        if existing_account_number:
            # User already has an account - go straight to operations!
            return ExecutionResult.success_result(
                outcome="ACCOUNT_EXISTS",
                updated_data={
                    # Preserve existing account data
                    "account_number": existing_account_number,
                    "deposits": existing_deposits,
                },
                # Action decides: go straight to account operations!
                next_steps=["ask_action"],
            )
        else:
            # New user - need to create account first
            return ExecutionResult.success_result(
                outcome="ACCOUNT_NOT_FOUND",
                updated_data={"deposits": []},
                # Action decides: need to create account first!
                next_steps=["account_type"],
            )

    def _create_account(self, state: Dict[str, Any]) -> ExecutionResult:
        """V3: Creates account and decides what's next."""
        account_number = random.randint(100000000, 999999999)

        return ExecutionResult.success_result(
            outcome="ACCOUNT_CREATED",
            updated_data={
                "account_number": account_number,
                "deposits": [],  # Start with empty deposits
            },
            # Action decides: account created, now offer operations!
            next_steps=["ask_action"],
        )

    def _process_action_choice(self, state: Dict[str, Any]) -> ExecutionResult:
        """V3: Processes user's choice and decides next step with enhanced error handling."""
        choice = state.get("data", {}).get("ask_action")
        valid_choices = ["deposit", "balance"]

        if choice == "deposit":
            return ExecutionResult.success_result(
                outcome="DEPOSIT_CHOSEN",
                # Action decides: need deposit amount!
                next_steps=["deposit_amount"],
            )
        elif choice == "balance":
            # Execute balance calculation directly here since no more input needed
            data = state.get("data", {})
            deposits = data.get("deposits", []) if data else []
            balance = sum(deposits)

            return ExecutionResult.success_result(
                outcome="BALANCE_CALCULATED",
                updated_data={"balance": balance},
                # Action decides: we're done!
                is_complete=True,
                completion_message=f"Your current balance is ${balance}.",
            )
        else:
            # V3: Enhanced error handling with recovery guidance
            return ExecutionResult.validation_error(
                error_message=f"Invalid choice '{choice}'. Please choose from: {', '.join(valid_choices)}",
                valid_choices=valid_choices,
                error_code="INVALID_ACTION_CHOICE",
                retry_step="ask_action"
            )

    def _make_deposit(self, state: Dict[str, Any]) -> ExecutionResult:
        """V3: Makes deposit and completes the service using enhanced ExecutionResult."""
        new_deposit_amount = state.get("data", {}).get("deposit_amount", 0)
        existing_deposits = state.get("data", {}).get("deposits", [])
        new_deposits = existing_deposits + [new_deposit_amount]
        new_balance = sum(new_deposits)

        return ExecutionResult.success_result(
            outcome="DEPOSIT_COMPLETE",
            updated_data={"deposits": new_deposits, "balance": new_balance},
            is_complete=True,
            completion_message=f"Deposit of ${new_deposit_amount} successful! Your new balance is ${new_balance}.",
        )
