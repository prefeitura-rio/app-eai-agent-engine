import json
import time
from src.services.tool import multi_step_service


def main():
    """
    Main function to run the test flow.
    """
    print("Sistema de serviços multi-step com schema dinâmico e estado transparente.\n")

    # user_id = f"test_user_{int(time.time())}"
    user_id = "agent"
    service_name = "bank_account_opening"

    # --- Turn 1: Start the service (no payload) ---
    print("--- Turn 1: Initial call ---")
    response = multi_step_service.invoke(
        {"service_name": service_name, "user_id": user_id, "payload": {}}
    )
    print(json.dumps(response, indent=2, ensure_ascii=False))

    # --- Turn 2: Send partial payload ---
    if response["status"] == "IN_PROGRESS":
        print("\n--- Turn 2: Sending partial payload (name only) ---")
        partial_payload = {
            "user_info.name": "John Doe",
            "user_info.email": "asd@gmail.com",
        }
        response = multi_step_service.invoke(
            {
                "service_name": service_name,
                "user_id": user_id,
                "payload": partial_payload,
            }
        )
        print(json.dumps(response, indent=2, ensure_ascii=False))
        print(response["execution_summary"]["dependency_tree_ascii"])


if __name__ == "__main__":
    main()
