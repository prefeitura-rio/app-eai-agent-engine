import json
import os
import shutil
from typing import List, Tuple

from src.services import multi_step_service
from src.services.tests import run_complete_tests


if "__main__" == __name__:
    # Build the service registry
    # print(multi_step_service.description)
    r = multi_step_service.invoke(
        {
            "service_name": "bank_account",
            "step": "account_type",
            "payload": "corrente",
            "user_id": "test_user",
        }
    )
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print("\n\n")
    run_complete_tests()
