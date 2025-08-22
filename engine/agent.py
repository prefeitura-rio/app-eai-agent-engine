from typing import Any, Iterator, List, Optional, AsyncIterable
from langchain.load.dump import dumpd
from datetime import datetime, timezone

# from langgraph.prebuilt import create_react_agent

# use custom graph without _validate_chat_history
from engine.custom_react_agent import create_react_agent
from langchain_google_vertexai import ChatVertexAI
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage
from vertexai.agent_engines import (
    AsyncQueryable,
    AsyncStreamQueryable,
    Queryable,
    StreamQueryable,
)

from os import getenv
from langchain_google_cloud_sql_pg import (
    PostgresEngine,
    PostgresSaver,
)


# OpenTelemetry imports
import os
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.langchain import LangchainInstrumentor


def setup_opentelemetry():
    """Setup OpenTelemetry with proper error handling and debugging."""
    try:
        # Configuration
        otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
        otlp_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        service_name = os.getenv("OTEL_SERVICE_NAME", "langgraph-agent")

        # Create resource
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": "1.0.0",
            }
        )

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Setup exporters
        exporters = []

        # Console exporter for debugging (optional)
        if os.getenv("OTEL_DEBUG", "false").lower() == "true":
            console_exporter = ConsoleSpanExporter()
            console_processor = BatchSpanProcessor(console_exporter)
            provider.add_span_processor(console_processor)
            exporters.append("console")

        # OTLP exporter
        # Parse headers if provided
        headers = {}
        if otlp_headers:
            for header in otlp_headers.split(","):
                if "=" in header:
                    key, value = header.split("=", 1)
                    headers[key.strip()] = value.strip()

        otlp_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers=headers if headers else None,
            insecure=otlp_endpoint.startswith("http://"),  # Use insecure for http
        )

        otlp_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(otlp_processor)
        exporters.append("otlp")

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Instrument LangChain
        LangchainInstrumentor().instrument()

        return True

    except Exception as e:
        return False


# Initialize OpenTelemetry at module level
otel_setup_success = setup_opentelemetry()


