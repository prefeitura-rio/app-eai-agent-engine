"""
Orchestrator tools for routing to specialized service agents.
"""

from typing import Annotated
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.prebuilt import InjectedState
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.types import Command


def create_handoff_tools():
    """
    Create handoff tools for routing to specialized service agents.
    
    Returns a list of tools that the main agent can use to route
    requests to specialized service agents.
    """
    
    @tool(description="Route tax-related requests to the specialized tax agent. Use for IPTU, ISS, tax payments, certifications, and any tax-related services.")
    def route_to_tax_agent(
        query: str,
        state: Annotated[AgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> Command:
        """Route request to tax services specialist."""
        return Command(
            goto="tax_agent",
            update={
                "messages": state["messages"] + [
                    ToolMessage(
                        content=f"Routing to tax services specialist for: {query}",
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
    
    @tool(description="Route infrastructure requests to the specialized infrastructure agent. Use for street lighting, potholes, road maintenance, public facility issues.")
    def route_to_infrastructure_agent(
        query: str,
        state: Annotated[AgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> Command:
        """Route request to infrastructure services specialist."""
        return Command(
            goto="infrastructure_agent",
            update={
                "messages": state["messages"] + [
                    ToolMessage(
                        content=f"Routing to infrastructure services specialist for: {query}",
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
    
    @tool(description="Route health-related requests to the specialized health agent. Use for medical appointments, clinic information, vaccination services, health programs.")
    def route_to_health_agent(
        query: str,
        state: Annotated[AgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> Command:
        """Route request to health services specialist."""
        return Command(
            goto="health_agent",
            update={
                "messages": state["messages"] + [
                    ToolMessage(
                        content=f"Routing to health services specialist for: {query}",
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
    
    return [
        route_to_tax_agent,
        route_to_infrastructure_agent, 
        route_to_health_agent
    ]
