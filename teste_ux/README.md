# 🎯 Testes UX - Comparação de Abordagens

Esta pasta contém todos os arquivos necessários para a equipe de UX avaliar e comparar as duas abordagens implementadas: **Service Agent** vs **Workflow**.

## 🚀 Como Usar

**Comando principal:**
```bash
cd teste_ux
uv run ux_test_selector.py
```

## 📁 Arquivos Incluídos

| Arquivo | Descrição |
|---------|-----------|
| `ux_test_selector.py` | 🎯 **ENTRADA PRINCIPAL** - Menu interativo para escolher qual abordagem testar |
| `test_service_agent_ux.py` | 🤖 Teste interativo do Service Agent |
| `test_workflow_ux.py` | ⚡ Teste interativo do Workflow |
| `UX_TEST_GUIDE.md` | 📖 Guia completo com critérios de avaliação UX |
| `QUICK_START.md` | ⚡ Início rápido para testes |

## 🎯 Opções do Seletor

1. **🤖 Service Agent** - Abordagem conversacional e flexível
2. **⚡ Workflow** - Abordagem estruturada e step-by-step
3. **📖 Guia** - Instruções detalhadas para avaliação

## 💡 Cenários de Teste Recomendados

- Validação de CPF: `"Meu CPF é 12345678901"`
- Validação de email: `"Quero validar meu email usuario@exemplo.com"`
- Registro de usuário: `"Preciso registrar um novo usuário"`
- Consulta existente: `"Sou João Silva"`

## 📊 Critérios de Avaliação

- **🎯 Naturalidade** - Quão natural é a conversa?
- **⚡ Performance** - Velocidade de resposta
- **🔄 Recuperação** - Facilidade para lidar com erros
- **📱 UX Geral** - Experiência global do usuário

## 🔧 Requisitos

- Python 3.13+
- UV package manager
- Dependências já instaladas no ambiente virtual

---

**Para dúvidas técnicas, consulte o `UX_TEST_GUIDE.md` dentro desta pasta.**
