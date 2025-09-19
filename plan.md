# Plano: Sistema de Schema Dinâmico e Payload Unificado

## 🎯 Visão Geral da Melhoria

### Conceito Principal
Transformar o sistema atual em uma experiência step-by-step inteligente onde:
- **Payload sempre é dict**: `{"step_name": "value"}` em todas as interações
- **Schema dinâmico**: Retorna apenas os campos disponíveis no momento atual
- **next_step_info como lista**: Múltiplos próximos steps baseados em dependências
- **Progressão guiada**: O agente vê exatamente o que pode fazer a cada momento

## 🔄 Fluxo Proposto

### Interação Atual vs. Nova

**Antes (Atual - Complexo):**
```json
// Start - modo especial
{"status": "bulk_request", "service_definition": {...}, "completed": false}

// Bulk mode - JSON string
'{"cpf": "123", "email": "test@example.com", "name": "João"}'

// Individual mode - string simples  
"corrente"

// Lógica confusa: bulk vs individual, JSON vs string
```

**Depois (Proposto - Simples):**
```json
// Start - mesmo padrão de sempre
{
  "status": "ready", 
  "available_steps": ["document_type", "account_type"],
  "next_steps_schema": {...}
}

// SEMPRE dict - sem exceções
{"document_type": "CPF"}

// Múltiplos campos - ainda dict
{"document_number": "12345678901", "account_type": "corrente"}

// Um campo - ainda dict  
{"email": "test@example.com"}

// Consistência total: payload sempre é Dict[str, str]
```

## 🏗️ Arquitetura Proposta

### 1. ServiceDefinition Aprimorada com Estado Completo

```python
class ServiceDefinition(BaseModel):
    service_name: str
    description: str
    steps: List[StepInfo]
    
    def get_state_analysis(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Análise completa do estado atual do serviço"""
        all_steps = {step.name: step for step in self.steps}
        completed_steps = list(completed_data.keys())
        available_steps = self.get_available_steps(completed_data)
        
        # Classificar steps disponíveis
        required_available = []
        optional_available = []
        for step_name in available_steps:
            step = all_steps[step_name]
            if step.required or self._is_conditionally_required(step, completed_data):
                required_available.append(step_name)
            else:
                optional_available.append(step_name)
        
        # Steps ainda pendentes (não disponíveis por dependências)
        pending_steps = []
        for step in self.steps:
            if step.name not in completed_steps and step.name not in available_steps:
                pending_steps.append(step.name)
        
        total_steps = len(self.steps)
        completed_count = len(completed_steps)
        
        return {
            "completed_steps": completed_steps,
            "available_steps": available_steps,
            "required_steps": required_available,
            "optional_steps": optional_available, 
            "pending_steps": pending_steps,
            "progress": {
                "completed": completed_count,
                "available": len(available_steps),
                "pending": len(pending_steps),
                "total": total_steps,
                "percentage": round((completed_count / total_steps) * 100, 1),
                "completion_estimate": self._estimate_completion(completed_count, total_steps)
            }
        }
    
    def get_contextual_schema(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Schema dinâmico baseado no estado atual"""
        available_steps = self.get_available_steps(completed_data)
        schema = {"type": "object", "properties": {}}
        
        for step_name in available_steps:
            step_info = self.get_step_info(step_name)
            step_schema = self._get_step_contextual_schema(step_name, completed_data)
            step_schema.update({
                "description": self._get_contextual_description(step_name, completed_data),
                "required": step_info.required or self._is_conditionally_required(step_info, completed_data)
            })
            schema["properties"][step_name] = step_schema
        
        return schema
    
    def get_state_summary(self, completed_data: Dict[str, Any]) -> str:
        """Resumo em linguagem natural do estado atual"""
        analysis = self.get_state_analysis(completed_data)
        
        if not completed_data:
            return f"Iniciando {self.service_name}. Escolha os primeiros campos disponíveis."
        
        completed_desc = ", ".join(analysis["completed_steps"])
        required_desc = ", ".join(analysis["required_steps"]) 
        
        summary = f"Concluído: {completed_desc}. "
        if required_desc:
            summary += f"Próximos obrigatórios: {required_desc}. "
        if analysis["optional_steps"]:
            summary += f"Opcionais disponíveis: {len(analysis['optional_steps'])}. "
        
        return summary
    
    def get_next_action_suggestion(self, completed_data: Dict[str, Any]) -> str:
        """Sugestão específica do que fazer a seguir"""
        analysis = self.get_state_analysis(completed_data)
        
        if analysis["required_steps"]:
            if len(analysis["required_steps"]) == 1:
                step_name = analysis["required_steps"][0]
                step_info = self.get_step_info(step_name)
                return f"Forneça {step_info.description.lower()}" + (f" (ex: {step_info.example})" if step_info.example else "")
            else:
                return f"Forneça qualquer um dos campos obrigatórios: {', '.join(analysis['required_steps'])}"
        elif analysis["optional_steps"]:
            return f"Todos campos obrigatórios concluídos. Opcionalmente: {', '.join(analysis['optional_steps'])}"
        else:
            return "Pronto para finalizar o serviço."
```

