"""Token counting utilities for message management."""

import tiktoken
from typing import List
from langchain_core.messages import BaseMessage
import logging

logger = logging.getLogger(__name__)


class TokenCounter:
    """Utility class for counting tokens in messages."""
    
    def __init__(self, model_name: str = "gpt-4"):
        """Initialize token counter with a specific model encoding.
        
        Args:
            model_name: Model name to use for encoding. Defaults to "gpt-4" 
                       which is compatible with most modern models.
        """
        try:
            # Use cl100k_base encoding which is used by GPT-4 and most modern models
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to get tiktoken encoding: {e}. Using approximation.")
            self.encoding = None
    
    def count_message_tokens(self, message: BaseMessage) -> int:
        """Count tokens in a single message.
        
        Args:
            message: The LangChain message to count tokens for
            
        Returns:
            Number of tokens in the message
        """
        try:
            # Get message content
            content = ""
            
            # Handle different message types
            if hasattr(message, 'content') and message.content:
                content = str(message.content)
            
            # Add tool calls if present (for AI messages)
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    content += f" {tool_call.get('name', '')} {str(tool_call.get('args', {}))}"
            
            # Add tool result if present (for tool messages)
            if hasattr(message, 'name') and message.name:
                content += f" tool:{message.name}"
            
            if self.encoding:
                # Use tiktoken for accurate counting
                return len(self.encoding.encode(content))
            else:
                # Fallback approximation: ~4 characters per token
                return len(content) // 4
                
        except Exception as e:
            logger.warning(f"Error counting tokens for message: {e}")
            # Fallback approximation
            return len(str(message.content)) // 4 if hasattr(message, 'content') else 0
    
    def count_messages_tokens(self, messages: List[BaseMessage]) -> int:
        """Count total tokens in a list of messages.
        
        Args:
            messages: List of LangChain messages
            
        Returns:
            Total number of tokens across all messages
        """
        total_tokens = 0
        for message in messages:
            total_tokens += self.count_message_tokens(message)
        return total_tokens
    
    def get_cumulative_token_counts(self, messages: List[BaseMessage]) -> List[int]:
        """Get cumulative token counts for a list of messages.
        
        Args:
            messages: List of LangChain messages
            
        Returns:
            List of cumulative token counts, where each index i contains
            the total tokens from message 0 to message i (inclusive)
        """
        cumulative_counts = []
        total_tokens = 0
        
        for message in messages:
            total_tokens += self.count_message_tokens(message)
            cumulative_counts.append(total_tokens)
        
        return cumulative_counts
