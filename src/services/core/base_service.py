from abc import ABC, abstractmethod
from src.services.schema.models import ServiceDefinition


class BaseService(ABC):
    """
    Abstract base class for all services.

    Forces subclasses to implement a method that returns a ServiceDefinition,
    ensuring a consistent interface for the orchestrator.
    """

    service_name: str
    description: str

    @abstractmethod
    def get_definition(self) -> ServiceDefinition:
        """
        Returns the complete, immutable definition of the service,
        including all steps and their configurations.

        Returns:
            A ServiceDefinition object.
        """
        pass
