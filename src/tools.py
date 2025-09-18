from typing import List, Optional, Dict, Any
from langchain_core.tools import BaseTool, tool
import asyncio
import json
from pathlib import Path
from datetime import datetime

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.config import env
from src.services import SERVICE_REGISTRY, BaseService


async def get_mcp_tools(
    include_tools: Optional[List[str]] = None, exclude_tools: Optional[List[str]] = None
) -> List[BaseTool]:
    """
    Inicializa o cliente MCP e busca as ferramentas disponíveis de forma assíncrona.

    Args:
        include_tools (List[str], optional): Lista de nomes de ferramentas para incluir.
                                           Se fornecida, apenas essas ferramentas serão retornadas.
        exclude_tools (List[str], optional): Lista de nomes de ferramentas para excluir.
                                           Se fornecida, todas as ferramentas exceto essas serão retornadas.

    Returns:
        List[BaseTool]: Lista de ferramentas disponíveis do servidor MCP, filtrada conforme os parâmetros
    """
    # Initialize default values
    if include_tools is None:
        include_tools = []
    if exclude_tools is None:
        exclude_tools = []

    client = MultiServerMCPClient(
        {
            "rio_mcp": {
                "transport": "streamable_http",
                "url": env.MPC_SERVER_URL,
                "headers": {
                    "Authorization": f"Bearer {env.MPC_API_TOKEN}",
                },
            },
        }
    )
    tools = await client.get_tools()

    # Apply filtering logic
    if include_tools:
        # If include list is not empty, return only tools in the include list
        filtered_tools = [tool for tool in tools if tool.name in include_tools]
    elif exclude_tools:
        # If exclude list is not empty, return all tools except the ones in exclude list
        filtered_tools = [tool for tool in tools if tool.name not in exclude_tools]
    else:
        # If both lists are empty, return all tools
        filtered_tools = tools

    return filtered_tools


# State management
STATE_DIR = Path("service_states")
STATE_DIR.mkdir(exist_ok=True)


def _save_service_state(
    session_id: str, service: BaseService, service_name: str, user_id: str
) -> None:
    """Save service state to file"""
    state_file = STATE_DIR / f"{session_id}.json"
    state_data = {
        "service_class": service.__class__.__name__,
        "service_name": service_name,
        "session_id": service.session_id,
        "user_id": user_id,
        "data": service.data,
        "created_at": service.created_at.isoformat(),
    }
    with open(state_file, "w") as f:
        json.dump(state_data, f, indent=2, ensure_ascii=False)


def _load_service_state(session_id: str) -> Optional[BaseService]:
    """Load service state from file"""
    state_file = STATE_DIR / f"{session_id}.json"
    if not state_file.exists():
        return None

    try:
        with open(state_file, "r") as f:
            state_data = json.load(f)

        # Find service class
        service_class_name = state_data["service_class"]
        service_class = None
        for name, cls in SERVICE_REGISTRY.items():
            if cls.__name__ == service_class_name:
                service_class = cls
                break

        if not service_class:
            return None

        # Recreate service instance
        service = service_class(state_data["session_id"])
        service.data = state_data["data"]
        return service

    except (json.JSONDecodeError, KeyError):
        return None


def _get_or_create_service(service_name: str, session_id: str) -> Optional[BaseService]:
    """Get existing service or create new one"""
    # Try to load existing state
    service = _load_service_state(session_id)
    if service:
        return service

    # Create new service
    service_class = SERVICE_REGISTRY.get(service_name)
    if service_class:
        return service_class(session_id)

    return None


@tool
def multi_step_service(
    service_name: str, step: str, payload: str, user_id: str
) -> Dict[str, Any]:
    """
    PLACE HOLDER - This docstring will be replaced dynamically
    """
    # Generate session_id if starting new service
    if step == "start":
        session_id = f"{service_name}_{int(datetime.now().timestamp())}"
    else:
        # For ongoing services, session_id should be passed somehow
        # For now, we'll try to find the most recent session for this service
        session_files = list(STATE_DIR.glob(f"{service_name}_*.json"))
        if not session_files:
            return {
                "status": "error",
                "message": f"Nenhuma sessão ativa encontrada para {service_name}. Use step='start' para iniciar.",
                "available_services": list(SERVICE_REGISTRY.keys()),
            }

        # Get most recent session
        session_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        session_id = session_files[0].stem

    # Load or create service instance
    service = _get_or_create_service(service_name=service_name, session_id=session_id)

    if not service:
        return {
            "status": "error",
            "message": f"Serviço '{service_name}' não encontrado",
            "available_services": list(SERVICE_REGISTRY.keys()),
        }

    # Handle start step
    if step == "start":
        first_step = service.get_steps()[0]
        result = {
            "status": "started",
            "message": service.get_step_prompt(first_step),
            "next_step": first_step,
            "completed": False,
            "session_id": session_id,
            "steps_info": service.get_steps_info(),
        }
        # Save initial state
        _save_service_state(
            session_id=session_id,
            service=service,
            service_name=service_name,
            user_id=user_id,
        )
        return result

    # Process current step
    result = service.process_step(step, payload)

    # Save state after processing
    _save_service_state(
        session_id=session_id,
        service=service,
        service_name=service_name,
        user_id=user_id,
    )

    # Add session_id to result
    result["session_id"] = session_id

    return result


def _get_service_descriptions():
    """Generate service descriptions"""
    descriptions = []
    for name, cls in SERVICE_REGISTRY.items():
        desc = f"- {name}: {cls.__doc__ or 'No description'}"
        descriptions.append(desc)
    return chr(10).join(descriptions)


multi_step_service_description = """
    Universal multi-step service tool for handling complex user interactions.

    Available services:
    {available_services}

    Args:
        service_name: Name of service to run.
        step: Current step name ('start' for new service)
        payload: User input for current step
        user_id: Agent identifier, always use 'agent'

    Returns:
        Dict with status, message, next_step, and other relevant data
    """.format(
    available_services=_get_service_descriptions(),
)

multi_step_service.description = multi_step_service_description
mcp_tools = asyncio.run(get_mcp_tools(exclude_tools=env.MCP_EXCLUDED_TOOLS))
mcp_tools.append(multi_step_service)
