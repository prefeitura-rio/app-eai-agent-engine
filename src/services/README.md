# Multi-Step Service Framework V3

## Visão Geral

O Multi-Step Service Framework V3 é uma arquitetura action-driven completamente agnóstica para orquestração de serviços multi-step com **Strict Graph Executor**, validação Pydantic, gerenciamento de estado avançado e visualização hierárquica completa do fluxo de execução.

## 🏗️ Arquitetura Core

### Princípios Fundamentais V3

1. **100% Agnóstico**: O core não contém nenhuma lógica específica de serviços
2. **Strict Graph Executor**: Validação rigorosa que só processa steps ativos (dependency-compliant)
3. **Action-Driven**: Actions controlam o fluxo através de `ExecutionResult.next_steps`
4. **Cascade Execution**: Transition loop executa actions em cascata até completion
5. **Pydantic Validation**: Validação de payload robusta com mensagens de erro claras
6. **State Persistence**: Gerenciamento automático de estado com diferentes níveis de persistência
7. **Complete Tree Visualization**: Árvore preservada antes dos resets para visualização completa

### Componentes Core

```
src/services/
├── core/
│   ├── orchestrator.py      # ServiceOrchestrator - brain do framework
│   ├── response_generator.py # ResponseGenerator - visualização e schemas
│   ├── state.py             # ServiceState - gerenciamento de estado
│   └── base_service.py      # BaseService - classe base para serviços
├── schema/
│   └── models.py            # Modelos Pydantic (StepInfo, ServiceDefinition, etc.)
├── repository/
│   ├── bank_account_service_v2.py  # Exemplo de serviço
│   └── order_service.py            # Exemplo de serviço diferente
└── tool.py                  # LangChain tool integration
```

## 🔧 Componentes Principais

### 1. ServiceOrchestrator (V3 Enhanced)

O cérebro do framework V3, responsável por:

- **Strict Graph Execution**: Calcula steps ativos e só processa aqueles com dependências atendidas
- **Transition Loop**: Executa actions em cascata até não haver mais actions disponíveis
- **Enhanced Error Handling**: Tratamento robusto de erros com recovery automático
- **Complete Tree Capture**: Preserva árvore completa antes dos resets de persistência
- **Gerenciamento de Estado**: Aplica hydratação e persistence resets com melhor sincronização

```python
from src.services.core.orchestrator import ServiceOrchestrator

orchestrator = ServiceOrchestrator(service_definition)
response = orchestrator.execute_turn(user_id, payload)
```

### 2. ServiceDefinition & StepInfo (V3 Enhanced)

Definição declarativa de serviços com validação Pydantic integrada:

```python
from src.services.schema.models import ServiceDefinition, StepInfo
from pydantic import BaseModel, Field

# V3: Pydantic validation schemas
class UserNamePayload(BaseModel):
    name: str = Field(..., min_length=1, description="User full name")

definition = ServiceDefinition(
    service_name="example_service",
    description="Service description",
    steps=[
        StepInfo(
            name="user_info",
            description="Collect user information",
            substeps=[
                StepInfo(
                    name="user_info.name",
                    description="User name",
                    payload_schema=UserNamePayload,  # V3: Pydantic integration
                ),
            ],
        ),
        StepInfo(
            name="process_data",
            action=self._process_data_action,
            depends_on=["user_info"],
            persistence_level="operation",  # V3: Enhanced persistence control
        ),
    ],
)
```

### 3. ExecutionResult

Actions retornam `ExecutionResult` para controlar o fluxo:

```python
from src.services.schema.models import ExecutionResult

def _my_action(self, state: Dict[str, Any]) -> ExecutionResult:
    return ExecutionResult(
        success=True,
        outcome="SUCCESS",
        updated_data={"result": "processed"},
        next_steps=["next_step"],          # Controla o fluxo
        is_complete=False,                 # Indica se o serviço terminou
        completion_message="Done!"         # Mensagem final
    )
```

### 4. ServiceState

Gerenciamento de estado com persistência JSON e dot notation:

```python
from src.services.core.state import ServiceState

state_manager = ServiceState(user_id)
service_state = state_manager.get_service_state("service_name")

# Dot notation access
state_manager.set("data.user.name", "John", service_state)
name = state_manager.get("data.user.name", service_state)
```

## 🔄 Levels de Persistência

