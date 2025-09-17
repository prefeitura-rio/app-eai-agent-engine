from typing import Any, Iterator, List, Optional, AsyncIterable
from langchain.load.dump import dumpd
from datetime import datetime, timezone
import json

# from langgraph.prebuilt import create_react_agent
# use custom graph without _validate_chat_history
from engine.custom_react_agent import create_react_agent
from langchain_google_vertexai import ChatVertexAI
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage
from src.utils.memory_manager import MemoryManager
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
from src.utils.memory_limited_checkpointer import MemoryLimitedPostgresSaver

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from opentelemetry.instrumentation.langchain import LangchainInstrumentor
import logging

logger = logging.getLogger(__name__)


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
        otpl_service: str = "langgraph-eai-vX",
    ):
        self._model = model
        self._tools = tools or []
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._otpl_service = otpl_service
        # Database configuration
        self._project_id = getenv("PROJECT_ID", "")
        self._region = getenv("LOCATION", "")
        self._instance_name = getenv("INSTANCE", "")
        self._database_name = getenv("DATABASE", "")
        self._database_user = getenv("DATABASE_USER", "")
        self._database_password = getenv("DATABASE_PASSWORD", "")
        
        # Initialize memory manager
        self._memory_manager = MemoryManager(model_name=self._model)
        # Debug flag for memory logging
        self._debug_memory = False
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

    def _set_up_opentelemetry(self):
        if self._opentelemetry_setup_complete:
            return
        provider = TracerProvider(
            resource=Resource.create({"service.name": self._otpl_service}),
            sampler=ALWAYS_ON,  # Garantir 100% de sampling
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

        # Configurar BatchSpanProcessor com parâmetros otimizados para reduzir perda de spans
        self._batch_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=8192,  # Aumentar buffer (padrão: 2048)
            schedule_delay_millis=1000,  # Flush mais frequente (padrão: 5000)
            export_timeout_millis=10000,  # Timeout menor (padrão: 30000)
            max_export_batch_size=256,  # Lotes menores para reduzir latência (padrão: 512)
        )
        provider.add_span_processor(self._batch_processor)
        trace.set_tracer_provider(provider)

        # Initialize tracer
        self._tracer = trace.get_tracer(__name__)

        LangchainInstrumentor().instrument()

        self._opentelemetry_setup_complete = True

    def _trace_conversation(self, filtered_result: dict, **kwargs):
        """Simple tracing to show user input and model output."""
        if not self._tracer:
            return

        # Extract input message
        input_msg = str(kwargs.get("input", ""))

        # Extract thread_id
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
        """Hook para adicionar timestamp nas mensagens usando additional_kwargs."""
        messages = state.get("messages", [])

        # Adicionar timestamp nas mensagens que não têm, gerando um timestamp único para cada
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

        return {"messages": messages}

    def _add_timestamp_to_tool_messages(self, state):
        """Hook para adicionar timestamp nas ToolMessages após execução."""
        messages = state.get("messages", [])
        current_time = datetime.now(timezone.utc).isoformat()

        # Adicionar timestamp nas mensagens que não têm
        for message in messages:
            if hasattr(message, "additional_kwargs"):
                # ToolMessage: timestamp após execução
                if (
                    message.__class__.__name__ == "ToolMessage"
                    and "timestamp" not in message.additional_kwargs
                ):
                    message.additional_kwargs["timestamp"] = current_time

                # AIMessage: timestamp quando é gerada (caso não tenha sido adicionado no pre-model)
                elif (
                    message.__class__.__name__ == "AIMessage"
                    and "timestamp" not in message.additional_kwargs
                ):
                    message.additional_kwargs["timestamp"] = current_time

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

        if thread_id:
            # Processa apenas a última mensagem AI que pode ter tool calls
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
                    break  # Processa apenas a última mensagem AI

        return {"messages": messages}

    def _limit_memory(self, state, config=None):
        """Hook to limit memory based on token count and time constraints."""
        messages = state.get("messages", [])
        if not messages:
            return state  # Return original state if no messages
        
        try:
            # Apply memory limitations
            limited_state = self._memory_manager.limit_memory(messages)
            
            # Ensure we always have a valid messages list
            limited_messages = limited_state.get("messages", [])
            if not limited_messages:
                logger.warning("Memory manager returned empty messages list, keeping original")
                return state
            
            # Log memory statistics if debug logging is enabled
            if hasattr(self, '_debug_memory') and self._debug_memory:
                stats = self._memory_manager.get_memory_stats(messages)
                logger.info(f"Memory stats: {stats}")
            
            return limited_state
            
        except Exception as e:
            logger.error(f"Error in memory limiting: {e}. Keeping original messages.")
            return state

    def _limit_memory_for_storage(self, state, config=None):
        """Hook to limit memory before saving to PostgreSQL database.
        
        This is the CRITICAL method that ensures only memory-limited messages
        are persisted in the database. This prevents old messages from being
        stored indefinitely and ensures true memory management.
        """
        messages = state.get("messages", [])
        if not messages:
            return state  # Return original state if no messages
        
        try:
            # Apply memory limitations for storage
            limited_result = self._memory_manager.limit_memory(messages)
            
            # Ensure we always have a valid messages list
            limited_messages = limited_result.get("messages", [])
            if not limited_messages:
                logger.warning("Memory manager returned empty messages list for storage, keeping most recent")
                # Keep at least the most recent message to prevent empty conversation
                limited_messages = [messages[-1]] if messages else []
            
            # Create new state with memory-limited messages
            limited_state = dict(state)
            limited_state["messages"] = limited_messages
            
            # Log storage memory statistics if debug logging is enabled
            if hasattr(self, '_debug_memory') and self._debug_memory:
                original_count = len(messages)
                limited_count = len(limited_messages)
                removed_count = original_count - limited_count
                logger.info(
                    f"Storage memory limiting: {original_count} -> {limited_count} messages "
                    f"(removed {removed_count} old messages from database storage)"
                )
            
            return limited_state
            
        except Exception as e:
            logger.error(f"Error in storage memory limiting: {e}. Keeping original messages.")
            return state

    def _combined_pre_model_hook(self, state, config=None):
        # CRITICAL: Apply memory limits FIRST to ensure only recent messages are processed
        # This affects both what the model sees AND what gets stored in the database
        state = self._limit_memory_for_storage(state, config)
        # Then add timestamps  
        state = self._add_timestamp_to_messages(state)
        # Finally inject thread IDs
        return self._inject_thread_id_in_user_id_params(state, config)

    def _combined_post_model_hook(self, state, config=None):
        # First add timestamps to tool messages
        state = self._add_timestamp_to_tool_messages(state)
        # Then inject thread IDs
        state = self._inject_thread_id_in_user_id_params(state, config)
        # Apply memory limits again to ensure storage consistency
        # (This is a safety net in case new messages were added)
        state = self._limit_memory_for_storage(state, config)
        return state

    def _create_react_agent(self, checkpointer: Optional[PostgresSaver] = None):
        """Create and configure the React Agent."""
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
        checkpointer = await MemoryLimitedPostgresSaver.create(engine=engine, memory_manager=self._memory_manager)
        self._create_react_agent(checkpointer=checkpointer)
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

        checkpointer = MemoryLimitedPostgresSaver.create_sync(engine=engine, memory_manager=self._memory_manager)
        self._create_react_agent(checkpointer=checkpointer)
        self._setup_complete_sync = True
        return self._graph

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

    def enable_memory_debug(self):
        """Enable debug logging for memory management."""
        self._debug_memory = True
        logger.info("Memory debug logging enabled")

    def disable_memory_debug(self):
        """Disable debug logging for memory management.""" 
        self._debug_memory = False
        logger.info("Memory debug logging disabled")

    def get_memory_stats(self, thread_id: str) -> dict:
        """Get memory statistics for a specific thread.
        
        Args:
            thread_id: The thread ID to get stats for
            
        Returns:
            Dictionary with memory usage statistics
        """
        try:
            # This would require accessing the checkpointer to get current state
            # For now, return basic info about limits
            return {
                "token_limit": self._memory_manager.token_limit,
                "time_limit_days": self._memory_manager.time_limit_days,
                "note": "Use during conversation to see actual memory usage"
            }
        except Exception as e:
            logger.error(f"Error getting memory stats: {e}")
            return {"error": str(e)}
