"""
Test 2: MC Agent with Service Agent Routing

This test shows the orchestrated agent routing to service agents for user identification.
The MC agent will have handoff tools and route user identification requests to the identification agent.
"""

import sys
import os
import asyncio
from datetime import datetime, timezone
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.orchestrated_agent import OrchestratedAgent
from engine.identification_service_tools import get_identification_service_tools
from src.tools import mcp_tools
from src.prompt import prompt_data


def create_agent_routing_agent():
    """
    Create an orchestrated agent that routes to service agents.
    This agent will have identification service agent tools.
    """
    
    # Enhanced prompt that focuses on service agent routing
    agent_prompt = prompt_data["prompt"] + """

IMPORTANT ROUTING INSTRUCTIONS:
- For user identification requests (when user says they want to identify themselves, need CPF collection, etc.), ALWAYS use the route_to_identification_agent tool
- This provides conversational, adaptive assistance through a specialized identification agent
- Use this tool for any identification-related requests
- The identification agent handles complex scenarios and provides personalized help

Available tools:
- route_to_identification_agent: Use this tool whenever user mentions identification, CPF, email collection, or wants to be identified

ALWAYS use route_to_identification_agent for identification requests - do not try to handle identification yourself.
"""
    
    # Get identification service tools
    identification_tools = get_identification_service_tools()
    all_tools = mcp_tools + identification_tools
    
    agent = OrchestratedAgent(
        model="gemini-2.5-flash",
        system_prompt=agent_prompt,
        tools=all_tools,
        temperature=0.7,
        enable_service_agents=False,   # Disable service agent handoffs
        enable_workflows=False        # Disable workflow routing
    )
    
    return agent


async def test_agent_routing():
    """Test the service agent routing approach"""
    
    print("🤖 TEST 2: MC Agent → Service Agent Routing")
    print("=" * 50)
    print("🎯 Testing orchestrated agent that routes to service agents")
    print("💡 Try: 'I need to identify myself to access municipal services'")
    print()
    
    try:
        agent = create_agent_routing_agent()
        print("✅ Service-agent-routing agent created successfully")
        
        # Interactive session
        user_id = "test_agent_routing4"
        
        while True:
            try:
                user_input = input("\n👤 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit']:
                    print("👋 Goodbye!")
                    break
                elif user_input.lower() == 'help':
                    print("\n📋 Test Commands:")
                    print("  - 'I need to identify myself' - Test agent routing")
                    print("  - 'I want to access municipal services' - Test agent routing")
                    print("  - 'I need tax advice' - Test tax agent routing")
                    print("  - 'quit' - Exit test")
                    continue
                elif not user_input:
                    continue
                
                print(f"\n🔄 Processing with service agent routing...")
                start_time = datetime.now(timezone.utc)
                
                # Prepare request
                data = {
                    "messages": [{"role": "human", "content": user_input}],
                }
                config = {"configurable": {"thread_id": user_id}}
                
                # Get response
                result = await agent.async_query(input=data, config=config)
                
                # Display result
                print(f"\n🤖 MC Agent Response (Service Agent Routing):")
                if result and "messages" in result:
                    for message in result["messages"]:
                        if hasattr(message, 'content') and message.content:
                            print(f"   💬 {message.content}")
                        
                        # Check for tool calls (handoff to service agents)
                        if hasattr(message, 'tool_calls') and message.tool_calls:
                            print(f"   🔧 Service Agent Handoffs:")
                            for tool_call in message.tool_calls:
                                print(f"      📞 {tool_call.get('name', 'unknown')}")
                                print(f"      📋 Args: {tool_call.get('args', {})}")
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                print(f"   ⏱️  Execution time: {execution_time:.3f}s")
                
            except KeyboardInterrupt:
                print("\n\n👋 Test interrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                
    except Exception as e:
        print(f"❌ Failed to create service-agent-routing agent: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🧪 Testing MC Agent with Service Agent Routing")
    print("This test shows how the MC agent routes to service agents for conversational processes")
    print()
    
    asyncio.run(test_agent_routing())
