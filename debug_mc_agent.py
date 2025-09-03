"""
Simple MC Agent Test - Debug version

This creates a simple test to see exactly what's happening with the MC agent routing.
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.orchestrated_agent import OrchestratedAgent
from engine.identification_service_tools import get_identification_service_tools
from src.tools import mcp_tools
from src.prompt import prompt_data


async def simple_test():
    """Simple test to see what's happening"""
    
    print("🔧 MC Agent Debug Test")
    print("=" * 30)
    
    try:
        # Create agent
        identification_tools = get_identification_service_tools()
        all_tools = mcp_tools + identification_tools
        
        print(f"📋 Available tools: {len(all_tools)}")
        for tool in identification_tools:
            print(f"   - {tool.name}: {tool.description}")
        
        agent = OrchestratedAgent(
            model="gemini-2.5-flash",
            system_prompt="Você é um assistente municipal. Para identificação de usuários, use sempre a ferramenta route_to_identification_agent.",
            tools=all_tools,
            temperature=0.7,
            enable_service_agents=False,
            enable_workflows=False
        )
        
        print("✅ Agent created")
        
        # Test multiple messages
        test_messages = [
            "oi, quero me identificar",
            "meu cpf é 11144477735 me chamo Bruno Silva e meu email é bruno@bruno.com"
        ]
        
        for i, test_message in enumerate(test_messages):
            print(f"\n🧪 Test {i+1}: '{test_message}'")
            
            data = {"messages": [{"role": "human", "content": test_message}]}
            config = {"configurable": {"thread_id": f"debug_test_{i}"}}
            
            result = await agent.async_query(input=data, config=config)
            
            if result and "messages" in result:
                # Show only the final AI response
                for message in result["messages"]:
                    if hasattr(message, 'content') and message.content and "AIMessage" in str(type(message)):
                        print(f"   🤖 Response: {message.content}")
                        break
            print("-" * 50)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(simple_test())
