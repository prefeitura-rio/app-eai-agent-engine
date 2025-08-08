import traceback
import asyncio
import json
from sys import argv

import vertexai
from vertexai import agent_engines

from src.config import env
from src.prompt import SYSTEM_PROMPT
from engine.agent import Agent
from src.tools import mcp_tools

vertexai.init(
    project=env.PROJECT_ID,
    location=env.LOCATION,
    staging_bucket=env.GCS_BUCKET_STAGING,
)


def get_agent():
    return agent_engines.get(
        f"projects/{env.PROJECT_NUMBER}/locations/{env.LOCATION}/reasoningEngines/{env.REASONING_ENGINE_ID}"
    )


user_id = "user_123"


# Initialize agents
remote_agent = get_agent()

local_agent = Agent(
    model="gemini-2.5-flash",
    system_prompt=SYSTEM_PROMPT,
    temperature=0.7,
    tools=mcp_tools,
)


def parse_agent_response(response, is_local=False):
    """Parse the agent response and show all steps."""
    print("\n" + "=" * 60)
    print("🤖 AGENT EXECUTION STEPS")
    print("=" * 60)

    if is_local:
        # Local agent returns LangChain message objects directly
        messages = response.get("messages", [])

        for i, message in enumerate(messages):
            msg_type = message.__class__.__name__

            if "HumanMessage" in msg_type:
                print(f"\n👤 USER MESSAGE #{i+1}:")
                print(f"   {message.content}")

            elif "AIMessage" in msg_type:
                print(f"\n🤖 AI RESPONSE #{i+1}:")

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

                print(f"   🛠️  Tool: {tool_name}")
                print(f"   📄 Response: {tool_content}")
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


async def interactive_chat(use_local=False):
    """Start an interactive chat session."""
    agent = local_agent if use_local else remote_agent
    agent_name = "Local Agent" if use_local else "Remote Agent"

    print(f"🤖 EAI {agent_name} Interactive Chat")
    print("=" * 60)
    print("Type 'quit' to exit, 'help' for commands")
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
                continue
            elif user_input.lower() == "clear":
                print("\n" * 50)
                continue
            elif not user_input:
                continue

            print(f"\n🔄 Processing: {user_input}")

            # Prepare the data
            data = {
                "messages": [{"role": "human", "content": user_input}],
            }

            config = {"configurable": {"thread_id": user_id}}
            try:
                # Use async_query for both agents
                if use_local:
                    result = await local_agent.async_query(input=data, config=config)
                else:
                    result = await remote_agent.async_query(input=data, config=config)
                print(result)
                # Parse and display the result
                parse_agent_response(result, is_local=use_local)

            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                traceback.print_exc()

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {str(e)}")


if __name__ == "__main__":
    use_local = len(argv) > 1 and argv[1] == "local"
    asyncio.run(interactive_chat(use_local=use_local))