O framework suporta 4 níveis de persistência de dados:

```python
StepInfo(
    name="step_name",
    persistence_level="operation"  # permanent | session | operation | transient
)
```

- **`permanent`**: Dados nunca são resetados (default)
- **`session`**: Reset no fim da sessão do usuário
- **`operation`**: Reset após cada operação completa
- **`transient`**: Reset imediatamente após uso

## 🌳 Visualização Hierárquica

### Dependency Tree Agnóstica

O framework gera automaticamente uma árvore de dependências visual baseada puramente no `ServiceDefinition`:

```
🌳 DEPENDENCY TREE: bank_account_opening_v2
│
└── 🟢 user_info
    ├── 🟢 user_info.name
    └── 🟢 user_info.email
    │
    ▼
    └── 🟢 check_account (action) → ACCOUNT_NOT_FOUND
        │
        ▼
        ├── 🟢 account_type
        │   │
        │   ▼
        │   └── 🟢 create_account (action) → ACCOUNT_CREATED
        └── 🟡 ask_action
            │
            ▼
            └── 🔴 process_action_choice (action)
```

**Legenda:**
- 🟢 Complete
- 🟡 Current/Pending
- 🔴 Pending/Blocked

### Pre-Reset Tree Capture (V3 New Feature)

🎯 **Problema Resolvido**: Anteriormente, após a conclusão do serviço, os resets de `persistence_level` faziam com que alguns steps aparecessem como pendentes (⭕) ao invés de completos (✅) na árvore final.

🔧 **Solução V3**: O framework agora captura a árvore **antes** de aplicar os resets de `persistence_level`, preservando o caminho completo de execução para visualização. A árvore é temporariamente mantida em memória (não salva no estado) e retornada na resposta final.

✅ **Resultado**: Quando um serviço completa, todos os steps executados aparecem como ✅ (verde) na árvore final, mostrando o caminho real de execução.

## 🆕 Melhorias V3

### 1. Strict Graph Executor

**Problema V2**: Steps podiam ser processados mesmo com dependências não atendidas, causando inconsistências.

**Solução V3**: O Strict Graph Executor calcula quais steps estão **ativos** (dependency-compliant) e só processa esses steps:

```python
# V3: Strict validation - only active steps are processed
active_steps = self._get_active_steps(state_manager, service_state)
active_step_names = {step.name for step in active_steps}

for step_name, value in payload.items():
    if step_name in active_step_names:
        # Process step
    else:
        # Ignore field due to dependency requirements
        ignored_fields.append(step_name)
```

**Benefício**: Previne violações de dependência e garante execução ordenada.

### 2. Transition Loop (Cascade Execution)

**Problema V2**: Actions eram executadas uma por vez, exigindo múltiplas iterações.

**Solução V3**: O transition loop executa actions em cascata até não haver mais actions disponíveis:

```python
# V3: Cascade action execution
while True:
    action_steps = [step for step in active_steps if step.action]
    if not action_steps:
        break  # No more actions to execute
    
    # Execute next action and continue loop
    next_action = action_steps[0]
    result = next_action.action(service_state)
    # Process result and continue...
```

**Benefício**: Execução mais eficiente e fluxo mais fluido.

### 3. Enhanced Pydantic Validation

**Problema V2**: Validação básica com mensagens de erro genéricas.

**Solução V3**: Integração nativa com Pydantic para validação robusta:

```python
# V3: Pydantic payload schemas
class UserEmailPayload(BaseModel):
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')

# Validation with clear error messages
is_valid, validation_error, validated_data = step.validate_payload(payload)
# Returns: "String should match pattern '^[^@]+@[^@]+\.[^@]+$'"
```

**Benefício**: Mensagens de erro claras e validação tipada.

### 4. Enhanced Error Handling & Recovery

**Problema V2**: Erros podiam deixar o serviço em estado inconsistente.

**Solução V3**: Sistema robusto de tratamento de erros com recovery automático:

```python
# V3: Enhanced error handling
try:
    result = action.execute(state)
except Exception as e:
    return AgentResponse(
        status="FAILED",
        error_message=f"Unexpected error in action '{action.name}': {e}",
        # State remains consistent
    )
```

**Benefício**: Serviços mais robustos e debuging facilitado.

### 5. Complete Tree Visualization

