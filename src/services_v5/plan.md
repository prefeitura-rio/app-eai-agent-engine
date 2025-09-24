# Services V5 - Plano Simplificado

Nesse repositorio imports relativos sao proibidos! É obrigatorio o uso de imports absolutos!!!

## Lógica Core da Versão Anterior

Após analisar `/src/services`, identifiquei os 4 conceitos essenciais:

### **1. Hidratação Automática**
- Auto-completa steps que já têm dados no state
- Marca como completed baseado em dados existentes

### **2. Execução em Cascata** 
- Executa nodes automaticamente até precisar de dados
- Continua execução após receber novos dados

### **3. Execução/Pausa Inteligente**
- Para quando encontra node que precisa de dados do agente
- Retorna informando exatamente quais dados são necessários

### **4. Next Steps**
- Identifica próximos steps baseado em dependências
- Informa ao agente através do AgentResponse

## Plano V5 - Apenas o Essencial

### **Objetivo**
Implementar apenas a lógica core usando LangGraph, sem modelos extras.

### **Arquitetura 100% Pydantic Oriented**

#### **Modelos Pydantic Mínimos:**

```python
# MODELOS PYDANTIC MÍNIMOS
class InternalState(BaseModel):
    """Estado interno para controle de fluxo"""
    completed_steps: Dict[str, bool] = {}
    pending_steps: List[str] = []
    service_completed: bool = False

class ServiceState(BaseModel):
    """Estado do serviço - tudo que LangGraph precisa"""
    user_id: str
    service_name: str
    status: Literal["progress", "completed", "error"] = "progress"
    data: Dict[str, Any] = {}
    internal: InternalState = Field(default_factory=InternalState)

class AgentResponse(BaseModel):
    """Resposta para o agente - tudo que ele precisa"""
    service_name: str
    status: Literal["progress", "completed", "error"] = "progress"
    error_message: Optional[str] = None
    description: str = ""
    payload_schema: Optional[Dict[str, Any]] = None
    data: Dict[str, Any] = {}
    internal: InternalState

# Opcional: Para validação de entrada
class ServiceRequest(BaseModel):
    service_name: str
    user_id: str
    payload: Dict[str, Any] = {}
```

**CONCEITOS ELIMINADOS:**
- ❌ `ServiceDefinition` → Workflow IS the definition
- ❌ `StepInfo` → Nodes ARE the steps  
- ❌ `ExecutionResult` → Nodes return AgentResponse directly
- ❌ `ExecutionSummary` → Desnecessário para MVP
- ❌ `IgnoredField` → Simplificar por agora

#### **BaseWorkflow.execute() - Simplificado**

```python
def execute(self, state: ServiceState, payload: Dict[str, Any]) -> AgentResponse:
    """
    SUPER SIMPLES:
    1. Aplicar payload ao state 
    2. Executar grafo LangGraph com state
    3. Determinar status baseado no state final
    4. Gerar AgentResponse
    """
    # 1. Aplicar payload ao state
    state = self._apply_payload(state, payload)
    
    # 2. Executar LangGraph
    graph = self.build_graph().compile()
    final_state = graph.invoke(state)
    
    # 3. Determinar status e gerar response
    return self._generate_response(final_state)
```

#### **Fluxo Super Simples:**

```text
1. Tool recebe Dict → Passa direto para execute()
2. execute() aplica ao ServiceState → Executa LangGraph → Retorna AgentResponse  
3. Tool retorna AgentResponse.model_dump()
```

#### **Nodes LangGraph - Padrões Simples**

**Data Collection Node:**
```python
def collect_user_info(state: ServiceState) -> ServiceState:
    # Se já tem dados, continua
    if state.data.get('user_info'):
        return state
    
    # Se não tem, para (LangGraph para naturalmente)
    state.internal.pending_steps = ['user_info']
    return state
```

**Action Node:**
```python  
def check_account(state: ServiceState) -> ServiceState:
    # Executa automaticamente
    user_info = state.data.get('user_info')
    account_exists = lookup_account(user_info['email'])
    
    state.data['account_exists'] = account_exists
    state.internal.completed_steps['check_account'] = True
    return state
```

