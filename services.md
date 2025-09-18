# Multi-Step Service Tool Documentation

## Overview

The Multi-Step Service Tool is a universal framework for handling complex, multi-step user interactions within the agent system. It provides a structured approach to collect, validate, and process user data through sequential steps while maintaining state persistence between interactions.

## Architecture Schematic

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│     Agent       │    │  multi_step_     │    │   BaseService   │
│                 │───▶│    service       │───▶│    Classes      │
│ (LangChain)     │    │      Tool        │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        │
                       ┌──────────────────┐              │
                       │  State Manager   │              │
                       │                  │              │
                       │ JSON Files Store │              │
                       └──────────────────┘              │
                                                         │
                       ┌──────────────────┐              │
                       │ Service Registry │◀─────────────┘
                       │                  │
                       │ data_collection  │
                       │ appointment_...  │
                       └──────────────────┘
```

## How It Works

### 1. Service Initialization
```python
# Agent calls tool to start a service
multi_step_service.invoke({
    "service_name": "data_collection",
    "step": "start",
    "user_id": "user123"
})
```

### 2. Step Processing Flow
```
Start → CPF Input → Email Input → Name Input → Complete
  │         │           │           │           │
  ▼         ▼           ▼           ▼           ▼
Save    Validate     Validate    Validate    Final
State   & Save       & Save      & Save      Data
```

### 3. State Persistence
Each service session creates a JSON file containing:
- Session ID
- Service name and class
- User ID (from hook)
- Collected data
- Creation timestamp

## Core Components

### BaseService Abstract Class

**Location**: `src/services.py`

**Purpose**: Provides the foundation for all multi-step services with common functionality.

**Key Methods**:

```python
@abstractmethod
def get_steps_info(self) -> List[Dict[str, Any]]:
    """Returns detailed information about all service steps"""
    
@abstractmethod  
def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
    """Validates and processes user input for a specific step"""
    
def process_step(self, step: str, payload: str) -> Dict[str, Any]:
    """Orchestrates step processing and determines next action"""
```

**Step Information Structure**:
```python
{
    "name": "cpf",
    "description": "Collect and validate user's CPF",
    "prompt": "Please provide your CPF:",
    "validation": "Must contain 11 numeric digits",
    "example": "12345678901",
    "required": True,
    "next_step": "email"
}
```

### Service Registry

**Location**: `src/services.py`

**Purpose**: Central registry mapping service names to their corresponding classes.

```python
SERVICE_REGISTRY = {
    "data_collection": DataCollectionService,
    # Add new services here
}
```

### Multi-Step Service Tool

**Location**: `src/tools.py`

**Purpose**: Main interface for agent interaction with multi-step services.

**Parameters**:
- `service_name`: Identifier for the service type
- `step`: Current step name ("start" for new services)
- `payload`: User input for validation
- `user_id`: User identifier (set by hooks)

**Return Structure**:
```python
{
    "status": "started|success|error|completed",
    "message": "User-facing message",
    "next_step": "next_step_name",
    "completed": False,
    "session_id": "unique_session_identifier",
    "steps_info": [...],  # Only on start
    "data": {...}         # Only on completion
}
```

## State Management

### Session Creation
- **Session ID Format**: `{service_name}_{timestamp}`
- **Storage Location**: `service_states/` directory
- **File Format**: JSON with UTF-8 encoding

### State Recovery
- Agent can resume interrupted services
- Most recent session automatically selected
- Complete data preservation across restarts

### State File Structure
```json
{
    "service_class": "DataCollectionService",
    "service_name": "data_collection", 
    "session_id": "data_collection_1703234567",
    "user_id": "user123",
    "data": {
        "cpf": "12345678901",
        "email": "user@example.com"
    },
    "created_at": "2024-01-15T10:30:00"
}
```

## Service Implementation Example

### DataCollectionService

**Purpose**: Collects user personal data (CPF, email, name) with validation.

**Steps Configuration**:
```python
def get_steps_info(self) -> List[Dict[str, Any]]:
    return [
        {
            "name": "cpf",
            "description": "Collect and validate user's CPF",
            "prompt": "Please provide your CPF:",
            "validation": "Must contain 11 numeric digits",
            "example": "12345678901",
            "required": True,
            "next_step": "email"
        },
        # ... additional steps
    ]
