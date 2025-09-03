"""
Test 1: MC Agent with Workflow Routing

This test shows the orchestrated agent routing to workflows for user identification.
The MC agent will have workflow tools and route user identification requests to the workflow.
"""

import sys
import os
import asyncio
from datetime import datetime, timezone
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.orchestrated_agent import OrchestratedAgent
from src.tools import mcp_tools
from src.prompt import prompt_data


def create_workflow_routing_agent():
    """
    Create an orchestrated agent that routes to workflows.
    This agent will have workflow tools but no service agent handoffs.
    """
    
    # Enhanced prompt that focuses on workflow routing
    workflow_prompt = prompt_data["prompt"] + """

IMPORTANT ROUTING INSTRUCTIONS:
- For user identification requests, use the user_identification_workflow tool
- Guide users through structured workflow processes
- Workflows provide step-by-step parameter collection with built-in validation
- Use workflows for transactional services (document requests, payments, reports)

Available workflow tools:
- user_identification_workflow: For collecting and validating user CPF, email, and name

Always prefer workflows for structured, transactional processes.
"""
    
    agent = OrchestratedAgent(
        model="gemini-2.5-flash",
        system_prompt=workflow_prompt,
        tools=mcp_tools,  # This includes workflow tools
        temperature=0.7,
        enable_service_agents=False,  # Disable service agent routing
        enable_workflows=True         # Enable workflow routing
    )
    
    return agent


async def test_workflow_routing():
    """Test the workflow routing approach"""
    
    print("🔄 TEST 1: MC Agent → Workflow Routing")
    print("=" * 50)
    print("🎯 Testing orchestrated agent that routes to workflows")
    print("💡 Try: 'I need to identify myself to access municipal services'")
    print()
    
    try:
        agent = create_workflow_routing_agent()
        print("✅ Workflow-routing agent created successfully")
        
        # Interactive session
        user_id = "test_workflow_routing"
        
        while True:
            try:
                user_input = input("\n👤 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit']:
                    print("👋 Goodbye!")
                    break
                elif user_input.lower() == 'help':
                    print("\n📋 Test Commands:")
                    print("  - 'I need to identify myself' - Test workflow routing")
                    print("  - 'I want to access municipal services' - Test workflow routing")
                    print("  - 'quit' - Exit test")
                    continue
                elif not user_input:
                    continue
                
                print(f"\n🔄 Processing with workflow routing...")
                start_time = datetime.now(timezone.utc)
                
                # Prepare request
                data = {
                    "messages": [{"role": "human", "content": user_input}],
                }
                config = {"configurable": {"thread_id": user_id}}
                
                # Get response
                result = await agent.async_query(input=data, config=config)
                
                # Display result
                print(f"\n🤖 MC Agent Response (Workflow Routing):")
                if result and "messages" in result:
                    for message in result["messages"]:
                        if hasattr(message, 'content') and message.content:
                            print(f"   💬 {message.content}")
                        
                        # Check for tool calls (workflow invocations)
                        if hasattr(message, 'tool_calls') and message.tool_calls:
                            print(f"   🔧 Workflow Tools Called:")
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
        print(f"❌ Failed to create workflow-routing agent: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🧪 Testing MC Agent with Workflow Routing")
    print("This test shows how the MC agent routes to workflows for structured processes")
    print()
    
    asyncio.run(test_workflow_routing())
