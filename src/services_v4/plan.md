# 🚀 Plano de Migração: Framework V3 → V4 (Arquitetura DAG Pythônica)

## 📊 **Análise da Arquitetura Atual V3**

### ❌ **Limitações Identificadas**
1. **Arquitetura Declarativa Rígida**: ServiceDefinition como estrutura estática
2. **Dependências Implícitas**: `depends_on` como strings, difícil de rastrear
3. **Fluxo Controlado por Actions**: Lógica de fluxo espalhada
4. **Schema Verbose**: Muita configuração para funcionalidades simples
5. **Debugging Complexo**: Difícil rastrear fluxo de execução

### ✅ **Pontos Fortes a Preservar**
- **Strict Graph Executor**: Validação rigorosa de dependências  
- **Enhanced Error Handling**: Recovery automático
- **State Management**: Persistência multi-nível
- **LangChain Integration**: Tool para agentes
- **Tree Visualization**: Debug visual excelente
- **Pydantic Validation**: Type safety

---

## 🎯 **Nova Arquitetura V4: DAG-Based Pythônica**

### 🏗️ **Conceitos Fundamentais V4**

#### **1. Flow (substitui ServiceDefinition)**
```python
from src.services_v4 import Flow, Task, DataCollectionTask, ActionTask

# V4: Pythônico e fluido
@flow(name="bank_account_service")
def create_bank_account_flow():
    """Flow pythônico para abertura de conta bancária"""
    
    # Tasks de coleta de dados
    user_name = DataCollectionTask(
        name="user_name",
        description="What's your full name?",
        schema=UserNameSchema
    )
    
    user_email = DataCollectionTask(
        name="user_email", 
        description="What's your email address?",
        schema=UserEmailSchema
    )
    
    # Task de ação (business logic)
    check_account = ActionTask(
        name="check_account",
        description="Check if user already has account"
    )
    
    # Dependências explícitas via >> operator (pythônico)
    [user_name, user_email] >> check_account
    
    # Conditional branching baseado em resultado de task
    account_type = DataCollectionTask(
        name="account_type",
        description="Choose account type",
        schema=AccountTypeSchema,
        wait_for=[check_account],  # Explicit dependency
        condition=lambda ctx: ctx.check_account.outcome == "ACCOUNT_NOT_FOUND"
    )
    
    create_account = ActionTask(name="create_account")
    account_type >> create_account
    
    # Return the flow
    return Flow(
        name="bank_account_service",
        tasks=[user_name, user_email, check_account, account_type, create_account]
    )
```

#### **2. Context (substitui ServiceState)**
```python
from src.services_v4 import FlowContext

class FlowContext:
    """Context compartilhado entre todas as tasks"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.data = {}  # User data
        self.task_results = {}  # Task outcomes
        self.metadata = {}  # Timestamps, etc
    
    # Dot notation access
    @property
    def user_name(self) -> str:
        return self.data.get("user_name")
    
    @property 
    def check_account(self) -> TaskResult:
        return self.task_results.get("check_account")
```

#### **3. Task Types (substitui StepInfo)**

```python
# === TIPOS DE TASKS ===

class DataCollectionTask(Task):
    """Task para coletar dados do usuário via agente"""
    
    def __init__(self, name: str, description: str, schema: BaseModel, 
                 wait_for: List[Task] = None, condition: Callable = None):
        super().__init__(name, wait_for, condition)
        self.description = description
        self.schema = schema
        self.type = "data_collection"
    
    def execute(self, context: FlowContext) -> TaskResult:
        # Implementação de coleta via agente
        pass

class ActionTask(Task):
    """Task para executar lógica de negócio/ações"""
    
    def __init__(self, name: str, action: Callable[[FlowContext], TaskResult] = None,
                 wait_for: List[Task] = None, condition: Callable = None):
        super().__init__(name, wait_for, condition)
        self.action = action or getattr(self, f"_{name}")
        self.type = "action"
    
    def execute(self, context: FlowContext) -> TaskResult:
        return self.action(context)

class DecisionTask(Task):
    """Task para tomar decisões baseadas no contexto"""
    
    def __init__(self, name: str, decision_logic: Callable[[FlowContext], str],
                 routes: Dict[str, List[Task]], wait_for: List[Task] = None):
        super().__init__(name, wait_for)
        self.decision_logic = decision_logic
        self.routes = routes
        self.type = "decision"
    
    def execute(self, context: FlowContext) -> TaskResult:
        outcome = self.decision_logic(context)
        next_tasks = self.routes.get(outcome, [])
        return TaskResult(success=True, outcome=outcome, next_tasks=next_tasks)

class ParallelTask(Task):
    """Task para executar múltiplas tasks em paralelo"""
    
    def __init__(self, name: str, parallel_tasks: List[Task],
                 wait_for: List[Task] = None):
        super().__init__(name, wait_for)
        self.parallel_tasks = parallel_tasks
        self.type = "parallel"
```

