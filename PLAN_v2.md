# Multi-Step Service Implementation Plan v2: Python Tool

## 🎯 Objective

Implement a generic multi-step service system as a Python function/class within this repository. Simple, self-contained solution for handling complex, multi-step user interactions.

## 🏗️ Architecture Overview

### Single Python Function
- Function: `multi_step_service(service_name, step, payload)`
- Service classes inherit from `BaseService`
- File-based state persistence
- Returns structured response with next step instructions

## 📋 Core Logic

### BaseService Class
```python
class BaseService(ABC):
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.data = {}
        
    @abstractmethod
    def get_steps(self) -> list:
        pass
        
    @abstractmethod
    def validate_step(self, step: str, payload: str) -> tuple[bool, str]:
        pass
        
    def process_step(self, step: str, payload: str) -> dict:
        # Validation logic
        # Data storage
        # Next step determination
        # Return formatted response
```

### Function Interface
```python
def multi_step_service(
    service_name: str,      # "data_collection"
    step: str,              # "cpf", "email", "name" 
    payload: str = ""       # User input
) -> dict:
    # Load/create service instance
    # Process step
    # Save state
    # Return response
```

## 📊 Input/Output Schema

### Input Parameters
- `service_name`: String (required) - Service type identifier
- `step`: String (required) - Current step name or "start"
- `payload`: String (optional) - User input for validation

### Output Schema
```python
# Starting service
{
    "status": "started",
    "message": "Por favor, informe seu CPF:",
    "next_step": "cpf",
    "session_id": "data_collection_1234567890"
}

# Step success
{
    "status": "success",
    "message": "Agora informe seu e-mail:",
    "next_step": "email"
}

# Validation error
{
    "status": "error", 
    "message": "CPF inválido. Tente novamente:",
    "next_step": "cpf"
}

# Service complete
{
    "status": "completed",
    "message": "Dados coletados com sucesso!",
    "data": {"cpf": "123...", "email": "...", "name": "..."}
}
```

## 🔧 Implementation Plan

### Week 1: Core Implementation
1. Create `BaseService` abstract class
2. Implement `DataCollectionService` 
3. Create `multi_step_service` function
4. File-based state persistence
5. Basic testing

### Week 2: Enhancement & Integration
1. Add second service type
2. Error handling improvements
3. Agent integration testing
4. Documentation

## 🎯 Success Criteria

- New service creation < 15 minutes
- Zero external dependencies
- Clean input/output interface
- Reliable state persistence
- Easy agent integration

## 🔄 Usage Flow

1. **Start**: `multi_step_service("data_collection", "start")` 
2. **Steps**: `multi_step_service("data_collection", "cpf", "123.456.789-00")`
3. **Complete**: Final step returns status="completed" with all data

Simple, focused, no complexity.