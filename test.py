import json
import time
from src.services.tool import multi_step_service


def main():
    """
    Main function to run the test flow.
    """
    print("Sistema de serviços multi-step com schema dinâmico e estado transparente.\n")

    # user_id = f"test_user_{int(time.time())}"
    # user_id = f"agent_{int(time.time())}"
    user_id = "agent3"
    service_name = "bank_account_opening_v2"
    partial_payload = {
        # Test empty payload to verify system asks for next action
    }
    response = multi_step_service.invoke(
        {
            "service_name": service_name,
            "user_id": user_id,
            "payload": partial_payload,
        }
    )
    print(json.dumps(response, indent=2, ensure_ascii=False))
    print(response["execution_summary"]["tree"])


if __name__ == "__main__":
    main()
