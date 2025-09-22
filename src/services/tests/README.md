# Multi-Step Service Framework - Tests

Estrutura centralizada de testes para o framework Multi-Step Service V3.

## Estrutura

```
tests/
├── README.md                 # Este arquivo
├── run.py                   # Runner centralizado (OBRIGATÓRIO)
├── test_v3_framework.py     # Testes do framework V3
└── [outros arquivos de teste...]
```

## Como Executar Testes

**⚠️ IMPORTANTE**: Todos os testes devem ser executados através do `run.py`. É proibido executar código Python diretamente via bash.

### Execução Centralizada (Comando Único)

```bash
# ÚNICO comando permitido:
python src/services/tests/run.py
```

### Configuração de Testes

Para escolher quais testes rodar, **edite o arquivo `run.py`** e altere as variáveis de configuração:

```python
# Configuração principal
TEST_MODE = "v3_framework"  # Opções: "v3_framework", "all", "specific_test"

# Para testes específicos
SPECIFIC_TESTS = {
    "instantiation": True,     # Test V3 service instantiation  
    "strict_executor": False,  # Desabilitado
    "pydantic": True,         # Test Pydantic validation
    "error_handling": False,  # Desabilitado
    "transition_loop": True,  # Test transition loop
}
```

### Testes Disponíveis

- **`v3_framework`**: Suite completa de testes do framework V3
  - Instanciação de serviços
  - Strict Graph Executor
  - Validação Pydantic
  - Tratamento de erros melhorado
  - Loop de transição (cascade actions)

## Adicionando Novos Testes

1. Crie um novo arquivo `test_[nome].py` na pasta tests
2. Implemente uma função `run_all_tests()` que retorna `True/False`
3. Adicione a importação e chamada no `run.py`
4. Use **imports absolutos** obrigatoriamente (ex: `from src.services.tool import multi_step_service`)

### Exemplo de Estrutura de Teste

```python
# test_exemplo.py
from src.services.tool import multi_step_service  # Import absoluto obrigatório

def test_funcionalidade_1():
    \"\"\"Testa funcionalidade específica\"\"\"
    # implementação do teste
    pass

def run_all_tests():
    \"\"\"Executa todos os testes deste módulo\"\"\"
    try:
        test_funcionalidade_1()
        print("✅ Todos os testes passaram!")
        return True
    except Exception as e:
        print(f"❌ Teste falhou: {str(e)}")
        return False
```

## Padrões e Convenções

- **Imports absolutos obrigatórios**: `from src.services.xxx import yyy`
- **Sem execução direta via bash**: Use sempre o `run.py`
- **Retorno booleano**: Funções de teste devem retornar `True/False`
- **Logging claro**: Use emojis e mensagens descritivas
- **Tratamento de exceções**: Capture e reporte erros adequadamente

## Framework V3 - Funcionalidades Testadas

### 🔒 Strict Graph Executor
- Validação rigorosa de dependências
- Prevenção de "salto de etapas"
- Processamento apenas de campos válidos

### 🛡️ Validação Pydantic
- Type-safe payload validation
- Schemas automáticos via models
- Feedback de validação melhorado

### 🔄 Enhanced Error Handling
- Mensagens de erro construtivas
- Sugestões de recuperação
- Choices válidos em caso de erro

### ⚡ Transition Loop
- Execução em cascata de actions
- Controle de fluxo via ExecutionResult
- Processamento automático de next_steps