class Agent(AsyncQueryable, AsyncStreamQueryable, Queryable, StreamQueryable):
    """
    An agent for sync/async/streaming queries with state persisted in PostgreSQL.

    Components are initialized lazily on the first query.

    Use engine.init_checkpoint_table() if the table does not exists
    """

    def __init__(
        self,
        *,
        model: str = "gemini-2.5-flash",
        system_prompt: str = "YOU ALWAYS RESPOND: `SYSTEM PROMPT NOT SET`",
        tools: List[BaseTool] = [],
        temperature: float = 0.7,
    ):
        self._model = model
        self._tools = tools or []
        self._system_prompt = system_prompt
        self._temperature = temperature

        # Database configuration
        self._project_id = getenv("PROJECT_ID", "")
        self._region = getenv("LOCATION", "")
        self._instance_name = getenv("INSTANCE", "")
        self._database_name = getenv("DATABASE", "")
        self._database_user = getenv("DATABASE_USER", "")
        self._database_password = getenv("DATABASE_PASSWORD", "")

        # Runtime components - initialized lazily
        self._graph = None
        self._setup_complete_async = False
        self._setup_complete_sync = False
        self._tracer = trace.get_tracer(__name__)

    def set_up(self):
        """Mark that setup is needed - actual setup happens lazily."""
        self._setup_complete_async = False
        self._setup_complete_sync = False

    def _add_timestamp_to_messages(self, state):
        """Hook para adicionar timestamp nas mensagens usando additional_kwargs."""
        with self._tracer.start_as_current_span("add_timestamp_to_messages") as span:
            messages = state.get("messages", [])

            # Adicionar timestamp nas mensagens que não têm, gerando um timestamp único para cada
            timestamp_added = 0
            for message in messages:
                if (
                    hasattr(message, "additional_kwargs")
                    and "timestamp" not in message.additional_kwargs
                ):
                    # Timestamp único para cada mensagem no momento certo:
                    # HumanMessage: quando chega
                    # AIMessage: quando é gerada
                    # ToolMessage: será adicionado após execução da tool
                    message.additional_kwargs["timestamp"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    timestamp_added += 1
            span.set_attribute("timestamps_added", timestamp_added)
            return {"messages": messages}

    def _add_timestamp_to_tool_messages(self, state):
        """Hook para adicionar timestamp nas ToolMessages após execução."""
        with self._tracer.start_as_current_span(
            "add_timestamp_to_tool_messages"
        ) as span:

            messages = state.get("messages", [])
            current_time = datetime.now(timezone.utc).isoformat()
            tool_messages_updated = 0
            ai_messages_updated = 0
            # Adicionar timestamp nas mensagens que não têm
            for message in messages:
                if hasattr(message, "additional_kwargs"):
                    # ToolMessage: timestamp após execução
                    if (
                        message.__class__.__name__ == "ToolMessage"
                        and "timestamp" not in message.additional_kwargs
                    ):
                        message.additional_kwargs["timestamp"] = current_time
                        tool_messages_updated += 1

                    # AIMessage: timestamp quando é gerada (caso não tenha sido adicionado no pre-model)
                    elif (
                        message.__class__.__name__ == "AIMessage"
                        and "timestamp" not in message.additional_kwargs
                    ):
                        message.additional_kwargs["timestamp"] = current_time
                        ai_messages_updated += 1
            span.set_attribute("tool_messages_updated", tool_messages_updated)
            span.set_attribute("ai_messages_updated", ai_messages_updated)
            return {"messages": messages}

    def _inject_thread_id_in_user_id_params(self, state, config=None):
        """Hook para injetar thread_id em qualquer parâmetro user_id de tool calls.

        Este hook processa todas as tool calls e substitui qualquer parâmetro
        'user_id' pelo thread_id atual, garantindo que todas as ferramentas
        recebam o identificador correto do usuário.

        Args:
            state: Estado do grafo contendo as mensagens
            config: Configuração do LangGraph (pode ser None em alguns contextos)

        Returns:
            dict: Estado atualizado com thread_id injetado em todos os parâmetros user_id
        """
        with self._tracer.start_as_current_span("inject_thread_id") as span:

            messages = state.get("messages", [])

            # Múltiplas formas de tentar obter o thread_id
            thread_id = None

            # Método 1: Diretamente do parâmetro config
            if config and isinstance(config, dict):
                configurable = config.get("configurable", {})
                thread_id = configurable.get("thread_id")

            # Método 2: Se config não foi passado, tenta do state (fallback)
            if not thread_id and hasattr(state, "config"):
                state_config = getattr(state, "config", {})
                if isinstance(state_config, dict):
                    configurable = state_config.get("configurable", {})
                    thread_id = configurable.get("thread_id")
            tool_calls_updated = 0
            if thread_id:
                # Processa apenas a última mensagem AI que pode ter tool calls
                span.set_attribute("thread_id", thread_id)
                for message in reversed(messages):
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            # Verifica se a tool call tem argumentos e se possui user_id
                            if (
                                "args" in tool_call
                                and isinstance(tool_call["args"], dict)
                                and "user_id" in tool_call["args"]
                            ):

                                # Substitui user_id pelo thread_id
                                tool_call["args"]["user_id"] = thread_id
                                tool_calls_updated += 1

                        break  # Processa apenas a última mensagem AI

            span.set_attribute("tool_calls_updated", tool_calls_updated)
            return {"messages": messages}

    def _combined_pre_model_hook(self, state, config=None):
        with self._tracer.start_as_current_span("pre_model_hook"):
            state = self._add_timestamp_to_messages(state)
            return self._inject_thread_id_in_user_id_params(state, config)

    def _combined_post_model_hook(self, state, config=None):
        with self._tracer.start_as_current_span("post_model_hook"):
            state = self._add_timestamp_to_tool_messages(state)
            return self._inject_thread_id_in_user_id_params(state, config)

    def _create_react_agent(self, checkpointer: Optional[PostgresSaver] = None):
        """Create and configure the React Agent."""
        with self._tracer.start_as_current_span("create_react_agent") as span:
            llm = ChatVertexAI(model_name=self._model, temperature=self._temperature)
            # llm_with_tools = llm.bind_tools(tools=self._tools, parallel_tool_calls=False)
            llm_with_tools = llm.bind_tools(tools=self._tools)

            self._graph = create_react_agent(
                model=llm_with_tools,
                tools=self._tools,
                prompt=self._system_prompt,
                checkpointer=checkpointer,
                pre_model_hook=self._combined_pre_model_hook,
                post_model_hook=self._combined_post_model_hook,
            )

    async def _ensure_async_setup(self):
        """Ensure async components are set up."""
        if self._setup_complete_async:
            return
        with self._tracer.start_as_current_span("async_setup") as span:

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
            self._create_react_agent(checkpointer=checkpointer)
            self._setup_complete_async = True
            span.set_attribute("setup_success", True)

    def _ensure_sync_setup(self):
        """Ensure sync components are set up."""
        if self._setup_complete_sync:
            return self._graph
        with self._tracer.start_as_current_span("sync_setup") as span:
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
            self._create_react_agent(checkpointer=checkpointer)
            self._setup_complete_sync = True
            span.set_attribute("setup_success", True)
            return self._graph

    async def async_query(self, **kwargs) -> dict[str, Any] | Any:
        """Asynchronous query execution with filtered current interaction."""
        with self._tracer.start_as_current_span("async_query") as span:

            await self._ensure_async_setup()
            if self._graph is None:
                raise ValueError(
                    "Graph is not initialized. Call _ensure_async_setup first."
                )
            result = await self._graph.ainvoke(**kwargs)
            span.set_attribute("query_success", True)
            return self._filter_current_interaction(result)

    async def async_stream_query(self, **kwargs) -> AsyncIterable[Any]:
        """Asynchronous streaming query execution with filtered chunks."""
        with self._tracer.start_as_current_span("async_stream_query") as span:

            async def async_generator() -> AsyncIterable[Any]:
                await self._ensure_async_setup()
                if self._graph is None:
                    raise ValueError(
                        "Graph is not initialized. Call _ensure_async_setup first."
                    )
                chunk_count = 0
                async for chunk in self._graph.astream(**kwargs):
                    filtered_chunk = self._filter_streaming_chunk(chunk)
                    chunk_count += 1
                    yield dumpd(filtered_chunk)
                span.set_attribute("chunk_count", chunk_count)
                span.set_attribute("stream_success", True)

        return async_generator()

    def query(self, **kwargs) -> dict[str, Any] | Any:
        """Synchronous query execution with filtered current interaction."""
        with self._tracer.start_as_current_span("sync_query") as span:
            self._ensure_sync_setup()
            if self._graph is None:
                raise ValueError(
                    "Graph is not initialized. Call _ensure_sync_setup first."
                )
            result = self._graph.invoke(**kwargs)
            span.set_attribute("query_success", True)
            return self._filter_current_interaction(result)

    def stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        """Synchronous streaming query execution with filtered chunks."""
        with self._tracer.start_as_current_span("sync_stream_query") as span:
            self._ensure_sync_setup()
            if self._graph is None:
                raise ValueError(
                    "Graph is not initialized. Call _ensure_sync_setup first."
                )
            chunk_count = 0
            for chunk in self._graph.stream(**kwargs):
                filtered_chunk = self._filter_streaming_chunk(chunk)
                chunk_count += 1
                yield dumpd(filtered_chunk)
            span.set_attribute("chunk_count", chunk_count)
            span.set_attribute("stream_success", True)

    def _filter_current_interaction(self, result: dict) -> dict:
        """Filters response to include only messages from the last human input."""
        with self._tracer.start_as_current_span("filter_current_interaction") as span:
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

            span.set_attribute("filtered", True)
            span.set_attribute("total_messages", len(messages))
            span.set_attribute("filtered_messages", len(filtered_result["messages"]))

            return filtered_result

    def _filter_streaming_chunk(self, chunk: dict) -> dict:
        """Applies interaction filter to a streaming chunk if applicable."""
        if isinstance(chunk, dict) and "messages" in chunk:
            return self._filter_current_interaction(chunk)
        return chunk
