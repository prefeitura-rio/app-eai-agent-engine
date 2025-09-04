"""
Orchestrated Agent - Enhanced main agent with service agent routing capabilities.
"""

from typing import Any, Iterator, List, Optional, AsyncIterable
from langchain.load.dump import dumpd
from datetime import datetime, timezone
import json
from os import getenv

from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import create_react_agent
from langchain_google_vertexai import ChatVertexAI
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage
from vertexai.agent_engines import (
    AsyncQueryable,
    AsyncStreamQueryable,
    Queryable,
    StreamQueryable,
)

from langchain_google_cloud_sql_pg import (
    PostgresEngine,
    PostgresSaver,
)

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.langchain import LangchainInstrumentor

# Import orchestrator and service agents
from engine.orchestrator import create_handoff_tools
from engine.services import TaxServiceAgent, InfrastructureServiceAgent, HealthServiceAgent
from engine.workflow_tools import get_workflow_tools
from engine.identification_service_tools import get_identification_service_tools, set_shared_checkpointer
from engine.robust_tools import robust_identification_tools


class OrchestratedAgent(AsyncQueryable, AsyncStreamQueryable, Queryable, StreamQueryable):
    """
    Orchestrated agent that routes requests to specialized service agents or handles them directly.
    
    This agent enhances the main agent capabilities with:
    - Intelligent routing to specialized service agents
    - Fallback to general tools for non-specialized requests
    - Maintains conversation context across service boundaries
    """
    
    def __init__(
        self,
        *,
        model: str = "gemini-2.5-flash",
        system_prompt: str = "YOU ALWAYS RESPOND: `SYSTEM PROMPT NOT SET`",
        tools: List[BaseTool] = [],
        temperature: float = 0.7,
        otpl_service: str = "langgraph-eai-vX",
        enable_service_agents: bool = True,
        enable_workflows: bool = True,
    ):
        self._model = model
        self._tools = tools or []
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._otpl_service = otpl_service
        self._enable_service_agents = enable_service_agents
        self._enable_workflows = enable_workflows
        
        # Database configuration
        self._project_id = getenv("PROJECT_ID", "")
        self._region = getenv("LOCATION", "")
        self._instance_name = getenv("INSTANCE", "")
        self._database_name = getenv("DATABASE", "")
        self._database_user = getenv("DATABASE_USER", "")
        self._database_password = getenv("DATABASE_PASSWORD", "")
        self._otlp_endpoint = getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
        self._otlp_header = getenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "")

        self._graph = None
        self._setup_complete_async = False
        self._setup_complete_sync = False
        self._opentelemetry_setup_complete = False

        # OpenTelemetry tracer e processor para shutdown
        self._tracer = None
        self._batch_processor = None
        self._shutdown_handlers_registered = False
        
        # Service agents for specialized handling
        self._service_agents = {
            "tax_agent": TaxServiceAgent(model=model, temperature=temperature),
            "infrastructure_agent": InfrastructureServiceAgent(model=model, temperature=temperature),
            "health_agent": HealthServiceAgent(model=model, temperature=temperature)
        }
    
    def _set_up_opentelemetry(self):
        """Set up OpenTelemetry tracing (unchanged from original)."""
        if self._opentelemetry_setup_complete:
            return
        provider = TracerProvider(
            resource=Resource.create({"service.name": self._otpl_service}),
            sampler=ALWAYS_ON,
        )
        otlp_exporter = OTLPSpanExporter(
            endpoint=self._otlp_endpoint,
            headers=(
                dict(
                    header.split("=")
                    for header in self._otlp_header.split(",")
                    if "=" in header
                )
                if self._otlp_header
                else None
            ),
        )

        self._batch_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=8192,
            schedule_delay_millis=1000,
            export_timeout_millis=10000,
            max_export_batch_size=256,
        )
        provider.add_span_processor(self._batch_processor)
        trace.set_tracer_provider(provider)

        self._tracer = trace.get_tracer(__name__)
        LangchainInstrumentor().instrument()
        self._opentelemetry_setup_complete = True

    def _trace_conversation(self, filtered_result: dict, **kwargs):
        """Simple tracing to show user input and model output (unchanged from original)."""
        if not self._tracer:
            return

        input_msg = str(kwargs.get("input", ""))
        thread_id = (
            kwargs.get("config", {}).get("configurable", {}).get("thread_id", "unknown")
        )

        with self._tracer.start_as_current_span("conversation") as span:
            span.set_attributes(
                {
                    "user.input": input_msg,
                    "model.output": json.dumps(
                        dumpd(filtered_result), ensure_ascii=False, indent=2
                    ),
                    "thread.id": thread_id,
                    "model.name": self._model,
                    "model.temperature": self._temperature,
                }
            )

    def set_up(self):
        """Mark that setup is needed - actual setup happens lazily."""
        self._setup_complete_async = False
        self._setup_complete_sync = False

    def _add_timestamp_to_messages(self, state):
        """Hook para adicionar timestamp nas mensagens usando additional_kwargs (unchanged from original)."""
        messages = state.get("messages", [])

        for message in messages:
            if (
                hasattr(message, "additional_kwargs")
                and "timestamp" not in message.additional_kwargs
            ):
                message.additional_kwargs["timestamp"] = datetime.now(
                    timezone.utc
                ).isoformat()

        return {"messages": messages}

    def _add_timestamp_to_tool_messages(self, state):
        """Hook para adicionar timestamp nas ToolMessages após execução (unchanged from original)."""
        messages = state.get("messages", [])
        current_time = datetime.now(timezone.utc).isoformat()

        for message in messages:
            if hasattr(message, "additional_kwargs"):
                if (
                    message.__class__.__name__ == "ToolMessage"
                    and "timestamp" not in message.additional_kwargs
                ):
                    message.additional_kwargs["timestamp"] = current_time

                elif (
                    message.__class__.__name__ == "AIMessage"
                    and "timestamp" not in message.additional_kwargs
                ):
                    message.additional_kwargs["timestamp"] = current_time

        return {"messages": messages}

    def _inject_thread_id_in_user_id_params(self, state, config=None):
        """Hook para injetar thread_id em qualquer parâmetro user_id de tool calls (unchanged from original)."""
        messages = state.get("messages", [])

        thread_id = None

        if config and isinstance(config, dict):
            configurable = config.get("configurable", {})
            thread_id = configurable.get("thread_id")

        if not thread_id and hasattr(state, "config"):
            state_config = getattr(state, "config", {})
            if isinstance(state_config, dict):
                configurable = state_config.get("configurable", {})
                thread_id = configurable.get("thread_id")

        if thread_id:
            for message in reversed(messages):
                if hasattr(message, "tool_calls") and message.tool_calls:
                    for tool_call in message.tool_calls:
                        if (
                            "args" in tool_call
                            and isinstance(tool_call["args"], dict)
                            and "user_id" in tool_call["args"]
                        ):
                            tool_call["args"]["user_id"] = thread_id
                    break

        return {"messages": messages}

    def _combined_pre_model_hook(self, state, config=None):
        state = self._add_timestamp_to_messages(state)
        return self._inject_thread_id_in_user_id_params(state, config)

    def _combined_post_model_hook(self, state, config=None):
        state = self._add_timestamp_to_tool_messages(state)
        return self._inject_thread_id_in_user_id_params(state, config)

    def _create_orchestrated_graph(self, checkpointer: Optional[PostgresSaver] = None):
        """Create the orchestrated graph with main agent and service agents."""
        
        # Set shared checkpointer for identification service agents
        if checkpointer:
            set_shared_checkpointer(checkpointer)
        
        llm = ChatVertexAI(model_name=self._model, temperature=self._temperature)
        
        # Conditionally add routing tools based on configuration
        all_tools = self._tools.copy()
        
        # Always add robust identification tools
        all_tools.extend(robust_identification_tools)
        
        if self._enable_service_agents:
            # Add handoff tools for service agent routing
            handoff_tools = create_handoff_tools()
            all_tools.extend(handoff_tools)
            
            # Add identification service tools for conversational approach
            identification_service_tools = get_identification_service_tools()
            all_tools.extend(identification_service_tools)
        
        if self._enable_workflows:
            # Add workflow tools for workflow routing
            workflow_tools = get_workflow_tools()
            all_tools.extend(workflow_tools)
        
        # Create routing-specific prompt based on enabled features
        routing_instructions = self._get_routing_instructions()
        
        # Enhanced system prompt with routing logic
        enhanced_prompt = f"""
{self._system_prompt}

{routing_instructions}
"""
        # Create main orchestrator agent
        main_agent = create_react_agent(
            model=llm.bind_tools(all_tools),
            tools=all_tools,
            prompt=enhanced_prompt,
            checkpointer=checkpointer,
            pre_model_hook=self._combined_pre_model_hook,
            post_model_hook=self._combined_post_model_hook,
        )
        
        # Create the multi-agent graph
        builder = StateGraph(MessagesState)
        
        # Add main orchestrator node
        builder.add_node("main_agent", main_agent)
        
        # Add service agent nodes only if service agents are enabled
        if self._enable_service_agents:
            for agent_name, service_agent in self._service_agents.items():
                agent_graph = service_agent.create_agent(checkpointer)
                builder.add_node(agent_name, agent_graph)
        
        # Set entry point
        builder.add_edge(START, "main_agent")
        
        # The handoff tools will handle routing via Command objects
        # No explicit edges needed - LangGraph handles Command routing
        
        return builder.compile(checkpointer=checkpointer)
    
    def _get_routing_instructions(self) -> str:
        """Generate routing instructions based on enabled features."""
        
        if self._enable_service_agents and self._enable_workflows:
            return """
# SERVICE ROUTING CAPABILITIES WITH ROBUST VALIDATION

You have access to both specialized service agents and structured workflows. Choose the best approach for each request:

## ROBUST USER IDENTIFICATION (use these tools FIRST):

🔥 **ALWAYS START WITH VALIDATION** - Use these tools for ANY identification request:

1. **validate_and_check_user_cpf** → Validates CPF and checks if user exists in database
2. **validate_user_email** → Validates email format
3. **confirm_existing_user_email** → For users already in database, confirm/update email
4. **register_new_user** → Register completely new users after validation
5. **get_user_summary** → Get complete user information summary

## FLOW LOGIC:
- If user provides CPF → use `validate_and_check_user_cpf` first
- If user found in database → greet by name, use `confirm_existing_user_email` 
- If user NOT in database → collect name and email, validate with tools, then `register_new_user`
- ALWAYS validate before registering

## SPECIALIZED SERVICES (use handoff tools):

1. **TAX SERVICES** → use `route_to_tax_agent`:
   - Complex tax consultations and advice
   - Multi-step tax procedures requiring expertise

2. **INFRASTRUCTURE SERVICES** → use `route_to_infrastructure_agent`:
   - Infrastructure problem reporting with follow-up
   - Complex infrastructure consultations

3. **HEALTH SERVICES** → use `route_to_health_agent`:
   - Health appointment scheduling and management
   - Health program consultations

## STRUCTURED WORKFLOWS (use workflow tools):

4. **USER IDENTIFICATION** → use workflow tools OR service agent:
   - Structured approach → use workflow tools (step-by-step with validation)
   - Conversational approach → use `route_to_identification_agent` (natural dialogue)
   - Both use the same PostgreSQL memory and share conversation history

## GENERAL SERVICES (use existing tools):

5. **INFORMATION & EQUIPMENT LOCATION** → use existing tools:
   - General municipal information → use `web_search_surkai`
   - Equipment and facility locations → use `equipments_by_address`
"""
        
        elif self._enable_service_agents:
            return """
# SERVICE AGENT ROUTING - PRIORITY INSTRUCTIONS WITH ROBUST VALIDATION

🚨 **IDENTIFICATION DETECTION**: If user mentions any of these keywords, use ROBUST VALIDATION TOOLS:
- "identificar", "identificação", "cpf", "email", "nome", "dados pessoais", "me identificar"
- Any message containing CPF numbers, email addresses, or personal names

## ROBUST VALIDATION TOOLS (use FIRST for identification):

1. **validate_and_check_user_cpf** → Validates CPF and checks if user exists in database
2. **validate_user_email** → Validates email format  
3. **confirm_existing_user_email** → For users already in database, confirm/update email
4. **register_new_user** → Register completely new users after validation
5. **get_user_summary** → Get complete user information summary

## FLOW LOGIC:
- If user provides CPF → use `validate_and_check_user_cpf` first
- If user found in database → greet by name, use `confirm_existing_user_email` 
- If user NOT in database → collect name and email, validate with tools, then `register_new_user`
- ALWAYS validate before registering

## ROUTING RULES:

1. **USER IDENTIFICATION** → Use robust validation tools above OR `route_to_identification_agent`:
   - For complex identification flows → route_to_identification_agent
   - For simple validation → use validation tools directly

2. **TAX SERVICES** → use `route_to_tax_agent`:
   - IPTU, ISS, tax payments, certifications

3. **INFRASTRUCTURE SERVICES** → use `route_to_infrastructure_agent`:  
   - Street lighting, roads, public facilities

4. **HEALTH SERVICES** → use `route_to_health_agent`:
   - Medical appointments, vaccination, health programs

## GENERAL SERVICES (use existing tools):
- General information → use `web_search_surkai`
- Equipment location → use `equipments_by_address`

⚠️ DO NOT ask "para qual serviço?" if user is clearly trying to identify themselves.
"""
        
        elif self._enable_workflows:
            return """
# WORKFLOW ROUTING - PRIORITY INSTRUCTIONS WITH ROBUST VALIDATION

🚨 **IDENTIFICATION DETECTION**: If user mentions any of these keywords, use ROBUST VALIDATION TOOLS:
- "identificar", "identificação", "cpf", "email", "nome", "dados pessoais", "me identificar"
- Any message containing CPF numbers, email addresses, or personal names

## ROBUST VALIDATION TOOLS (use FIRST for identification):

1. **validate_and_check_user_cpf** → Validates CPF and checks if user exists in database
2. **validate_user_email** → Validates email format
3. **confirm_existing_user_email** → For users already in database, confirm/update email
4. **register_new_user** → Register completely new users after validation
5. **get_user_summary** → Get complete user information summary

## FLOW LOGIC:
- If user provides CPF → use `validate_and_check_user_cpf` first
- If user found in database → greet by name, use `confirm_existing_user_email` 
- If user NOT in database → collect name and email, validate with tools, then `register_new_user`
- ALWAYS validate before registering

## WORKFLOW RULES:

1. **USER IDENTIFICATION** → Use robust validation tools above OR workflow tools:
   - For structured flows → use `start_user_identification` and `process_user_identification`  
   - For direct validation → use validation tools directly

## GENERAL SERVICES (use existing tools):
- General information → use `web_search_surkai`
- Equipment location → use `equipments_by_address`
- User feedback → use `user_feedback`

⚠️ DO NOT provide generic responses for identification requests - USE THE VALIDATION TOOLS.
"""
        
        else:
            return """
# GENERAL SERVICES ONLY

Use your existing tools for all requests:
- General municipal information → use `web_search_surkai`
- Equipment and facility locations → use `equipments_by_address`
- User feedback → use `user_feedback`
"""

    async def _ensure_async_setup(self):
        """Ensure async components are set up."""
        self._set_up_opentelemetry()

        if self._setup_complete_async:
            return
        engine = await PostgresEngine.afrom_instance(
            project_id=self._project_id,
            region=self._region,
            instance=self._instance_name,
            database=self._database_name,
            user=self._database_user,
            password=self._database_password,
            engine_args={"pool_pre_ping": True, "pool_recycle": 300},
        )
        checkpointer = await PostgresSaver.create(engine=engine)
        self._graph = self._create_orchestrated_graph(checkpointer=checkpointer)
        self._setup_complete_async = True

    def _ensure_sync_setup(self):
        """Ensure sync components are set up."""
        self._set_up_opentelemetry()

        if self._setup_complete_sync:
            return self._graph
        engine = PostgresEngine.from_instance(
            project_id=self._project_id,
            region=self._region,
            instance=self._instance_name,
            database=self._database_name,
            user=self._database_user,
            password=self._database_password,
            engine_args={"pool_pre_ping": True, "pool_recycle": 300},
        )

        checkpointer = PostgresSaver.create_sync(engine=engine)
        self._graph = self._create_orchestrated_graph(checkpointer=checkpointer)
        self._setup_complete_sync = True
        return self._graph

    # The rest of the methods (async_query, query, stream_query, etc.) remain unchanged from original
    async def async_query(self, **kwargs) -> dict[str, Any] | Any:
        """Asynchronous query execution with filtered current interaction."""
        await self._ensure_async_setup()
        if self._graph is None:
            raise ValueError(
                "Graph is not initialized. Call _ensure_async_setup first."
            )

        result = await self._graph.ainvoke(**kwargs)
        filtered_result = self._filter_current_interaction(result)

        # Simple tracing
        self._trace_conversation(filtered_result, **kwargs)

        return filtered_result

    async def async_stream_query(self, **kwargs) -> AsyncIterable[Any]:
        """Asynchronous streaming query execution with filtered chunks."""

        async def async_generator() -> AsyncIterable[Any]:
            await self._ensure_async_setup()
            if self._graph is None:
                raise ValueError(
                    "Graph is not initialized. Call _ensure_async_setup first."
                )
            async for chunk in self._graph.astream(**kwargs):
                filtered_chunk = self._filter_streaming_chunk(chunk)
                yield dumpd(filtered_chunk)

        return async_generator()

    def query(self, **kwargs) -> dict[str, Any] | Any:
        """Synchronous query execution with filtered current interaction."""
        self._ensure_sync_setup()
        if self._graph is None:
            raise ValueError("Graph is not initialized. Call _ensure_sync_setup first.")

        result = self._graph.invoke(**kwargs)
        filtered_result = self._filter_current_interaction(result)

        # Simple tracing
        self._trace_conversation(filtered_result, **kwargs)

        return filtered_result

    def stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        """Synchronous streaming query execution with filtered chunks."""
        self._ensure_sync_setup()
        if self._graph is None:
            raise ValueError("Graph is not initialized. Call _ensure_sync_setup first.")
        for chunk in self._graph.stream(**kwargs):
            filtered_chunk = self._filter_streaming_chunk(chunk)
            yield dumpd(filtered_chunk)

    def _filter_current_interaction(self, result: dict) -> dict:
        """Filters response to include only messages from the last human input."""
        if "messages" not in result or not isinstance(result["messages"], list):
            return result
        messages = result["messages"]
        last_human_index = -1
        for i, msg in reversed(list(enumerate(messages))):
            if isinstance(msg, HumanMessage):
                last_human_index = i
                break
        if last_human_index == -1:
            return result
        filtered_result = result.copy()
        filtered_result["messages"] = messages[last_human_index:]
        return filtered_result

    def _filter_streaming_chunk(self, chunk: dict) -> dict:
        """Applies interaction filter to a streaming chunk if applicable."""
        if isinstance(chunk, dict) and "messages" in chunk:
            return self._filter_current_interaction(chunk)
        return chunk
