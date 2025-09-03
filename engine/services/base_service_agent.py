"""
Base class for service agents.
"""

from abc import ABC, abstractmethod
from typing import List, Any, Dict
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage
from langgraph.prebuilt import create_react_agent
from langchain_google_vertexai import ChatVertexAI


class BaseServiceAgent(ABC):
    """
    Base class for specialized service agents.
    
    Each service agent handles a specific domain (tax, infrastructure, health, etc.)
    with focused prompts and domain-specific tools.
    """
    
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.7,
        tools: List[BaseTool] = None,
        checkpointer=None
    ):
        self.model_name = model
        self.temperature = temperature
        self.tools = tools or []
        self.checkpointer = checkpointer
        self._agent = None
    
    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique identifier for this service agent."""
        pass
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt with domain-specific knowledge and instructions."""
        pass
    
    @property
    @abstractmethod
    def service_description(self) -> str:
        """Description of what services this agent handles."""
        pass
    
    def create_agent(self, checkpointer=None):
        """Create the LangGraph agent for this service."""
        if self._agent is None:
            llm = ChatVertexAI(
                model_name=self.model_name, 
                temperature=self.temperature
            )
            
            # Use the provided checkpointer or fall back to the instance checkpointer
            agent_checkpointer = checkpointer or self.checkpointer
            
            self._agent = create_react_agent(
                model=llm.bind_tools(self.tools),
                tools=self.tools,
                prompt=self.system_prompt,
                checkpointer=agent_checkpointer
            )
        
        return self._agent
    
    def invoke(self, input_data: Dict[str, Any], config: Dict[str, Any] = None):
        """Invoke the service agent with input data."""
        if self._agent is None:
            raise ValueError("Agent not created. Call create_agent() first.")
        
        return self._agent.invoke(input_data, config=config)
    
    async def ainvoke(self, input_data: Dict[str, Any], config: Dict[str, Any] = None):
        """Async invoke the service agent with input data."""
        if self._agent is None:
            raise ValueError("Agent not created. Call create_agent() first.")
        
        return await self._agent.ainvoke(input_data, config=config)
