# Services Framework

## Visão Geral

Este é um framework de execução de fluxos de serviços multi-step projetado para ser usado como ferramenta por agentes de IA. O framework permite a criação de fluxos complexos com dependências condicionais, coleta de dados hierárquica e persistência de estado.

## Arquitetura

### Componentes Principais

#### 1. **Core Components** (`src/services/core/`)

- **`base_service.py`**: Classe abstrata que define a interface padrão para todos os serviços
- **`orchestrator.py`**: O "cérebro" do framework, responsável por orquestrar a execução dos fluxos
- **`state.py`**: Gerenciador de estado persistente com suporte a notação de pontos
- **`response_generator.py`**: Gerador de respostas estruturadas para o agente
- **`evaluator.py`**: Avaliador seguro de condições usando JMESPath

#### 2. **Schema Models** (`src/services/schema/`)

- **`models.py`**: Define todas as estruturas de dados usando Pydantic
  - `StepInfo`: Definição de um passo no fluxo
  - `ServiceDefinition`: Blueprint completo de um serviço
  - `AgentResponse`: Resposta estruturada para o agente
  - `ExecutionResult`: Resultado da execução de ações

#### 3. **Repository** (`src/services/repository/`)

- **`bank_account_service.py`**: Exemplo de implementação de serviço bancário

#### 4. **Tool Interface** (`src/services/tool.py`)

- Interface principal que expõe o framework como ferramenta LangChain
- Registro de serviços disponíveis
- Função `multi_step_service` para execução

## Funcionalidades Principais

### 1. **Fluxos Multi-Step com Dependências**

```python
StepInfo(
    name="account_type",
    description="What type of account would you like to open?",
    depends_on=["user_info"],  # Depende da conclusão do step user_info
    condition='_internal.outcomes.check_account == "ACCOUNT_NOT_FOUND"'
)
```

### 2. **Hierarquia de Steps (Substeps)**

```python
StepInfo(
    name="user_info",
    description="Collect basic user information.",
    substeps=[
        StepInfo(name="user_info.name", description="Please provide your full name."),
        StepInfo(name="user_info.email", description="What is your email address?")
    ]
)
```

### 3. **Condições Dinâmicas**

O framework suporta condições baseadas no estado usando JMESPath:
- Resultados de ações: `_internal.outcomes.check_account == "ACCOUNT_FOUND"`
- Dados do usuário: `data.ask_next_action.next_action == "balance"`

### 4. **Persistência de Estado**

- Estado persistido automaticamente em arquivos JSON
- Suporte a múltiplos usuários simultâneos
- Recuperação automática de estado entre sessões

### 5. **Execução de Ações**

```python
def _check_account_exists(self, state: Dict[str, Any]) -> ExecutionResult:
    return ExecutionResult(
        success=True,
        outcome="ACCOUNT_EXISTS",
        updated_data={"account_found": True}
    )
```

### 6. **Visualização de Progresso**

O framework gera automaticamente uma árvore ASCII mostrando o progresso:

```
🌳 EXECUTION GRAPH:
├── 🟢 user_info
├── 🟢 check_account
├── 🟢 account_type [deps: check_account; if: '_internal.outcomes.check_account == "ACCOUNT_NOT_FOUND"']
├── 🟡 initial_deposit [deps: account_type]   <-- CURRENT
```

## Como Usar

### 1. **Definindo um Serviço**

```python
class MyService(BaseService):
    service_name = "my_service"
    description = "Description of my service"
    
    def get_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description=self.description,
            steps=[
                StepInfo(
                    name="collect_data",
                    description="Please provide your information",
                    payload_schema={
                        "type": "object",
                        "properties": {"name": {"type": "string"}}
                    }
                )
            ]
        )
```

### 2. **Registrando o Serviço**

```python
# Em tool.py
_service_classes = [MyService, BankAccountService]
```

### 3. **Usando a Ferramenta**

```python
from src.services.tool import multi_step_service

response = multi_step_service(
    service_name="my_service",
    user_id="user123",
    payload={"name": "João Silva"}
)
```

## Pontos Fortes

### ✅ **Flexibilidade e Extensibilidade**
- Arquitetura modular permite fácil adição de novos serviços
- Suporte a fluxos complexos com ramificações condicionais
- Hierarquia de steps permite organização estruturada

### ✅ **Gerenciamento de Estado Robusto**
- Persistência automática entre sessões
- Suporte a múltiplos usuários
- Notação de pontos para acesso a dados aninhados

