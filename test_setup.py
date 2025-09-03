"""
Quick validation script to check if all agents can be imported and initialized.
Run this before using the interactive test to ensure everything is working.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test all imports for the interactive testing tool"""
    
    print("🔧 Testing Agent Imports and Initialization")
    print("=" * 50)
    
    try:
        print("📦 Testing basic imports...")
        from src.config import env
        from src.prompt import prompt_data
        from src.tools import mcp_tools
        print("✅ Basic imports successful")
        
        print("\n📦 Testing agent imports...")
        from engine.agent import Agent
        from engine.orchestrated_agent import OrchestratedAgent
        from engine.services.identification_agent import create_identification_agent
        from engine.workflows.user_identification import user_identification_workflow
        print("✅ Agent imports successful")
        
        print("\n🤖 Testing agent initialization...")
        
        # Test local agent
        local_agent = Agent(
            model="gemini-2.5-flash",
            system_prompt=prompt_data["prompt"],
            temperature=0.7,
            tools=mcp_tools,
            otpl_service=f"eai-langgraph-v{prompt_data['version']}",
        )
        print("✅ Local agent initialized")
        
        # Test orchestrated agent
        orchestrated_agent = OrchestratedAgent(
            model="gemini-2.5-flash",
            system_prompt=prompt_data["prompt"],
            tools=mcp_tools,
            temperature=0.7
        )
        print("✅ Orchestrated agent initialized")
        
        # Test identification agent
        identification_agent = create_identification_agent()
        print("✅ Identification agent initialized")
        
        # Test workflow
        workflow_type = type(user_identification_workflow)
        print(f"✅ User identification workflow loaded: {workflow_type}")
        
        print("\n🎉 All tests passed! Interactive testing tool is ready.")
        print("\n🚀 You can now run:")
        print("   uv run src/interactive_test.py")
        print("   or")
        print("   uv run src/interactive_test.py orchestrated")
        print("   or")
        print("   uv run src/interactive_test.py identification")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_imports()
    if success:
        print("\n✅ Ready for interactive testing!")
    else:
        print("\n❌ Fix the errors above before running interactive tests.")
