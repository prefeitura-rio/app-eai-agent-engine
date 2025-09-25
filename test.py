import json
import time
from src.services.tool import multi_step_service, save_single_workflow_graph


def main():
    """
    Main function to run the test flow.
    """

    # user_id = f"test_user_{int(time.time())}"
    # user_id = f"agent_{int(time.time())}"
    user_id = "asd"
    service_name = "bank_account"
    partial_payload = {
        # "user_info": {
        #     "name": "Aasd da Silva",
        #     "email": "jane@newuser.com",
        # },
        # "account_type": "checking",
        # "ask_action": "balance",
        # "deposit_amount": 500,
    }

    # print(multi_step_service.description)
    # save_single_workflow_graph(service_name=service_name)

    response = multi_step_service.invoke(
        {
            "service_name": service_name,
            "user_id": user_id,
            "payload": partial_payload,
        }
    )
    print(json.dumps(response, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
