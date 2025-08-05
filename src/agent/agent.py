from typing import Any, Callable, Iterator, Sequence
import asyncio
from langchain_core.load.serializable import Serializable
from langchain_core.load import dumpd, loads

from langchain.load.dump import dumpd
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent
from langchain_google_vertexai import ChatVertexAI
from vertexai.agent_engines import (
    AsyncQueryable,
    AsyncStreamQueryable,
    Queryable,
    StreamQueryable,
)
from src.agent.prompt import SYSTEM_PROMPT
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.config import env


class Agent(AsyncQueryable, AsyncStreamQueryable, Queryable, StreamQueryable):
    def __init__(
        self,
        *,
        model: str = "gemini-2.5-flash",
        system_prompt: str = SYSTEM_PROMPT,
        tools: Sequence[Callable] = None,
        temperature: float = 0.7,
        pg_uri: str = env.PG_URI,
    ):
        self._model: str = model
        self._tools: Sequence[Callable] = tools
        self._graph: CompiledGraph = None
        self._system_prompt: str = system_prompt
        self._temperature: float = temperature
        self._pg_uri: str = pg_uri
        self._checkpointer = None
        self._checkpointer_cm = None  # Store the context manager separately
        self._setup_complete = False

    def set_up(self):
        # Just mark that we want to set up, actual setup happens in _ensure_setup
        self._setup_complete = False

    async def _ensure_setup(self):
        if not self._setup_complete:
            llm = ChatVertexAI(model_name=self._model, temperature=self._temperature)
            llm_with_tools = llm.bind_tools(tools=self._tools)

            # Create AsyncPostgresSaver with JsonPlusSerializer for proper message serialization
            self._checkpointer_cm = AsyncPostgresSaver.from_conn_string(self._pg_uri)
            # Enter the context manager to get the actual checkpointer instance
            self._checkpointer = await self._checkpointer_cm.__aenter__()

            self._graph = create_react_agent(
                llm_with_tools,
                self._tools,
                prompt=self._system_prompt,
                checkpointer=self._checkpointer,
            )
            self._setup_complete = True

    def _ensure_setup_sync(self):
        # For sync methods, use synchronous PostgresSaver
        if not self._setup_complete:
            llm = ChatVertexAI(model_name=self._model, temperature=self._temperature)
            llm_with_tools = llm.bind_tools(tools=self._tools)

            # Use synchronous PostgresSaver for sync methods with proper serialization
            checkpointer = PostgresSaver.from_conn_string(self._pg_uri)

            self._graph = create_react_agent(
                llm_with_tools,
                self._tools,
                prompt=self._system_prompt,
                checkpointer=checkpointer,
            )
            self._setup_complete = True

    def query(self, **kwargs) -> dict[str, Any] | Any:
        self._ensure_setup_sync()
        return self._graph.invoke(**kwargs)

    def stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        self._ensure_setup_sync()
        for chunk in self._graph.stream(**kwargs):
            yield dumpd(chunk)

    async def async_query(self, **kwargs) -> dict[str, Any] | Any:
        await self._ensure_setup()
        print(kwargs)
        return await self._graph.ainvoke(**kwargs)

    async def async_stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        await self._ensure_setup()
        async for chunk in self._graph.astream(**kwargs):
            yield dumpd(chunk)

    async def __aenter__(self):
        await self._ensure_setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._checkpointer_cm:
            await self._checkpointer_cm.__aexit__(exc_type, exc_val, exc_tb)
