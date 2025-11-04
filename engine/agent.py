from typing import Any, Iterator, List, Optional, AsyncIterable
from langchain.load.dump import dumpd
from datetime import datetime, timezone
import json
from langchain_core.messages import trim_messages

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

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from opentelemetry.instrumentation.langchain import LangchainInstrumentor


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

    def _filter_short_term_memory(self, state):
        """Filter messages based on time and token limits for short-term memory.
        
        This method implements short-term memory by:
        1. Filtering out messages older than SHORT_MEMORY_TIME_LIMIT
        2. Applying token limit using trimMessages
        3. Always preserving system messages
        
        NOTE: PostgresCheckpointer loads ALL messages from the database for the thread.
        This filter reduces what goes to the LLM (saves tokens/improves performance),
        but the full history remains in the database.
        
        Args:
            state: The current state containing messages (full history from database)
            
        Returns:
            dict: Updated state with filtered messages (only recent messages)
        """
        from src.config.env import SHORT_MEMORY_TIME_LIMIT, SHORT_MEMORY_TOKEN_LIMIT
        from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
        import logging
        
        logger = logging.getLogger(__name__)
        messages = state.get("messages", [])
        
        if not messages:
            return {"messages": []}
        
        # Log the initial message count (retrieved from database)
        logger.info(f"[Short-Term Memory] Loaded {len(messages)} messages from database")
        
        # Separate system messages (always kept)
        system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
        non_system_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
        
        logger.info(f"[Short-Term Memory] System messages: {len(system_messages)}, Non-system messages: {len(non_system_messages)}")
        
        if not non_system_messages:
            return {"messages": system_messages}
        
        # Step 1: Time filtering - remove messages older than time limit
        current_time = datetime.now(timezone.utc)
        time_filtered_messages = []
        
        for message in non_system_messages:
            timestamp_str = message.additional_kwargs.get("timestamp") if hasattr(message, "additional_kwargs") else None
            
            if timestamp_str:
                try:
                    message_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    age_seconds = (current_time - message_time).total_seconds()
                    
                    if age_seconds <= SHORT_MEMORY_TIME_LIMIT:
                        time_filtered_messages.append(message)
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Invalid timestamp format in message: {timestamp_str}, error: {e}")
                    # Keep messages with invalid timestamps
                    time_filtered_messages.append(message)
            else:
                # Keep messages without timestamps (e.g., new messages)
                time_filtered_messages.append(message)
        
        if not time_filtered_messages:
            # If all messages are filtered out, keep at least the last message
            logger.warning(f"[Short-Term Memory] All messages filtered by time limit, keeping last message")
            time_filtered_messages = [non_system_messages[-1]]
        else:
            messages_filtered_by_time = len(non_system_messages) - len(time_filtered_messages)
            if messages_filtered_by_time > 0:
                logger.info(f"[Short-Term Memory] Filtered out {messages_filtered_by_time} messages older than {SHORT_MEMORY_TIME_LIMIT / 86400:.1f} days")
        
        # Step 2: Apply token limiting using trimMessages
        try:
            # Use trimMessages to limit tokens
            token_filtered_messages = trim_messages(
                time_filtered_messages,
                max_tokens=SHORT_MEMORY_TOKEN_LIMIT,
                strategy="last",
                token_counter=lambda msgs: sum(len(str(m.content)) // 4 for m in msgs),  # Rough token estimation
                start_on="human",
                end_on=["human", "tool"],
            )
            
            messages_filtered_by_tokens = len(time_filtered_messages) - len(token_filtered_messages)
            if messages_filtered_by_tokens > 0:
                logger.info(f"[Short-Term Memory] Filtered out {messages_filtered_by_tokens} messages due to {SHORT_MEMORY_TOKEN_LIMIT} token limit")
            
            # If trim_messages returns empty or if the most recent message alone exceeds the limit
            if not token_filtered_messages:
                logger.error(
                    f"[Short-Term Memory] The most recent message exceeds token limit ({SHORT_MEMORY_TOKEN_LIMIT} tokens). "
                    "Proceeding with just the last message."
                )
                token_filtered_messages = [time_filtered_messages[-1]]
                
        except Exception as e:
            logger.error(f"[Short-Term Memory] Error applying token limit: {e}. Using time filtered messages.")
            token_filtered_messages = time_filtered_messages
        
        # Step 3: Combine system messages with filtered messages
        filtered_messages = system_messages + token_filtered_messages
        
        logger.info(
            f"[Short-Term Memory] Final result: {len(filtered_messages)} messages "
            f"({len(system_messages)} system + {len(token_filtered_messages)} conversation) "
            f"sent to LLM out of {len(messages)} total in database"
        )
        
        return {"messages": filtered_messages}

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

    def _combined_pre_model_hook(self, state, config=None):
        # Step 1: Add timestamps to new messages
        state = self._add_timestamp_to_messages(state)
        
        # Step 2: Apply short-term memory filtering
        state = self._filter_short_term_memory(state)
        
        # Step 3: Inject thread_id into tool calls
        return self._inject_thread_id_in_user_id_params(state, config)

    def _combined_post_model_hook(self, state, config=None):
        state = self._add_timestamp_to_tool_messages(state)
        return self._inject_thread_id_in_user_id_params(state, config)

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
        checkpointer = await PostgresSaver.create(engine=engine)
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

        checkpointer = PostgresSaver.create_sync(engine=engine)
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
        type = kwargs.pop("type", None)
        if type == "history":
            # Bypass filtering for history requests
            self._graph.update_state(
                config=kwargs.get("config", {}), values=kwargs.get("input", {})
            )
            return {}
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
