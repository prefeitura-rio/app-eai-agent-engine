import json
import os
import shutil
from typing import List, Tuple

from src.services import multi_step_service
from src.services.state import get_or_create_service
from src.services.tests import run_complete_tests
from src.services.base_service import build_service_registry
from src.services.repository import DataCollectionService, BankAccountService
from uuid import uuid4

# Service Registry - automatically generated from service classes
SERVICE_REGISTRY = build_service_registry(
    DataCollectionService,
    BankAccountService,
)

if "__main__" == __name__:
    # Build the service registry
    # print(multi_step_service.description)
    # Load or create service instance
    service_name = "bank_account_advanced"
    user_id = str(uuid4())
    # user_id = "dep_bug_test"
    r = multi_step_service.invoke(
        {
            "user_id": user_id,
            "service_name": service_name,
            "payload": {
                "name": "João",
                "document_type": "CPF",
                "document_number": "12345678901",
                "email": "test@example.com",
            },
        },
    )
    print(json.dumps(r, indent=2, ensure_ascii=False))

    print(r["visual_schematic"])
    print("\n\n")
    # run_complete_tests()
