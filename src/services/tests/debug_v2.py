#!/usr/bin/env python3
"""
Debug script for V2 service behavior.
"""

import os
import json
from src.services.tool import multi_step_service
from src.services.repository.bank_account_service_v2 import BankAccountServiceV2

def clean_state(user_id):
    """Remove test state file."""
    state_file = f"src/services/data/{user_id}.json"
    if os.path.exists(state_file):
        os.remove(state_file)

def debug_existing_user():
    """Debug the existing user flow step by step."""
    print("🔍 DEBUGGING EXISTING USER FLOW")
    print("=" * 50)
    
    # Register the service
    from src.services.tool import _services
    _services["bank_account_opening_v2"] = BankAccountServiceV2
    
    user_id = 'debug_existing'
    service_name = 'bank_account_opening_v2'
    clean_state(user_id)
    
    print("📝 Step 1: Sending user info for existing user...")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {
            'user_info.name': 'User Existente', 
            'user_info.email': 'existing@example.com'
        }
    })
    
    if result['status'] == 'FAILED':
        print("📝 Step 2: User recognized! Now choosing to check balance...")
        result = multi_step_service.invoke({
            "service_name": service_name,
            "user_id": user_id,
            "payload": {'ask_action': {'action': 'balance'}}
        })
    
    print(f"   Status: {result['status']}")
    data = result['current_data']['data'] if 'data' in result['current_data'] else {}
    print(f"   Current data: {data}")
    print(f"   user_info.name in data: {data.get('user_info', {}).get('name', 'NOT FOUND')}")
    print(f"   user_info.email in data: {data.get('user_info', {}).get('email', 'NOT FOUND')}")
    print(f"   Completed steps: {result['current_data'].get('_internal', {}).get('completed_steps', {})}")
    print(f"   Next step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    print(f"   Error: {result.get('error_message', 'None')}")
    
    if result['next_step_info']:
        print(f"   Next step description: {result['next_step_info']['description']}")
    
    print("\n🔍 Full result:")
    print(json.dumps(result, indent=2))
    
    # Let's try again to trigger the action
    if result['status'] == 'IN_PROGRESS' and result['next_step_info']:
        print("\n📝 Step 2: Triggering empty payload to see if action executes...")
        result2 = multi_step_service.invoke({
            "service_name": service_name,
            "user_id": user_id,
            "payload": {}
        })
        print(f"   Status: {result2['status']}")
        print(f"   Next step: {result2['next_step_info']['step_name'] if result2['next_step_info'] else 'None'}")
        print(f"   Error: {result2.get('error_message', 'None')}")
        
        print("\n🌳 Execution tree after empty payload:")
        print(result2['execution_summary']['tree'])
        
        # More detailed debug: Let's check if check_account should be executable
        print(f"\n🔍 check_account dependencies:")
        print(f"   Depends on: user_info")
        print(f"   user_info is complete: {result2['current_data']['_internal']['completed_steps'].get('user_info', False)}")
        
        # The issue might be the action should execute now
        print("\n📝 Step 3: Let's manually try to trigger action by sending nothing...")
        result3 = multi_step_service.invoke({
            "service_name": service_name,
            "user_id": user_id,
            "payload": {}
        })
        print(f"   Status: {result3['status']}")
        print(f"   Error: {result3.get('error_message', 'None')}")
        if result3['status'] == 'IN_PROGRESS':
            print("🌳 Still not executing action - tree:")
            print(result3['execution_summary']['tree'])

if __name__ == "__main__":
    debug_existing_user()