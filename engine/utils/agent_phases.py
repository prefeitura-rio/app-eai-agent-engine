"""
Agent Execution Phase Constants

Define constants for each phase of the LangGraph ReAct agent execution lifecycle.
Used by error_interceptor to classify errors by agent phase rather than tool name.
"""

from typing import Any, Dict, Optional


# Phase constants
PRE_INVOKE = "pre_invoke"
GRAPH_INVOCATION = "graph_invocation"
PRE_MODEL_HOOK = "pre_model_hook"
AGENT_NODE = "agent_node"
TOOL_EXECUTION = "tool_execution"
POST_MODEL_HOOK = "post_model_hook"
RESPONSE_FILTER = "response_filter"

# Operation constants
PRE_INVOKE_COMBINED = "combined"
PRE_INVOKE_TIMESTAMP = "add_timestamp"
PRE_INVOKE_SANITIZE = "sanitize_inputs"

PRE_MODEL_COMBINED = "combined"
PRE_MODEL_INJECT_MEMORY = "inject_memory"
PRE_MODEL_FILTER_MEMORY = "filter_memory"
PRE_MODEL_INJECT_THREAD_ID = "inject_thread_id"

AGENT_LLM_CALL_SYNC = "llm_call_sync"
AGENT_LLM_CALL_ASYNC = "llm_call_async"

POST_MODEL_COMBINED = "combined"
POST_MODEL_LOG_TOKENS = "log_tokens"

RESPONSE_FILTER_FILTER = "filter"

GRAPH_ASYNC_QUERY = "async_query"
GRAPH_QUERY = "query"
GRAPH_ASYNC_STREAM = "async_stream_query"
GRAPH_STREAM = "stream_query"


def make_source(
    phase: str,
    operation: str,
    context: Optional[Dict[str, Any]] = None,
    source: str = "eai-engine"
) -> Dict[str, Any]:
    """Create a standardized source dictionary for error reporting."""
    result = {
        "source": source,
        "phase": phase,
        "operation": operation,
    }
    
    if context:
        result["context"] = context
    
    return result


def make_tool_source(
    tool_name: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a source dictionary specifically for tool execution errors."""
    return make_source(TOOL_EXECUTION, tool_name, context=context)


def extract_thread_id_from_config(args, kwargs) -> str:
    """Extract thread_id from LangGraph config for use as user_id."""
    config = kwargs.get("config", {})
    if isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict):
            return configurable.get("thread_id", "unknown")
    return "unknown"
