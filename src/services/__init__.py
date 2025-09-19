"""
Services module for multi-step services with dependency management.
Self-contained module ready for MCP migration.
"""

from src.services.base_service import BaseService, build_service_registry
from src.services.schema import StepInfo, ConditionalDependency
from src.services.repository import DataCollectionService, BankAccountService
from src.services.tool import create_multi_step_service_tool
from src.services import state

# Service Registry - automatically generated from service classes
SERVICE_REGISTRY = build_service_registry(
    DataCollectionService,
    BankAccountService,
)

# Create the tool with dependency injection
multi_step_service = create_multi_step_service_tool(SERVICE_REGISTRY)

__all__ = [
    # Core classes
    "BaseService",
    "StepInfo", 
    "ConditionalDependency",
    
    # Service implementations
    "DataCollectionService",
    "BankAccountService",
    
    # Registry
    "SERVICE_REGISTRY",
    "build_service_registry",
    
    # Tool
    "multi_step_service",
    
    # State management
    "state",
]