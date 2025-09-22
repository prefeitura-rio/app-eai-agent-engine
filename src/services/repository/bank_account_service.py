from src.services.schema.models import ServiceDefinition, StepInfo

bank_account_service_def = ServiceDefinition(
    service_name="bank_account_opening",
    description="A service to open a new bank account.",
    steps=[
        StepInfo(
            name="user_info",
            description="Collect basic user information.",
            substeps=[
                StepInfo(
                    name="user_info.name",
                    description="Please provide your full name.",
                    required=True,
                    payload_schema={
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                ),
                StepInfo(
                    name="user_info.email",
                    description="What is your email address?",
                    required=True,
                    payload_schema={
                        "type": "object",
                        "properties": {"email": {"type": "string"}},
                    },
                ),
                StepInfo(
                    name="user_info.doc_type",
                    description="What document type will you use? (e.g., passport, driver's license)",
                    required=True,
                    payload_schema={
                        "type": "object",
                        "properties": {"doc_type": {"type": "string"}},
                    },
                ),
            ],
        ),
        StepInfo(
            name="account_type",
            description="What type of account would you like to open? (checking/savings)",
            payload_schema={
                "type": "object",
                "properties": {
                    "account_type": {"type": "string", "enum": ["checking", "savings"]}
                },
            },
            depends_on=["user_info"],
        ),
        StepInfo(
            name="initial_deposit",
            description="An initial deposit of at least $50 is required for savings accounts. How much would you like to deposit?",
            payload_schema={
                "type": "object",
                "properties": {"deposit_amount": {"type": "number", "minimum": 50}},
            },
            depends_on=["account_type"],
            condition='account_type == "savings"',
        ),
        StepInfo(
            name="create_account",
            description="Creating the account...",
            action="create_bank_account",
            depends_on=[
                "account_type"
            ],  # Depends on account_type and potentially initial_deposit
        ),
        StepInfo(
            name="account_created_success",
            description="Your account has been created successfully!",
            is_end=True,
            depends_on=["create_account"],
            condition='_internal.outcomes.create_account == "ACCOUNT_CREATED"',
        ),
        StepInfo(
            name="account_creation_failed",
            description="There was an error creating your account.",
            is_end=True,
            depends_on=["create_account"],
            condition='_internal.outcomes.create_account == "ERROR"',
        ),
    ],
)
