from typing import Any, Callable, Iterator, Sequence, Optional
from langchain_core.load import dumpd
from langchain.load.dump import dumpd
from langgraph.prebuilt import create_react_agent
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
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


class Agent(AsyncQueryable, AsyncStreamQueryable, Queryable, StreamQueryable):
    def __init__(
        self,
        *,
        model: str = "gemini-2.5-flash",
        system_prompt: str = None,
        tools: Sequence[Callable] = None,
        temperature: float = 0.7,
        project_id: str = getenv("PROJECT_ID"),
        region: str = getenv("LOCATION"),
        instance_name: str = getenv("INSTANCE"),
        database_name: str = getenv("DATABASE"),
        database_user: str = getenv("DATABASE_USER"),
        database_password: str = getenv("DATABASE_PASSWORD"),
    ):
        self._model = model
        self._tools = tools or []
        self._system_prompt = system_prompt
        self._temperature = temperature

        # Database configuration
        self._project_id = project_id
        self._region = region
        self._instance_name = instance_name
        self._database_name = database_name
        self._database_user = database_user
        self._database_password = database_password

        # Runtime components - initialized lazily
        self._graph = None
        self._checkpointer_async = None
        self._checkpointer_sync = None
        self._setup_complete_async = False
        self._setup_complete_sync = False

    def set_up(self):
        """Mark that setup is needed - actual setup happens lazily."""
        self._setup_complete_async = False
        self._setup_complete_sync = False

    def _create_llm_with_tools(self):
        """Create and configure the LLM with tools."""

    def _create_react_agent(self, checkpointer: Optional[PostgresSaver] = None):
        """Create and configure the React Agent."""
        llm = ChatVertexAI(model_name=self._model, temperature=self._temperature)
        llm_with_tools = llm.bind_tools(tools=self._tools)
        self._graph = create_react_agent(
            model=llm_with_tools,
            tools=self._tools,
            prompt=self._system_prompt,
            checkpointer=checkpointer,
        )

    async def _ensure_async_setup(self):
        """Ensure async components are set up."""
        if self._setup_complete_async:
            return
        engine = await PostgresEngine.afrom_instance(
            project_id=self._project_id,
            region=self._region,
            instance=self._instance_name,
            database=self._database_name,
            user=self._database_user,
            password=self._database_password,
        )
        checkpointer = await PostgresSaver.create(engine=engine)
        self._create_react_agent(checkpointer=checkpointer)
        self._setup_complete_async = True
        self._engine_async = True

    def _ensure_sync_setup(self):
        """Ensure sync components are set up."""
        if self._setup_complete_sync:
            return
        engine = PostgresEngine.from_instance(
            project_id=self._project_id,
            region=self._region,
            instance=self._instance_name,
            database=self._database_name,
            user=self._database_user,
            password=self._database_password,
        )
        checkpointer = PostgresSaver.create_sync(engine=engine)
        self._create_react_agent(checkpointer=checkpointer)
        self._setup_complete_sync = True

    async def async_query(self, **kwargs) -> dict[str, Any] | Any:
        """Asynchronous query execution with filtered current interaction."""
        await self._ensure_async_setup()
        result = await self._graph.ainvoke(**kwargs)
        return self._filter_current_interaction(result)

    async def async_stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        """Asynchronous streaming query execution with filtered chunks."""
        await self._ensure_async_setup()
        async for chunk in self._graph.astream(**kwargs):
            filtered_chunk = self._filter_streaming_chunk(chunk)
            yield dumpd(filtered_chunk)

    def query(self, **kwargs) -> dict[str, Any] | Any:
        """Synchronous query execution with filtered current interaction."""
        self._ensure_sync_setup()
        result = self._graph.invoke(**kwargs)
        return self._filter_current_interaction(result)

    def stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        """Synchronous streaming query execution with filtered chunks."""
        self._ensure_sync_setup()
        for chunk in self._graph.stream(**kwargs):
            filtered_chunk = self._filter_streaming_chunk(chunk)
            yield dumpd(filtered_chunk)

    def _filter_current_interaction(self, result: dict) -> dict:
        """
        Filtra apenas as mensagens da interação atual.
        Retorna apenas as mensagens desde a última HumanMessage até o final.
        """
        if "messages" not in result:
            return result

        messages = result["messages"]
        if not messages:
            return result

        # Encontra o índice da última mensagem humana
        last_human_index = -1
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_human_index = i
                break

        # Se não encontrou mensagem humana, retorna tudo
        if last_human_index == -1:
            return result

        # Filtra apenas as mensagens da interação atual
        current_interaction_messages = messages[last_human_index:]

        # Cria uma cópia do resultado com apenas as mensagens filtradas
        filtered_result = result.copy()
        filtered_result["messages"] = current_interaction_messages

        return filtered_result

    def _filter_streaming_chunk(self, chunk: dict) -> dict:
        """
        Filtra chunks de streaming para incluir apenas mensagens da interação atual.
        """
        if isinstance(chunk, dict) and "messages" in chunk:
            return self._filter_current_interaction(chunk)
        return chunk
