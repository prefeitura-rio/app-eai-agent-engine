# Multi-Step Services Framework

## Visão Geral

Framework modular para criação de serviços multi-step com dependências, validação automática e persistência de estado. Desenvolvido para integração com LangChain e preparado para migração para Model Context Protocol (MCP).

## Arquitetura

### 🏗️ Estrutura do Framework

```
src/services/
├── __init__.py              # Exports e registry principal
├── base_service.py          # Classe base abstrata
├── tool.py                  # Tool LangChain com injeção de dependência
├── state.py                 # Gerenciamento de estado/persistência
├── repository/              # Implementações de serviços
│   ├── data_collection.py   # Serviço simples (exemplo)
│   ├── bank_account.py      # Serviço com dependências
│   └── bank_account_advanced.py  # Serviço híbrido com substeps
├── schema/                  # Sistema de esquemas modular
│   ├── step_info.py         # Definição de steps
│   ├── service_definition.py # Definição completa do serviço
│   ├── dependency_engine.py # Gerenciamento de dependências
│   ├── validation.py        # Engine de validação
│   └── visualization.py     # Engine de visualização
└── tests.py                 # Testes completos
```

### 🎯 Princípios de Design

1. **Single Source of Truth**: `ServiceDefinition` é a única fonte de configuração
2. **Separation of Concerns**: Engines especializados para diferentes responsabilidades
3. **Dependency Injection**: Registry dinâmico de serviços
4. **Estado Transparente**: Persistência automática e recuperação de estado
5. **Schema Dinâmico**: Contexto baseado no estado atual

## Conceitos Fundamentais

### StepInfo - Definição de Steps

```python
from src.services.schema import StepInfo

step = StepInfo(
    name="document_type",
    description="Tipo de documento (CPF ou CNPJ)",
    payload_example={"document_type": "CPF"},
    required=True,
    data_type="str",  # "str", "dict", "list_dict"
    depends_on=["prerequisite_step"]
)
```

**Tipos de Dados:**
- `str`: String simples
- `dict`: Objeto JSON 
- `list_dict`: Array de objetos (modo append automático)

### ServiceDefinition - Configuração Completa

```python
from src.services.schema import ServiceDefinition, StepInfo

definition = ServiceDefinition(
    service_name="my_service",
    description="Descrição do serviço",
    steps=[
        StepInfo(name="step1", description="Primeiro step", payload_example={"step1": "value"}),
        StepInfo(name="step2", description="Segundo step", depends_on=["step1"])
    ]
)
```

### BaseService - Implementação

```python
from src.services.base_service import BaseService

class MyService(BaseService):
    service_name = "my_service"  # Obrigatório
    
    def get_service_definition(self) -> ServiceDefinition:
        return ServiceDefinition(...)
    
    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        # Validação específica do step
        return True, ""  # (is_valid, error_message)
    
    def get_completion_message(self) -> str:
        return "Serviço completado com sucesso!"
```

## Funcionalidades Avançadas

### 🔄 Sistema de Dependências

```python
StepInfo(
    name="document_number",
    depends_on=["document_type"],  # Só disponível após document_type
    # ...
)
```

**Comportamento:**
- Steps só ficam disponíveis quando dependências são satisfeitas
- Validação automática em tempo real
- Processamento em ordem topológica

### 🎭 Substeps (Híbrido)

Para steps complexos com múltiplos campos:

```python
StepInfo(
    name="user_info",
    data_type="dict",
    substeps=[
        StepInfo(name="name", description="Nome completo", required=True),
        StepInfo(name="email", description="E-mail", required=True),
        StepInfo(name="phone", description="Telefone", required=False)
    ]
)
```

**Uso pelo Agente:**
```json
// Substeps individuais
{"name": "João Silva"}
{"email": "joao@email.com"}

// OU JSON completo
{"user_info": {"name": "João Silva", "email": "joao@email.com", "phone": "123456789"}}
```

### 📦 Arrays com Append Automático

```python
StepInfo(
    name="deposits",
    data_type="list_dict",  # Detecta append automaticamente
    payload_example={"deposits": [{"amount": 1000, "date": "2024-01-01"}]}
)
```

**Comportamento:**
- Primeiro payload: inicializa array
- Payloads subsequentes: append automático
- Suporta objeto único ou array de objetos

### 🎨 Visualização de Estado