### 2. Tool Interface Ultra-Simplificada

```python
@tool
def multi_step_service(service_name: str, payload: Dict[str, str], user_id: str) -> Dict[str, Any]:
    """
    Sistema de serviços multi-step com schema dinâmico e estado transparente.
    
    INTERFACE UNIFICADA: 
    - ✅ Sempre recebe Dict[str, str] (nunca string, nunca JSON, nunca start)
    - ✅ Sempre retorna mesmo formato de response (estado + schema + progresso)
    - ✅ Elimina complexidade de bulk vs individual vs start modes
    
    Args:
        service_name: Nome do serviço (ex: "bank_account")
        payload: Dict com campos (ex: {"document_type": "CPF", "account_type": "corrente"})
        user_id: ID do usuário
    
    Returns:
        Estado completo: current_data, available_steps, schema dinâmico, progresso
    
    Exemplos:
        # Início - payload vazio
        payload = {}
        
        # Um campo
        payload = {"document_type": "CPF"}
        
        # Múltiplos campos
        payload = {"document_number": "12345678901", "account_type": "corrente"}
    """
```

### 3. Response Structure Unificada com Estado Completo

```python
# Todas as respostas seguem este padrão expandido:
{
    "status": "ready|progress|completed|error",
    "service_name": "bank_account",
    
    # ESTADO ATUAL - O que já foi coletado
    "current_data": {
        "document_type": "CPF",
        "account_type": "corrente"
    },
    
    # PROGRESSÃO DETALHADA
    "completed_steps": ["document_type", "account_type"],
    "available_steps": ["document_number", "personal_name", "initial_deposit"],
    "pending_steps": ["email"],  # Steps ainda não disponíveis por dependências
    "optional_steps": ["initial_deposit"],  # Steps opcionais disponíveis
    "required_steps": ["document_number", "personal_name"],  # Steps obrigatórios disponíveis
    
    # SCHEMA DINÂMICO - Apenas para steps disponíveis
    "next_steps_schema": {
        "document_number": {
            "type": "string",
            "description": "CPF com 11 dígitos (baseado no tipo selecionado)",
            "pattern": "^[0-9]{11}$",  # Dinâmico baseado em document_type
            "example": "12345678901",
            "required": true
        },
        "personal_name": {
            "type": "string", 
            "description": "Nome completo da pessoa física",
            "minLength": 2,
            "required": true
        },
        "initial_deposit": {
            "type": "number",
            "description": "Depósito inicial obrigatório para conta corrente",
            "minimum": 100,  # Dinâmico baseado em account_type
            "required": true  # Mudou para true por causa do account_type
        }
    },
    
    # VISÃO GERAL DO PROGRESSO
    "progress": {
        "completed": 2,
        "available": 3, 
        "pending": 1,
        "total": 6,
        "percentage": 33.3,
        "completion_estimate": "2-3 more steps"
    },
    
    # CONTEXTO ADICIONAL
    "state_summary": "Documento CPF selecionado, conta corrente escolhida. Agora precisa: número do CPF, nome e depósito mínimo.",
    "next_action_suggestion": "Forneça o número do CPF (11 dígitos) e seu nome completo.",
    
    # APENAS SE HOUVER PROBLEMAS
    "errors": {},
    "warnings": ["Conta corrente requer depósito mínimo de R$ 100"],
    
    # APENAS SE COMPLETED
    "completion_message": "..."
}
```

## 🚀 Benefícios da Nova Abordagem

### 1. Experiência do Agente
- ✅ **Interface unificada**: Sempre `Dict[str, str]` - sem exceções
- ✅ **Zero complexidade**: Eliminada confusão bulk vs individual vs start
- ✅ **Estado transparente**: Vê dados coletados + disponíveis + pendentes  
- ✅ **Schema contextual**: Validações adaptadas ao estado atual
- ✅ **Progressão visual**: Sabe exatamente quanto falta para completar