**Problema V2**: Árvore final não mostrava corretamente os steps executados após resets.

**Solução V3**: Captura da árvore antes dos resets de persistência:

```python
# V3: Capture complete tree before resets
if result.is_complete:
    # Capture tree BEFORE applying persistence resets
    complete_tree = response_gen._generate_dependency_tree_ascii()
    
    # Apply persistence resets
    self._apply_persistence_resets(state_manager, service_state)
    
    # Return complete tree in response
    return complete_tree
```

**Benefício**: Visualização precisa do caminho de execução completo.

## 🚀 Como Criar um Novo Serviço

### 1. Definir a Classe do Serviço

```python
from typing import Dict, Any
from src.services.core.base_service import BaseService
from src.services.schema.models import ExecutionResult, ServiceDefinition, StepInfo

class MyService(BaseService):
    service_name = "my_service"
    description = "My custom service"

    def _my_action(self, state: Dict[str, Any]) -> ExecutionResult:
        # Lógica da action
        return ExecutionResult(
            success=True,
            outcome="SUCCESS",
            next_steps=["next_step"]
        )

    def get_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description=self.description,
            steps=[
                # Definir steps aqui
            ]
        )
```

### 2. Registrar o Serviço

No arquivo `tool.py`:

```python
from src.services.repository.my_service import MyService

_service_classes = [BankAccountServiceV2, OrderService, MyService]
```

### 3. Usar via LangChain Tool

```python
from src.services.tool import multi_step_service

result = multi_step_service.invoke({
    "service_name": "my_service",
    "user_id": "user123",
    "payload": {"field": "value"}
})
```

## 📊 Estrutura de Dados

### AgentResponse

Resposta completa do framework:

```python
{
    "service_name": "service_name",
    "status": "IN_PROGRESS" | "COMPLETED" | "FAILED",
    "error_message": "Error details if any",
    "current_data": {
        "_metadata": {
            "id": "user_id_uuid",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00"
        },
        "data": {
            # User data
        },
        "_internal": {
            "completed_steps": {"step1": true},
            "pending_steps": ["step2"],
            "outcomes": {"action1": "SUCCESS"},
            "service_completed": true,
            "execution_tree_complete": "tree_ascii"
        }
    },
    "next_step_info": {
        "step_name": "step_name",
        "description": "Step description",
        "payload_schema": {...},
        "substeps": [...]
    },
    "execution_summary": {
        "tree": "ascii_tree_visualization"
    }
}
```

## 🔍 Validação de Dependências

### Sistema Rigoroso

O framework implementa validação rigorosa de dependências:

```python
# CRITICAL: Check dependencies before processing
dependencies_met = all(
    self._is_dependency_met(dep_name, state_manager, service_state)
    for dep_name in step.depends_on
)

if dependencies_met or step_name in pending_step_names:
    # Process step
else:
    # Log dependency violation
    print(f"⚠️  Dependency violation: {step_name} requires {unmet_deps}")
```

### Dependency Resolution

- **Container Steps**: Marcados como completos quando todos os substeps obrigatórios são completados
- **Action Steps**: Validação baseada em outcomes (não apenas completion flags)
- **Substeps**: Herdam status do parent quando apropriado

## 🎯 Exemplos Práticos

### Serviço Bancário (bank_account_opening_v2)

```python
# Fluxo: user_info → check_account → [account_type → create_account] → ask_action → process_action_choice → [deposit_amount → execute_deposit | balance]

# Action controls flow:
def _check_account_exists(self, state):
    if existing_account:
        return ExecutionResult(outcome="ACCOUNT_EXISTS", next_steps=["ask_action"])
    else:
        return ExecutionResult(outcome="ACCOUNT_NOT_FOUND", next_steps=["account_type"])
```

### Serviço de Pedidos (order_processing)

```python
# Fluxo: customer_info → order_items → validate_order → payment_info → process_payment

# Different structure, same framework:
def _validate_order(self, state):
    if valid_order:
        return ExecutionResult(outcome="ORDER_VALID", next_steps=["payment_info"])
    else:
        return ExecutionResult(outcome="ORDER_EMPTY", next_steps=["order_items"])
```

## 🧪 Testing (V3 Enhanced)

### Setup de Teste V3

