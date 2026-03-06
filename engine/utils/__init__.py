"""
Safe error monitoring utilities with graceful fallbacks.

This module provides conditional imports that fallback to no-op implementations
if error monitoring is not available or fails to load.
"""

from functools import wraps
from typing import Any, Callable, Dict, Optional


# Try to import error monitoring, fallback to no-op if unavailable
try:
    from engine.utils.error_interceptor import (
        interceptor,
        send_error_to_interceptor,
        send_api_error,
        send_general_error,
    )
    from engine.utils.agent_phases import (
        PRE_INVOKE,
        PRE_MODEL_HOOK,
        POST_MODEL_HOOK,
        GRAPH_INVOCATION,
        RESPONSE_FILTER,
        AGENT_NODE,
        TOOL_EXECUTION,
        PRE_INVOKE_COMBINED,
        PRE_INVOKE_TIMESTAMP,
        PRE_INVOKE_SANITIZE,
        PRE_MODEL_COMBINED,
        PRE_MODEL_INJECT_MEMORY,
        PRE_MODEL_FILTER_MEMORY,
        PRE_MODEL_INJECT_THREAD_ID,
        POST_MODEL_COMBINED,
        POST_MODEL_LOG_TOKENS,
        RESPONSE_FILTER_FILTER,
        AGENT_LLM_CALL_SYNC,
        AGENT_LLM_CALL_ASYNC,
        GRAPH_ASYNC_QUERY,
        GRAPH_QUERY,
        GRAPH_ASYNC_STREAM,
        GRAPH_STREAM,
        make_source,
        make_tool_source,
        extract_thread_id_from_config,
    )
    ERROR_MONITORING_AVAILABLE = True
except Exception as e:
    # Error monitoring not available - create no-op implementations
    ERROR_MONITORING_AVAILABLE = False
    
    # No-op decorator that does nothing
    def interceptor(
        source: Dict[str, Any],
        error_types: tuple = (Exception,),
        extract_user_id: Optional[Callable] = None,
        extract_source: Optional[Callable] = None,
    ):
        """No-op interceptor when error monitoring is unavailable."""
        def decorator(func):
            return func
        return decorator
    
    # Placeholder constants
    PRE_INVOKE = "pre_invoke"
    PRE_MODEL_HOOK = "pre_model_hook"
    POST_MODEL_HOOK = "post_model_hook"
    GRAPH_INVOCATION = "graph_invocation"
    RESPONSE_FILTER = "response_filter"
    AGENT_NODE = "agent_node"
    TOOL_EXECUTION = "tool_execution"
    
    PRE_INVOKE_COMBINED = "combined"
    PRE_INVOKE_TIMESTAMP = "add_timestamp"
    PRE_INVOKE_SANITIZE = "sanitize_inputs"
    PRE_MODEL_COMBINED = "combined"
    PRE_MODEL_INJECT_MEMORY = "inject_memory"
    PRE_MODEL_FILTER_MEMORY = "filter_memory"
    PRE_MODEL_INJECT_THREAD_ID = "inject_thread_id"
    POST_MODEL_COMBINED = "combined"
    POST_MODEL_LOG_TOKENS = "log_tokens"
    RESPONSE_FILTER_FILTER = "filter"
    AGENT_LLM_CALL_SYNC = "llm_call_sync"
    AGENT_LLM_CALL_ASYNC = "llm_call_async"
    GRAPH_ASYNC_QUERY = "async_query"
    GRAPH_QUERY = "query"
    GRAPH_ASYNC_STREAM = "async_stream_query"
    GRAPH_STREAM = "stream_query"
    
    def extract_thread_id_from_config(args, kwargs) -> str:
        return "unknown"
    
    def make_source(phase: str, operation: str, context=None, source: str = "eai-engine") -> Dict[str, Any]:
        return {"source": source, "phase": phase, "operation": operation}
    
    def make_tool_source(tool_name: str, context=None) -> Dict[str, Any]:
        return {"source": "eai-engine", "phase": "tool_execution", "operation": tool_name}


__all__ = [
    "interceptor",
    "ERROR_MONITORING_AVAILABLE",
    "PRE_INVOKE",
    "PRE_MODEL_HOOK",
    "POST_MODEL_HOOK",
    "GRAPH_INVOCATION",
    "RESPONSE_FILTER",
    "AGENT_NODE",
    "TOOL_EXECUTION",
    "PRE_INVOKE_COMBINED",
    "PRE_INVOKE_TIMESTAMP",
    "PRE_INVOKE_SANITIZE",
    "PRE_MODEL_COMBINED",
    "PRE_MODEL_INJECT_MEMORY",
    "PRE_MODEL_FILTER_MEMORY",
    "PRE_MODEL_INJECT_THREAD_ID",
    "POST_MODEL_COMBINED",
    "POST_MODEL_LOG_TOKENS",
    "RESPONSE_FILTER_FILTER",
    "AGENT_LLM_CALL_SYNC",
    "AGENT_LLM_CALL_ASYNC",
    "GRAPH_ASYNC_QUERY",
    "GRAPH_QUERY",
    "GRAPH_ASYNC_STREAM",
    "GRAPH_STREAM",
    "extract_thread_id_from_config",
    "make_source",
    "make_tool_source",
]
