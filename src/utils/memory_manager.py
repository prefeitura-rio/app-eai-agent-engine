"""
Memory management utilities for implementing short-term memory limits.

This module provides functions to filter and trim messages based on time
and token limits, using LangGraph's RemoveMessage and LangChain's trim_messages.
"""

from typing import List, Sequence, Dict, Any
from datetime import datetime, timezone, timedelta
from langchain_core.messages import BaseMessage
from langchain_core.messages import trim_messages
from langgraph.graph.message import RemoveMessage
from src.utils.token_counter import find_messages_within_token_limit
import logging

logger = logging.getLogger(__name__)


def filter_messages_by_time_limit(
    messages: Sequence[BaseMessage], 
    time_limit_days: float
) -> Dict[str, Any]:
    """
    Filter messages to only include those within the time limit.
    Messages older than time_limit_days will be marked for removal.
    
    Args:
        messages: Sequence of messages to filter
        time_limit_days: Maximum age of messages in days
        
    Returns:
        List of messages within the time limit
    """
    if time_limit_days <= 0:
        return list(messages)  # No time limit
    
    if not messages:
        return []
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=time_limit_days)
    filtered_messages = []
    
    for message in messages:
        message_time = None
        
        # Try to get timestamp from additional_kwargs (our custom timestamp)
        if hasattr(message, 'additional_kwargs') and message.additional_kwargs:
            timestamp_str = message.additional_kwargs.get('timestamp')
            if timestamp_str:
                try:
                    message_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except (ValueError, TypeError) as e:
                    logger.debug(f"Could not parse timestamp '{timestamp_str}': {e}")
        
        # Fallback: check if message has a created_at or timestamp attribute
        if message_time is None:
            for attr in ['created_at', 'timestamp']:
                if hasattr(message, attr):
                    attr_value = getattr(message, attr)
                    if isinstance(attr_value, datetime):
                        message_time = attr_value
                        break
                    elif isinstance(attr_value, str):
                        try:
                            message_time = datetime.fromisoformat(attr_value.replace('Z', '+00:00'))
                            break
                        except (ValueError, TypeError):
                            continue
        
        # If we still don't have a time, assume the message is recent
        if message_time is None:
            logger.debug(f"No timestamp found for message {getattr(message, 'id', 'unknown')}, keeping it")
            filtered_messages.append(message)
            continue
        
        # Ensure timezone awareness
        if message_time.tzinfo is None:
            message_time = message_time.replace(tzinfo=timezone.utc)
        
        # Keep message if it's within the time limit
        if message_time >= cutoff_time:
            filtered_messages.append(message)
        else:
            logger.debug(f"Filtering out message older than {time_limit_days} days: {message_time}")
    
    return filtered_messages


def create_remove_messages_for_old_messages(
    messages: Sequence[BaseMessage], 
    time_limit_days: float
) -> List[RemoveMessage]:
    """
    Create RemoveMessage objects for messages older than the time limit.
    
    Args:
        messages: Sequence of messages to check
        time_limit_days: Maximum age of messages in days
        
    Returns:
        List of RemoveMessage objects for old messages
    """
    if time_limit_days <= 0:
        return []  # No time limit
    
    if not messages:
        return []
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=time_limit_days)
    remove_messages = []
    
    for message in messages:
        message_time = None
        
        # Try to get timestamp from additional_kwargs (our custom timestamp)
        if hasattr(message, 'additional_kwargs') and message.additional_kwargs:
            timestamp_str = message.additional_kwargs.get('timestamp')
            if timestamp_str:
                try:
                    message_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except (ValueError, TypeError) as e:
                    logger.debug(f"Could not parse timestamp '{timestamp_str}': {e}")
        
        # Fallback: check if message has a created_at or timestamp attribute
        if message_time is None:
            for attr in ['created_at', 'timestamp']:
                if hasattr(message, attr):
                    attr_value = getattr(message, attr)
                    if isinstance(attr_value, datetime):
                        message_time = attr_value
                        break
                    elif isinstance(attr_value, str):
                        try:
                            message_time = datetime.fromisoformat(attr_value.replace('Z', '+00:00'))
                            break
                        except (ValueError, TypeError):
                            continue
        
        # If we have a time and it's too old, mark for removal
        if message_time is not None:
            # Ensure timezone awareness
            if message_time.tzinfo is None:
                message_time = message_time.replace(tzinfo=timezone.utc)
            
            if message_time < cutoff_time:
                if hasattr(message, 'id') and message.id:
                    remove_messages.append(RemoveMessage(id=message.id))
                    logger.debug(f"Marking old message for removal: {message.id} (age: {message_time})")
    
    return remove_messages


