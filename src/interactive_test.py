import traceback
import asyncio
import json
from sys import argv
from datetime import datetime, timezone

import vertexai
from vertexai import agent_engines

from src.config import env
from src.prompt import prompt_data
from engine.agent import Agent
from engine.orchestrated_agent import OrchestratedAgent
from engine.services.identification_agent import create_identification_agent
from engine.workflows.user_identification import user_identification_workflow
from src.tools import mcp_tools

vertexai.init(
    project=env.PROJECT_ID,
    location=env.LOCATION,
    staging_bucket=env.GCS_BUCKET,
)


def get_agent():
    return agent_engines.get(
        f"projects/{env.PROJECT_NUMBER}/locations/{env.LOCATION}/reasoningEngines/{env.REASONING_ENGINE_ID}"
    )


user_id = "bruno_teste_003"


# Initialize agents
remote_agent = get_agent()

local_agent = Agent(
    model="gemini-2.5-flash",
    system_prompt=prompt_data["prompt"],
    temperature=0.7,
    tools=mcp_tools,
    otpl_service=f"eai-langgraph-v{prompt_data["version"]}",
)

# Enhanced orchestrated agent with workflows and service agents
orchestrated_agent = OrchestratedAgent(
    model="gemini-2.5-flash",
    system_prompt=prompt_data["prompt"],
    tools=mcp_tools,
    temperature=0.7
)

# Identification-specific agents for comparison
identification_agent = create_identification_agent()


def parse_agent_response(response, is_local=False, start_time=None):
    """Parse the agent response and show all steps"""
    print("\n" + "=" * 60)
    print("🤖 AGENT EXECUTION STEPS")
    print("=" * 60)

    if is_local:
        # Local agent returns LangChain message objects directly
        messages = response.get("messages", [])

        previous_timestamp = None
        total_execution_time = None

        # Calcular tempo total se start_time foi fornecido
        if start_time and messages:
            # Pegar timestamp da última mensagem
            last_message = messages[-1]
            last_timestamp_str = getattr(last_message, "additional_kwargs", {}).get(
                "timestamp"
            )
            if last_timestamp_str and last_timestamp_str != "No timestamp":
                try:
                    last_timestamp = datetime.fromisoformat(
                        last_timestamp_str.replace("Z", "+00:00")
                    )
                    total_execution_time = (last_timestamp - start_time).total_seconds()
                except:
                    pass

        for i, message in enumerate(messages):
            msg_type = message.__class__.__name__

            # Extrair timestamp do additional_kwargs se existir
            timestamp_str = getattr(message, "additional_kwargs", {}).get(
                "timestamp", "No timestamp"
            )

            # Calcular tempo desde a mensagem anterior
            time_since_last = None
            if timestamp_str != "No timestamp":
                try:
                    current_timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                    if previous_timestamp:
                        time_since_last = (
                            current_timestamp - previous_timestamp
                        ).total_seconds()
                    previous_timestamp = current_timestamp
                except:
                    pass

            if "HumanMessage" in msg_type:
                print(f"\n👤 USER MESSAGE #{i+1}:")
                print(f"   ⏰ Timestamp: {timestamp_str}")
                if time_since_last:
                    print(f"   ⏱️  Time since last: {time_since_last:.3f}s")
                print(f"   {message.content}")

            elif "AIMessage" in msg_type:
                print(f"\n🤖 AI RESPONSE #{i+1}:")
                print(f"   ⏰ Timestamp: {timestamp_str}")
                if time_since_last:
                    print(f"   ⏱️  Time since last: {time_since_last:.3f}s")

                # Check for tool calls
                tool_calls = getattr(message, "tool_calls", [])
                if tool_calls:
                    print("   🔧 TOOL CALLS:")
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("name", "unknown")
                        tool_args = tool_call.get("args", {})
                        print(f"      📞 Calling: {tool_name}")
                        print(f"      📋 Arguments: {json.dumps(tool_args, indent=8)}")

                # Show AI content if any
                if message.content:
                    print(f"   💬 Response: {message.content}")

                # Show usage metadata
                usage = getattr(message, "usage_metadata", {})
                if usage:
                    total_tokens = usage.get("total_tokens", 0)
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    print(
                        f"   📊 Tokens: {input_tokens} in, {output_tokens} out, {total_tokens} total"
                    )

            elif "ToolMessage" in msg_type:
                print(f"\n🔧 TOOL RESPONSE #{i+1}:")
                tool_name = getattr(message, "name", "unknown")
                tool_content = message.content
                print(f"   ⏰ Timestamp: {timestamp_str}")
                if time_since_last:
                    print(f"   ⏱️  Time since last: {time_since_last:.3f}s")
                print(f"   🛠️  Tool: {tool_name}")
                print(f"   📄 Response: {tool_content}")

        # Mostrar tempo total no final
        if total_execution_time:
            print(f"\n📈 EXECUTION SUMMARY:")
            print(f"   🎯 Total execution time: {total_execution_time:.3f}s")
            if start_time:
                actual_wall_time = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()
                print(f"   🕐 Actual wall clock time: {actual_wall_time:.3f}s")
                print(
                    f"   📊 Efficiency: {(total_execution_time/actual_wall_time*100):.1f}% (message timestamps vs wall clock)"
                )
    else:
        # Remote agent returns direct message objects
        if "messages" not in response:
            print("❌ Unexpected response format")
            return

        messages = response["messages"]

        for i, message in enumerate(messages):
            msg_type = message.get("type", "unknown")
            content = message.get("content", "")

            if msg_type == "human":
                print(f"\n👤 USER MESSAGE #{i+1}:")
                print(f"   {content}")

            elif msg_type == "ai":
                print(f"\n🤖 AI RESPONSE #{i+1}:")

                # Check for tool calls
                tool_calls = message.get("tool_calls", [])
                if tool_calls:
                    print("   🔧 TOOL CALLS:")
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("name", "unknown")
                        tool_args = tool_call.get("args", {})
                        print(f"      📞 Calling: {tool_name}")
                        print(f"      📋 Arguments: {json.dumps(tool_args, indent=8)}")

                # Show AI content if any
                if content:
                    print(f"   💬 Response: {content}")

                # Show usage metadata
                usage = message.get("usage_metadata", {})
                if usage:
                    total_tokens = usage.get("total_tokens", 0)
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    print(
                        f"   📊 Tokens: {input_tokens} in, {output_tokens} out, {total_tokens} total"
                    )

            elif msg_type == "tool":
                print(f"\n🔧 TOOL RESPONSE #{i+1}:")
                tool_name = message.get("name", "unknown")
                tool_content = message.get("content", "")
                tool_status = message.get("status", "unknown")

                print(f"   🛠️  Tool: {tool_name}")
                print(f"   📊 Status: {tool_status}")
                print(f"   📄 Response: {tool_content}")


