#!/usr/bin/env python3
"""
Teste automatizado do agente local para verificar erro de additionalProperties
"""

import asyncio
import json
import traceback
from datetime import datetime, timezone


from src.config import env
from src.prompt import prompt_data
from engine.agent import Agent
from src.agent_tools import mcp_tools

# User ID for testing
from uuid import uuid4

user_id = str(uuid4())

# Initialize local agent
local_agent = Agent(
    model="gemini-2.5-flash",
    system_prompt=prompt_data["prompt"],
    temperature=0.7,
    tools=mcp_tools,
    otpl_service=f"eai-langgraph-v{prompt_data['version']}",
)


def parse_tool_calls(message):
    """Extract and display tool calls from message"""
    tool_calls = getattr(message, "tool_calls", [])
    if tool_calls:
        print("   🔧 TOOL CALLS:")
        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "unknown")
            tool_args = tool_call.get("args", {})
            print(f"      📞 Tool: {tool_name}")
            print(
                f"      📋 Args: {json.dumps(tool_args, indent=8, ensure_ascii=False)}"
            )
    return tool_calls


async def test_agent_with_message(message_text: str):
    """Test the agent with a specific message"""
    print(f"\n{'='*80}")
    print(f"🧪 TESTING MESSAGE: {message_text}")
    print(f"{'='*80}")

    # Prepare the data
    data = {
        "messages": [{"role": "human", "content": message_text}],
    }

    config = {"configurable": {"thread_id": user_id}}

    try:
        start_time = datetime.now(timezone.utc)
        # Query the agent
        result = await local_agent.async_query(input=data, config=config)

        print(f"\n📊 RESPONSE ANALYSIS:")
        print(f"   Status: {'✅ Success' if result else '❌ Failed'}")

        if result and "messages" in result:
            messages = result["messages"]
            print(f"   Message count: {len(messages)}")

            # Look for tool calls and responses
            for i, message in enumerate(messages):
                msg_type = message.__class__.__name__
                print(f"\n   📨 Message #{i+1} ({msg_type}):")

                if "AIMessage" in msg_type:
                    tool_calls = parse_tool_calls(message)
                    if message.content:
                        print(f"      💬 Content: {message.content}")

                elif "ToolMessage" in msg_type:
                    tool_name = getattr(message, "name", "unknown")
                    tool_content = message.content
                    print(f"      🛠️  Tool: {tool_name}")

                    # Check for schema-related content
                    if (
                        "schema" in tool_content.lower()
                        or "additionalproperties" in tool_content.lower()
                    ):
                        print(f"      ⚠️  Schema content detected!")
                        print(
                            f"      📄 Content: {json.dumps(tool_content, indent=2, ensure_ascii=False)}"
                        )

                    # Try to parse as JSON to see schema structure
                    try:
                        if tool_content.strip().startswith("{"):
                            parsed = json.loads(tool_content)
                            if "next_steps_schema" in parsed:
                                schema = parsed["next_steps_schema"]
                                print(f"      📋 Schema structure:")
                                print(f"         Type: {schema.get('type', 'unknown')}")
                                print(
                                    f"         Properties: {list(schema.get('properties', {}).keys())}"
                                )
                                print(
                                    f"         Required: {schema.get('required', [])}"
                                )

                                # Check for invalid schema properties
                                for prop_name, prop_schema in schema.get(
                                    "properties", {}
                                ).items():
                                    if "required" in prop_schema:
                                        print(
                                            f"      ❌ ERROR: Property '{prop_name}' has invalid 'required' field!"
                                        )
                                    if "additionalProperties" in prop_schema:
                                        print(
                                            f"      ❌ ERROR: Property '{prop_name}' has 'additionalProperties' field!"
                                        )
                    except json.JSONDecodeError:
                        pass

        end_time = datetime.now(timezone.utc)
        execution_time = (end_time - start_time).total_seconds()
        print(f"\n⏱️  Execution time: {execution_time:.3f}s")

        return result

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        traceback.print_exc()
        return None


async def run_agent_tests():
    """Run a series of predefined tests"""
    print("🚀 TESTE AUTOMATIZADO DO AGENTE LOCAL")
    print("Verificando erro 'additionalProperties' no schema")
    print("=" * 80)

    # Predefined test messages for testing the refactored bank_account workflow
    test_messages = [
        "preciso abrir uma conta bancária",
        "meu nome é João Silva e email joao@test.com",
        "quero conta corrente",
        "quero fazer um depósito",
        "500 reais",
        "quero ver meu saldo",
    ]

    results = []
    start_time = datetime.now(timezone.utc)

    for i, message in enumerate(test_messages, 1):
        print(f"\n🧪 TEST {i}/{len(test_messages)}")
        result = await test_agent_with_message(message)
        results.append(
            {"message": message, "success": result is not None, "result": result}
        )

        # Small delay between tests
        await asyncio.sleep(1)

    # Summary
    print(f"\n{'='*80}")
    print("📊 TEST SUMMARY")
    print(f"{'='*80}")

    successful_tests = sum(1 for r in results if r["success"])
    total_tests = len(results)

    print(f"✅ Successful tests: {successful_tests}/{total_tests}")
    print(f"❌ Failed tests: {total_tests - successful_tests}/{total_tests}")

    for i, result in enumerate(results, 1):
        status = "✅" if result["success"] else "❌"
        print(f"   {status} Test {i}: {result['message']}")

    print(
        f"\n🎯 Final Status: {'All tests passed!' if successful_tests == total_tests else 'Some tests failed'}"
    )
    end_time = datetime.now(timezone.utc)
    execution_time = (end_time - start_time).total_seconds()
    print(f"\n⏱️  Total execution time: {execution_time:.3f}s")


if __name__ == "__main__":
    asyncio.run(run_agent_tests())