```

**Validation Logic**:
```python
def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
    if step == "cpf":
        return self._validate_cpf(payload)
    elif step == "email":
        return self._validate_email(payload)
    # ... other validations
```

## User Experience Flow

### Complete Service Flow Example

1. **Service Initiation**
   ```
   User: "I want to register"
   Agent: Calls multi_step_service("data_collection", "start")
   Tool: Returns "Please provide your CPF:" + steps_info
   ```

2. **Step Processing**
   ```
   User: "123.456.789-00"
   Agent: Calls multi_step_service("data_collection", "cpf", "123.456.789-00")
   Tool: Validates CPF, returns "Now provide your email:"
   ```

3. **Service Completion**
   ```
   User: "John Silva"
   Agent: Calls multi_step_service("data_collection", "name", "John Silva")
   Tool: Returns completion message + all collected data
   ```

### Error Handling
```
User: "invalid-cpf"
Agent: Calls multi_step_service("data_collection", "cpf", "invalid-cpf")
Tool: Returns error status + "CPF must have 11 digits. Try again:"
Agent: Prompts user to retry with correct format
```

## Adding New Services

### Step 1: Create Service Class
```python
class AppointmentBookingService(BaseService):
    """Service for booking appointments"""
    
    def get_steps_info(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "date",
                "description": "Select appointment date",
                "prompt": "Please select a date:",
                "validation": "Must be a future date",
                "example": "2024-01-20",
                "required": True,
                "next_step": "time"
            }
            # ... more steps
        ]
    
    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        # Implementation specific validation
        pass
```

### Step 2: Register Service
```python
SERVICE_REGISTRY = {
    "data_collection": DataCollectionService,
    "appointment_booking": AppointmentBookingService,  # Add here
}
```

### Step 3: Implement Validation Logic
```python
def _validate_date(self, date_str: str) -> Tuple[bool, str]:
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        if date_obj <= datetime.now():
            return False, "Date must be in the future. Try again:"
        return True, ""
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD:"
```

## Tool Integration

### Agent Usage
The agent automatically receives the tool description including all available services:

```
Available services:
- data_collection: Service for collecting user personal data
- appointment_booking: Service for booking appointments
```

### Hook Integration
The tool is designed to work with hooks that inject the real user ID:

```python
# Hook automatically sets user_id
tool_result = multi_step_service.invoke({
    "service_name": "data_collection",
    "step": "start", 
    "user_id": "real_user_id_from_session"  # Set by hook
})
```

## Testing

### Running Tests
```bash
python test.py
```

### Test Coverage
- Complete service flow testing
- Error case validation
- Service registry verification
- State persistence testing

### Test Structure
- `test_service_registry()`: Verifies available services
- `test_data_collection_service()`: Tests full workflow
- `test_error_cases()`: Validates error handling

## Benefits

### For Developers
- **Modular Design**: Easy to add new services
- **Consistent Interface**: Same pattern for all multi-step workflows
- **Automatic State Management**: No manual session handling required
- **Built-in Validation**: Framework handles input validation

### For Users
- **Natural Conversation Flow**: Seamless step-by-step interaction
- **Error Recovery**: Clear feedback and retry mechanisms
- **Session Persistence**: Can resume interrupted processes
- **Progress Tracking**: Clear indication of current step

### For System
- **Scalable Architecture**: Supports unlimited service types
- **Clean Separation**: Services independent of tool logic
- **Persistent State**: Survives system restarts
- **Hook Integration**: Works with authentication and user management

## Performance Considerations

- **File-based Storage**: Simple and reliable for moderate loads
- **Session Cleanup**: Automatic cleanup of old sessions (configurable)
- **Memory Efficiency**: Services loaded on-demand
- **Response Time**: < 100ms for typical operations

## Security

- **Input Validation**: All user input validated before processing
- **State Isolation**: Each session isolated from others
- **No Sensitive Storage**: Sensitive data can be encrypted before storage
- **User Authentication**: Relies on hook-provided user identification