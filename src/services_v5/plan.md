# Services V5: LangGraph Native Implementation

## Visão Geral

Implementação minimalista de serviços multi-step usando **LangGraph puro**, aproveitando ao máximo suas funcionalidades nativas sem abstrações desnecessárias.

## Funcionalidades Core

### ✅ **Funcionalidades Essenciais**
1. **Persistência Automática**: Retomar fluxo de qualquer edge usando LangGraph checkpoints
2. **Skip Steps Inteligente**: Pular steps quando dados necessários já estão no state
3. **Schema Dinâmico**: Cada node/edge retorna seu próprio schema JSON
4. **Modelos de Resposta**: Estruturas definidas para comunicação com agente
5. **Estado Compartilhado**: Acesso completo ao state por todos nodes/edges (JSON local)
6. **Dependências Automáticas**: LangGraph gerencia dependências nativamente

### ❌ **O que NÃO vamos fazer**

- Orquestrador complexo
- Abstrações desnecessárias sobre LangGraph
- Sistema de validação custom (usar Pydantic direto)
- Gerenciamento manual de fluxo (deixar para LangGraph)

## Arquitetura Minimalista

### Core Components

#### 1. **Models (Já existente)** (`src/services_v5/core/models.py`)

```python
# Modelos já definidos e funcionais
class ServiceRequest(BaseModel):
    service_name: str
    user_id: str
    payload: Dict[str, Any] = {}

class ServiceState(BaseModel):
    user_id: str
    service_name: str
    status: Literal["running", "completed", "error"] = "running"
    data: Dict[str, Any] = {}

class AgentResponse(BaseModel):
    service_name: str
    status: str
    error_message: Optional[str] = None
    description: str = ""
    data: Dict[str, Any] = {}
```


#### 3. **Orquestrador Simples** (`src/services_v5/core/orchestrator.py`)

```python
from langgraph import StateGraph
from typing import Dict, Any

class SimpleOrchestrator:
    """Orquestrador agnóstico para workflows LangGraph"""
    
    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager
        self.workflows = {}  # Registry de workflows
    
    def register_workflow(self, name: str, workflow_class):
        """Registra um workflow no orquestrador"""
        self.workflows[name] = workflow_class
    
    def execute_service(self, request: ServiceRequest) -> AgentResponse:
        """Executa um serviço de forma agnóstica"""
        # 1. Carrega ou cria state
        state = self.state_manager.load_service_state(
            request.user_id, request.service_name
        ) or ServiceState(
            user_id=request.user_id,
            service_name=request.service_name
        )
        
        # 2. Aplica payload no state
        if request.payload:
            state.data.update(request.payload)
        
        # 3. Executa workflow LangGraph
        workflow = self.workflows[request.service_name]()
        result = workflow.execute(state)
        
        # 4. Salva state
        self.state_manager.save_service_state(result.state)
        
        # 5. Retorna resposta agnóstica
        return result.response
