"""
Example usage of the Orchestrated Agent with service routing.
"""

import asyncio
from engine import OrchestratedAgent
from src.tools import mcp_tools
from src.prompt import prompt_data


async def main():
    """
    Example demonstrating the orchestrated agent with service routing.
    """
    
    # Create orchestrated agent with enhanced routing capabilities
    agent = OrchestratedAgent(
        model="gemini-2.5-flash",
        system_prompt=prompt_data["prompt"],
        tools=mcp_tools,
        temperature=0.7
    )
    
    # Configuration for conversation threading
    config = {"configurable": {"thread_id": "example-thread-123"}}
    
    print("🤖 Orchestrated Agent Example")
    print("=" * 50)
    
    # Example 1: Tax service request (should route to tax agent)
    print("\n📋 Example 1: Tax Service Request")
    print("User: Preciso da segunda via do IPTU do meu imóvel")
    
    try:
        result = await agent.async_query(
            input={"messages": [{"role": "user", "content": "Preciso da segunda via do IPTU do meu imóvel"}]},
            config=config
        )
        print(f"Agent: {result['messages'][-1].content}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "-" * 50)
    
    # Example 2: Infrastructure request (should route to infrastructure agent)
    print("\n🚧 Example 2: Infrastructure Service Request")
    print("User: Tem um buraco na rua da minha casa, como faço para reportar?")
    
    try:
        result = await agent.async_query(
            input={"messages": [{"role": "user", "content": "Tem um buraco na rua da minha casa, como faço para reportar?"}]},
            config=config
        )
        print(f"Agent: {result['messages'][-1].content}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "-" * 50)
    
    # Example 3: General information request (should use existing tools)
    print("\n🔍 Example 3: General Information Request")
    print("User: Onde fica a prefeitura do Rio de Janeiro?")
    
    try:
        result = await agent.async_query(
            input={"messages": [{"role": "user", "content": "Onde fica a prefeitura do Rio de Janeiro?"}]},
            config=config
        )
        print(f"Agent: {result['messages'][-1].content}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Example completed!")


def sync_example():
    """
    Synchronous example for testing.
    """
    # Create orchestrated agent
    agent = OrchestratedAgent(
        model="gemini-2.5-flash",
        system_prompt=prompt_data["prompt"],
        tools=mcp_tools,
        temperature=0.7
    )
    
    # Configuration for conversation threading
    config = {"configurable": {"thread_id": "sync-example-456"}}
    
    print("🤖 Orchestrated Agent Sync Example")
    print("=" * 50)
    
    # Simple tax query
    print("\nUser: Como faço para pagar o IPTU?")
    
    try:
        result = agent.query(
            input={"messages": [{"role": "user", "content": "Como faço para pagar o IPTU?"}]},
            config=config
        )
        print(f"Agent: {result['messages'][-1].content}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("Choose example to run:")
    print("1. Async example (recommended)")
    print("2. Sync example")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        asyncio.run(main())
    elif choice == "2":
        sync_example()
    else:
        print("Invalid choice. Running async example...")
        asyncio.run(main())
