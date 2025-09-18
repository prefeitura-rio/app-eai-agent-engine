"""
Memory-limited PostgreSQL checkpointer that implements short-term memory limits.

This module wraps PostgresSaver to add token and time-based filtering of messages 
retrieved from the database.
"""

from typing import Optional, Dict, Any, List, Sequence, AsyncIterator, Iterator
from langchain_google_cloud_sql_pg import PostgresSaver
from langgraph.checkpoint.base import CheckpointTuple
from langchain_core.messages import BaseMessage
import logging

from src.config.env import SHORT_MEMORY_TOKEN_LIMIT, SHORT_MEMORY_TIME_LIMIT
from src.utils.memory_manager import apply_memory_limits, get_memory_management_stats

logger = logging.getLogger(__name__)


class MemoryLimitedPostgresSaver:
    """
    PostgreSQL checkpointer wrapper with built-in short-term memory limits.
    
    This wrapper delegates to the standard PostgresSaver but automatically
    filters messages based on:
    - Token limits: Only retrieve messages up to SHORT_MEMORY_TOKEN_LIMIT tokens
    - Time limits: Only retrieve messages newer than SHORT_MEMORY_TIME_LIMIT days
    
    Messages are never truncated - complete messages are preserved.
    """
    
    def __init__(
        self, 
        base_checkpointer: PostgresSaver, 
        token_limit: Optional[int] = None,
        time_limit_days: Optional[float] = None,
        model_name: str = "gemini-2.5-flash",
        enable_stats_logging: bool = True,
    ):
        """
        Initialize the memory-limited checkpointer wrapper.
        
        Args:
            base_checkpointer: The underlying PostgresSaver instance
            token_limit: Maximum tokens to retrieve (defaults to SHORT_MEMORY_TOKEN_LIMIT)
            time_limit_days: Maximum age in days (defaults to SHORT_MEMORY_TIME_LIMIT)
            model_name: Model name for token counting
            enable_stats_logging: Whether to log memory management statistics
        """
        self._base = base_checkpointer
        
        self.token_limit = token_limit if token_limit is not None else SHORT_MEMORY_TOKEN_LIMIT
        self.time_limit_days = time_limit_days if time_limit_days is not None else SHORT_MEMORY_TIME_LIMIT
        self.model_name = model_name
        self.enable_stats_logging = enable_stats_logging
        
        logger.info(f"MemoryLimitedPostgresSaver initialized with token_limit={self.token_limit}, "
                   f"time_limit_days={self.time_limit_days}, model={self.model_name}")
        
        # Enable debug logging for this module
        logging.getLogger(__name__).setLevel(logging.DEBUG)
    
    def _apply_memory_limits_to_checkpoint(self, checkpoint: CheckpointTuple) -> CheckpointTuple:
        """
        Apply memory limits to a checkpoint's messages.
        
        This method preserves recent conversation context while limiting historical messages.
        It ensures the agent always has access to recent messages needed for proper responses.
        
        Args:
            checkpoint: The checkpoint to filter
            
        Returns:
            Filtered checkpoint with memory limits applied
        """
        if not checkpoint or not checkpoint.checkpoint:
            return checkpoint
        
        # Get messages from checkpoint
        checkpoint_data = checkpoint.checkpoint
        messages = checkpoint_data.get("channel_values", {}).get("messages", [])
        
        if not messages:
            logger.debug("No messages in checkpoint to filter")
            return checkpoint  # No messages to filter
        
        logger.info(f"🔍 Applying memory limits to {len(messages)} messages")
        
        # Always preserve the last few messages to maintain conversation context
        # This ensures the agent can respond to the current human message
        min_recent_messages = 3  # Keep at least the last 3 messages (reduced from 5)
        
        if len(messages) <= min_recent_messages:
            # If we have very few messages, don't filter at all
            logger.info(f"Only {len(messages)} messages, skipping filtering")
            return checkpoint
        
        # Split messages into historical and recent
        recent_messages = messages[-min_recent_messages:]  # Last N messages (always keep)
        historical_messages = messages[:-min_recent_messages]  # Older messages (can be filtered)
        
        # Apply memory limits only to historical messages
        if historical_messages:
            # Calculate remaining token budget after accounting for recent messages
            from src.utils.token_counter import estimate_tokens_for_message
            recent_tokens = sum(estimate_tokens_for_message(msg) for msg in recent_messages)
            remaining_token_budget = max(0, self.token_limit - recent_tokens)
            
            logger.debug(f"Recent messages tokens: {recent_tokens}, remaining budget: {remaining_token_budget}")
            
            if remaining_token_budget > 0:
                # Apply memory limits to historical messages with remaining budget
                filtered_historical = apply_memory_limits(
                    historical_messages, 
                    remaining_token_budget, 
                    self.time_limit_days, 
                    self.model_name
                )
            else:
                # No budget left for historical messages
                filtered_historical = []
            
            # Combine filtered historical with recent messages
            filtered_messages = filtered_historical + recent_messages
        else:
            # No historical messages, just keep recent ones
            filtered_messages = recent_messages
        
        # Log statistics if enabled
        original_count = len(messages)
        if self.enable_stats_logging and original_count != len(filtered_messages):
            stats = get_memory_management_stats(
                messages, filtered_messages, self.token_limit, self.time_limit_days
            )
            logger.info(f"Memory filtering applied: {stats['messages_removed']} messages removed "
                       f"({stats['removal_percentage']}%), {stats['tokens_removed']} tokens saved. "
                       f"Final: {stats['filtered_message_count']} messages, "
                       f"{stats['filtered_estimated_tokens']} tokens. "
                       f"Recent messages preserved: {len(recent_messages)}")
        
        # Update checkpoint with filtered messages
        new_checkpoint_data = checkpoint_data.copy()
        new_channel_values = new_checkpoint_data.get("channel_values", {}).copy()
        new_channel_values["messages"] = filtered_messages
        new_checkpoint_data["channel_values"] = new_channel_values
        
        # Return new checkpoint tuple with filtered data
        return CheckpointTuple(
            config=checkpoint.config,
            checkpoint=new_checkpoint_data,
            metadata=checkpoint.metadata,
            parent_config=checkpoint.parent_config,
            pending_writes=checkpoint.pending_writes
        )
    
    def get(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """
        Get checkpoint with memory limits applied (sync version).
        
        Args:
            config: Checkpoint configuration
            
        Returns:
            Filtered checkpoint tuple or None
        """
        logger.info(f"🔍 MemoryLimitedCheckpointer.get() called with config: {config}")
        
        # Get the original checkpoint
        checkpoint = self._base.get(config)
        
        if checkpoint is None:
            logger.info("No checkpoint found from base checkpointer")
            return None
        
        logger.info(f"Retrieved checkpoint from base, applying memory limits...")
        
        # Apply memory limits
        filtered_checkpoint = self._apply_memory_limits_to_checkpoint(checkpoint)
        
        logger.info(f"Memory limits applied, returning filtered checkpoint")
        return filtered_checkpoint
    
    async def aget(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """
        Get checkpoint with memory limits applied (async version).
        
        Args:
            config: Checkpoint configuration
            
        Returns:
            Filtered checkpoint tuple or None
        """
        logger.info(f"🔍 MemoryLimitedCheckpointer.aget() called with config: {config}")
        
        # Get the original checkpoint
        checkpoint = await self._base.aget(config)
        
        if checkpoint is None:
            logger.info("No checkpoint found from base checkpointer")
            return None
        
        logger.info(f"Retrieved checkpoint from base, applying memory limits...")
        
        # Apply memory limits
        filtered_checkpoint = self._apply_memory_limits_to_checkpoint(checkpoint)
        
        logger.info(f"Memory limits applied, returning filtered checkpoint")
        return filtered_checkpoint
    
    def list(
        self, 
        config: Optional[Dict[str, Any]] = None, 
        *, 
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> Iterator[CheckpointTuple]:
        """
        List checkpoints with memory limits applied (sync version).
        
        Args:
            config: Base configuration
            filter: Filter criteria
            before: Before configuration
            limit: Maximum number of checkpoints to return
            
        Yields:
            Filtered checkpoint tuples
        """
        # Get original checkpoints
        for checkpoint in self._base.list(config, filter=filter, before=before, limit=limit):
            # Apply memory limits to each checkpoint
            yield self._apply_memory_limits_to_checkpoint(checkpoint)
    
    async def alist(
        self, 
        config: Optional[Dict[str, Any]] = None, 
        *, 
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[CheckpointTuple]:
        """
        List checkpoints with memory limits applied (async version).
        
        Args:
            config: Base configuration
            filter: Filter criteria  
            before: Before configuration
            limit: Maximum number of checkpoints to return
            
        Yields:
            Filtered checkpoint tuples
        """
        # Get original checkpoints
        async for checkpoint in self._base.alist(config, filter=filter, before=before, limit=limit):
            # Apply memory limits to each checkpoint
            yield self._apply_memory_limits_to_checkpoint(checkpoint)
    
    def put(self, config: Dict[str, Any], checkpoint: CheckpointTuple, metadata: Dict[str, Any], new_versions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Delegate put operations to the base checkpointer.
        """
        return self._base.put(config, checkpoint, metadata, new_versions)
    
    async def aput(self, config: Dict[str, Any], checkpoint: CheckpointTuple, metadata: Dict[str, Any], new_versions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Delegate async put operations to the base checkpointer.
        """
        return await self._base.aput(config, checkpoint, metadata, new_versions)
    
    def put_writes(self, config: Dict[str, Any], writes: List[Any], task_id: str) -> None:
        """
        Delegate put_writes operations to the base checkpointer.
        """
        return self._base.put_writes(config, writes, task_id)
    
    async def aput_writes(self, config: Dict[str, Any], writes: List[Any], task_id: str) -> None:
        """
        Store writes to checkpoint asynchronously (delegates to base).
        """
        await self._base.aput_writes(config, writes, task_id)
    
    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """
        Get checkpoint tuple asynchronously with memory limits applied.
        This is the method that LangGraph actually calls for message retrieval.
        """
        logger.info(f"MemoryLimitedPostgresSaver.aget_tuple called with config: {config}")
        
        # Get the raw checkpoint tuple from base checkpointer
        checkpoint_tuple = await self._base.aget_tuple(config)
        
        if checkpoint_tuple is None:
            logger.debug("No checkpoint tuple found")
            return None
        
        # Apply memory limits to the checkpoint
        filtered_tuple = self._apply_memory_limits_to_checkpoint(checkpoint_tuple)
        
        logger.info(f"aget_tuple: Applied memory limits to checkpoint")
        return filtered_tuple
    
    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """
        Get checkpoint tuple synchronously with memory limits applied.
        """
        logger.info(f"MemoryLimitedPostgresSaver.get_tuple called with config: {config}")
        
        # Get the raw checkpoint tuple from base checkpointer
        checkpoint_tuple = self._base.get_tuple(config)
        
        if checkpoint_tuple is None:
            logger.debug("No checkpoint tuple found")
            return None
        
        # Apply memory limits to the checkpoint
        filtered_tuple = self._apply_memory_limits_to_checkpoint(checkpoint_tuple)
        
        logger.info(f"get_tuple: Applied memory limits to checkpoint")
        return filtered_tuple
    
    def get_next_version(self, current: Optional[str], channel: str) -> str:
        """
        Generate the next checkpoint version (delegates to base).
        """
        return self._base.get_next_version(current, channel)
    
    def __getattr__(self, name):
        """
        Delegate any other attribute access to the base checkpointer.
        This ensures all methods and properties are properly forwarded.
        """
        logger.debug(f"MemoryLimitedPostgresSaver: Delegating method/attribute '{name}' to base checkpointer")
        attr = getattr(self._base, name)
        
        # If it's a callable method, wrap it with logging
        if callable(attr):
            def wrapper(*args, **kwargs):
                logger.warning(f"MemoryLimitedPostgresSaver: Method '{name}' called via delegation - memory limits NOT applied! Args: {len(args)}, Kwargs: {list(kwargs.keys())}")
                return attr(*args, **kwargs)
            return wrapper
        
        return attr
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get current memory management configuration.
        
        Returns:
            Dictionary with current memory limits and settings
        """
        return {
            "token_limit": self.token_limit,
            "time_limit_days": self.time_limit_days,
            "model_name": self.model_name,
            "stats_logging_enabled": self.enable_stats_logging,
        }
    
    def update_memory_limits(self, token_limit: Optional[int] = None, time_limit_days: Optional[int] = None):
        """
        Update memory limits at runtime.
        
        Args:
            token_limit: New token limit (None to keep current)
            time_limit_days: New time limit in days (None to keep current)
        """
        if token_limit is not None:
            old_token_limit = self.token_limit
            self.token_limit = token_limit
            logger.info(f"Token limit updated from {old_token_limit} to {token_limit}")
        
        if time_limit_days is not None:
            old_time_limit = self.time_limit_days
            self.time_limit_days = time_limit_days
            logger.info(f"Time limit updated from {old_time_limit} to {time_limit_days} days")


def create_memory_limited_checkpointer(
    base_checkpointer: PostgresSaver,
    token_limit: Optional[int] = None,
    time_limit_days: Optional[float] = None,
    model_name: str = "gemini-2.5-flash",
) -> MemoryLimitedPostgresSaver:
    """
    Factory function to create a memory-limited checkpointer wrapper.
    
    Args:
        base_checkpointer: The underlying PostgresSaver instance
        token_limit: Maximum tokens to retrieve (defaults to env variable)
        time_limit_days: Maximum age in days (defaults to env variable)
        model_name: Model name for token counting
        
    Returns:
        MemoryLimitedPostgresSaver wrapper instance
    """
    return MemoryLimitedPostgresSaver(
        base_checkpointer=base_checkpointer,
        token_limit=token_limit,
        time_limit_days=time_limit_days,
        model_name=model_name,
    )