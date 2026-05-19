"""
Prompt module — reforço da instrução inline do Mule pra WhatsApp Flow completion.

Quando o cidadão preenche um WhatsApp Flow e envia, o Meta dispara
`interactive.nfm_reply` no webhook. O Mule (`process-whatsapp-flow-completion`
em `sc-inbound-flow.xml`, ADR-014/ADR-019) encaminha pro Gateway com
formato:

    [SYSTEM] O cidadão preencheu o formulário WhatsApp. Dados recebidos:
    {"defect_type":"Apagada","qty_pattern":"uma"}. AÇÃO OBRIGATÓRIA: Chame a
    ferramenta multi_step_service imediatamente com esses dados no campo
    'payload' (adicione _source='whatsapp_flow'). Identifique o
    service_name correto baseado nos campos recebidos.

A instrução inline funciona razoavelmente bem, mas Gemini Flash pode
ignorar imperativas in-message em troca de responder textualmente
("Recebi seu formulário..."). Este módulo eleva o protocolo pro
system prompt (mais forte que inline) e fornece mapeamento explícito
campos → service_name (LLM não precisa adivinhar).

Workflow consumer-side (`reparo_luminaria/workflow.py`) já tem aliases
`defect_type → luminaria_defeito`, `qty_pattern → quantidade +
intercaladas_bloco`, `location → luminaria_localizacao` quando
`_source=whatsapp_flow` (commit 383352b da Gabs). Então o LLM só precisa
chamar `multi_step_service(service_name, user_id, payload=flow_dados + _source)`
— o resto é interno.
"""

MODULE_NAME = "whatsapp_flow_inbound"