### ✅ **Segurança**
- Avaliação segura de condições sem uso de `eval()`
- Validação de dados usando Pydantic schemas
- Isolamento de estado por usuário

### ✅ **Experiência do Desenvolvedor**
- Código bem estruturado e documentado
- Visualização clara do progresso com árvores ASCII
- Interface consistente entre serviços

### ✅ **Integração com Agentes IA**
- Exposição como ferramenta LangChain
- Respostas estruturadas e consistentes
- Schema dinâmico para validação de payload

## Pontos Fracos

### ❌ **Complexidade de Configuração**
- Definição de serviços requer conhecimento profundo da estrutura
- Curva de aprendizado elevada para novos desenvolvedores
- Configuração de dependências e condições pode ser propensa a erros

### ❌ **Limitações de Escalabilidade**
- Persistência em arquivos JSON não é adequada para produção
- Falta de mecanismos de cache ou otimização
- Não há suporte a transações ou rollback

### ❌ **Tratamento de Erros**
- Falta de estratégias de retry ou recuperação
- Logs limitados para debugging
- Não há validação de integridade de dependências

### ❌ **Funcionalidades Limitadas**
- Não suporta execução paralela de steps
- Falta de timeouts ou limites de execução
- Não há suporte a webhooks ou notificações

### ❌ **Testes e Documentação**
- Cobertura de testes limitada
- Documentação de API incompleta
- Falta de exemplos práticos para casos complexos

## Sugestões de Melhorias

### 🚀 **Curto Prazo (1-2 sprints)**

1. **Melhorar Documentação**
   - Adicionar exemplos práticos para cada funcionalidade
   - Documentar padrões de design recomendados
   - Criar guia de migração e troubleshooting

2. **Validação e Testes**
   - Implementar validação de dependências circulares
   - Adicionar testes unitários abrangentes
   - Criar testes de integração end-to-end

3. **Logging e Debugging**
   - Adicionar sistema de logging estruturado
   - Implementar rastreamento de execução
   - Melhorar mensagens de erro

### 🎯 **Médio Prazo (3-6 sprints)**

4. **Persistência Robusta**
   - Migrar para banco de dados (Redis/PostgreSQL)
   - Implementar controle de versão de estado
   - Adicionar backup e recuperação automática

5. **Performance e Escalabilidade**
   - Implementar cache inteligente
   - Otimizar algoritmos de resolução de dependências
   - Adicionar métricas de performance

6. **Funcionalidades Avançadas**
   - Suporte a execução paralela de steps independentes
   - Sistema de plugins para extensões
   - Integração com sistemas de workflow externos

### 🌟 **Longo Prazo (6+ sprints)**

7. **Ferramentas de Desenvolvimento**
   - Editor visual para criação de fluxos
   - Debugger interativo para execução
   - Dashboard de monitoramento em tempo real

8. **Recursos Empresariais**
   - Controle de acesso e permissões
   - Auditoria completa de execuções
   - API REST para integração externa

9. **IA e Automação**
   - Auto-geração de steps baseada em requisitos
   - Otimização automática de fluxos
   - Predição de falhas e auto-recuperação

## Exemplos de Uso

### Exemplo 1: Fluxo Bancário Simples

```python
# Iniciar serviço
response = multi_step_service("bank_account_opening", "user123", {})

# Fornecer informações do usuário
response = multi_step_service("bank_account_opening", "user123", {
    "user_info.name": "João Silva",
    "user_info.email": "joao@email.com"
})

# Escolher tipo de conta
response = multi_step_service("bank_account_opening", "user123", {
    "account_type": "savings"
})

# Depósito inicial
response = multi_step_service("bank_account_opening", "user123", {
    "initial_deposit": 1000
})
```

### Exemplo 2: Verificação de Estado

```python
# Verificar estado atual sem enviar dados
response = multi_step_service("bank_account_opening", "user123", {})

print(f"Status: {response['status']}")
print(f"Próximo passo: {response['next_step_info']['step_name']}")
print(f"Dados atuais: {response['current_data']}")
```

## Conclusão

O Services Framework é uma solução robusta e bem estruturada para execução de fluxos multi-step. Sua arquitetura modular e flexível permite a criação de serviços complexos com facilidade. Embora existam oportunidades de melhoria, especialmente em escalabilidade e ferramentas de desenvolvimento, o framework já oferece uma base sólida para integração com agentes de IA.

A implementação atual é adequada para prototipagem e casos de uso de média complexidade, mas recomenda-se investir nas melhorias sugeridas para uso em produção.