### 🔗 **API Pythônica para Conexões**

```python
# === OPERATORS PYTHÔNICOS ===

class Task:
    """Base class para todas as tasks"""
    
    def __init__(self, name: str, wait_for: List['Task'] = None, 
                 condition: Callable[[FlowContext], bool] = None):
        self.name = name
        self.wait_for = wait_for or []
        self.condition = condition
        self.downstream_tasks = []
    
    def __rshift__(self, other: 'Task') -> 'Task':
        """Operator >> para conectar tasks: task1 >> task2"""
        other.wait_for.append(self)
        self.downstream_tasks.append(other)
        return other
    
    def __or__(self, other: 'Task') -> List['Task']:
        """Operator | para tasks paralelas: task1 | task2"""
        return [self, other]
    
    def __and__(self, other: 'Task') -> 'Task':
        """Operator & para join de tasks: (task1 | task2) & join_task"""
        other.wait_for.extend([self] if not isinstance(self, list) else self)
        return other

# === EXEMPLOS DE USO ===

# Sequencial: A >> B >> C
user_data >> check_account >> create_account

# Paralelo: A | B >> C  
(user_name | user_email) >> check_account

# Condicional: A >> B (se condição)
check_account >> account_type.when(lambda ctx: ctx.check_account.outcome == "NEW_USER")

# Join: (A | B) & C
(collect_docs | verify_identity) & approve_account
```

### 🧠 **Sistema de Context Compartilhado**

```python
from typing import Any, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TaskResult:
    """Resultado de execução de uma task"""
    success: bool
    outcome: str
    data: Dict[str, Any] = None
    error_message: Optional[str] = None
    next_tasks: List[str] = None
    timestamp: datetime = None

class FlowContext:
    """Context inteligente compartilhado entre todas as tasks"""
    
    def __init__(self, user_id: str, flow_name: str):
        self.user_id = user_id
        self.flow_name = flow_name
        
        # Core data
        self.data = {}           # User-provided data
        self.task_results = {}   # Task execution results
        self.metadata = {        # System metadata
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "flow_id": f"{user_id}_{flow_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }
        
        # State tracking
        self.completed_tasks = set()
        self.failed_tasks = set()
        self.current_task = None
    
    # === DYNAMIC ATTRIBUTE ACCESS ===
    def __getattr__(self, name: str) -> Any:
        """Dynamic access: ctx.user_name, ctx.check_account, etc."""
        # Try task results first
        if name in self.task_results:
            return self.task_results[name]
        # Then user data
        if name in self.data:
            return self.data[name]
        # Default
        raise AttributeError(f"'{name}' not found in context")
    
    def __setattr__(self, name: str, value: Any):
        """Dynamic setting: ctx.user_name = "John" """
        if name.startswith('_') or name in ['user_id', 'flow_name', 'data', 'task_results', 'metadata', 'completed_tasks', 'failed_tasks', 'current_task']:
            super().__setattr__(name, value)
        else:
            self.data[name] = value
    
    # === CONTEXT QUERY METHODS ===
    def has_data(self, field: str) -> bool:
        """Check if field exists in user data"""
        return field in self.data
    
    def has_result(self, task_name: str) -> bool:
        """Check if task has been executed"""
        return task_name in self.task_results
    
    def get_outcome(self, task_name: str) -> Optional[str]:
        """Get outcome of a specific task"""
        result = self.task_results.get(task_name)
        return result.outcome if result else None
    
    def was_successful(self, task_name: str) -> bool:
        """Check if task executed successfully"""
        result = self.task_results.get(task_name)
        return result.success if result else False
    
    # === CONTEXT OPERATIONS ===
    def set_task_result(self, task_name: str, result: TaskResult):
        """Store task execution result"""
        self.task_results[task_name] = result
        if result.success:
            self.completed_tasks.add(task_name)
        else:
            self.failed_tasks.add(task_name)
        
        # Merge task data into context
        if result.data:
            self.data.update(result.data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize context for persistence"""
        return {
            "user_id": self.user_id,
            "flow_name": self.flow_name,
            "data": self.data,
            "task_results": {k: v.__dict__ for k, v in self.task_results.items()},
            "metadata": self.metadata,
            "completed_tasks": list(self.completed_tasks),
            "failed_tasks": list(self.failed_tasks)
        }
```

### 📋 **Tipos de Tasks Especializadas**

