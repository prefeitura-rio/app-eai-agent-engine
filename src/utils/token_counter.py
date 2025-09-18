"""
Token counting utilities for short-term memory management.

This module provides functions to count tokens in messages using the same
tokenizer as the agent's model to ensure accurate token counting for memory limits.
"""

from typing import List
from langchain_core.messages import BaseMessage
from langchain_google_vertexai import ChatVertexAI
import logging

logger = logging.getLogger(__name__)


def count_tokens_in_messages(messages: List[BaseMessage], model_name: str = "gemini-2.5-flash") -> int:
    """
    Count the total number of tokens for a list of messages using the same
    tokenizer as the agent's model.
    
    Args:
        messages: List of BaseMessage objects to count tokens for
        model_name: Name of the model to use for token counting (should match agent's model)
        
    Returns:
        Total number of tokens across all messages
    """
    if not messages:
        return 0
    
    try:
        # Create a temporary model instance for token counting
        # We use temperature=0 and minimal settings since we only need tokenization
        llm = ChatVertexAI(model_name=model_name, temperature=0)
        
        # Convert messages to the format expected by the model
        total_tokens = 0
        
        for message in messages:
            try:
                # Get token count for individual message
                # ChatVertexAI should have a method to count tokens
                if hasattr(llm, 'get_num_tokens'):
                    tokens = llm.get_num_tokens(message.content)
                else:
                    # Fallback: rough estimation based on character count
                    # Generally, 1 token ≈ 4 characters for most models
                    tokens = len(str(message.content)) // 4
                    
                total_tokens += tokens
                
                # Add some overhead for message metadata (type, role, etc.)
                # This accounts for system tokens used for message structure
                total_tokens += 10  # Small overhead per message
                
            except Exception as e:
                logger.warning(f"Error counting tokens for message {message.id}: {e}")
                # Fallback estimation
                total_tokens += len(str(message.content)) // 4 + 10
                
        return total_tokens
        
    except Exception as e:
        logger.error(f"Error initializing model for token counting: {e}")
        # Fallback: rough estimation based on character count
        total_chars = sum(len(str(msg.content)) for msg in messages)
        return (total_chars // 4) + (len(messages) * 10)  # 4 chars per token + overhead


def estimate_tokens_for_message(message: BaseMessage) -> int:
    """
    Quick estimation of tokens for a single message without model initialization.
    
    Args:
        message: BaseMessage to estimate tokens for
        
    Returns:
        Estimated number of tokens
    """
    # Simple estimation: ~4 characters per token + message overhead
    content_length = len(str(message.content))
    estimated_tokens = (content_length // 4) + 10
    
    # Add extra tokens for tool calls if present
    if hasattr(message, 'tool_calls') and message.tool_calls:
        # Each tool call adds significant token overhead
        estimated_tokens += len(message.tool_calls) * 50
    
    return estimated_tokens


def find_messages_within_token_limit(
    messages: List[BaseMessage], 
    token_limit: int, 
    model_name: str = "gemini-2.5-flash"
) -> List[BaseMessage]:
    """
    Find the maximum number of recent messages that fit within the token limit.
    Messages are processed from newest to oldest.
    
    Args:
        messages: List of messages ordered from oldest to newest
        token_limit: Maximum number of tokens allowed
        model_name: Model name for accurate token counting
        
    Returns:
        List of messages that fit within the token limit, preserving order
    """
    if not messages:
        return []
    
    if token_limit <= 0:
        return []
    
    # Process messages from newest to oldest
    result_messages = []
    total_tokens = 0
    
    # Reverse to process from newest to oldest
    for message in reversed(messages):
        # Estimate tokens for this message
        message_tokens = estimate_tokens_for_message(message)
        
        # Check if adding this message would exceed the limit
        if total_tokens + message_tokens > token_limit:
            # If this is the first message and it's too big, skip it
            # Otherwise, stop here to stay within limit
            break
            
        # Add message to the beginning of result (to maintain chronological order)
        result_messages.insert(0, message)
        total_tokens += message_tokens
    
    # If we have messages, do a final accurate count to ensure we're within limit
    if result_messages:
        accurate_count = count_tokens_in_messages(result_messages, model_name)
        
        # If accurate count exceeds limit, remove oldest messages until we fit
        while result_messages and accurate_count > token_limit:
            result_messages.pop(0)  # Remove oldest message
            if result_messages:
                accurate_count = count_tokens_in_messages(result_messages, model_name)
            else:
                accurate_count = 0
    
    return result_messages