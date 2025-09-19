from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Tuple, Optional, Type

from src.services.schema import ServiceDefinition


class BaseService(ABC):
    """
    Simplified base class for multi-step services.
    Focus: Only service execution and data storage.
    Heavy logic moved to ServiceDefinition.
    """
    
    # Service identifier - must be defined in each service class
    service_name: Optional[str] = None

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.data = {}
        self.created_at = datetime.now()
        
        # Ensure service_name is defined
        if self.__class__.service_name is None:
            raise ValueError(f"Service {self.__class__.__name__} must define service_name")

    @abstractmethod
    def get_service_definition(self) -> ServiceDefinition:
        """Return the complete service definition - single source of truth"""
        pass

    @abstractmethod
    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """Validate input for a step. Returns (is_valid, error_message)"""
        pass

    @abstractmethod
    def get_completion_message(self) -> str:
        """Get message when service is completed"""
        pass
    


def build_service_registry(*service_classes: Type[BaseService]) -> Dict[str, Type[BaseService]]:
    """
    Build SERVICE_REGISTRY dynamically from service classes.
    
    Args:
        *service_classes: Service classes that inherit from BaseService
        
    Returns:
        Dict mapping service_name to service class
        
    Raises:
        ValueError: If service_name is not defined or duplicated
    """
    registry = {}
    
    for service_class in service_classes:
        if not issubclass(service_class, BaseService):
            raise ValueError(f"{service_class.__name__} must inherit from BaseService")
        
        if service_class.service_name is None:
            raise ValueError(f"{service_class.__name__} must define service_name")
        
        service_name = service_class.service_name
        
        if service_name in registry:
            existing_class = registry[service_name]
            raise ValueError(
                f"Duplicate service_name '{service_name}' found in "
                f"{existing_class.__name__} and {service_class.__name__}"
            )
        
        registry[service_name] = service_class
    
    return registry