### 2. Flexibilidade
- ✅ **Steps paralelos**: Pode fazer document_type e account_type juntos
- ✅ **Schema adaptativo**: document_number muda baseado em document_type
- ✅ **Dependências inteligentes**: Mostra apenas o que faz sentido
- ✅ **Validação dinâmica**: Regras mudam conforme o contexto

### 3. Performance
- ✅ **Menos dados**: Retorna apenas o necessário
- ✅ **Validação eficiente**: Apenas nos campos enviados
- ✅ **Cache inteligente**: Schema computado apenas quando muda

## 📋 Implementação Step-by-Step

### Fase 1: Estender ServiceDefinition
- [ ] Adicionar `get_progressive_schema(completed_data)`
- [ ] Adicionar `get_next_steps_info(completed_data)`
- [ ] Implementar schema contextual (ex: CPF vs CNPJ)
- [ ] Adicionar cálculo de progresso

### Fase 2: Refatorar Tool Interface
- [ ] Mudar assinatura para sempre receber `Dict[str, str]`
- [ ] **ELIMINAR** conceitos de `bulk_request`, `start`, `bulk` mode
- [ ] **REMOVER** lógica condicional bulk vs individual vs step
- [ ] Implementar processamento unificado: sempre dict → sempre mesmo response
- [ ] Implementar response structure com estado completo

### Fase 3: Melhorar StepInfo
- [ ] Adicionar `validation_pattern` dinâmico
- [ ] Implementar `contextual_schema(current_data)`
- [ ] Adicionar `enum_values` baseado em estado
- [ ] Suporte a validações condicionais avançadas

### Fase 4: UX Enhancements
- [ ] Implementar progress tracking
- [ ] Adicionar estimativa de conclusão
- [ ] Melhorar mensagens de erro contextuais
- [ ] Implementar sugestões de valores

## 🔍 Casos de Uso Detalhados

### Cenário 1: Bank Account Creation - Visibilidade Completa do Estado

