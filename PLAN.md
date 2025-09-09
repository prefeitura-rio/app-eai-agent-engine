# Multi-Step Service Implementation Plan

## 🎯 Objective

Implement a generic multi-step service system using LangGraph native patterns (`interrupt` + `Command`) to support various services requiring user interaction, validation, API calls, and retry logic.

## 🏗️ Architecture Overview

### Core Components

1. **Extended Agent State**: Add service-specific fields to current `AgentState`
2. **Service Nodes**: Individual nodes for each service type  
3. **Human Input Node**: Universal user input collector using `interrupt`
4. **Service Registry**: Configuration-driven service definitions
5. **Conditional Routing**: Smart routing between services and normal conversation

## 📋 Implementation Strategy

### **1. State Extension**

Extend current `AgentState` with service-specific fields:
- `active_service`: Current running service name
- `current_step`: Current step within the service
- `service_data`: Collected data during service execution
- `retry_count`: Number of retry attempts
- `waiting_for_input`: Flag to indicate if waiting for user input

### **2. Service Registry System**

Create a configuration-driven approach where each service is defined by:
- **Service Definition**: Name, description, timeout settings
- **Step Definitions**: Each step with message template, validation rules, API calls
- **Flow Control**: Next step logic and completion criteria

Example service structure:
```
data_collection:
  - collect_cpf → validate → collect_email → validate → collect_name → complete
```

### **3. Core Node Functions**

**Human Input Node**
- Uses `interrupt()` to pause execution and wait for user input
- Routes back to service processing or normal agent flow based on context

**Service Processing Node**
- Validates user input against current step requirements
- Handles retry logic with configurable limits
- Makes external API calls when needed
- Advances to next step or completes service

**Service Starter Nodes**
- One node per service type (e.g., `start_data_collection`)
- Initializes service state and begins first step

### **4. Workflow Integration**

Extend current workflow with new conditional edges:
- Agent → Service Detection → Start Service OR Continue Normal Flow
- Service Nodes → Human Input → Service Processing → Next Step OR Complete
- Maintain existing agent → tools → agent flow for normal operations

### **5. Service Control Mechanism**

Add `StartServiceTool` to existing MCP tools:
- Agent can call this tool when user requests multi-step processes
- Tool triggers appropriate service starter node
- Seamless transition from normal chat to service mode

## 🔄 User Experience Flow

### Starting a Service
1. User: "Quero me cadastrar"
2. Agent: Detects intent, calls `start_service` tool
3. System: Routes to `start_data_collection` node
4. System: Sends first prompt "Por favor, informe seu CPF:"
5. Graph: Pauses at `human_input` node using `interrupt`

### Continuing a Service
1. User: Provides CPF "123.456.789-00"
2. System: Resumes via `Command(resume=input)`
3. Service: Validates CPF, stores data, moves to next step
4. System: Sends next prompt "Agora informe seu e-mail:"
5. Cycle continues until service completion

### Service Completion
1. After final step validation
2. System: Sends completion message
3. State: Clears service context
4. Flow: Returns to normal agent conversation

## 🔧 Implementation Phases

### **Phase 1: Foundation (Week 1-2)**
- Extend `AgentState` with service fields
- Implement basic `human_input` and `process_service` nodes
- Add simple service detection routing
- Create data collection service prototype
- Test basic service flow with interrupt/resume pattern

### **Phase 2: Service Framework (Week 3-4)**
- Implement service registry system
- Add validation function framework
- Create API integration layer
- Add retry logic and error handling
- Test with multiple service types

### **Phase 3: Production Features (Week 5-6)**
- Service timeout and cancellation handling
- Advanced routing and conflict resolution
- Performance optimization
- Monitoring and analytics integration
- Documentation and deployment

## 🎯 Technical Decisions

### **Why LangGraph Native Over Tools?**
- **State Persistence**: Automatic checkpointing handles interruptions
- **Observability**: Native tracing for each service step
- **Flow Control**: Conditional edges provide robust routing
- **Scalability**: Adding services = adding nodes (not custom logic)
- **User Experience**: Natural conversation flow with seamless interruptions

### **Service Registry Benefits**
- **Declarative**: Services defined by configuration, not code
- **Maintainable**: Easy to modify service flows without code changes  
- **Testable**: Each service component can be tested independently
- **Extensible**: New validation rules and API integrations plug in easily

### **Integration Strategy**
- **Non-Breaking**: Extends existing workflow without modifications
- **Backward Compatible**: Normal conversations work exactly as before
- **Gradual Migration**: Can implement services one at a time
- **Rollback Safe**: Can disable services without affecting core functionality

