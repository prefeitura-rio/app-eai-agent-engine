from typing import Dict, Any, List, Literal
from pydantic import BaseModel, Field
from src.services.core.base_service import BaseService
from src.services.schema.models import ExecutionResult, ServiceDefinition, StepInfo

# V3: Pydantic models for type-safe payload validation
class CustomerNamePayload(BaseModel):
    """Customer name input payload"""
    name: str = Field(..., description="Customer full name", min_length=2, max_length=100)

class CustomerEmailPayload(BaseModel):
    """Customer email input payload"""
    email: str = Field(..., description="Valid email address", pattern=r'^[^@]+@[^@]+\.[^@]+$')

class OrderItemsPayload(BaseModel):
    """Order items input payload"""
    order_items: List[str] = Field(..., description="List of items to order", min_items=1)

class PaymentMethodPayload(BaseModel):
    """Payment method input payload"""
    payment_method: Literal["credit_card", "debit_card"] = Field(..., description="Payment method")

class BillingAddressPayload(BaseModel):
    """Billing address input payload"""
    billing_address: str = Field(..., description="Billing address", min_length=10, max_length=200)


class OrderService(BaseService):
    """
    V3: Enhanced order processing service with Strict Graph Executor and Pydantic validation.
    Features strict dependency validation and enhanced error recovery.
    """

    service_name = "order_processing"
    description = "V3: Enhanced order processing service with strict validation and error recovery"

    def _validate_order(self, state: Dict[str, Any]) -> ExecutionResult:
        """V3: Validates the order and decides next step with enhanced error handling."""
        items = state.get("data", {}).get("order_items", [])
        
        if len(items) > 0:
            return ExecutionResult.success_result(
                outcome="ORDER_VALID",
                next_steps=["payment_info"],
            )
        else:
            return ExecutionResult.success_result(
                outcome="ORDER_EMPTY",
                next_steps=["order_items"],
            )

    def _process_payment(self, state: Dict[str, Any]) -> ExecutionResult:
        """V3: Processes payment and completes order with enhanced error handling."""
        payment_method = state.get("data", {}).get("payment_method")
        valid_methods = ["credit_card", "debit_card"]
        
        if payment_method in valid_methods:
            return ExecutionResult.success_result(
                outcome="PAYMENT_SUCCESS",
                updated_data={"order_status": "confirmed", "order_id": "ORD-12345"},
                is_complete=True,
                completion_message="Order confirmed! Your order ID is ORD-12345",
            )
        else:
            # V3: Enhanced error handling with recovery guidance
            return ExecutionResult.validation_error(
                error_message=f"Invalid payment method '{payment_method}'. Please choose from: {', '.join(valid_methods)}",
                valid_choices=valid_methods,
                error_code="INVALID_PAYMENT_METHOD",
                retry_step="payment_method"
            )

    def get_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description=self.description,
            steps=[
                # 1. Customer Info Collection - V3: Using Pydantic models
                StepInfo(
                    name="customer_info",
                    description="Collect customer information",
                    substeps=[
                        StepInfo(
                            name="customer_info.name",
                            description="Please provide the customer's full name",
                            payload_schema=CustomerNamePayload,
                        ),
                        StepInfo(
                            name="customer_info.email",
                            description="What is the customer's email address?",
                            payload_schema=CustomerEmailPayload,
                        ),
                    ],
                ),
                # 2. Order Items Collection - V3: Using Pydantic models
                StepInfo(
                    name="order_items",
                    description="What items would you like to order?",
                    payload_schema=OrderItemsPayload,
                    depends_on=["customer_info"],
                ),
                # 3. Validate Order (Action controls what's next!)
                StepInfo(
                    name="validate_order",
                    action=self._validate_order,
                    depends_on=["order_items"],
                ),
                # 4. Payment Info Collection - V3: Using Pydantic models
                StepInfo(
                    name="payment_info",
                    description="Collect payment information",
                    substeps=[
                        StepInfo(
                            name="payment_method",
                            description="Please choose your payment method",
                            payload_schema=PaymentMethodPayload,
                        ),
                        StepInfo(
                            name="billing_address",
                            description="Please provide your billing address",
                            payload_schema=BillingAddressPayload,
                        ),
                    ],
                    depends_on=["validate_order"],
                ),
                # 5. Process Payment (Action completes the order)
                StepInfo(
                    name="process_payment",
                    action=self._process_payment,
                    depends_on=["payment_info"],
                ),
            ],
        )