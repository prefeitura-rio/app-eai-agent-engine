from typing import Dict, Any
from src.services.core.base_service import BaseService
from src.services.schema.models import ExecutionResult, ServiceDefinition, StepInfo


class OrderService(BaseService):
    """
    A completely different service to prove the tree visualization is agnostic.
    """

    service_name = "order_processing"
    description = "Process customer orders with validation and payment"

    def _validate_order(self, state: Dict[str, Any]) -> ExecutionResult:
        """Validates the order and decides next step."""
        items = state.get("data", {}).get("order_items", [])
        
        if len(items) > 0:
            return ExecutionResult(
                success=True,
                outcome="ORDER_VALID",
                next_steps=["payment_info"],
            )
        else:
            return ExecutionResult(
                success=True,
                outcome="ORDER_EMPTY",
                next_steps=["order_items"],
            )

    def _process_payment(self, state: Dict[str, Any]) -> ExecutionResult:
        """Processes payment and completes order."""
        payment_method = state.get("data", {}).get("payment_method")
        
        if payment_method == "credit_card":
            return ExecutionResult(
                success=True,
                outcome="PAYMENT_SUCCESS",
                updated_data={"order_status": "confirmed", "order_id": "ORD-12345"},
                is_complete=True,
                completion_message="Order confirmed! Your order ID is ORD-12345",
            )
        else:
            return ExecutionResult(
                success=False,
                outcome="PAYMENT_FAILED",
                error_message="Invalid payment method",
            )

    def get_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description=self.description,
            steps=[
                # Customer Info
                StepInfo(
                    name="customer_info",
                    description="Collect customer information",
                    substeps=[
                        StepInfo(
                            name="customer_info.name",
                            description="Customer full name",
                            payload_schema={
                                "type": "object",
                                "properties": {"customer_info.name": {"type": "string"}},
                            },
                        ),
                        StepInfo(
                            name="customer_info.email",
                            description="Customer email address",
                            payload_schema={
                                "type": "object",
                                "properties": {"customer_info.email": {"type": "string"}},
                            },
                        ),
                    ],
                ),
                # Order Items
                StepInfo(
                    name="order_items",
                    description="List of items to order",
                    payload_schema={
                        "type": "object",
                        "properties": {"order_items": {"type": "array"}},
                    },
                    depends_on=["customer_info"],
                ),
                # Validate Order Action
                StepInfo(
                    name="validate_order",
                    action=self._validate_order,
                    depends_on=["order_items"],
                ),
                # Payment Info
                StepInfo(
                    name="payment_info",
                    description="Payment information",
                    substeps=[
                        StepInfo(
                            name="payment_method",
                            description="Payment method (credit_card, debit_card)",
                            payload_schema={
                                "type": "object",
                                "properties": {"payment_method": {"type": "string"}},
                            },
                        ),
                        StepInfo(
                            name="billing_address",
                            description="Billing address",
                            payload_schema={
                                "type": "object",
                                "properties": {"billing_address": {"type": "string"}},
                            },
                        ),
                    ],
                    depends_on=["validate_order"],
                ),
                # Process Payment Action
                StepInfo(
                    name="process_payment",
                    action=self._process_payment,
                    depends_on=["payment_info"],
                ),
            ],
        )