```python
# Estado visual ASCII
result["visual_schematic"]  # Árvore de dependências e progresso

# Análise estruturada
result["available_steps"]   # Steps disponíveis
result["completed_steps"]   # Steps completados  
result["required_steps"]    # Steps obrigatórios pendentes
result["optional_steps"]    # Steps opcionais disponíveis
```

### 💾 Persistência Automática

```python
# Estados salvos automaticamente em service_states/
# Formato: {user_id}__{service_name}.json

{
  "service_class": "DataCollectionService",
  "service_name": "data_collection", 
  "user_id": "agent",
  "data": {"cpf": "12345678901", "email": "test@email.com"},
  "created_at": "2024-01-01T10:00:00",
  "last_updated": "2024-01-01T10:05:00"
}
```

## Uso Prático

### 🚀 Uso Básico

```python
from src.services import multi_step_service

# Início do serviço
result = multi_step_service.invoke({
    "service_name": "data_collection",
    "payload": {},  # Payload vazio para ver estado inicial
    "user_id": "agent"
})

# Enviar dados
result = multi_step_service.invoke({
    "service_name": "data_collection", 
    "payload": {"cpf": "12345678901", "email": "test@email.com"},
    "user_id": "agent"
})
```

### 📋 Schema Dinâmico

O framework gera automaticamente schemas JSON baseados no estado atual:

```python
# Schema retornado
{
    "type": "object",
    "properties": {
        "cpf": {
            "description": "CPF do usuário",
            "data_type": "str",
            "payload_example": {"cpf": "12345678901"}
        }
    },
    "required": ["cpf"]
}
```

### 🔍 Monitoramento de Progresso

```python
# Resposta estruturada
{
    "status": "progress",           # ready, progress, completed, validation_error
    "service_name": "data_collection",
    "current_data": {...},          # Dados atuais
    "available_steps": [...],       # Steps disponíveis
    "completed_steps": [...],       # Steps já completados
    "next_steps_schema": {...},     # Schema dinâmico
    "visual_schematic": "..."       # Visualização ASCII
}
```

## Exemplos de Serviços

### 📝 Serviço Simples

```python
# src/services/repository/data_collection.py
class DataCollectionService(BaseService):
    service_name = "data_collection"
    
    def get_service_definition(self):
        return ServiceDefinition(
            service_name=self.service_name,
            description="Coleta de dados pessoais",
            steps=[
                StepInfo(name="cpf", description="CPF", payload_example={"cpf": "12345678901"}),
                StepInfo(name="email", description="E-mail", payload_example={"email": "test@email.com"}),
                StepInfo(name="name", description="Nome", payload_example={"name": "João Silva"})
            ]
        )
```

### 🏦 Serviço com Dependências

```python
# src/services/repository/bank_account.py  
class BankAccountService(BaseService):
    service_name = "bank_account"
    
    def get_service_definition(self):
        return ServiceDefinition(
            service_name=self.service_name,
            description="Criação de conta bancária com dependências",
            steps=[
                StepInfo(name="document_type", description="Tipo documento"),
                StepInfo(name="document_number", depends_on=["document_type"]),
                StepInfo(name="account_type", description="Tipo da conta"),
                StepInfo(name="initial_deposit", depends_on=["account_type"], required=False),
                # ...
            ]
        )
```

### 🏗️ Serviço Híbrido Avançado

```python
# src/services/repository/bank_account_advanced.py
class BankAccountAdvancedService(BaseService):
    service_name = "bank_account_advanced"
    
    def get_service_definition(self):
        return ServiceDefinition(
            service_name=self.service_name, 
            description="Conta bancária com dados estruturados",
            steps=[
                # Step com substeps
                StepInfo(
                    name="user_info",
                    data_type="dict",
                    substeps=[
                        StepInfo(name="name", required=True),
                        StepInfo(name="email", required=True),
                        # ...
                    ]
                ),
                # Steps JSON simples
                StepInfo(name="account_info", data_type="dict"),
                StepInfo(name="address", data_type="dict"),
                # Array com append
                StepInfo(name="deposits", data_type="list_dict", required=False)
            ]
        )
```

## Registry e Extensibilidade

### 📚 Registry Automático

```python
# src/services/__init__.py
from src.services.base_service import build_service_registry

SERVICE_REGISTRY = build_service_registry(
    DataCollectionService,
    BankAccountService, 
    BankAccountAdvancedService,
)

# Tool criado automaticamente
multi_step_service = create_multi_step_service_tool(SERVICE_REGISTRY)
```

