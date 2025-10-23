# Workflow IPTU - Prefeitura do Rio de Janeiro

Workflow para consulta e emissão de guias de IPTU da Prefeitura do Rio de Janeiro.

## 📋 Visão Geral

Este workflow implementa o fluxo completo de consulta de IPTU seguindo o fluxograma oficial da Prefeitura do Rio. Permite ao usuário:

- Consultar guias de IPTU por inscrição imobiliária
- Escolher ano de exercício fiscal
- Selecionar guias e cotas específicas para pagamento
- Gerar boletos (DARMs) únicos ou separados
- Continuar operações (mais cotas, outras guias, outro imóvel)

## 🗂️ Estrutura do Código

```
iptu_pagamento/
├── README.md                    # Este arquivo
├── iptu_workflow.py             # Workflow principal (StateGraph)
├── models.py                    # Modelos Pydantic para validação
├── constants.py                 # Constantes e valores mágicos
├── validators.py                # Funções de validação reutilizáveis
├── state_helpers.py             # Helpers para manipulação de state
├── payload_helpers.py           # Helpers para processamento de payloads
├── templates.py                 # Templates de mensagens ao usuário
├── api_service.py               # Cliente da API real da Prefeitura
├── api_service_fake.py          # Mock da API para testes
├── utils.py                     # Utilidades gerais
├── test_iptu_workflow.py        # Testes completos do workflow
└── test_helpers.py              # Fixtures e helpers para testes
```

## 🚀 Quick Start

### Uso Básico

```python
from src.services.tool import multi_step_service

# Iniciar workflow
response = multi_step_service.invoke({
    "service_name": "iptu_pagamento",
    "user_id": "user_123",
    "payload": {"inscricao_imobiliaria": "01234567890123"}
})

# Continuar com próxima etapa
response = multi_step_service.invoke({
    "service_name": "iptu_pagamento",
    "user_id": "user_123",
    "payload": {"ano_exercicio": 2025}
})
```

### Uso com API Fake (Testes)

```python
import os

# Configurar para usar API fake
os.environ["IPTU_USE_FAKE_API"] = "true"

# Agora o workflow usará dados mockados
response = multi_step_service.invoke({...})
```

## 📊 Fluxo do Workflow

```
1. Informar Inscrição Imobiliária
   ↓
2. Escolher Ano de Exercício (2020-2025)
   ↓
3. Consultar Guias Disponíveis
   ↓
4. Escolher Guia (00, 01, 02...)
   ↓
5. Consultar Cotas da Guia
   ↓
6. Escolher Cotas a Pagar
   ↓
7. Escolher Formato do DARM (único ou separado)
   ↓
8. Confirmar Dados
   ↓
9. Gerar DARM(s)
   ↓
10. Quer pagar mais cotas da mesma guia? → Volta para 6
    Quer pagar outras guias do mesmo imóvel? → Volta para 4
    Quer emitir guia para outro imóvel? → Volta para 1
    Não quer mais nada? → Finaliza
```

## 🧪 Testes

### Executar Todos os Testes

```bash
pytest src/services/workflows/iptu_pagamento/test_iptu_workflow.py -v
```

### Executar Teste Específico

```bash
pytest src/services/workflows/iptu_pagamento/test_iptu_workflow.py::TestIPTUWorkflowHappyPath::test_fluxo_completo_cota_unica -v
```

### Cobertura de Testes

Os testes cobrem:

- ✅ Fluxos completos (happy paths)
- ✅ Validações de entrada
- ✅ Erros e edge cases
- ✅ Continuidade (mais cotas, outras guias, outro imóvel)
- ✅ Reset de estado
- ✅ Diferentes combinações de guias e cotas

## 🛠️ Desenvolvimento

### Adicionar Nova Validação

1. Adicione a constante em `constants.py`:
```python
NOVO_LIMITE = 100
```

2. Crie a função de validação em `validators.py`:
```python
def validar_novo_campo(valor: int) -> int:
    if valor > NOVO_LIMITE:
        raise ValueError(f"Valor deve ser <= {NOVO_LIMITE}")
    return valor
```

3. Use no Pydantic model em `models.py`:
```python
from src.services.workflows.iptu_pagamento.validators import validar_novo_campo

class NovoPayload(BaseModel):
    campo: int

    @field_validator("campo")
    @classmethod
    def validate_campo(cls, v: int) -> int:
        return validar_novo_campo(v)
```

### Adicionar Novo Nó ao Workflow