```python
# === TASK TYPES HIERARCHY ===

class DataCollectionTask(Task):
    """Coleta dados do usuário via agente"""
    
    def __init__(self, name: str, description: str, schema: BaseModel,
                 required: bool = True, persistence: str = "permanent"):
        super().__init__(name)
        self.description = description
        self.schema = schema
        self.required = required
        self.persistence = persistence
    
    async def execute(self, context: FlowContext) -> TaskResult:
        # Will be called by agent interaction
        if context.has_data(self.name):
            return TaskResult(
                success=True,
                outcome="DATA_AVAILABLE", 
                data={self.name: getattr(context, self.name)}
            )
        else:
            return TaskResult(
                success=False,
                outcome="AWAITING_INPUT",
                error_message=f"Waiting for user input: {self.description}"
            )

class ActionTask(Task):
    """Executa lógica de negócio"""
    
    def __init__(self, name: str, action: Callable = None):
        super().__init__(name)
        self.action = action or getattr(self, f"_{name}", self._default_action)
    
    async def execute(self, context: FlowContext) -> TaskResult:
        return await self.action(context)
    
    def _default_action(self, context: FlowContext) -> TaskResult:
        return TaskResult(success=True, outcome="SUCCESS")

class DecisionTask(Task):
    """Toma decisões baseadas no contexto"""
    
    def __init__(self, name: str, decision_logic: Callable[[FlowContext], str],
                 routes: Dict[str, List[Task]]):
        super().__init__(name)
        self.decision_logic = decision_logic
        self.routes = routes
    
    async def execute(self, context: FlowContext) -> TaskResult:
        outcome = self.decision_logic(context)
        next_tasks = self.routes.get(outcome, [])
        return TaskResult(
            success=True,
            outcome=outcome,
            next_tasks=[t.name for t in next_tasks]
        )

class ValidationTask(Task):
    """Valida dados usando Pydantic"""
    
    def __init__(self, name: str, fields: List[str], schema: BaseModel):
        super().__init__(name)
        self.fields = fields
        self.schema = schema
    
    async def execute(self, context: FlowContext) -> TaskResult:
        data_to_validate = {field: getattr(context, field) for field in self.fields}
        try:
            validated = self.schema.model_validate(data_to_validate)
            return TaskResult(success=True, outcome="VALID", data=validated.model_dump())
        except ValidationError as e:
            return TaskResult(success=False, outcome="INVALID", error_message=str(e))

class ApiCallTask(Task):
    """Chama APIs externas"""
    
    def __init__(self, name: str, endpoint: str, method: str = "GET",
                 data_mapper: Callable[[FlowContext], Dict] = None):
        super().__init__(name)
        self.endpoint = endpoint
        self.method = method
        self.data_mapper = data_mapper or (lambda ctx: {})
    
    async def execute(self, context: FlowContext) -> TaskResult:
        # Implementation for API calls
        pass

class LoopTask(Task):
    """Executa tasks em loop até condição"""
    
    def __init__(self, name: str, loop_tasks: List[Task], 
                 condition: Callable[[FlowContext], bool]):
        super().__init__(name)
        self.loop_tasks = loop_tasks
        self.condition = condition
    
    async def execute(self, context: FlowContext) -> TaskResult:
        # Implementation for loops
        pass
```

### 🎯 **Exemplo de Migração: Serviço Bancário V3 → V4**

```python
# === V3 (ATUAL) ===
class BankAccountServiceV3(BaseService):
    def get_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name="bank_account_opening_v2",
            description="Bank account service",
            steps=[
                StepInfo(name="user_info", substeps=[
                    StepInfo(name="user_info.name", payload_schema=UserNamePayload),
                    StepInfo(name="user_info.email", payload_schema=UserEmailPayload)
                ]),
                StepInfo(name="check_account", action=self._check_account_exists, depends_on=["user_info"]),
                # ... mais 10 linhas de configuração
            ]
        )

# === V4 (NOVO) ===
@flow(name="bank_account_opening_v4")
def bank_account_flow():
    """Flow pythônico e intuitivo"""
    
    # Tasks de coleta
    user_name = DataCollectionTask("user_name", "What's your full name?", UserNameSchema)
    user_email = DataCollectionTask("user_email", "What's your email?", UserEmailSchema)
    
    # Task de ação
    check_account = ActionTask("check_account")
    
    # DAG explícito e readable
    [user_name, user_email] >> check_account
    
    # Branching condicional
    new_account_branch = check_account.branch(
        condition=lambda ctx: ctx.check_account.outcome == "NEW_USER",
        tasks=[
            DataCollectionTask("account_type", "Choose account type", AccountTypeSchema),
            ActionTask("create_account")
        ]
    )
    
    existing_account_branch = check_account.branch(
        condition=lambda ctx: ctx.check_account.outcome == "EXISTING_USER", 
        tasks=[
            ActionTask("load_account")
        ]
    )
    
    # Join branches
    account_operations = ActionTask("account_operations")
    [new_account_branch, existing_account_branch] >> account_operations
    
    return Flow([user_name, user_email, check_account, new_account_branch, 
                existing_account_branch, account_operations])

# === IMPLEMENTAÇÃO DE ACTIONS ===
class BankAccountActions:
    """Actions pythônicas como métodos de classe"""
    
    @staticmethod
    async def check_account(ctx: FlowContext) -> TaskResult:
        """Check if user already has an account"""
        user_email = ctx.user_email
        # Business logic here
        if existing_account(user_email):
            return TaskResult(success=True, outcome="EXISTING_USER", 
                            data={"account_id": 12345})
        else:
            return TaskResult(success=True, outcome="NEW_USER")
    
    @staticmethod  
    async def create_account(ctx: FlowContext) -> TaskResult:
        """Create new bank account"""
        account_id = generate_account_id()
        return TaskResult(success=True, outcome="ACCOUNT_CREATED",
                        data={"account_id": account_id})
```