async def interactive_chat(agent_type="local"):
    """Start an interactive chat session."""
    
    # Select agent based on type
    if agent_type == "remote":
        agent = remote_agent
        agent_name = "Remote Agent"
        use_local = False
    elif agent_type == "orchestrated":
        agent = orchestrated_agent
        agent_name = "Orchestrated Agent (Workflows + Service Agents)"
        use_local = True
    elif agent_type == "identification":
        agent = identification_agent
        agent_name = "Identification Agent (Service Agent Approach)"
        use_local = True
    elif agent_type == "workflow":
        agent = user_identification_workflow
        agent_name = "User Identification Workflow (Workflow Approach)"
        use_local = True
    else:  # local
        agent = local_agent
        agent_name = "Local Agent (Original)"
        use_local = True

    print(f"🤖 EAI {agent_name} Interactive Chat")
    print("=" * 60)
    
    # Show specific instructions based on agent type
    if agent_type == "orchestrated":
        print("🎯 Test the hybrid architecture with intelligent routing!")
        print("💡 Try: 'I need to identify myself' or 'I want to pay my IPTU'")
    elif agent_type == "identification":
        print("🎯 Test the service agent approach for user identification!")
        print("💡 Try: 'I need to identify myself to access municipal services'")
    elif agent_type == "workflow":
        print("🎯 Test the workflow approach for user identification!")
        print("💡 This will run the structured workflow directly")
    
    print("Type 'quit' to exit, 'help' for commands, 'switch' to change agent")
    print()

    while True:
        try:
            user_input = input("\n👤 You: ").strip()

            if user_input.lower() == "quit":
                print("👋 Goodbye!")
                break
            elif user_input.lower() == "help":
                print("\n📋 Available commands:")
                print("  - Type your message to chat with the agent")
                print("  - 'quit' to exit")
                print("  - 'help' to show this help")
                print("  - 'clear' to clear the screen")
                print("  - 'switch' to change agent type")
                print("\n🎯 Agent-specific tips:")
                if agent_type == "orchestrated":
                    print("  - Ask for user identification, tax services, infrastructure reports")
                    print("  - The agent will route to appropriate workflows/agents")
                elif agent_type == "identification":
                    print("  - Provide your CPF, email, and name when asked")
                    print("  - Try invalid data to see validation in action")
                elif agent_type == "workflow":
                    print("  - The workflow will guide you step by step")
                    print("  - You can exit at any point by saying 'exit'")
                continue
            elif user_input.lower() == "clear":
                print("\n" * 50)
                continue
            elif user_input.lower() == "switch":
                print("\n🔄 Available agent types:")
                print("  1. local - Original local agent")
                print("  2. remote - Remote deployed agent")
                print("  3. orchestrated - Enhanced agent with workflows + service agents")
                print("  4. identification - Service agent for user identification")
                print("  5. workflow - Direct workflow for user identification")
                
                choice = input("\nSelect agent type (1-5): ").strip()
                agent_map = {
                    "1": "local", "2": "remote", "3": "orchestrated", 
                    "4": "identification", "5": "workflow"
                }
                
                if choice in agent_map:
                    new_agent_type = agent_map[choice]
                    print(f"\n🔄 Switching to {new_agent_type} agent...")
                    return await interactive_chat(new_agent_type)
                else:
                    print("❌ Invalid choice. Staying with current agent.")
                continue
            elif not user_input:
                continue

            print(f"\n🔄 Processing: {user_input}")

            # Handle different agent types
            start_time = datetime.now(timezone.utc)
            
            try:
                if agent_type == "workflow":
                    # Handle workflow directly
                    print("🔄 Running user identification workflow...")
                    config = {"configurable": {"thread_id": user_id}}
                    
                    # For workflow, we need to simulate the workflow execution
                    # In practice, this would be integrated through the orchestrated agent
                    print("💡 Workflow execution would be handled by the orchestrated agent.")
                    print("🔄 Try the 'orchestrated' agent to see workflow integration!")
                    continue
                    
                elif agent_type == "identification":
                    # Handle identification agent
                    result = identification_agent.run(user_input)
                    print(f"\n🤖 Identification Agent Response:")
                    print(f"   💬 {result['response']}")
                    if result.get('cpf'):
                        print(f"   📄 CPF: {result['cpf']}")
                    if result.get('email'):
                        print(f"   📧 Email: {result['email']}")
                    if result.get('name'):
                        print(f"   👤 Name: {result['name']}")
                    if result.get('is_complete'):
                        print("   ✅ Identification complete!")
                    continue
                    
                else:
                    # Handle regular agents (local, remote, orchestrated)
                    data = {
                        "messages": [{"role": "human", "content": user_input}],
                    }

                    config = {"configurable": {"thread_id": user_id}}
                    
                    if agent_type == "remote":
                        result = await remote_agent.async_query(input=data, config=config)
                    elif agent_type == "orchestrated":
                        result = await orchestrated_agent.async_query(input=data, config=config)
                    else:  # local
                        result = await local_agent.async_query(input=data, config=config)
                    
                    # Parse and display the result
                    parse_agent_response(result, is_local=use_local, start_time=start_time)

            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                traceback.print_exc()

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {str(e)}")


