# 🎯 GUIA DE TESTES UX

## 🚀 Como Executar os Testes

### 📋 Comando Principal
```bash
uv run ux_test_selector.py
```

### 🤖 Teste Service Agent Direto
```bash
uv run test_service_agent_ux.py
```

### 📊 Teste Workflow Direto
```bash
uv run test_workflow_ux.py
```

---

## 🎯 INSTRUÇÕES PARA AVALIAÇÃO UX

### 📝 O que Avaliar

#### 1. **Experiência da Conversa**
- [ ] A conversa flui naturalmente?
- [ ] As respostas são claras e úteis?
- [ ] O assistente entende bem o contexto?
- [ ] O tom está apropriado para atendimento público?

#### 2. **Performance e Responsividade**
- [ ] Tempo de resposta é aceitável? (< 15 segundos)
- [ ] Há travamentos ou demoras excessivas?
- [ ] O sistema responde de forma consistente?

#### 3. **Funcionalidades e Validações**
- [ ] Validação de CPF funciona corretamente?
- [ ] Validação de email funciona corretamente?
- [ ] Mensagens de erro são claras e úteis?
- [ ] Sistema diferencia usuários existentes vs novos?

#### 4. **Usabilidade Geral**
- [ ] É fácil entender como usar?
- [ ] Usuário sabe o que esperar?
- [ ] Feedback do sistema é claro?

---

## 🧪 CENÁRIOS DE TESTE OBRIGATÓRIOS

### ✅ **Testes Básicos**
```
"Oi, quero me identificar. Meu CPF é 111.444.777-35"
"Preciso de ajuda com IPTU"
"Onde fica a prefeitura?"
```

### ⚠️ **Testes de Validação**
```
"Meu CPF é 111.444.777-99" (CPF inválido)
"Meu email é usuario@dominio" (email inválido)
"Quero me cadastrar, nome João Silva, CPF 529.982.247-25"
```

### 🔧 **Testes de Serviços**
```
"Tem um buraco na minha rua, como reporto?"
"Quero marcar uma consulta médica"
"Preciso pagar meus impostos"
```

---

## 📊 DIFERENÇAS PRINCIPAIS

### 🤖 **Service Agent** 
**Melhor para:**
- Conversas naturais e livres
- Usuários que preferem chat flexível
- Cenários inesperados ou complexos

**Características:**
- Roteamento automático para especialistas
- Mais conversacional
- Tempo médio: ~15.1s

### 📋 **Workflow**
**Melhor para:**
- Processos estruturados
- Fluxos previsíveis
- Eficiência em tarefas específicas

**Características:**
- Etapas claras e organizadas
- Mais rápido (4.4% melhor performance)
- Tempo médio: ~14.5s

---

##  **Planilha de Avaliação Sugerida**

| Critério | Service Agent | Workflow | Observações |
|----------|---------------|----------|-------------|
| Tempo de Resposta | | | |
| Clareza da Resposta | | | |
| Facilidade de Uso | | | |
| Tratamento de Erros | | | |
| Fluxo da Conversa | | | |
| **TOTAL** | | | |

**Escala:** 1-5 (1=Ruim, 5=Excelente)

---

## 🎉 **DECISÃO FINAL**

Teste ambos e vejam qual oferece melhor UX para nossos cidadãos! 

**Os dados técnicos mostram que Workflow é 4.4% mais rápido, mas a experiência do usuário é que vai decidir!** 🏛️