1. Crie o método do nó em `iptu_workflow.py`:
```python
@handle_errors
def _meu_novo_no(self, state: ServiceState) -> ServiceState:
    """Descrição do que este nó faz."""
    # Lógica do nó
    return state
```

2. Adicione ao grafo em `build_graph()`:
```python
graph.add_node("meu_novo_no", self._meu_novo_no)
```

3. Conecte com edges:
```python
graph.add_edge("no_anterior", "meu_novo_no")
graph.add_edge("meu_novo_no", "proximo_no")
```

### Adicionar Novos Templates de Mensagem

Em `templates.py`:

```python
@staticmethod
def nova_mensagem(param1: str, param2: int) -> str:
    """Template para nova mensagem."""
    return f"""
    # Nova Mensagem

    Param1: {param1}
    Param2: {param2}
    """
```

## 📝 Constantes Importantes

### Validação

```python
ANO_MIN_VALIDO = 2020          # Ano mínimo válido
ANO_MAX_VALIDO = 2025          # Ano máximo válido
INSCRICAO_MIN_LENGTH = 8       # Tamanho mínimo da inscrição
INSCRICAO_MAX_LENGTH = 15      # Tamanho máximo da inscrição
MAX_TENTATIVAS_ANO = 3         # Máximo de tentativas antes de pedir nova inscrição
```

### Chaves de State

```python
STATE_IS_DATA_CONFIRMED = "is_data_confirmed"
STATE_WANTS_MORE_QUOTAS = "wants_more_quotas"
STATE_WANTS_OTHER_GUIAS = "wants_other_guias"
STATE_WANTS_OTHER_PROPERTY = "wants_other_property"
STATE_HAS_CONSULTED_GUIAS = "has_consulted_guias"
STATE_USE_SEPARATE_DARM = "use_separate_darm"
STATE_IS_SINGLE_QUOTA_FLOW = "is_single_quota_flow"
```

## 🔧 Helpers Disponíveis

### State Helpers

```python
from src.services.workflows.iptu_pagamento import state_helpers

# Validar dados obrigatórios
campo_faltante = state_helpers.validar_dados_obrigatorios(
    state,
    ["inscricao_imobiliaria", "ano_exercicio"]
)

# Reset completo ou seletivo
state_helpers.reset_completo(state, manter_inscricao=True)

# Reset para seleção de cotas
state_helpers.reset_para_selecao_cotas(state)
```

### Payload Helpers

```python
from src.services.workflows.iptu_pagamento import payload_helpers

# Processar payload simples
sucesso = payload_helpers.processar_payload_simples(
    state,
    campo_payload="ano_exercicio",
    campo_destino="ano_exercicio",
    modelo_pydantic=EscolhaAnoPayload,
    usar_internal=False
)
```

### Test Helpers

```python
from src.services.workflows.iptu_pagamento.test_helpers import *

# Setup/Teardown
setup_fake_api()
teardown_fake_api()

# Gerar payloads
payload = criar_payload_inscricao("01234567890123")
payload = criar_payload_ano(2025)
payload = criar_payload_confirmacao(True)

# Verificações
assert verificar_response_sem_erro(response)
assert verificar_response_tem_schema(response)
```

## 🐛 Debug

### Ativar Logs Detalhados

O workflow usa `loguru` para logging estruturado:

```python
from loguru import logger

logger.debug("Mensagem de debug detalhada")
logger.info("Informação importante")
logger.warning("Aviso")
logger.error("Erro")
```

### Inspecionar State

```python
# No código do workflow
logger.debug(f"State.data: {state.data}")
logger.debug(f"State.internal: {state.internal}")
logger.debug(f"State.payload: {state.payload}")
```

## 📖 Referências

- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)
- [Pydantic Validation](https://docs.pydantic.dev/latest/concepts/validators/)
- [API Prefeitura do Rio](https://api.dados.rio/) (documentação oficial)

## 🤝 Contribuindo

Ao contribuir para este workflow:

1. **Siga as convenções de nomenclatura**:
   - Constantes: `UPPER_SNAKE_CASE`
   - Funções/métodos: `snake_case`
   - Classes: `PascalCase`
   - State keys: prefixos padronizados (`is_`, `has_`, `wants_`)

2. **Adicione testes** para qualquer novo código

3. **Documente** usando docstrings com:
   - Descrição do que faz
   - Args com tipos
   - Returns com tipo
   - Examples quando útil

4. **Use type hints** em todas as funções

5. **Extraia magic values** para `constants.py`

## 📄 Licença

Este código é parte do projeto app-eai-agent-goole-engine.
