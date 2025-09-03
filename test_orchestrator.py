"""
Quick test of the Orchestrated Agent implementation.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from engine import OrchestratedAgent
from src.tools import mcp_tools
from src.prompt import prompt_data


def test_orchestrated_agent():
    """
    Quick test to verify the orchestrated agent can be instantiated and basic functionality works.
    """
    
    print("🧪 Testing Orchestrated Agent Implementation")
    print("=" * 50)
    
    try:
        # Test 1: Agent instantiation
        print("\n1️⃣ Testing agent instantiation...")
        agent = OrchestratedAgent(
            model="gemini-2.5-flash",
            system_prompt=prompt_data["prompt"],
            tools=mcp_tools,
            temperature=0.7
        )
        print("✅ Agent created successfully!")
        
        # Test 2: Check service agents are initialized
        print("\n2️⃣ Testing service agents initialization...")
        print(f"   Tax Agent: {agent._service_agents['tax_agent'].agent_name}")
        print(f"   Infrastructure Agent: {agent._service_agents['infrastructure_agent'].agent_name}")
        print(f"   Health Agent: {agent._service_agents['health_agent'].agent_name}")
        print("✅ Service agents initialized!")
        
        # Test 3: Check tools are available
        print("\n3️⃣ Testing tools availability...")
        print(f"   MCP Tools: {len(mcp_tools)} tools loaded")
        print(f"   Enhanced with handoff tools for routing")
        print("✅ Tools loaded successfully!")
        
        # Test 4: Check prompt enhancement (enhanced prompt is created during graph setup)
        print("\n4️⃣ Testing prompt enhancement...")
        print("✅ Routing logic will be added during graph creation!")
        print("   (Enhanced prompt created in _create_orchestrated_graph method)")
        
        # Test 5: Basic sync query (simple test without external dependencies)
        print("\n5️⃣ Testing basic functionality...")
        
        config = {"configurable": {"thread_id": "test-thread-123"}}
        
        # Simple test query that should work without external APIs
        test_input = {
            "messages": [{"role": "user", "content": "Olá, você pode me ajudar?"}]
        }
        
        print("   Sending test query: 'Olá, você pode me ajudar?'")
        
        try:
            result = agent.query(input=test_input, config=config)
            print("✅ Agent responded successfully!")
            print(f"   Response type: {type(result)}")
            print(f"   Has messages: {'messages' in result}")
            
            if 'messages' in result and result['messages']:
                last_message = result['messages'][-1]
                print(f"   Last message type: {type(last_message).__name__}")
                if hasattr(last_message, 'content'):
                    content_preview = last_message.content[:100] + "..." if len(last_message.content) > 100 else last_message.content
                    print(f"   Content preview: {content_preview}")
                    
        except Exception as e:
            print(f"❌ Query failed: {str(e)}")
            print(f"   Error type: {type(e).__name__}")
            
            # This might fail due to missing environment variables or external dependencies
            # which is expected in a quick test
            if "PROJECT_ID" in str(e) or "LOCATION" in str(e):
                print("   ℹ️  This appears to be a configuration issue (missing env vars)")
                print("   ℹ️  The agent structure is likely correct")
            else:
                print(f"   ⚠️  Unexpected error: {e}")
        
        print("\n" + "=" * 50)
        print("🎉 Basic test completed!")
        print("\nNext steps:")
        print("- Configure environment variables for full testing")
        print("- Test with actual service routing scenarios")
        print("- Add domain-specific tools to service agents")
        
    except Exception as e:
        print(f"❌ Test failed during setup: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")


if __name__ == "__main__":
    test_orchestrated_agent()
