"""
Modular schema system for multi-step services.
Separated responsibilities for better maintainability and clarity.
"""

from src.services.schema.step_info import StepInfo, ConditionalDependency
from src.services.schema.dependency_engine import DependencyEngine
from src.services.schema.validation import ValidationEngine
from src.services.schema.visualization import VisualizationEngine
from src.services.schema.service_definition import ServiceDefinition

__all__ = [
    # Core models
    "StepInfo",
    "ConditionalDependency",
    
    # Engines
    "DependencyEngine",
    "ValidationEngine", 
    "VisualizationEngine",
    
    # Main definition
    "ServiceDefinition",
]