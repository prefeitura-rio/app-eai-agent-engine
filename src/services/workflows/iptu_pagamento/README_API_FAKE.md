# API Fake para Testes - IPTU Workflow

Este documento explica como usar a API fake para realizar testes completos do workflow IPTU com diferentes cenários mockados.

## Visão Geral

Foi criado o arquivo `api_service_fake.py` que implementa a mesma interface do `api_service.py` real, porém retorna dados mockados. Isso permite testar todos os cenários possíveis de forma controlada e previsível.

## Como Usar

### 1. Configuração no Workflow

O workflow pode ser inicializado para usar a API fake:

```python
# API real (padrão)
workflow = IPTUWorkflow()

# API fake para testes
workflow = IPTUWorkflow(use_fake_api=True)
```

### 2. Cenários de Teste Disponíveis

#### Inscrições com Dados Mockados:

| Inscrição | Cenário | Guias Disponíveis |
|-----------|---------|-------------------|
| `01234567890123` | Padrão completo | IPTU (R$ 2.878,00) + Taxa de Lixo (R$ 520,00) |
| `11111111111111` | Apenas IPTU | IPTU (R$ 1.500,00) |
| `22222222222222` | Apenas Taxa | Taxa de Lixo (R$ 320,00) |
| `33333333333333` | Todas quitadas | Nenhuma (filtradas por estar quitadas) |
| `44444444444444` | IPTU alto | IPTU (R$ 8.500,00) - teste desconto |
| `55555555555555` | IPTU baixo | IPTU (R$ 180,00) |
| Qualquer outra | Não encontrada | Nenhuma |

#### Anos Válidos:
- **2020 a 2025**: Retorna dados conforme inscrição
- **Fora do range**: Nenhuma guia encontrada

#### Cotas Mockadas:

**Para IPTU (Guia 00):**
- 32 cotas de R$ 89,44 (inscrição padrão) ou valores proporcionais
- Cotas 01-03: PAGAS
- Cotas 04-25: EM ABERTO
- Cotas 26-32: VENCIDAS

**Para Taxa de Lixo (Guia 01):**
- 6 cotas de R$ 86,67 (inscrição padrão) ou valores proporcionais
- Todas EM ABERTO

### 3. Exemplo de Uso Prático

```python
from src.services.workflows.iptu_pagamento.iptu_workflow import IPTUWorkflow

# Teste com dados mockados
workflow = IPTUWorkflow(use_fake_api=True)

# Simular consulta com sucesso
state = ServiceState(
    user_id="test_user",
    service_name="iptu_pagamento",
    data={},
    payload={
        "inscricao_imobiliaria": "01234567890123",
        "ano_exercicio": 2024
    }
)

result = workflow.execute(state, state.payload)
# Resultado: encontrará IPTU + Taxa de Lixo

# Simular inscrição não encontrada
state.payload = {
    "inscricao_imobiliaria": "99999999999999",
    "ano_exercicio": 2024
}

result = workflow.execute(state, state.payload)
# Resultado: nenhuma guia encontrada, solicitará nova inscrição
```

### 4. Executar Testes

Para ver todos os cenários em ação:

```bash
python src/services/workflows/iptu_pagamento/test_fake_api.py
```

## Vantagens da API Fake

1. **Testes Determinísticos**: Sempre retorna os mesmos dados para as mesmas entradas
2. **Cobertura Completa**: Testa todos os cenários (sucesso, erro, edge cases)
3. **Sem Dependências Externas**: Não precisa de rede ou API real
4. **Desenvolvimento Offline**: Permite desenvolver sem acesso à API real
5. **Testes Automatizados**: Ideal para CI/CD e testes unitários

## Cenários Específicos de Teste

### Teste de Erro - Inscrição Não Encontrada
```python
guias = await api.consultar_guias("99999999999999", 2024)
assert guias is None
```

### Teste de Ano Inválido
```python
guias = await api.consultar_guias("01234567890123", 2019)
assert guias is None
```

### Teste de DARM Completo
```python
darm = await api.consultar_darm("01234567890123", 2024, "00", ["04", "05", "06"])
assert darm is not None
assert darm.darm.valor_numerico == 268.32
assert len(darm.darm.cotas) == 3
```

### Teste de PDF
```python
pdf = await api.download_pdf_darm("01234567890123", 2024, "00", ["04", "05"])
assert pdf is not None
assert pdf.startswith("JVBERi0x")  # PDF header em base64
```

## Migração entre APIs

Para trocar entre API real e fake, basta alterar o parâmetro no construtor:

```python
# Desenvolvimento/Testes
workflow = IPTUWorkflow(use_fake_api=True)

# Produção
workflow = IPTUWorkflow(use_fake_api=False)  # ou simplesmente IPTUWorkflow()
```

## Estrutura dos Dados Mockados

Todos os dados seguem exatamente a mesma estrutura da API real:

- **Guias**: Mesmos campos, formatos e tipos da API real
- **Cotas**: Estrutura idêntica com situações variadas
- **DARM**: Linha digitável e código de barras válidos
- **PDF**: Base64 de um PDF mínimo válido

Isso garante que os testes com a API fake sejam 100% compatíveis com a API real.