```python
from src.services.tool import multi_step_service

# Test complete flow with V3 features
result = multi_step_service.invoke({
    "service_name": "bank_account_opening_v2",
    "user_id": "test_user",
    "payload": {
        "user_info.name": "Test User",
        "user_info.email": "test@example.com"
    }
})

print(result["execution_summary"]["tree"])
```

### V3 Test Suite

Execute os testes V3 via comando centralizado:

```bash
# Run all V3 framework tests
python src/services/tests/run.py

# Run specific test
python src/services/tests/run.py test_strict_graph_executor
python src/services/tests/run.py test_tree_completion_visualization
python src/services/tests/run.py test_clean_state
```

### Casos de Teste V3

1. **Strict Graph Executor**: Verificar que só steps ativos são processados
2. **Cascade Action Execution**: Testar transition loop com múltiplas actions
3. **Pydantic Validation**: Verificar mensagens de erro claras
4. **Enhanced Error Handling**: Testar recovery de erros
5. **Complete Tree Visualization**: Verificar árvore com todos steps verdes após completion
6. **Clean State Management**: Confirmar que execution_tree_complete não é salvo
7. **Dependency Validation**: Tentar executar steps fora de ordem
8. **Persistence Levels**: Verificar resets após operations
9. **Multi-Service**: Testar diferentes tipos de serviços
10. **State Hydration**: Verificar recuperação de estado existente

## 🔧 Debugging

### Logs de Dependência

O framework automaticamente loga violações de dependência:

```
⚠️  Dependency violation: deposit_amount requires ['process_action_choice'] to be completed first
```

### State Inspection

Verificar estado interno:

```python
print("Completed steps:", result["current_data"]["_internal"]["completed_steps"])
print("Outcomes:", result["current_data"]["_internal"]["outcomes"])
print("Pending:", result["current_data"]["_internal"]["pending_steps"])
```

### Visual Tree Debug

A árvore visual mostra exatamente o estado de cada step:

```
◄── NEXT: ask_action
```

## 🏆 Principais Conquistas

### ✅ Problemas Resolvidos

1. **Erro Gravíssimo Corrigido**: Removida toda lógica hardcoded da visualização
2. **Dependency Validation**: Sistema rigoroso que previne execução fora de ordem
3. **Action-Driven Flow**: Actions controlam completamente o fluxo via `next_steps`
4. **Persistence Management**: Sistema flexível de reset baseado em `persistence_level`
5. **State Metadata**: IDs únicos, timestamps automáticos
6. **Pre-Reset Tree Capture**: Preserva caminho completo de execução
7. **Agnostic Visualization**: Árvore 100% agnóstica funciona com qualquer serviço

### 🎯 Framework Characteristics

- **Zero Service Logic in Core**: Core completamente agnóstico
- **Declarative Service Definition**: Serviços definidos via `StepInfo` hierárquico
- **Automatic State Management**: Hydratação, persistência e resets automáticos
- **Visual Debugging**: Árvore ASCII clara do fluxo de execução
- **Type Safety**: Uso extensivo de Pydantic para validação de tipos
- **LangChain Integration**: Tool nativo para uso em agents

## 📈 Evolução do Framework

### V1 → V2 → V3 Principais Mudanças

#### ❌ **V1 Problems (Fixed)**
- **Complex Condition Strings**: Condições JMESPath complexas e propensas a erro
- **is_end Flags**: Lógica de finalização confusa e hardcoded
- **Service-Specific Core Logic**: Visualização com lógica hardcoded de serviços específicos
- **Weak Dependency Validation**: Permitia execução fora de ordem
- **No State Metadata**: Falta de tracking e timestamps
- **No Persistence Management**: Dados nunca eram resetados

#### ✅ **V2 Solutions (Implemented)**
- **Action-Driven Architecture**: Actions controlam o fluxo via `ExecutionResult.next_steps`
- **Service Completion Control**: Actions decidem quando o serviço termina via `is_complete`
- **100% Agnostic Core**: Zero lógica de serviços específicos no core
- **Rigorous Dependency Validation**: Validação rigorosa antes de qualquer execução
- **Automatic State Metadata**: IDs únicos, created_at, updated_at automáticos
- **Flexible Persistence Levels**: 4 níveis de persistência (permanent, session, operation, transient)

