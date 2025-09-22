"""
Centralized test runner for Multi-Step Service Framework
All test executions should go through this file

Usage:
    python src/services/tests/run.py

Configure which tests to run by changing the TEST_MODE variable below.
"""

import sys
import os

# Add project root to Python path for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.tests.test_v3_framework import run_all_tests as run_v3_tests

# ============================================================
# CONFIGURAÇÃO: Altere aqui para escolher quais testes rodar
# ============================================================
TEST_MODE = "v3_framework"  # Opções: "v3_framework", "all", "specific_test"

# Para testes específicos, configure aqui:
SPECIFIC_TESTS = {
    "instantiation": True,     # Test V3 service instantiation  
    "strict_executor": True,   # Test Strict Graph Executor
    "pydantic": True,         # Test Pydantic validation
    "error_handling": True,   # Test enhanced error handling
    "transition_loop": True,  # Test transition loop
    "clean_state": True,      # Test clean state (no execution_tree_complete)
}
# ============================================================


def run_all_tests():
    """Run all available test suites"""
    print("🌟 Running ALL Multi-Step Service Framework Tests")
    print("=" * 70)
    
    success = True
    
    # Run V3 framework tests
    print("\n📦 V3 Framework Tests")
    print("-" * 30)
    if not run_v3_tests():
        success = False
    
    print("\n" + "=" * 70)
    if success:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED!")
    
    return success


def run_v3_framework_tests():
    """Run only V3 framework tests"""
    return run_v3_tests()


def run_specific_tests():
    """Run specific tests based on SPECIFIC_TESTS configuration"""
    from src.services.tests.test_v3_framework import (
        test_v3_service_instantiation,
        test_strict_graph_executor, 
        test_pydantic_validation,
        test_enhanced_error_handling,
        test_transition_loop,
        test_clean_state
    )
    
    print("🎯 Running SPECIFIC Multi-Step Service Framework Tests")
    print("=" * 70)
    
    try:
        if SPECIFIC_TESTS.get("instantiation", False):
            test_v3_service_instantiation()
            
        if SPECIFIC_TESTS.get("strict_executor", False):
            test_strict_graph_executor()
            
        if SPECIFIC_TESTS.get("pydantic", False):
            test_pydantic_validation()
            
        if SPECIFIC_TESTS.get("error_handling", False):
            test_enhanced_error_handling()
            
        if SPECIFIC_TESTS.get("transition_loop", False):
            test_transition_loop()
            
        if SPECIFIC_TESTS.get("clean_state", False):
            test_clean_state()
        
        print("\n" + "=" * 70)
        print("🎉 All specified tests completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Specific test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test runner entry point"""
    print(f"🚀 Test Mode: {TEST_MODE}")
    print(f"📍 Command: python src/services/tests/run.py")
    print()
    
    if TEST_MODE == "v3_framework":
        success = run_v3_framework_tests()
    elif TEST_MODE == "all":
        success = run_all_tests()
    elif TEST_MODE == "specific_test":
        success = run_specific_tests()
    else:
        print(f"❌ Invalid TEST_MODE: {TEST_MODE}")
        print("Valid options: 'v3_framework', 'all', 'specific_test'")
        success = False
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()