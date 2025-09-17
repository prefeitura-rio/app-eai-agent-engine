"""Custom PostgresSaver that applies memory limiting during save operations."""

from typing import List, Any, Dict, Optional
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import BaseMessage
from src.utils.memory_manager import MemoryManager
import logging

logger = logging.getLogger(__name__)


class MemoryLimitedPostgresSaver(PostgresSaver):
    """PostgresSaver that applies memory limiting before saving to database."""
    
    def __init__(self, engine, memory_manager: MemoryManager = None):
        """Initialize with memory manager."""
        super().__init__(engine)
        self.memory_manager = memory_manager
        logger.info("MemoryLimitedPostgresSaver initialized")
    
    @classmethod
    async def create(cls, engine, memory_manager: MemoryManager = None):
        """Create instance with memory manager."""
        instance = await super().create(engine)
        instance.memory_manager = memory_manager
        return instance
    
    @classmethod
    def create_sync(cls, engine, memory_manager: MemoryManager = None):
        """Create sync instance with memory manager."""
        instance = super().create_sync(engine)
        instance.memory_manager = memory_manager
        return instance
    
    def _apply_memory_limits(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Apply memory limits to state before saving."""
        if not self.memory_manager:
            return state
        
        messages = state.get("messages", [])
        if not messages:
            return state
        
        try:
            # Apply memory limiting
            limited_result = self.memory_manager.limit_memory(messages)
            limited_messages = limited_result.get("messages", [])
            
            if not limited_messages:
                logger.warning("Memory limiting resulted in empty messages, keeping most recent")
                limited_messages = [messages[-1]] if messages else []
            
            # Create new state with limited messages
            limited_state = dict(state)
            limited_state["messages"] = limited_messages
            
            removed_count = len(messages) - len(limited_messages)
            if removed_count > 0:
                logger.info(f"PostgresSaver: Removed {removed_count} old messages before saving to database")
            
            return limited_state
            
        except Exception as e:
            logger.error(f"Error applying memory limits in checkpointer: {e}")
            return state
    
    async def aput(self, config, checkpoint, metadata, new_versions):
        """Override aput to apply memory limits before saving."""
        if checkpoint and 'channel_values' in checkpoint:
            # Apply memory limits to the checkpoint data
            channel_values = checkpoint['channel_values']
            if isinstance(channel_values, dict):
                channel_values = self._apply_memory_limits(channel_values)
                checkpoint = dict(checkpoint)
                checkpoint['channel_values'] = channel_values
        
        return await super().aput(config, checkpoint, metadata, new_versions)
    
    def put(self, config, checkpoint, metadata, new_versions):  
        """Override put to apply memory limits before saving (sync version)."""
        if checkpoint and 'channel_values' in checkpoint:
            # Apply memory limits to the checkpoint data
            channel_values = checkpoint['channel_values']
            if isinstance(channel_values, dict):
                channel_values = self._apply_memory_limits(channel_values)
                checkpoint = dict(checkpoint)
                checkpoint['channel_values'] = channel_values
        
        return super().put(config, checkpoint, metadata, new_versions)