## 🛣️ **Estratégia de Migração Gradual**

### **Fase 1: Dual Support (V3 + V4)**
- ✅ Manter V3 funcionando (backward compatibility)
- ✅ Implementar V4 core (Flow, Task, Context)
- ✅ Criar adapter V3→V4 para migração transparente
- ✅ LangChain tool suporta ambos formatos

### **Fase 2: V4 Implementation**  
- ✅ Migrar serviços existentes para V4
- ✅ Enhanced debugging tools para DAGs
- ✅ Performance improvements
- ✅ Advanced task types (Parallel, Loop, etc.)

### **Fase 3: V3 Deprecation**
- ✅ Mark V3 as deprecated
- ✅ Migration guide V3→V4
- ✅ Remove V3 code
- ✅ Full V4 ecosystem

## 🚀 **Vantagens da Nova Arquitetura V4**

### **🎯 Developer Experience**
```python
# V3: Verbose e confusing
StepInfo(name="check_account", action=self._check_account_exists, depends_on=["user_info"])

# V4: Clean e pythônico  
user_info >> check_account >> create_account
```

### **🔍 Debugging & Visualization**
- **Flow Graph**: Visualização clara do DAG
- **Task Tracing**: Rastreamento de execução por task
- **Context Inspection**: Debug em tempo real do contexto

### **🧩 Composability**
```python
# Reusable task components
user_verification_flow = [verify_email, verify_phone, verify_identity]
payment_flow = [collect_payment, process_payment, send_receipt]

# Compose complex flows
complete_flow = user_verification_flow + payment_flow
```

### **⚡ Performance**  
- **Parallel Execution**: Tasks independentes executam em paralelo
- **Lazy Evaluation**: Tasks só executam quando necessário
- **Smart Caching**: Context inteligente com cache automático

### **🔧 Advanced Features**
```python
# Retry logic
@retry(max_attempts=3, backoff=exponential)
class PaymentTask(ActionTask):
    pass

# Conditional execution
conditional_task = task.when(lambda ctx: ctx.user_tier == "premium")

# Dynamic task generation  
for item in ctx.shopping_cart:
    process_item = ActionTask(f"process_{item.id}")
    flow.add_task(process_item)
```

---

## 📋 **Resumo Executivo do Plano V4**

Este plano de migração propõe uma transformação completa do framework de uma arquitetura declarativa (V3) para uma arquitetura DAG pythônica (V4) inspirada no Prefect 3.

### **🎯 Principais Benefícios:**

1. **📝 Sintaxe Pythônica**: `user_info >> check_account >> create_account`
2. **🔗 Dependências Explícitas**: Connections via operators (`>>`, `|`, `&`)
3. **🧠 Context Inteligente**: Acesso dinâmico via `ctx.user_name`, `ctx.check_account.outcome`
4. **🎭 Task Types Especializadas**: DataCollection, Action, Decision, Validation, etc.
5. **⚡ Parallel Execution**: Tasks independentes executam simultaneamente
6. **🔍 Enhanced Debugging**: Visualização clara do DAG e rastreamento de execução
7. **🧩 Composability**: Flows reutilizáveis e componíveis

### **🛣️ Estratégia de Migração:**
- **Fase 1**: Dual support (V3 + V4) com backward compatibility
- **Fase 2**: Migração gradual dos serviços existentes  
- **Fase 3**: Deprecação do V3 e ecosystem V4 completo

### **🚀 Resultado Final:**
Um framework extremamente flexível que permite executar qualquer tipo de serviço, independente da complexidade, com uma sintaxe pythônica intuitiva e debugging superior.

---

## 🎯 **Próximos Passos**

1. **Implementar o core V4** (Flow, Task, Context classes)
2. **Criar o adapter V3→V4** para backward compatibility  
3. **Migrar o serviço bancário** como proof of concept
4. **Implementar enhanced debugging tools** para DAGs

---

**Data de criação**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
**Versão**: V4 Migration Plan 1.0