```python
# Step 1: Start - Estado inicial
payload = {}
response = {
    "status": "ready",
    "service_name": "bank_account",
    "current_data": {},  # Nada coletado ainda
    
    "completed_steps": [],
    "available_steps": ["document_type", "account_type"],  # Podem ser feitos em paralelo
    "pending_steps": ["document_number", "personal_name", "business_name", "email", "initial_deposit"],
    "required_steps": ["document_type", "account_type"],  # Ambos obrigatórios no início
    "optional_steps": [],
    
    "next_steps_schema": {
        "document_type": {"type": "string", "enum": ["CPF", "CNPJ"], "required": true},
        "account_type": {"type": "string", "enum": ["corrente", "poupança"], "required": true}
    },
    
    "progress": {"completed": 0, "available": 2, "pending": 5, "total": 7, "percentage": 0},
    "state_summary": "Iniciando bank_account. Escolha os primeiros campos disponíveis.",
    "next_action_suggestion": "Forneça qualquer um dos campos obrigatórios: document_type, account_type"
}

# Step 2: Document type selected - Agente vê o impacto imediato
payload = {"document_type": "CPF"}
response = {
    "status": "progress",
    "service_name": "bank_account", 
    "current_data": {"document_type": "CPF"},  # Estado atual visível
    
    "completed_steps": ["document_type"],
    "available_steps": ["document_number", "personal_name", "account_type"],  # business_name sumiu!
    "pending_steps": ["email", "initial_deposit"],  # email depende de document_number
    "required_steps": ["document_number", "personal_name", "account_type"],
    "optional_steps": [],
    
    "next_steps_schema": {
        "document_number": {
            "type": "string",
            "pattern": "^[0-9]{11}$",  # Schema mudou para CPF!
            "description": "CPF com 11 dígitos (baseado no tipo selecionado)",
            "example": "12345678901",
            "required": true
        },
        "personal_name": {  # Apareceu porque document_type=CPF
            "type": "string", 
            "description": "Nome completo da pessoa física",
            "minLength": 2,
            "required": true
        },
        "account_type": {"type": "string", "enum": ["corrente", "poupança"], "required": true}
    },
    
    "progress": {"completed": 1, "available": 3, "pending": 2, "total": 6, "percentage": 16.7},
    "state_summary": "Concluído: document_type. Próximos obrigatórios: document_number, personal_name, account_type.",
    "next_action_suggestion": "Forneça qualquer um dos campos obrigatórios: document_number, personal_name, account_type",
    "warnings": []
}

# Step 3: Multiple fields - O agente vê mudança dinâmica de regras
payload = {"document_number": "12345678901", "account_type": "corrente"}
response = {
    "status": "progress",
    "service_name": "bank_account",
    "current_data": {  # Estado completo sempre visível
        "document_type": "CPF",
        "document_number": "12345678901", 
        "account_type": "corrente"
    },
    
    "completed_steps": ["document_type", "document_number", "account_type"],
    "available_steps": ["personal_name", "initial_deposit", "email"],  # email liberou!
    "pending_steps": [],  # Todos disponíveis agora
    "required_steps": ["personal_name", "initial_deposit"],  # initial_deposit virou obrigatório!
    "optional_steps": ["email"],
    
    "next_steps_schema": {
        "personal_name": {"type": "string", "minLength": 2, "required": true},
        "initial_deposit": {
            "type": "number",
            "minimum": 100,  # Regra dinâmica por conta_type=corrente
            "description": "Depósito inicial obrigatório para conta corrente",
            "required": true  # Mudou para obrigatório!
        },
        "email": {"type": "string", "format": "email", "required": false}
    },
    
    "progress": {"completed": 3, "available": 3, "pending": 0, "total": 6, "percentage": 50.0},
    "state_summary": "Concluído: document_type, document_number, account_type. Próximos obrigatórios: personal_name, initial_deposit.",
    "next_action_suggestion": "Forneça nome completo da pessoa física (ex: João da Silva)",
    "warnings": ["Conta corrente requer depósito mínimo de R$ 100"]
}

# Step 4: Finalizando - Agente vê o que falta claramente
payload = {"personal_name": "João da Silva", "email": "joao@email.com"}
response = {
    "status": "progress",
    "service_name": "bank_account",
    "current_data": {
        "document_type": "CPF",
        "document_number": "12345678901",
        "account_type": "corrente", 
        "personal_name": "João da Silva",
        "email": "joao@email.com"
    },
    
    "completed_steps": ["document_type", "document_number", "account_type", "personal_name", "email"],
    "available_steps": ["initial_deposit"],  # Só falta 1!
    "pending_steps": [],
    "required_steps": ["initial_deposit"],
    "optional_steps": [],
    
    "next_steps_schema": {
        "initial_deposit": {
            "type": "number",
            "minimum": 100,
            "description": "Depósito inicial obrigatório para conta corrente",
            "required": true
        }
    },
    
    "progress": {"completed": 5, "available": 1, "pending": 0, "total": 6, "percentage": 83.3},
    "state_summary": "Concluído: document_type, document_number, account_type, personal_name, email. Próximos obrigatórios: initial_deposit.",
    "next_action_suggestion": "Forneça depósito inicial obrigatório para conta corrente (mínimo R$ 100)",
    "warnings": []
}
```

### Cenário 2: Schema Contextual Avançado

```python
class BankAccountService(BaseService):
    def get_contextual_schema(self, step_name: str, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """Schema que muda baseado no contexto atual"""
        if step_name == "document_number":
            doc_type = current_data.get("document_type")
            if doc_type == "CPF":
                return {"type": "string", "pattern": "^[0-9]{11}$", "description": "CPF com 11 dígitos"}
            elif doc_type == "CNPJ":
                return {"type": "string", "pattern": "^[0-9]{14}$", "description": "CNPJ com 14 dígitos"}
        
        if step_name == "initial_deposit":
            account_type = current_data.get("account_type")
            if account_type == "corrente":
                return {"type": "number", "minimum": 100, "description": "Mínimo R$ 100"}
            else:
                return {"type": "number", "minimum": 0, "description": "Valor opcional"}
```

## 🎯 Resultado Final Esperado

### API Limpa e Intuitiva
```python
# Sempre a mesma interface
service_tool.invoke({
    "service_name": "bank_account",
    "payload": {"document_type": "CPF", "account_type": "corrente"},
    "user_id": "user123"
})

# Response sempre consistente
{
    "status": "progress",
    "available_steps": ["document_number", "personal_name"],
    "next_steps_schema": {...},  # Apenas o que pode ser feito agora
    "progress": {"completed": 2, "total": 6}
}
```

### Vantagens para o Agente
1. **Zero ambiguidade**: Sempre sabe exatamente o que pode fazer
2. **Context-aware**: Schema muda baseado nas escolhas anteriores  
3. **Eficiência**: Pode preencher múltiplos campos de uma vez
4. **Feedback claro**: Progresso visual e próximos passos óbvios

---

**Próximo Passo**: Validar este plano e começar a implementação pela Fase 1.