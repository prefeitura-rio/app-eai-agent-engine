from openai import OpenAI
import json

from src.config import env

client = OpenAI(
    api_key=env.RIO_API_KEY,
    base_url="https://rio-api-test.onrender.com/v1",
)

tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Fetch weather by city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
            "additionalProperties": False,
        },
    },
}]

messages = [{"role": "user", "content": "Use the weather tool for London right now."}]

resp1 = client.chat.completions.create(
    model="rio-2.5-fast",
    messages=messages,
    tools=tools,
    tool_choice="auto",
)

call = resp1.choices[0].message.tool_calls[0]
messages.append({
    "role": "assistant",
    "tool_calls": [{
        "id": call.id,
        "type": call.type,
        "function": {"name": call.function.name, "arguments": call.function.arguments},
    }],
})
messages.append({
    "role": "tool",
    "tool_call_id": call.id,
    "content": json.dumps({"status": "sunny", "city": "London"}),
})

resp2 = client.chat.completions.create(
    model="rio-2.5-fast",
    messages=messages,
)
print(resp2.choices[0].message.content)