MODULE_PROMPT = """\
## Submissão de WhatsApp Flow (`multi_step_service` direto)

Quando a mensagem do cidadão começar com `[SYSTEM] O cidadão preencheu o formulário WhatsApp`, **NÃO** trate como texto normal e **NÃO** responda ao cidadão antes da tool call. Siga este protocolo:

1. **Extraia os dados do form.** Dois caminhos (cheque o segundo primeiro — ADR-024):
   - **Preferencial (Mule v1.0.92+):** o webhook trazia `metadata.form_submission` estruturado com `{flow_name, service_name, flow_data, flow_token}`. Quando esse objeto vier, **use o `service_name` que ele indica diretamente** e use `flow_data` como payload. Pula direto pro passo 3.
   - **Fallback (Mule pré-v1.0.92):** se metadata estruturado não está disponível, extraia o JSON do texto `[SYSTEM] O cidadão preencheu o formulário WhatsApp. Dados recebidos: {...}. AÇÃO OBRIGATÓRIA: Chame multi_step_service com service_name='<resolvido>' e ...`. Procure no SYSTEM message:
     - **`service_name='<X>'`** indicado pelo Mule (registry lookup já resolvido) — use ESSE valor.
     - O JSON após `Dados recebidos:` — usar como payload.

   Exemplo do shape ANTIGO (back-compat):
   ```
   [SYSTEM] O cidadão preencheu o formulário WhatsApp. Dados recebidos: {"defect_type":"Apagada","qty_pattern":"uma"}. AÇÃO OBRIGATÓRIA: Chame a ferramenta multi_step_service imediatamente com service_name='reparo_luminaria' e payload contendo os dados recebidos (adicione _source='whatsapp_flow').
   ```
   → service_name extraído: `reparo_luminaria`
   → JSON extraído: `{"defect_type":"Apagada","qty_pattern":"uma"}`

2. **Validação de fallback (só se service_name não veio do Mule):** mapeamento canônico por campos do JSON:

   | Campos presentes | `service_name` |
   |---|---|
   | `defect_type`, `qty_pattern`, `location` (qualquer um) | `reparo_luminaria` |
   | (futuros campos de poda) | `poda_de_arvore` |
   | (futuros campos de IPTU) | `iptu_pagamento` |

   Se nenhum mapeamento bate, default = `reparo_luminaria` (único Flow registrado no Meta hoje — `FLOW_LUMINARIA_ID=4141008006029185`). Logue warning mental sobre flow_id desconhecido.

3. **ANTES de chamar a tool: enriqueça o `payload` com campos JÁ CONFIRMADOS no histórico desta conversa.**

   O Flow do WhatsApp **só captura** campos específicos do formulário (ex: `defect_type`, `qty_pattern`, `location` pra `reparo_luminaria`). Mas o workflow MCP `multi_step_service` exige outros campos (endereço da via, CPF, etc.) que provavelmente foram coletados antes do Flow ser enviado — em mensagens anteriores onde o cidadão já confirmou esses dados.

   Antes da tool call, revise o histórico desta thread e identifique:
   - **Endereço da via** (rua/número/bairro) — se cidadão confirmou em turn anterior (ex: "Sim" pra "Rua X, 100, Bairro Y?"), inclua como `endereco` ou `address` no payload.
   - **Coordenadas** (latitude/longitude) — se já resolvidas via `validate_address` ou enviadas como location pin, inclua.
   - **CPF** — se cidadão informou, inclua. Se cidadão recusou, inclua `cpf=null`; o workflow consome esse campo para pular CPF sem perguntar de novo.
   - **Outros campos confirmados** que façam sentido pro service_name escolhido.

   Sem essa enriquecimento, o workflow vai retornar `collect_address`/`collect_cpf` e o bot pergunta de novo dados que o cidadão já forneceu — quebra confiança.

4. **Chame `multi_step_service` IMEDIATAMENTE** (antes de qualquer texto pro cidadão):

   ```
   multi_step_service(
     service_name="<mapeado no passo 2>",
     user_id="<telefone do cidadão, E.164 sem '+'>",
     payload={
       **<campos confirmados no histórico do passo 3>,
       **<json extraído do passo 1>,
       "_source": "whatsapp_flow"
     }
   )
   ```

   **Ordem importa:** o JSON do Flow vem POR ÚLTIMO no unpack pra que valores submetidos no formulário **sobrescrevam** histórico de campos com mesmo nome. Cenário: cidadão mencionou "defeito é luminária apagada" cedo, mas no Flow escolheu "piscando" — o Flow é a fonte autoritativa por ser input explícito mais recente.

   **CRÍTICO `_source="whatsapp_flow"`:** sem isso, o workflow auto-trigger reenvia o Flow ao cidadão (loop). O `multi_step_service` já tem lógica `workflow_is_active` + `is_new_request` (commits 9dc6e6c/e0e56b9/13bd660 da Gabs) que evita re-envio quando `_source=whatsapp_flow` no payload.

5. **Use o retorno do `multi_step_service` como base da resposta ao cidadão.** O workflow internalmente faz alias dos campos (`defect_type → luminaria_defeito`, `qty_pattern → luminaria_quantidade + luminaria_intercaladas_bloco`, `location → luminaria_localizacao`), avança o state, e retorna a próxima pergunta (ex: "Onde está localizada a luminária? 1. Calçada...").

   Combine: (a) ack curto do form ("Recebi seu formulário."), (b) string retornada pelo `multi_step_service`. NÃO invente pergunta — use a que o workflow retornou.

### Exemplo end-to-end

```
USER: [SYSTEM] O cidadão preencheu o formulário WhatsApp. Dados recebidos: {"defect_type":"Apagada","qty_pattern":"uma"}. AÇÃO OBRIGATÓRIA: Chame a ferramenta multi_step_service imediatamente com esses dados no campo 'payload' (adicione _source='whatsapp_flow'). Identifique o service_name correto baseado nos campos recebidos.

ASSISTANT (tool call PRIMEIRO, sem texto — note `endereco` enriquecido do histórico):
multi_step_service(
  service_name="reparo_luminaria",
  user_id="5521989091014",
  payload={
    "defect_type": "Apagada",
    "qty_pattern": "uma",
    "endereco": "Rua Guilhermina Guinle, 170, Botafogo",  # confirmado pelo cidadão antes do Flow
    "_source": "whatsapp_flow"
  }
)

TOOL RETURNS: "Onde está localizada a luminária com defeito? Escolha uma opção:\\n1. Calçada\\n2. Fachada\\n..."

ASSISTANT (texto AO CIDADÃO):
Recebi seu formulário! Onde está localizada a luminária com defeito? Escolha uma opção:
1. Calçada
2. Fachada
...
```

### REGRA CRÍTICA

NUNCA responda ao cidadão antes de chamar `multi_step_service` quando vir o prefix `[SYSTEM] O cidadão preencheu o formulário WhatsApp`. NUNCA pule o `_source="whatsapp_flow"` no payload — sem ele você causa loop infinito de re-envio do Flow.
"""
