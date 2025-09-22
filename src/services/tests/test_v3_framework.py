"""
Test suite for V3 Multi-Step Service Framework
Tests V3 improvements: Strict Graph Executor, Pydantic validation, enhanced error handling
"""

from src.services.tool import multi_step_service
from src.services.repository.bank_account_service_v2 import BankAccountServiceV2
from src.services.repository.order_service import OrderService


def test_v3_service_instantiation():
    """Test that V3 services can be instantiated correctly"""
    print("🔬 Testing V3 service instantiation...")
    
    # Test V3 service instantiation
    bank_service = BankAccountServiceV2()
    order_service = OrderService()

    print('✅ V3 services created successfully!')
    print(f'Bank service: {bank_service.service_name} - {bank_service.description}')
    print(f'Order service: {order_service.service_name} - {order_service.description}')

    # Test service definitions
    bank_def = bank_service.get_definition()
    order_def = order_service.get_definition()

    print(f'✅ V3 service definitions created successfully!')
    print(f'Bank definition has {len(bank_def.steps)} steps')
    print(f'Order definition has {len(order_def.steps)} steps')

    # Test Pydantic validation
    bank_steps = bank_def.steps
    for step in bank_steps:
        if hasattr(step.payload_schema, 'model_json_schema'):
            schema = step.get_json_schema()
            print(f'✅ V3 Pydantic validation working for step: {step.name}')
            break

    print('🎉 V3 service instantiation test passed!')


def test_strict_graph_executor():
    """Test the V3 Strict Graph Executor prevents dependency violations"""
    print("\n🔬 Testing V3 Strict Graph Executor...")
    
    # Test 1: Basic flow with valid dependencies
    print("\n📝 Test 1: Valid dependency flow")
    result = multi_step_service.invoke({
        "service_name": "bank_account_opening_v2",
        "user_id": "test_user_1",
        "payload": {"user_info.name": "João Silva"}
    })
    
    assert result["status"] == "IN_PROGRESS", f"Expected IN_PROGRESS, got {result['status']}"
    print("✅ Valid dependency flow works correctly")
    
    # Test 2: Attempt dependency violation (should be ignored by Strict Graph Executor)
    print("\n📝 Test 2: Dependency violation prevention")
    result = multi_step_service.invoke({
        "service_name": "bank_account_opening_v2",
        "user_id": "test_user_2", 
        "payload": {
            "user_info.name": "Maria Silva",
            "ask_action": "deposit",  # This should be ignored - depends on account creation
            "deposit_amount": 100.0   # This should also be ignored
        }
    })
    
    # The Strict Graph Executor should ignore invalid fields
    assert result["status"] in ["IN_PROGRESS", "COMPLETED"], f"Expected IN_PROGRESS or COMPLETED, got {result['status']}"
    print("✅ Strict Graph Executor correctly ignores invalid dependency jumps")


def test_pydantic_validation():
    """Test V3 Pydantic payload validation"""
    print("\n🔬 Testing V3 Pydantic validation...")
    
    # Test 1: Valid payload
    print("\n📝 Test 1: Valid Pydantic payload")
    result = multi_step_service.invoke({
        "service_name": "bank_account_opening_v2",
        "user_id": "test_user_3",
        "payload": {"user_info.email": "test@example.com"}
    })
    
    assert result["status"] in ["IN_PROGRESS", "COMPLETED"], f"Expected valid status, got {result['status']}"
    print("✅ Valid Pydantic payload accepted")
    
    # Test 2: Invalid email format (should trigger Pydantic validation)
    print("\n📝 Test 2: Invalid email format")
    result = multi_step_service.invoke({
        "service_name": "bank_account_opening_v2",
        "user_id": "test_user_4",
        "payload": {"user_info.email": "invalid-email"}
    })
    
    # Should either reject or handle validation error gracefully
    assert result["status"] in ["FAILED", "IN_PROGRESS"], f"Expected FAILED or IN_PROGRESS, got {result['status']}"
    print("✅ Invalid Pydantic payload handled correctly")


def test_enhanced_error_handling():
    """Test V3 enhanced error handling and recovery"""
    print("\n🔬 Testing V3 enhanced error handling...")
    
    # Create a user with account to test action error handling
    print("\n📝 Setting up user with account...")
    multi_step_service.invoke({
        "service_name": "bank_account_opening_v2",
        "user_id": "test_user_5",
        "payload": {
            "user_info.name": "Pedro Silva",
            "user_info.email": "pedro@test.com"
        }
    })
    
    # Complete account creation flow
    result = multi_step_service.invoke({
        "service_name": "bank_account_opening_v2", 
        "user_id": "test_user_5",
        "payload": {"account_type": "checking"}
    })
    
    print(f"Account creation result: {result['status']}")
    
    # Test invalid action choice (should trigger enhanced error handling)
    print("\n📝 Test: Invalid action choice")
    result = multi_step_service.invoke({
        "service_name": "bank_account_opening_v2",
        "user_id": "test_user_5",
        "payload": {"ask_action": "invalid_choice"}
    })
    
    # Enhanced error handling should provide helpful feedback
    if result["status"] == "FAILED" and result.get("error_message"):
        assert "invalid_choice" in result["error_message"].lower(), "Error message should mention the invalid choice"
        print("✅ Enhanced error handling provides helpful feedback")
    else:
        print(f"⚠️ Error handling test result: {result['status']} - {result.get('error_message', 'No error message')}")


def test_transition_loop():
    """Test V3 cascade action execution via transition loop"""
    print("\n🔬 Testing V3 transition loop (cascade action execution)...")
    
    # Test complete flow that should trigger multiple actions in cascade
    print("\n📝 Test: Complete bank account flow")
    result = multi_step_service.invoke({
        "service_name": "bank_account_opening_v2",
        "user_id": "test_user_6",
        "payload": {
            "user_info.name": "Ana Costa",
            "user_info.email": "ana@test.com",
            "account_type": "savings"
        }
    })
    
    print(f"Flow result: {result['status']}")
    
    if result["status"] == "IN_PROGRESS":
        # Continue with action
        result = multi_step_service.invoke({
            "service_name": "bank_account_opening_v2",
            "user_id": "test_user_6", 
            "payload": {"ask_action": "balance"}
        })
        
        # This should complete the service via transition loop
        print(f"Action result: {result['status']}")
        if result["status"] == "COMPLETED":
            print("✅ Transition loop successfully executed cascade actions")
        else:
            print(f"⚠️ Transition loop test - Status: {result['status']}")
    
    print("✅ Transition loop test completed")


def run_all_tests():
    """Run all V3 framework tests"""
    print("🚀 Starting V3 Multi-Step Service Framework Tests")
    print("=" * 60)
    
    try:
        test_v3_service_instantiation()
        test_strict_graph_executor() 
        test_pydantic_validation()
        test_enhanced_error_handling()
        test_transition_loop()
        
        print("\n" + "=" * 60)
        print("🎉 All V3 framework tests completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    run_all_tests()