### **Implementação**

#### **1. BaseWorkflow.execute()**
- Hidratar state com payload
- Invocar grafo compilado
- Analisar resultado do grafo
- Retornar AgentResponse apropriada

#### **2. Nodes no Workflow**
- Verificar se têm dados suficientes no state
- Executar se têm dados, pausar se não têm
- LangGraph para naturalmente quando node não pode continuar

#### **3. Schema Generation**
- Gerar payload_schema dinamicamente baseado em quais dados faltam
- Usar schemas Pydantic já definidos nos nodes

### **Vantagens**
- **Zero modelos extras**: ServiceState e AgentResponse são suficientes
- **LangGraph nativo**: Usar conditional edges, routing nativo
- **Simples**: Apenas hidratação + execução + análise
- **Compatível**: Mesma interface da versão anterior

### **Funcionalidades Críticas Identificadas**

Após revisão detalhada da versão anterior, identifiquei funcionalidades que **NÃO PODEMOS PERDER**:

#### **1. Strict Step Validation** ⚠️ CRÍTICO
- Só processar campos de steps **ativos** (com dependências satisfeitas)
- Ignorar campos fora de ordem e informar ao agente
- Implementar: `_get_active_steps()` baseado em dependências

#### **2. Service Completion Reset** ⚠️ CRÍTICO  
- Reset automático quando serviço completa e nova operação inicia
- Limpar flags `_internal.service_completed`
- Aplicar persistence resets entre operações

#### **3. Persistence Levels** ⚠️ IMPORTANTE
- Suportar: `permanent`, `session`, `operation`, `transient`
- Reset dados baseado no nível de persistência
- Implementar: `_apply_persistence_resets()`

#### **4. Dot Notation Support** ⚠️ IMPORTANTE
- Suportar hierarquia: `user_info.name`, `user_info.email`
- Estrutura de dados complexa no state
- Validação hierárquica de steps

#### **5. Rich Response Generation** ⚠️ UX
- Execution summary, dependency tree, detailed status
- Visibilidade completa do progresso para debugging
- Campos ignorados e razões

#### **6. Internal State Management** ⚠️ CRÍTICO
- `_internal.completed_steps.{step_name}`
- `_internal.outcomes.{step_name}` 
- `_internal.pending_steps`
- `_internal.action_next_steps`

### **Plano V5 Revisado**

#### **BaseWorkflow.execute() Expandido**
```python
def execute(self, state: ServiceState, payload: Dict[str, Any]) -> ExecutionResult:
    """
    Lógica completa baseada na versão anterior:
    
    1. RESET CHECK: Verificar se serviço completou e resetar se necessário
    2. STRICT VALIDATION: Só processar campos de steps ativos  
    3. HIDRATAÇÃO: Aplicar payload + auto-completar dados existentes
    4. EXECUÇÃO: Roda grafo LangGraph até pausar ou completar
    5. PERSISTENCE: Aplicar resets baseado em persistence_level
    6. ANÁLISE: Determinar status e next steps
    7. RESPOSTA: AgentResponse rica com execution summary
    """
```

#### **Implementação 100% Pydantic**

#### **1. Tool Layer (tool.py)**
```python
@tool
def multi_step_service(
    service_name: str, 
    user_id: str, 
    payload: Dict[str, Any]
) -> dict:
    # Converter Dict para PayloadModel dinâmico
    PayloadModel = create_dynamic_payload_model(payload)
    typed_payload = PayloadModel(**payload)
    
    # Executar workflow com tipos
    result = orchestrator.execute_workflow(
        ServiceRequest(
            service_name=service_name,
            user_id=user_id,
            payload=typed_payload
        )
    )
    
    return result.model_dump()
```