if __name__ == "__main__":
    print("🚀 EAI Agent Interactive Testing Tool")
    print("=" * 50)
    print("\n🎯 Available Agents for Testing:")
    print("  1. local - Original local agent")
    print("  2. remote - Remote deployed agent") 
    print("  3. orchestrated - Enhanced agent with workflows + service agents")
    print("  4. identification - Service agent for user identification")
    print("  5. workflow - Direct workflow for user identification")
    
    print("\n💡 Test Scenarios:")
    print("  🔹 User Identification:")
    print("     - Try: 'I need to identify myself'")
    print("     - Compare agent vs workflow approaches")
    print("  🔹 Municipal Services:")
    print("     - Try: 'I want to pay my IPTU taxes'")
    print("     - Try: 'Report a broken street light'")
    print("  🔹 Routing Intelligence:")
    print("     - Test how orchestrated agent routes requests")
    
    # Get agent type from command line or prompt user
    if len(argv) > 1:
        agent_type_map = {
            "local": "local",
            "remote": "remote", 
            "orchestrated": "orchestrated",
            "identification": "identification",
            "workflow": "workflow"
        }
        agent_type = agent_type_map.get(argv[1], "local")
    else:
        print("\n🔧 Select agent type:")
        choice = input("Enter choice (1-5) or agent name: ").strip()
        
        choice_map = {
            "1": "local", "2": "remote", "3": "orchestrated",
            "4": "identification", "5": "workflow",
            "local": "local", "remote": "remote", "orchestrated": "orchestrated",
            "identification": "identification", "workflow": "workflow"
        }
        
        agent_type = choice_map.get(choice, "local")
    
    print(f"\n🎯 Starting with {agent_type} agent...")
    asyncio.run(interactive_chat(agent_type=agent_type))
