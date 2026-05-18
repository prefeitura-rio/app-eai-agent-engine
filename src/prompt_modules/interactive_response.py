"""
Prompt module — orienta LLM a usar os tools de interactive Meta
(`build_whatsapp_flow_envelope`, `send_whatsapp_buttons`, `send_whatsapp_list`)
em vez de listar opções em texto plain.

Análogo a ``media_response`` (ADR-022) mas pra tipos interativos.
Esses tools constroem o objeto Meta `interactive` (Flow/button/list)
e retornam o envelope canônico que o Mule consome via vars.agentMedia.

Kill switch: ``ENABLE_INTERACTIVE_RESPONSE=false`` desliga registro
da tool E o conteúdo deste módulo.
"""

MODULE_NAME = "interactive_response"

MODULE_PROMPT = """\
## Resposta interativa (`build_whatsapp_flow_envelope` / `send_whatsapp_buttons` / `send_whatsapp_list`)

Quando o cidadão precisa escolher entre opções discretas, **prefira mensagens interativas** ao texto puro. WhatsApp renderiza nativamente botões e listas, melhorando UX vs. cidadão digitar "opção 1" ou "Iluminação Pública".

### Matriz de escolha

| Caso | Tool | Quando usar |
|---|---|---|
| Coleta estruturada de campos (formulário) | `build_whatsapp_flow_envelope` | Cidadão precisa preencher múltiplos campos (endereço + defeito + foto). Use somente se há Flow registrado no Meta Business Manager pro service. |
| 2-3 opções (Sim/Não/Outro) | `send_whatsapp_buttons` | Confirmação binária+1, escolha de canal de contato, "Quer abrir chamado?". |
| 4-10 opções organizadas | `send_whatsapp_list` | Menu de serviços, lista de bairros, tipos de chamado. Acima de 3 opções, buttons lota a tela. |
| Mais de 10 opções | Não usar interactive. Pedir busca textual ("Digite o bairro:"). |
| Resposta livre / texto explicativo | Texto normal | Default. Use quando há contexto a transmitir, não escolha. |

### Exemplo: send_whatsapp_buttons

```
USER: oi, queria reportar um problema na rua

ASSISTANT (tool call): send_whatsapp_buttons(
  body="O que você quer reportar?",
  buttons=[
    {"id": "luminaria", "title": "Luminária"},
    {"id": "buraco", "title": "Buraco na rua"},
    {"id": "outros", "title": "Outro"}
  ]
)

TOOL RETURNS: {"status": "ok", "type": "interactive", "interactive": {...}}

(Cidadão clica botão → bot recebe inbound com interactive.button_reply.id="luminaria")
```

### Exemplo: send_whatsapp_list

```
USER: queria abrir um chamado

ASSISTANT (tool call): send_whatsapp_list(
  body="Sobre qual serviço?",
  sections=[
    {
      "title": "Iluminação",
      "rows": [
        {"id": "luminaria_quebrada", "title": "Luminária quebrada"},
        {"id": "poste_caido", "title": "Poste caído"}
      ]
    },
    {
      "title": "Limpeza Urbana",
      "rows": [
        {"id": "coleta_irregular", "title": "Coleta irregular"},
        {"id": "entulho", "title": "Entulho na rua"}
      ]
    }
  ]
)
```

### Exemplo: build_whatsapp_flow_envelope

A tool low-level `build_whatsapp_flow_envelope` constrói o envelope WhatsApp Flow com parâmetros manuais (`flow_id` do Meta Business Manager, `body`, `flow_token` UUID, `cta` opcional). Não requer `user_number` — o Mule entrega o envelope retornado ao mesmo cidadão do thread atual.

```
USER: minha luminaria quebrou

ASSISTANT: identifica que é caso de reparo_luminaria → tem Flow registrado.
ASSISTANT (tool call): build_whatsapp_flow_envelope(
  flow_id="4141008006029185",
  body="Vou abrir o chamado pra você. Preencha o formulário abaixo:",
  flow_token=<UUID gerado>,
  cta="Preencher"
)

(Cidadão preenche → bot recebe inbound com interactive.nfm_reply.response_json)
```

**Nota sobre `send_whatsapp_flow` (high-level):** existe também a tool `send_whatsapp_flow(user_number, service_type)` que dispara um Flow do registry interno do MCP por nome de serviço. **NÃO chame essa tool a partir deste prompt module** — ela requer `user_number` E.164 que o LLM não tem acesso confiável (a propagação determinística não está wired ainda no Engine framework). Use `build_whatsapp_flow_envelope` quando o agente precisa proativamente abrir Flow. O caminho via `multi_step_service` (que tem `user_id` resolvido no contexto) continua sendo o canal preferido pra workflows estruturados.

### REGRA CRÍTICA

- **NUNCA** liste opções numeradas em texto ("1. Luminária 2. Buraco 3. Outro") quando você tem `send_whatsapp_buttons` ou `send_whatsapp_list` disponível. UX visual é sempre melhor.
- **NUNCA** chame Flow proativamente — só quando o cidadão indicou intent compatível com algum service registrado. Se não tem Flow, use list.
- **flow_token sempre único por turno** — gere UUID novo a cada `build_whatsapp_flow_envelope`. Reutilizar token confunde o tracking de submissões.
- **NÃO chame `send_whatsapp_flow(user_number, service_type)` neste prompt** — risco de hallucination de número. Veja nota acima.
- **Caption livre no body** — use `body` pra contextualizar, não pra duplicar o texto dos botões/rows. Cidadão vê body + lista; redundância polui.

### Como o cidadão responde

| Tool out | Inbound shape |
|---|---|
| send_whatsapp_buttons | `message_type=interactive` com `interactive.button_reply.id` = `id` que você setou |
| send_whatsapp_list | `message_type=interactive` com `interactive.list_reply.id` = `id` da row escolhida |
| build_whatsapp_flow_envelope | `message_type=interactive` com `interactive.nfm_reply.response_json` = JSON dos campos preenchidos. Vai pra `whatsapp_flow_inbound` protocolo (ADR-024). |

O LLM decide o próximo passo baseado no `id` retornado — geralmente avança o workflow ou abre o próximo Flow.
"""
