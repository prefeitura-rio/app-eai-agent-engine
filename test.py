import json
import os
import shutil
from typing import List, Tuple

from src.services.tool import multi_step_service
from uuid import uuid4

if "__main__" == __name__:
    # Build the service registry
    # print(multi_step_service.description)
    # Load or create service instance

    print(multi_step_service.description)
    print("\n\n-----------\n\n")
    service_name = "bank_account_opening"
    # user_id = str(uuid4())
    user_id = "dep_bug_test"
    r = multi_step_service.invoke(
        {
            "user_id": user_id,
            "service_name": service_name,
            # "payload": {
            #     "user_info.name": "João",
            #     # "document_type": "CPF",
            #     # "document_number": "12345678901",
            #     "user_info.email": "test@example.com",
            # },
        },
    )
    print(json.dumps(r, indent=2, ensure_ascii=False))