def _preserve_function_call_pairs(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Ensure function calls and their responses stay together.
    If a function call is included, its response must also be included.
    If a function response is included, its call must also be included.
    
    Args:
        messages: List of messages to check for function call/response pairs
        
    Returns:
        List of messages with complete function call/response pairs
    """
    from langchain_core.messages import AIMessage, ToolMessage
    
    # Track which tool calls need their responses and vice versa
    tool_call_ids = set()
    tool_response_ids = set()
    
    # First pass: identify all tool calls and responses
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_call_ids.add(tool_call['id'])
        elif isinstance(message, ToolMessage) and hasattr(message, 'tool_call_id'):
            tool_response_ids.add(message.tool_call_id)
    
    # Find orphaned calls and responses
    orphaned_calls = tool_call_ids - tool_response_ids
    orphaned_responses = tool_response_ids - tool_call_ids
    
    if not orphaned_calls and not orphaned_responses:
        return messages  # All pairs are complete
    
    # Filter out orphaned tool calls and responses
    filtered_messages = []
    
    for message in messages:
        should_include = True
        
        # Check if this is an orphaned tool call
        if isinstance(message, AIMessage) and message.tool_calls:
            # Remove tool calls that don't have responses
            valid_tool_calls = [
                tc for tc in message.tool_calls 
                if tc['id'] not in orphaned_calls
            ]
            
            if len(valid_tool_calls) != len(message.tool_calls):
                if valid_tool_calls:
                    # Create new message with only valid tool calls
                    new_message = AIMessage(
                        content=message.content,
                        tool_calls=valid_tool_calls,
                        additional_kwargs=message.additional_kwargs,
                        response_metadata=getattr(message, 'response_metadata', {}),
                        id=message.id
                    )
                    filtered_messages.append(new_message)
                else:
                    # No valid tool calls, include as regular AI message
                    new_message = AIMessage(
                        content=message.content,
                        additional_kwargs=message.additional_kwargs,
                        response_metadata=getattr(message, 'response_metadata', {}),
                        id=message.id
                    )
                    filtered_messages.append(new_message)
                continue
        
        # Check if this is an orphaned tool response
        elif isinstance(message, ToolMessage) and hasattr(message, 'tool_call_id'):
            if message.tool_call_id in orphaned_responses:
                should_include = False
        
        if should_include:
            filtered_messages.append(message)
    
    return filtered_messages


def trim_messages_by_token_limit(
    messages: List[BaseMessage], 
    token_limit: int, 
    model_name: str = "gemini-2.5-flash"
) -> List[BaseMessage]:
    """
    Trim messages to stay within token limit while preserving function call/response pairs.
    This ensures complete messages are preserved (no truncation) and that tool calls
    always have their corresponding responses.
    
    Args:
        messages: List of messages to trim (should be in chronological order)
        token_limit: Maximum number of tokens allowed
        model_name: Model name for token counting
        
    Returns:
        List of messages that fit within the token limit with complete function pairs
    """
    if not messages or token_limit <= 0:
        return []
    
    try:
        # Use LangChain's trim_messages which respects complete messages
        from langchain_google_vertexai import ChatVertexAI
        
        # Create temporary model for token counting
        llm = ChatVertexAI(model_name=model_name, temperature=0)
        
        # Use trim_messages with our specific requirements
        trimmed_messages = trim_messages(
            messages,
            max_tokens=token_limit,
            token_counter=llm,  # Use the same model as the agent
            strategy="last",  # Keep the most recent messages
            allow_partial=False,  # Don't truncate messages
            start_on="human",  # Prefer to start on human messages when possible
            end_on=("human", "ai"),  # Can end on either human or AI messages
        )
        
        # Ensure function call/response pairs are preserved
        final_messages = _preserve_function_call_pairs(trimmed_messages)
        
        return final_messages
        
    except Exception as e:
        logger.warning(f"Error using trim_messages, falling back to manual trimming: {e}")
        
        # Fallback to our custom implementation
        manual_trimmed = find_messages_within_token_limit(messages, token_limit, model_name)
        return _preserve_function_call_pairs(manual_trimmed)


def apply_memory_limits(
    messages: Sequence[BaseMessage],
    token_limit: int,
    time_limit_days: float,
    model_name: str = "gemini-2.5-flash"
) -> List[BaseMessage]:
    """
    Apply both time and token limits to a list of messages.
    
    This function:
    1. First filters out messages older than time_limit_days
    2. Then trims remaining messages to fit within token_limit
    3. Preserves complete messages (no truncation)
    4. Maintains chronological order
    
    Args:
        messages: Sequence of messages to filter
        token_limit: Maximum number of tokens allowed
        time_limit_days: Maximum age of messages in days
        model_name: Model name for accurate token counting
        
    Returns:
        List of filtered and trimmed messages
    """
    if not messages:
        return []
    
    # Step 1: Filter by time limit
    time_filtered_messages = filter_messages_by_time_limit(messages, time_limit_days)
    
    if not time_filtered_messages:
        logger.debug("No messages remaining after time filtering")
        return []
    
    logger.debug(f"After time filtering: {len(time_filtered_messages)} messages remain "
                f"(from original {len(messages)})")
    
    # Step 2: Trim by token limit
    token_trimmed_messages = trim_messages_by_token_limit(
        time_filtered_messages, token_limit, model_name
    )
    
    logger.debug(f"After token trimming: {len(token_trimmed_messages)} messages remain "
                f"(from {len(time_filtered_messages)} time-filtered messages)")
    
    return token_trimmed_messages


def get_memory_management_stats(
    original_messages: Sequence[BaseMessage],
    filtered_messages: List[BaseMessage],
    token_limit: int,
    time_limit_days: int
) -> dict:
    """
    Get statistics about memory management filtering.
    
    Args:
        original_messages: Original message list before filtering
        filtered_messages: Message list after filtering
        token_limit: Token limit that was applied
        time_limit_days: Time limit that was applied
        
    Returns:
        Dictionary with filtering statistics
    """
    from src.utils.token_counter import count_tokens_in_messages, estimate_tokens_for_message
    
    original_count = len(original_messages)
    filtered_count = len(filtered_messages)
    
    # Estimate token counts
    original_tokens = sum(estimate_tokens_for_message(msg) for msg in original_messages)
    filtered_tokens = sum(estimate_tokens_for_message(msg) for msg in filtered_messages)
    
    # Calculate time span
    time_span_hours = None
    if filtered_messages and len(filtered_messages) > 1:
        try:
            oldest_msg = filtered_messages[0]
            newest_msg = filtered_messages[-1]
            
            oldest_time = None
            newest_time = None
            
            for msg in [oldest_msg, newest_msg]:
                if hasattr(msg, 'additional_kwargs') and msg.additional_kwargs:
                    timestamp_str = msg.additional_kwargs.get('timestamp')
                    if timestamp_str:
                        try:
                            msg_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            if msg == oldest_msg:
                                oldest_time = msg_time
                            else:
                                newest_time = msg_time
                        except (ValueError, TypeError):
                            pass
            
            if oldest_time and newest_time:
                time_span_hours = (newest_time - oldest_time).total_seconds() / 3600
                
        except Exception as e:
            logger.debug(f"Could not calculate time span: {e}")
    
    return {
        "original_message_count": original_count,
        "filtered_message_count": filtered_count,
        "messages_removed": original_count - filtered_count,
        "removal_percentage": round((original_count - filtered_count) / original_count * 100, 1) if original_count > 0 else 0,
        "original_estimated_tokens": original_tokens,
        "filtered_estimated_tokens": filtered_tokens,
        "tokens_removed": original_tokens - filtered_tokens,
        "token_limit": token_limit,
        "time_limit_days": time_limit_days,
        "conversation_span_hours": round(time_span_hours, 2) if time_span_hours else None,
        "within_token_limit": filtered_tokens <= token_limit,
    }