#### **2. Orchestrator (orchestrator.py)**
```python 
class Orchestrator:
    def execute_workflow(self, request: ServiceRequest) -> AgentResponse:
        # Carregar state como ServiceState (Pydantic)
        state = self.state_manager.load_state(request.user_id, request.service_name)
        
        # Executar workflow com tipos
        result = workflow.execute(state, request.payload)
        
        # Salvar state tipado
        self.state_manager.save_state(result.state)
        
        return result.response
```

#### **3. BaseWorkflow (base_workflow.py)**
```python
def execute(self, state: ServiceState, payload: BaseModel) -> ExecutionResult:
    # 1. RESET CHECK (Pydantic)
    if state.internal.service_completed:
        state = self._reset_for_new_operation(state)
    
    # 2. STRICT VALIDATION (Pydantic)
    validation_result = self._validate_payload_strict(state, payload)
    state = validation_result.updated_state
    
    # 3. HIDRATAÇÃO (Pydantic)
    state = self._hydrate_state(state)
    
    # 4. EXECUÇÃO LANGGRAPH (Pydantic)
    graph = self.build_graph().compile()
    state = graph.invoke(state)
    
    # 5. PERSISTENCE (Pydantic)
    state = self._apply_persistence_resets(state)
    
    # 6. ANÁLISE + RESPOSTA (Pydantic)
    response = self._generate_agent_response(state, validation_result)
    
    return ExecutionResult(state=state, response=response)
```

#### **4. Métodos Helper Tipados**
```python
def _validate_payload_strict(
    self, 
    state: ServiceState, 
    payload: BaseModel
) -> PayloadValidationResult:
    """Retorna PayloadValidationResult (Pydantic)"""

def _generate_agent_response(
    self, 
    state: ServiceState, 
    validation: PayloadValidationResult
) -> AgentResponse:
    """Retorna AgentResponse (Pydantic)"""

def _get_active_steps(self, state: ServiceState) -> List[StepInfo]:
    """Retorna List[StepInfo] (Pydantic)"""
```

### **Arquitetura Final - Super Simples**

```python
# APENAS 4 MODELOS FINAIS
class InternalState(BaseModel):
    """Estado interno para controle de fluxo"""
    completed_steps: Dict[str, bool] = {}
    pending_steps: List[str] = []
    service_completed: bool = False

class ServiceState(BaseModel):
    user_id: str
    service_name: str
    status: Literal["progress", "completed", "error"] = "progress"
    data: Dict[str, Any] = {}
    internal: InternalState = Field(default_factory=InternalState)

class AgentResponse(BaseModel):
    service_name: str
    status: Literal["progress", "completed", "error"] = "progress"
    description: str = ""
    payload_schema: Optional[Dict[str, Any]] = None
    data: Dict[str, Any] = {}
    error_message: Optional[str] = None
    internal: InternalState

class ServiceRequest(BaseModel):
    service_name: str  
    user_id: str
    payload: Dict[str, Any] = {}
```

### **Lógica do Status (no _generate_response)**

```python
def _generate_response(self, state: ServiceState) -> AgentResponse:
    # Se service completou
    if state.internal.service_completed:
        return AgentResponse(
            service_name=state.service_name,
            status="completed",
            description="Serviço concluído",
            data=state.data,
            internal=state.internal
        )
    
    # Se tem pending_steps, precisa de mais dados
    if state.internal.pending_steps:
        return AgentResponse(
            service_name=state.service_name,
            status="progress", 
            description="Dados necessários",
            payload_schema=self._generate_schema(state.internal.pending_steps),
            data=state.data,
            internal=state.internal
        )
    
    # Se não tem pending nem completed, algo deu errado
    return AgentResponse(
        service_name=state.service_name,
        status="error",
        error_message="Fluxo interrompido inesperadamente",
        internal=state.internal
    )
```

### **Benefícios da Simplificação**
- **Menos Abstrações**: ServiceDefinition → Workflow IS the definition
- **Menos Modelos**: StepInfo → Nodes ARE the steps  
- **Status Automático**: execute() determina status baseado no state
- **LangGraph Nativo**: Usar resources nativos do framework
- **Type Safety**: Pydantic onde faz sentido
- **Simplicidade**: Foco no essencial sem over-engineering