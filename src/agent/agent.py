from typing import Any, Callable, Iterator, Sequence

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


class Agent(AsyncQueryable, AsyncStreamQueryable, Queryable, StreamQueryable):
    def __init__(
        self,
        *,
        model: str = "gemini-2.5-flash",
        system_prompt: str = SYSTEM_PROMPT,
        tools: Sequence[Callable] = None,
        temperature: float = 0.7,
    ):
        self._model: str = model
        self._tools: Sequence[Callable] = tools
        self._graph: CompiledGraph = None
        self._system_prompt: str = system_prompt
        self._temperature: float = temperature

    def set_up(self):
        llm = ChatVertexAI(model_name=self._model, temperature=self._temperature)
        llm_with_tools = llm.bind_tools(tools=self._tools)
        self._graph = create_react_agent(
            model=llm_with_tools, tools=self._tools, prompt=self._system_prompt
        )

    def query(self, **kwargs) -> dict[str, Any] | Any:
        return self._graph.invoke(**kwargs)

    def stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        for chunk in self._graph.stream(**kwargs):
            yield dumpd(chunk)

    async def async_query(self, **kwargs) -> dict[str, Any] | Any:
        return await self._graph.ainvoke(**kwargs)

    async def async_stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        async for chunk in self._graph.astream(**kwargs):
            yield dumpd(chunk)
