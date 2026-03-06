"""
Monitored Tool Node

A wrapper around LangGraph's ToolNode that adds automatic error reporting
for tool execution failures. This provides visibility into which tools are
failing and why, helping with debugging and monitoring.
"""

import traceback
from typing import Any, Dict, List, Union
from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.types import interrupt

from engine.utils import send_general_error, make_tool_source, TOOL_EXECUTION
from engine.log import logger


class MonitoredToolNode(ToolNode):
    """
    Enhanced ToolNode that reports tool execution errors to the error interceptor.
    
    Wraps LangGraph's ToolNode to add automatic error monitoring without changing
    the tool execution behavior. Errors are reported asynchronously and do not
    block or interfere with normal error propagation.
    
    Usage:
        Instead of:
            tool_node = ToolNode(tools)
        
        Use:
            tool_node = MonitoredToolNode(tools)
    """

    async def _arun(
        self,
        tool_input: Dict[str, Any],
        *,
        store: Any = None,
        config: Dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        """
        Execute tool with error monitoring.
        
        This overrides ToolNode's _arun to wrap it with error reporting.
        All errors are reported to the error interceptor before being re-raised.
        """
        tool_name = "unknown"
        thread_id = "unknown"
        
        try:
            # Extract context for error reporting
            tool_name = tool_input.get("name", "unknown") if isinstance(tool_input, dict) else "unknown"
            
            # Extract thread_id from config
            if isinstance(config, dict):
                configurable = config.get("configurable", {})
                thread_id = configurable.get("thread_id", "unknown")
            
            # Execute the tool using parent class method
            return await super()._arun(tool_input, store=store, config=config, **kwargs)
            
        except Exception as e:
            # Report error to interceptor
            try:
                # Extract tool arguments for context
                tool_args = {}
                if isinstance(tool_input, dict):
                    tool_args = tool_input.get("args", {})
                    # Limit size of args to avoid huge payloads
                    if isinstance(tool_args, dict):
                        tool_args = {k: str(v)[:100] for k, v in list(tool_args.items())[:10]}
                
                # Create source with tool context
                source = make_tool_source(
                    tool_name=tool_name,
                    context={"args_preview": tool_args} if tool_args else None
                )
                
                # Send error report (non-blocking)
                await send_general_error(
                    user_id=thread_id,
                    source=source,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    traceback=traceback.format_exc(),
                    input_body=tool_input,
                )
                
                logger.info(
                    f"[Error Monitor] Reported tool execution error: {tool_name} | "
                    f"Error: {type(e).__name__}: {str(e)[:100]}"
                )
                
            except Exception as report_error:
                # If error reporting fails, log but don't interfere with original error
                logger.warning(
                    f"[Error Monitor] Failed to report tool error: {report_error}"
                )
            
            # Re-raise original error to maintain normal error flow
            raise

    def _run(
        self,
        tool_input: Dict[str, Any],
        *,
        store: Any = None,
        config: Dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        """
        Synchronous tool execution with error monitoring.
        
        Similar to _arun but for synchronous execution.
        Note: Error reporting is still async, handled via event loop.
        """
        tool_name = "unknown"
        thread_id = "unknown"
        
        try:
            # Extract context for error reporting
            tool_name = tool_input.get("name", "unknown") if isinstance(tool_input, dict) else "unknown"
            
            # Extract thread_id from config
            if isinstance(config, dict):
                configurable = config.get("configurable", {})
                thread_id = configurable.get("thread_id", "unknown")
            
            # Execute the tool using parent class method
            return super()._run(tool_input, store=store, config=config, **kwargs)
            
        except Exception as e:
            # Report error to interceptor
            try:
                import asyncio
                
                # Extract tool arguments for context
                tool_args = {}
                if isinstance(tool_input, dict):
                    tool_args = tool_input.get("args", {})
                    # Limit size of args to avoid huge payloads
                    if isinstance(tool_args, dict):
                        tool_args = {k: str(v)[:100] for k, v in list(tool_args.items())[:10]}
                
                # Create source with tool context
                source = make_tool_source(
                    tool_name=tool_name,
                    context={"args_preview": tool_args} if tool_args else None
                )
                
                # Send error report (try to run async in current event loop)
                try:
                    loop = asyncio.get_running_loop()
                    # Schedule error reporting as a task (fire and forget)
                    loop.create_task(send_general_error(
                        user_id=thread_id,
                        source=source,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        traceback=traceback.format_exc(),
                        input_body=tool_input,
                    ))
                except RuntimeError:
                    # No event loop, skip async error reporting
                    logger.warning(
                        f"[Error Monitor] Cannot report sync tool error (no event loop): {tool_name}"
                    )
                
                logger.info(
                    f"[Error Monitor] Reported tool execution error: {tool_name} | "
                    f"Error: {type(e).__name__}: {str(e)[:100]}"
                )
                
            except Exception as report_error:
                # If error reporting fails, log but don't interfere with original error
                logger.warning(
                    f"[Error Monitor] Failed to report tool error: {report_error}"
                )
            
            # Re-raise original error to maintain normal error flow
            raise