#### 🚀 **V3 Enhancements (New)**
- **Strict Graph Executor**: Só processa steps ativos (dependency-compliant)
- **Cascade Action Execution**: Transition loop executa actions em cascata
- **Enhanced Pydantic Validation**: Validação robusta com mensagens claras
- **Enhanced Error Handling**: Recovery automático e estado consistente
- **Complete Tree Visualization**: Árvore preservada antes dos resets de persistência
- **Improved State Synchronization**: Melhor sincronização entre status, tree e next_step_info
- **Clean State Management**: execution_tree_complete não é salvo no estado

### V1 → V2 → V3 Evolution Example

**V1 (Old Way):**
```python
# ❌ Complex condition strings
condition='_internal.outcomes.check_account == "ACCOUNT_NOT_FOUND"'

# ❌ Hardcoded is_end logic
is_end=True  # Service ends here?

# ❌ Service-specific visualization
if step.name == "check_account":  # Hardcoded in core!
    tree_lines.append("check_account logic...")
```

**V2 (Better):**
```python
# ✅ Action-driven flow control
def _check_account_exists(self, state):
    return ExecutionResult(
        outcome="ACCOUNT_NOT_FOUND",
        next_steps=["account_type"]  # Action decides next step
    )

# ✅ Action-driven completion
def _make_deposit(self, state):
    return ExecutionResult(
        is_complete=True,  # Action decides completion
        completion_message="Deposit successful!"
    )

# ✅ 100% agnostic visualization
def render_step_and_dependents(step: StepInfo):
    # Works with ANY service definition
    for dependent in find_dependents(step):
        render_step_and_dependents(dependent)
```

**V3 (Best):**
```python
# 🚀 Strict Graph Executor + Pydantic validation
class UserEmailPayload(BaseModel):
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')

# Only active steps are processed
active_steps = self._get_active_steps(state_manager, service_state)
if step_name in {s.name for s in active_steps}:
    is_valid, error, data = step.validate_payload(payload)  # Pydantic
    if is_valid:
        # Process step
    else:
        # Return clear validation error

# 🚀 Cascade action execution
service_completed, error, complete_tree = self._execute_transition_loop()
if service_completed and complete_tree:
    # Tree captured BEFORE persistence resets
    return ExecutionSummary(tree=complete_tree)
```


### Extensibilidade

O framework foi projetado para ser facilmente extensível:

- **Novos Persistence Levels**: Adicionar novos tipos de persistência
- **Custom Actions**: Actions podem ser tão complexas quanto necessário
- **Multiple Backends**: State pode ser facilmente migrado para outros backends
- **Plugin Architecture**: Suporte futuro para plugins de terceiros

## 🎓 Lições Aprendidas (V1 → V2 → V3)

### Princípios Arquiteturais Validados

1. **Agnosticism is King**: Core agnóstico permite evolução sem breaking changes
2. **Actions Know Best**: Actions têm contexto completo para decidir o fluxo
3. **Dependency Validation is Critical**: Previne bugs sutis e comportamentos inesperados  
4. **Visual Feedback is Essential**: Árvore de dependências facilita debugging
5. **State Metadata Pays Off**: IDs e timestamps são essenciais para debugging
6. **Persistence Flexibility Required**: Diferentes níveis de persistência atendem casos diversos

### Novas Descobertas V3

7. **Strict Validation Prevents Chaos**: Só processar steps ativos previne estados inconsistentes
8. **Cascade Execution is More Efficient**: Transition loop reduz iterações desnecessárias
9. **Pydantic Integration is Game-Changing**: Validação tipada melhora significativamente a UX
10. **Tree Timing Matters**: Capturar árvore antes dos resets preserva o contexto de execução
11. **Clean State is Essential**: Não salvar dados temporários no estado mantém a arquitetura limpa
12. **Error Handling Must be Comprehensive**: Recovery automático evita estados corrompidos
13. **Testing Framework Centralized**: Sistema de testes centralizado facilita CI/CD

### Problemas Críticos Resolvidos V3

- **🐛 Tree Visualization Bug**: Árvore final agora mostra corretamente todos steps executados como verdes
- **🔒 Dependency Violations**: Strict Graph Executor previne 100% das violações de dependência
- **💥 Action Cascade Issues**: Transition loop executa actions de forma mais eficiente
- **📝 Validation Feedback**: Mensagens de erro Pydantic são claras e acionáveis
- **🧹 State Pollution**: execution_tree_complete não polui mais o estado persistente
