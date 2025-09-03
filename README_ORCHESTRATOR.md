# Orchestrated Agent Architecture

This implementation adds intelligent service routing capabilities to the main municipal agent, allowing it to route specialized requests to focused service agents while maintaining its general-purpose capabilities.

## Architecture Overview

```
User Request
     ↓
Main Agent (Enhanced with Routing Logic)
     ↓
├── Tax Services → Tax Agent (IPTU, ISS, payments)
├── Infrastructure → Infrastructure Agent (lighting, potholes)  
├── Health Services → Health Agent (appointments, clinics)
└── General Information → Existing Tools (web_search, equipment_location)
```

## Key Components

### 1. OrchestratedAgent (`engine/orchestrated_agent.py`)
- Enhanced main agent with intelligent routing capabilities
- Maintains conversation context across service boundaries
- Falls back to general tools for non-specialized requests
- Backwards compatible with existing functionality

### 2. Service Agents (`engine/services/`)
- **BaseServiceAgent**: Abstract base class for all service agents
- **TaxServiceAgent**: Handles IPTU, ISS, tax payments, certifications
- **InfrastructureServiceAgent**: Handles street lighting, potholes, maintenance
- **HealthServiceAgent**: Handles appointments, clinics, vaccination services

### 3. Orchestrator Tools (`engine/orchestrator.py`)
- Handoff tools that route requests to appropriate service agents
- Uses LangGraph's `Command` objects for seamless agent transitions
- Maintains conversation state during handoffs

## How It Works

### Routing Logic
The main agent analyzes incoming requests and determines the appropriate handling:

1. **Specialized Services**: Routes to domain-specific agents using handoff tools
   - Tax queries → `route_to_tax_agent`
   - Infrastructure issues → `route_to_infrastructure_agent`
   - Health services → `route_to_health_agent`

2. **General Services**: Uses existing tools directly
   - Information searches → `web_search_surkai`
   - Equipment location → `equipments_by_address`
   - User feedback → `user_feedback`

### Service Agent Templates
Each service agent is currently a simple template with:
- Focused system prompt for the domain
- Placeholder for domain-specific tools
- Specialized expertise and business rules
- Parameter collection and validation capabilities (ready for implementation)

## Usage

### Basic Usage
```python
from engine import OrchestratedAgent
from src.tools import mcp_tools
from src.prompt import prompt_data

# Create orchestrated agent
agent = OrchestratedAgent(
    model="gemini-2.5-flash",
    system_prompt=prompt_data["prompt"],
    tools=mcp_tools,
    temperature=0.7
)

# Use like the original agent
config = {"configurable": {"thread_id": "my-conversation"}}
result = await agent.async_query(
    input={"messages": [{"role": "user", "content": "Preciso da segunda via do IPTU"}]},
    config=config
)
```

### Example Requests and Routing

| Request | Routing Destination | Reasoning |
|---------|-------------------|-----------|
| "Preciso da segunda via do IPTU" | Tax Agent | Tax-related service |
| "Buraco na rua" | Infrastructure Agent | Infrastructure issue |
| "Agendar consulta médica" | Health Agent | Health service |
| "Onde fica a prefeitura?" | General Tools | Information query |

## Files Structure

```
engine/
├── agent.py                 # Original agent (unchanged)
├── orchestrated_agent.py    # New orchestrated agent
├── orchestrator.py          # Handoff tools for routing
└── services/
    ├── __init__.py
    ├── base_service_agent.py      # Base class for service agents
    ├── tax_agent.py               # Tax services specialist
    ├── infrastructure_agent.py    # Infrastructure specialist  
    └── health_agent.py            # Health services specialist

example_orchestrated_agent.py     # Usage examples
```

## Benefits

1. **Scalability**: Easy to add new service agents without modifying existing code
2. **Focused Expertise**: Each service agent has domain-specific knowledge and tools
3. **Backward Compatibility**: Original agent functionality preserved
4. **Performance**: Specialized prompts are smaller and more efficient
5. **Maintainability**: Service logic is isolated and easier to maintain

## Next Steps

### For Service Agent Development
1. **Add Domain-Specific Tools**: Integrate tax APIs, infrastructure reporting systems, health appointment tools
2. **Implement Parameter Collection**: Add progressive parameter gathering for complex services
3. **Add Validation Logic**: Implement business rules and data validation
4. **Create Service Schemas**: Define parameter requirements and validation rules

### For Production Deployment
1. **Replace Original Agent**: Update deployment to use `OrchestratedAgent` instead of `Agent`
2. **Add Service Monitoring**: Track routing decisions and service agent performance
3. **Implement Error Handling**: Add fallback mechanisms for service agent failures
4. **Add Service Registry**: Dynamic service discovery and configuration

## Testing

Run the example script to test the orchestrated agent:

```bash
python example_orchestrated_agent.py
```

This will demonstrate:
- Tax service routing
- Infrastructure service routing  
- General information handling
- Conversation continuity across services

## Compatibility

- **Fully backward compatible** with existing `Agent` class
- **Same API interface** - drop-in replacement
- **Existing tools work unchanged** - no modifications needed
- **Same database schema** - uses existing checkpointer infrastructure
