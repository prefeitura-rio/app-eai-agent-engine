"""
Agent Execution Phase Constants

Define constants for each phase of the LangGraph ReAct agent execution lifecycle.
Used by error_interceptor to classify errors by agent phase rather than tool name.

This provides better observability into the agent execution flow:
- Pre-invoke: Input preparation and sanitization
- Pre-model: Memory injection, filtering, thread_id injection
- Agent node: LLM API calls
- Tool execution: External API calls via MCP
- Post-model: Token logging, cleanup
- Graph invocation: Overall graph execution
- Response filter: Final message filtering
"""

from typing import Any, Dict, Optional


# ============================================================================
# PHASE CONSTANTS
# ============================================================================

# Phase 1: Pre-invoke hook (request preparation)
PRE_INVOKE = "pre_invoke"

# Phase 2: Graph invocation (overall execution)
GRAPH_INVOCATION = "graph_invocation"

# Phase 3: Pre-model hook (before LLM call)
PRE_MODEL_HOOK = "pre_model_hook"

# Phase 4: Agent node (LLM execution)
AGENT_NODE = "agent_node"

# Phase 5: Tool execution (MCP tool calls)
TOOL_EXECUTION = "tool_execution"

# Phase 6: Post-model hook (after LLM response)
POST_MODEL_HOOK = "post_model_hook"

# Phase 7: Response filtering
RESPONSE_FILTER = "response_filter"


# ============================================================================
# OPERATION CONSTANTS (Sub-operations within each phase)
# ============================================================================

# Pre-invoke operations
PRE_INVOKE_COMBINED = "combined"
PRE_INVOKE_TIMESTAMP = "add_timestamp"
PRE_INVOKE_SANITIZE = "sanitize_inputs"

# Pre-model operations
PRE_MODEL_COMBINED = "combined"
PRE_MODEL_INJECT_MEMORY = "inject_memory"
PRE_MODEL_FILTER_MEMORY = "filter_memory"
PRE_MODEL_INJECT_THREAD_ID = "inject_thread_id"

# Agent node operations
AGENT_LLM_CALL_SYNC = "llm_call_sync"
AGENT_LLM_CALL_ASYNC = "llm_call_async"

# Tool execution operations (dynamic, based on tool name)
TOOL_EXECUTION_DYNAMIC = "tool_{tool_name}"

# Post-model operations
POST_MODEL_COMBINED = "combined"
POST_MODEL_LOG_TOKENS = "log_tokens"

# Response filter operations
RESPONSE_FILTER_FILTER = "filter"

# Graph invocation operations
GRAPH_ASYNC_QUERY = "async_query"
GRAPH_QUERY = "query"
GRAPH_ASYNC_STREAM = "async_stream_query"
GRAPH_STREAM = "stream_query"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def make_source(
    phase: str,
    operation: str,
    context: Optional[Dict[str, Any]] = None,
    source: str = "eai-engine"
) -> Dict[str, Any]:
    """
    Create a standardized source dictionary for error reporting.

    Args:
        phase: Agent execution phase (use constants above)
        operation: Specific operation within the phase
        context: Additional context information (optional)
        source: Source system name (default: "eai-engine")

    Returns:
        Dictionary with source, phase, operation, and optional context

    Examples:
        >>> make_source(PRE_MODEL_HOOK, PRE_MODEL_INJECT_MEMORY)
        {'source': 'eai-engine', 'phase': 'pre_model_hook', 'operation': 'inject_memory'}

        >>> make_source(TOOL_EXECUTION, "google_search", context={"query": "test"})
        {'source': 'eai-engine', 'phase': 'tool_execution', 'operation': 'google_search', 'context': {'query': 'test'}}

        >>> make_source(AGENT_NODE, AGENT_LLM_CALL_ASYNC, context={"model": "gemini-pro"})
        {'source': 'eai-engine', 'phase': 'agent_node', 'operation': 'llm_call_async', 'context': {'model': 'gemini-pro'}}
    """
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
    """
    Create a source dictionary specifically for tool execution errors.

    Args:
        tool_name: Name of the tool being executed
        context: Additional context (e.g., tool parameters)

    Returns:
        Dictionary with phase=tool_execution and operation=tool_name

    Example:
        >>> make_tool_source("google_search", context={"query": "Rio de Janeiro"})
        {'source': 'eai-engine', 'phase': 'tool_execution', 'operation': 'google_search', 'context': {'query': 'Rio de Janeiro'}}
    """
    return make_source(TOOL_EXECUTION, tool_name, context=context)


def extract_thread_id_from_config(args, kwargs) -> str:
    """
    Extract thread_id from LangGraph config for use as user_id.

    This is a helper function for the @interceptor decorator's extract_user_id parameter.

    Args:
        args: Positional arguments passed to the decorated function
        kwargs: Keyword arguments passed to the decorated function

    Returns:
        thread_id if found, otherwise "unknown"

    Example:
        >>> @interceptor(
        ...     source=make_source(PRE_MODEL_HOOK, PRE_MODEL_COMBINED),
        ...     extract_user_id=extract_thread_id_from_config
        ... )
        ... async def _combined_pre_model_hook(state, config):
        ...     pass
    """
    config = kwargs.get("config", {})
    if isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict):
            return configurable.get("thread_id", "unknown")
    return "unknown"


# ============================================================================
# BACKWARD COMPATIBILITY
# ============================================================================

# Support old MCP-style source dictionaries for gradual migration
def normalize_source(source: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize old-style (MCP) source dicts to new agent phase format.

    Converts:
        {"source": "eai-engine", "tool": "search"} 
    To:
        {"source": "eai-engine", "phase": "tool_execution", "operation": "search"}

    Args:
        source: Source dictionary (old or new format)

    Returns:
        Normalized source dictionary with phase/operation format
    """
    # Already in new format
    if "phase" in source:
        return source
    
    # Convert old MCP format
    if "tool" in source:
        phase = TOOL_EXECUTION
        operation = source["tool"]
        
        # If workflow is specified, combine them
        if "workflow" in source:
            operation = f"{operation}({source['workflow']})"
        
        return {
            "source": source.get("source", "eai-engine"),
            "phase": phase,
            "operation": operation,
        }
    
    # Unknown format, return as-is
    return source
