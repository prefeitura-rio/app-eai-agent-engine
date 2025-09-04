# 🏛️ EAI Agent Engine - Prefeitura do Rio

Assistente Inteligente da Prefeitura do Rio de Janeiro com duas abordagens para comparação UX.

## 🎯 Objetivo

Comparar duas abordagens diferentes para o assistente:
- **🤖 Service Agent**: Roteamento inteligente para agentes especializados
- **📋 Workflow**: Fluxos estruturados step-by-step

## 🚀 Para a Equipe UX

**Todos os arquivos de teste estão organizados na pasta `teste_ux/`:**

```bash
cd teste_ux
uv run ux_test_selector.py
```

A pasta `teste_ux/` contém:
- 🎯 **Seletor interativo** para escolher qual abordagem testar
- 🤖 **Service Agent** - Teste da abordagem conversacional  
- ⚡ **Workflow** - Teste da abordagem estruturada
- 📖 **Guias completos** com critérios de avaliação UX

# Teste Workflow  
uv run test_workflow_ux.py
```

## 📋 Para o Pessoal de UX

1. **Execute**: `uv run ux_test_selector.py`
2. **Escolha** uma abordagem para testar
3. **Avalie** a experiência do usuário
4. **Compare** as duas abordagens
5. **Documente** suas observações

### Cenários de Teste Essenciais
- **Identificação**: "Oi, quero me identificar. Meu CPF é 111.444.777-35"
- **Validação**: "Meu CPF é 111.444.777-99" (CPF inválido)
- **Serviços**: "Preciso de ajuda com IPTU"

## 📊 Diferenças Principais

| Aspecto | Service Agent | Workflow |
|---------|---------------|----------|
| **Conversa** | Mais natural | Mais estruturada |
| **Performance** | ~15.1s | ~14.5s (4.4% mais rápido) |
| **Uso** | Chat livre | Processos organizados |
| **Flexibilidade** | Alta | Média |

## 🛠️ Configuração

```bash
# Instalar dependências
uv sync

# Configurar variáveis de ambiente (se necessário)
cp .env.example .env
```

## 📚 Documentação

- **[UX_TEST_GUIDE.md](UX_TEST_GUIDE.md)**: Guia completo para testes UX
- **engine/**: Código dos agentes e workflows
- **src/**: Ferramentas e configurações

## 🎯 Decisão Final

**A escolha entre Service Agent e Workflow deve ser baseada na experiência do usuário!**

Os dados técnicos mostram que Workflow é mais eficiente, mas a experiência do cidadão é o que realmente importa.
