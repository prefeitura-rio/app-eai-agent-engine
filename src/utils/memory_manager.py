"""Memory management utilities for limiting context based on tokens and time."""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, RemoveMessage
from src.utils.token_counter import TokenCounter
from src.config import env
import logging

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages conversation memory with token and time-based limits."""
    
    def __init__(
        self, 
        token_limit: int = None, 
        time_limit_days: int = None,
        model_name: str = "gpt-4"
    ):
        """Initialize memory manager.
        
        Args:
            token_limit: Maximum number of tokens to keep in memory
            time_limit_days: Maximum age of messages in days
            model_name: Model name for token counting
        """
        self.token_limit = token_limit or env.SHORT_MEMORY_TOKEN_LIMIT
        self.time_limit_days = time_limit_days or env.SHORT_MEMORY_TIME_LIMIT
        self.token_counter = TokenCounter(model_name)
        
        logger.info(
            f"MemoryManager initialized - Token limit: {self.token_limit}, "
            f"Time limit: {self.time_limit_days} days"
        )
    
    def _get_message_timestamp(self, message: BaseMessage) -> Optional[datetime]:
        """Extract timestamp from message additional_kwargs.
        
        Args:
            message: LangChain message
            
        Returns:
            Datetime object if timestamp found, None otherwise
        """
        try:
            if hasattr(message, 'additional_kwargs') and 'timestamp' in message.additional_kwargs:
                timestamp_str = message.additional_kwargs['timestamp']
                # Handle ISO format with or without 'Z'
                if timestamp_str.endswith('Z'):
                    timestamp_str = timestamp_str.replace('Z', '+00:00')
                return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.debug(f"Could not parse timestamp from message: {e}")
        
        return None
    
    def _is_message_too_old(self, message: BaseMessage, cutoff_time: datetime) -> bool:
        """Check if a message is older than the time limit.
        
        Args:
            message: LangChain message
            cutoff_time: Messages older than this time should be filtered out
            
        Returns:
            True if message is too old, False otherwise
        """
        msg_time = self._get_message_timestamp(message)
        if msg_time is None:
            # If no timestamp, consider it recent (don't filter out)
            return False
        
        return msg_time < cutoff_time
    
    def limit_memory(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """Limit messages based on token count and time constraints.
        
        This function processes messages from newest to oldest, keeping messages
        until either the token limit or time limit is reached. It never truncates
        a message - if adding a message would exceed the token limit, the full
        message is included and processing stops.
        
        Args:
            messages: List of messages from oldest to newest
            
        Returns:
            Dict with 'messages' key containing the limited message list
        """
        if not messages:
            return {"messages": messages}
        
        # Calculate time cutoff
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.time_limit_days)
        
        # Process messages from newest to oldest
        limited_messages = []
        total_tokens = 0
        
        # Reverse the list to process from newest to oldest
        for message in reversed(messages):
            # Check time limit first
            if self._is_message_too_old(message, cutoff_time):
                logger.debug(f"Message too old, stopping memory collection")
                break
            
            # Count tokens for this message
            message_tokens = self.token_counter.count_message_tokens(message)
            
            # Check if adding this message would exceed token limit
            potential_total = total_tokens + message_tokens
            
            if potential_total > self.token_limit and limited_messages:
                # We would exceed the limit and we already have some messages
                # Stop here without adding this message
                logger.debug(
                    f"Token limit would be exceeded ({potential_total} > {self.token_limit}), "
                    f"stopping memory collection with {len(limited_messages)} messages"
                )
                break
            
            # Add the message (even if it exceeds the limit, we don't truncate)
            limited_messages.insert(0, message)  # Insert at beginning to maintain order
            total_tokens = potential_total
            
            logger.debug(
                f"Added message to memory: {message.__class__.__name__}, "
                f"tokens: {message_tokens}, total: {total_tokens}"
            )
        
        # CRITICAL: Always ensure we have at least some messages to prevent empty list
        if not limited_messages and messages:
            # If all messages were filtered out, keep at least the most recent message
            # to prevent empty message list which causes LLM errors
            most_recent = messages[-1]
            limited_messages = [most_recent]
            total_tokens = self.token_counter.count_message_tokens(most_recent)
            logger.warning(
                f"All messages filtered out! Keeping most recent message to prevent empty list. "
                f"Tokens: {total_tokens}"
            )
        
        # Return the filtered messages
        messages_to_keep = limited_messages
        if len(messages_to_keep) < len(messages):
            messages_removed = len(messages) - len(messages_to_keep)
            logger.info(
                f"Memory limited: kept {len(messages_to_keep)} messages "
                f"({total_tokens} tokens), removed {messages_removed} older messages"
            )
        else:
            logger.debug(f"Memory check: keeping all {len(messages)} messages ({total_tokens} tokens)")
        
        # Simply return the filtered messages without RemoveMessage markers
        # This is safer and avoids potential issues with message flow
        return {"messages": messages_to_keep}
    
    def get_memory_stats(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """Get statistics about current memory usage.
        
        Args:
            messages: List of messages to analyze
            
        Returns:
            Dict with memory usage statistics
        """
        if not messages:
            return {
                "message_count": 0,
                "total_tokens": 0,
                "oldest_message_age_days": None,
                "newest_message_age_days": None,
                "token_limit": self.token_limit,
                "time_limit_days": self.time_limit_days
            }
        
        total_tokens = self.token_counter.count_messages_tokens(messages)
        now = datetime.now(timezone.utc)
        
        # Find oldest and newest message timestamps
        timestamps = []
        for msg in messages:
            ts = self._get_message_timestamp(msg)
            if ts:
                timestamps.append(ts)
        
        oldest_age_days = None
        newest_age_days = None
        
        if timestamps:
            oldest_ts = min(timestamps)
            newest_ts = max(timestamps)
            oldest_age_days = (now - oldest_ts).days
            newest_age_days = (now - newest_ts).days
        
        return {
            "message_count": len(messages),
            "total_tokens": total_tokens,
            "oldest_message_age_days": oldest_age_days,
            "newest_message_age_days": newest_age_days,
            "token_limit": self.token_limit,
            "time_limit_days": self.time_limit_days,
            "within_token_limit": total_tokens <= self.token_limit,
            "within_time_limit": oldest_age_days is None or oldest_age_days <= self.time_limit_days
        }