### ➕ Adicionando Novos Serviços

1. **Criar classe de serviço:**
```python
class NewService(BaseService):
    service_name = "new_service"
    
    def get_service_definition(self):
        # Definir steps...
    
    def execute_step(self, step, payload):
        # Implementar validação...
```

2. **Registrar no framework:**
```python
# Adicionar ao SERVICE_REGISTRY em __init__.py
SERVICE_REGISTRY = build_service_registry(
    DataCollectionService,
    BankAccountService,
    NewService,  # ← Novo serviço
)
```

## Engines Especializados

### 🔗 DependencyEngine
**Responsabilidade:** Gerenciamento de dependências e ordem de processamento
```python
engine.get_available_steps(completed_data)
engine.validate_dependencies(step_name, completed_data) 
engine.get_processing_order(steps)
```

### ✅ ValidationEngine  
**Responsabilidade:** Processamento bulk e validação
```python
engine.process_bulk_data(payload, service_executor)
```

### 📊 VisualizationEngine
**Responsabilidade:** Visualizações e análises de estado
```python
engine.get_visual_schematic(completed_data)
engine.get_state_analysis(completed_data)
```

## Testes

### 🧪 Executar Testes

```bash
# Testes completos
python src/services/tests.py

# Ou via pytest
pytest src/services/tests.py -v
```

### 📝 Cobertura de Testes

- ✅ Funcionalidade básica de serviços
- ✅ Sistema de dependências
- ✅ Validação de dados
- ✅ Persistência de estado
- ✅ Substeps e arrays
- ✅ Casos de erro
- ✅ Registry dinâmico

## Arquitetura Técnica

### 🏛️ Padrões Utilizados

- **Factory Pattern**: `create_multi_step_service_tool()`
- **Strategy Pattern**: Engines especializados
- **Registry Pattern**: `SERVICE_REGISTRY`
- **Template Method**: `BaseService`
- **Dependency Injection**: Tool factory

### 🎯 Características Técnicas

- **Type Safety**: Pydantic models com validação
- **Modular**: Engines independentes
- **Testável**: 100% cobertura de testes
- **Extensível**: Registry dinâmico
- **Performático**: Schemas cacheados
- **Resiliente**: Tratamento robusto de erros

## Migração MCP

### 🚀 Preparação para MCP

O framework foi projetado para migração direta para Model Context Protocol:

1. **Isolamento**: Dependências mínimas (Pydantic + LangChain core)
2. **Auto-contido**: Estado gerenciado internamente
3. **Tool Interface**: Interface padronizada
4. **Registry**: Serviços registrados dinamicamente

### 📦 Estrutura Migratória

```python
# Atual (LangChain)
from langchain_core.tools import tool

# Futuro (MCP)
from mcp_server.tools import tool  # Adaptação mínima necessária
```

## Melhorias Futuras

### 🔮 Roadmap

- [ ] **Webhooks**: Notificações de mudança de estado
- [ ] **Métricas**: Coleta de estatísticas de uso
- [ ] **Cache**: Sistema de cache para definitions
- [ ] **Backup**: Backup automático de estados
- [ ] **Monitoring**: Dashboard de monitoramento
- [ ] **API REST**: Interface HTTP opcional

### 🎨 Funcionalidades Avançadas

- [ ] **Conditional Steps**: Steps condicionais baseados em dados
- [ ] **Parallel Steps**: Processamento paralelo de steps independentes
- [ ] **Step Templates**: Templates reutilizáveis de steps
- [ ] **Dynamic Validation**: Validações baseadas em rules engine
- [ ] **Workflow Builder**: Interface visual para criação de workflows

---

## 📖 Documentação Adicional

- [**API Reference**](src/services/schema/) - Documentação detalhada das classes
- [**Examples**](src/services/repository/) - Exemplos de implementação
- [**Tests**](src/services/tests.py) - Casos de teste abrangentes

## 🤝 Contribuição

Para adicionar novos serviços ou melhorar o framework:

1. Implementar `BaseService`
2. Adicionar ao `SERVICE_REGISTRY`
3. Criar testes correspondentes
4. Atualizar documentação

---

**Framework Multi-Step Services** - Versão simplificada e robusta para produção ✨