## 📊 Success Metrics

### **Technical Metrics**
- Zero data loss during service interruptions
- Sub-second service resumption times
- Complete trace visibility for all service steps
- Memory usage remains constant during long services

### **User Experience Metrics**
- Natural conversation flow maintained
- Clear service progress indication
- Intuitive error messages and retry prompts
- Successful service completion rate > 95%

### **Development Metrics**
- New service implementation < 50 lines of configuration
- Service testing coverage > 90%
- Documentation covers all service patterns
- Developer onboarding for new services < 1 hour

## 🚨 Risk Mitigation

### **State Management Risks**
- **Risk**: Service state corruption during interruptions
- **Mitigation**: Comprehensive state validation and recovery mechanisms

### **Performance Risks**
- **Risk**: Memory bloat from long-running services
- **Mitigation**: Automatic cleanup of completed services and timeout handling

### **User Experience Risks**
- **Risk**: Users getting stuck in service flows
- **Mitigation**: Clear cancellation paths and timeout with graceful exits

### **Integration Risks**
- **Risk**: Breaking existing workflow functionality
- **Mitigation**: Comprehensive testing with existing conversation patterns

## 🎪 Open Questions

1. **Service Timeout Strategy**: Fixed timeout vs. step-based timeout?
2. **Concurrent Services**: Should users be able to run multiple services simultaneously?
3. **Service Persistence**: How long to keep completed service data?
4. **Error Recovery**: Should failed services be auto-retryable later?
5. **Service Analytics**: What metrics are most valuable for service optimization?

## 🔄 Alternative Approach: Functional API with @task

### **Overview**

Instead of modifying the graph structure, use LangGraph's **Functional API** with `@task` decorators to implement services as composable functions with built-in persistence and human-in-the-loop capabilities.

### **Key Concepts**

**@task Decorator**
- Functions become persistent, resumable tasks
- Automatic state management and checkpointing
- Built-in support for `interrupt()` and resume patterns

**@entrypoint Decorator**
- Orchestrates multiple tasks into workflows
- Provides persistence and threading capabilities
- Can be called as tools from existing agent

### **Implementation Strategy**

**Service as Task Functions**
- Each service step becomes a `@task` function
- Use `interrupt()` for user input collection
- Natural retry logic through function composition

**Tool Integration**
- Create `ExecuteServiceTool` that calls service entrypoints
- Services reuse the same checkpointer from main graph
- Results returned to main agent conversation

**Example Structure**
```
@task
def collect_cpf() -> str:
    cpf = interrupt("Por favor, informe seu CPF:")
    if not validate_cpf(cpf):
        return collect_cpf()  # Retry via recursion
    return cpf

@entrypoint(checkpointer=checkpointer)
def data_collection_service():
    cpf = collect_cpf().result()
    email = collect_email().result() 
    name = collect_name().result()
    return {"cpf": cpf, "email": email, "name": name}
```

### **Pros vs. Graph Approach**

**Advantages**
- Zero modification to existing graph structure
- Simpler implementation with less code
- Natural function composition and testing
- Automatic persistence per service
- Easy service isolation and debugging

**Trade-offs**
- Less integration with main conversation flow
- Service state managed in separate thread namespace
- Service traces separate from main agent traces
- Limited cross-service communication

### **Decision Matrix**

| Criteria | Graph Extension | Functional API |
|----------|----------------|----------------|
| **Implementation Complexity** | High | Low |
| **Graph Integration** | Native | Tool-based |
| **State Management** | Unified | Same Checkpointer |
| **Observability** | Complete | Service-level |
| **Development Speed** | Slow | Fast |
| **Testing Isolation** | Complex | Simple |
| **Rollback Safety** | Medium | High |

## 🚀 Next Steps

### **Option A: Graph Extension (Recommended)**
1. **Stakeholder Review**: Get approval on architecture and phases
2. **Proof of Concept**: Implement minimal viable service flow
3. **Technical Spec**: Detail exact implementation for Phase 1

### **Option B: Functional API (Alternative)**
1. **Rapid Prototype**: Build data collection service with @task
2. **Tool Integration**: Create ExecuteServiceTool for agent
3. **Validation**: Test service isolation and persistence

### **Decision Process**
1. **Week 1**: Implement both prototypes
2. **Week 2**: Evaluate based on integration quality and development velocity
3. **Week 3**: Choose approach and proceed with full implementation