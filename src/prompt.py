from src.config import env
from loguru import logger
import httpx
import asyncio


async def get_system_prompt_from_api(agent_type: str = "agentic_search") -> str:
    """Obtém o system prompt via API"""
    try:
        base_url = getattr(env, "EAI_AGENT_URL", "http://localhost:8000")
        api_url = f"{base_url}api/v1/system-prompt?agent_type={agent_type}"

        bearer_token = getattr(env, "EAI_AGENT_TOKEN", "")

        headers = {}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(api_url, headers=headers)
            response.raise_for_status()
            data = response.json()

            logger.info(
                f"System prompt obtido via API. version: {data['version']} | agent_type: {data['agent_type']}"
            )
            return data["prompt"]

    except Exception as e:
        logger.warning(
            f"Erro ao obter system prompt via API: {str(e)}. Usando fallback."
        )
        # Fallback para prompt padrão
        return f"""You are an AI assistant for the {agent_type} role.
Follow these guidelines:
1. Answer concisely but accurately
2. Use tools when necessary
3. Focus on providing factual information
4. Be helpful, harmless, and honest"""


SYSTEM_PROMPT = asyncio.run(get_system_prompt_from_api())
