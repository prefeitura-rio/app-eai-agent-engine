import json
import os
from src.services.tool import run_service

def print_response(response):
    """Helper to pretty-print the agent response."""
    print("\n" + "="*80)
    print(f"STATUS: {response.status}")
    if response.error_message:
        print(f"ERROR: {response.error_message}")
    
    if response.next_step_info:
        print(f"NEXT STEP: {response.next_step_info.step_name}")
        print(f"DESCRIPTION: {response.next_step_info.description}")
        print(f"PAYLOAD SCHEMA: {json.dumps(response.next_step_info.payload_schema, indent=2)}")

    if response.execution_summary:
        print(response.execution_summary.dependency_tree_ascii)

    if response.final_output:
        print(f"FINAL OUTPUT: {json.dumps(response.final_output, indent=2)}")
    print("="*80 + "\n")


def run_test_flow():
    """Simulates a full conversation to open a savings account."""
    USER_ID = "test_user_123"
    SERVICE_NAME = "bank_account_opening"
    
    # Clean up previous state
    state_file = f"src/services/data/{USER_ID}.json"
    if os.path.exists(state_file):
        os.remove(state_file)

    # 1. Start the service
    print("--- Turn 1: Starting the service ---")
    response = run_service(service_name=SERVICE_NAME, user_id=USER_ID)
    print_response(response)
    assert response.next_step_info.step_name == "user_info.name"

    # 2. Provide name
    print("--- Turn 2: Providing name ---")
    response = run_service(service_name=SERVICE_NAME, user_id=USER_ID, payload={"name": "John Doe"})
    print_response(response)
    assert response.next_step_info.step_name == "user_info.email"

    # 3. Provide email
    print("--- Turn 3: Providing email ---")
    response = run_service(service_name=SERVICE_NAME, user_id=USER_ID, payload={"email": "john.doe@example.com"})
    print_response(response)
    assert response.next_step_info.step_name == "account_type"

    # 4. Provide account type (savings)
    print("--- Turn 4: Providing account type (savings) ---")
    response = run_service(service_name=SERVICE_NAME, user_id=USER_ID, payload={"account_type": "savings"})
    print_response(response)
    assert response.next_step_info.step_name == "initial_deposit"

    # 5. Provide deposit
    print("--- Turn 5: Providing initial deposit ---")
    response = run_service(service_name=SERVICE_NAME, user_id=USER_ID, payload={"deposit_amount": 100})
    print_response(response)
    assert response.status in ["COMPLETED", "FAILED"]
    if response.status == "COMPLETED":
        assert response.final_output["account_details"]["account_number"] is not None

if __name__ == "__main__":
    run_test_flow()
