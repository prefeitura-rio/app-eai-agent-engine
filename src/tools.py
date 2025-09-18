from typing import List, Optional, Dict, Any
from langchain_core.tools import BaseTool, tool
import asyncio
import json
from pathlib import Path

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


def _save_service_state(service: BaseService, service_name: str, user_id: str) -> None:
    """Save service state to file"""
    state_file = STATE_DIR / f"{user_id}__{service_name}.json"
    state_data = {
        "service_class": service.__class__.__name__,
        "service_name": service_name,
        "user_id": user_id,
        "data": service.data,
        "created_at": service.created_at.isoformat(),
    }
    with open(state_file, "w") as f:
        json.dump(state_data, f, indent=2, ensure_ascii=False)


def _load_service_state(service_name: str, user_id: str) -> Optional[BaseService]:
    """Load service state from file"""
    state_file = STATE_DIR / f"{user_id}__{service_name}.json"
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
        service = service_class(user_id)
        service.data = state_data["data"]
        return service

    except (json.JSONDecodeError, KeyError):
        return None


def _get_or_create_service(service_name: str, user_id: str) -> Optional[BaseService]:
    """Get existing service or create new one"""
    # Try to load existing state
    service = _load_service_state(service_name, user_id)
    if service:
        return service

    # Create new service
    service_class = SERVICE_REGISTRY.get(service_name)
    if service_class:
        return service_class(user_id)

    return None


@tool
def multi_step_service(
    service_name: str, step: str, payload: str, user_id: str
) -> Dict[str, Any]:
    """
    PLACE HOLDER - This docstring will be replaced dynamically
    """

    # Check if this is not a start and session doesn't exist
    if step != "start":
        state_file = STATE_DIR / f"{user_id}__{service_name}.json"
        if not state_file.exists():
            return {
                "status": "error",
                "message": f"Nenhuma sessão ativa encontrada para {service_name}. Use step='start' para iniciar.",
                "available_services": list(SERVICE_REGISTRY.keys()),
            }

    # Load or create service instance
    service = _get_or_create_service(service_name=service_name, user_id=user_id)

    if not service:
        return {
            "status": "error",
            "message": f"Serviço '{service_name}' não encontrado",
            "available_services": list(SERVICE_REGISTRY.keys()),
        }

    # Handle start step - sempre solicita todos os dados de uma vez
    if step == "start":
        result = {
            "status": "bulk_request",
            "schema": service.get_schema(),
            "steps_info": service.get_steps_info(),
            "completed": False,
        }

        # Save initial state
        _save_service_state(
            service=service,
            service_name=service_name,
            user_id=user_id,
        )
        return result

    # Auto-detect bulk vs step-by-step based on payload
    is_bulk = False
    bulk_payload = None

    try:

        bulk_payload = json.loads(payload)
        # If JSON parsing succeeds and it's a dict, it's bulk mode
        if isinstance(bulk_payload, dict):
            is_bulk = True
    except (json.JSONDecodeError, TypeError):
        # Not JSON or not a dict, treat as step-by-step
        is_bulk = False

    # Process accordingly
    if is_bulk and bulk_payload is not None:
        result = service.process_bulk(bulk_payload)
    else:
        result = service.process_step(step, payload)

    # Save state after processing
    _save_service_state(
        service=service,
        service_name=service_name,
        user_id=user_id,
    )

    return result


def _get_service_descriptions():
    """Generate service descriptions"""
    descriptions = []
    for name, cls in SERVICE_REGISTRY.items():
        desc = f"- {name}: {cls.__doc__ or 'No description'}"
        descriptions.append(desc)
    return chr(10).join(descriptions)


multi_step_service_description = """
    Tool Universal de serviços.
    
    IMPORTANTE - Quando solicitar dados ao usuario siga essas instruções:
    - Sua menssagens de solicitação devem ser claras, objetivas e seguindo sua Persona original.
    - Apresente os campos necessários em formato de lista.
    - Examemplo:
        Para iniciar seu cadastro, por favor forneça as seguintes informações:
        - CPF
        - Nome completo
        - E-mail

    
    Servicos disponíveis:
    {available_services}

    Args:
        service_name: Nome do serviço a ser executado
        step: Passo atual ('start' para a primeira interação, bulk para multiplos passos em um unico request, ou o nome especifico do passo a ser executado.)
        payload: Resposta do usuário (string para passos especificos, JSON string para bulk)
        user_id: Identificador do agente, sempre utilize 'agent'

    Returns:
        Dict com status, next_step_info (detalhes completos do proximo passo), schema, e outros dados relevantes.
    """.format(
    available_services=_get_service_descriptions(),
)

multi_step_service.description = multi_step_service_description
mcp_tools = asyncio.run(get_mcp_tools(exclude_tools=env.MCP_EXCLUDED_TOOLS))
mcp_tools.append(multi_step_service)
