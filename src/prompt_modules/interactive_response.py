"""
Prompt module — orienta LLM a usar os tools de interactive Meta
(`send_whatsapp_flow`, `send_whatsapp_buttons`, `send_whatsapp_list`)
em vez de listar opções em texto plain.

Análogo a ``media_response`` (ADR-022) mas pra tipos interativos.
Esses tools constroem o objeto Meta `interactive` (Flow/button/list)
e retornam o envelope canônico que o Mule consome via vars.agentMedia.

Kill switch: ``ENABLE_INTERACTIVE_RESPONSE=false`` desliga registro
da tool E o conteúdo deste módulo.
"""

MODULE_NAME = "interactive_response"

MODULE_PROMPT = """\
## Resposta interativa (`send_whatsapp_flow` / `_buttons` / `_list`)

Quando o cidadão precisa escolher entre opções discretas, **prefira mensagens interativas** ao texto puro. WhatsApp renderiza nativamente botões e listas, melhorando UX vs. cidadão digitar "opção 1" ou "Iluminação Pública".

### Matriz de escolha

| Caso | Tool | Quando usar |
|---|---|---|
| Coleta estruturada de campos (formulário) | `send_whatsapp_flow` | Cidadão precisa preencher múltiplos campos (endereço + defeito + foto). Use somente se há Flow registrado no Meta Business Manager pro service. |
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

### Exemplo: send_whatsapp_flow

```
USER: minha luminaria quebrou

ASSISTANT: identifica que é caso de reparo_luminaria → tem Flow registrado.
ASSISTANT (tool call): send_whatsapp_flow(
  flow_id="4141008006029185",
  body="Vou abrir o chamado pra você. Preencha o formulário abaixo:",
  flow_token=<UUID gerado>,
  cta="Preencher"
)

(Cidadão preenche → bot recebe inbound com interactive.nfm_reply.response_json)
```

### REGRA CRÍTICA

- **NUNCA** liste opções numeradas em texto ("1. Luminária 2. Buraco 3. Outro") quando você tem `send_whatsapp_buttons` ou `send_whatsapp_list` disponível. UX visual é sempre melhor.
- **NUNCA** chame Flow proativamente — só quando o cidadão indicou intent compatível com algum service registrado. Se não tem Flow, use list.
- **flow_token sempre único por turno** — gere UUID novo a cada `send_whatsapp_flow`. Reutilizar token confunde o tracking de submissões.
- **Caption livre no body** — use `body` pra contextualizar, não pra duplicar o texto dos botões/rows. Cidadão vê body + lista; redundância polui.

### Como o cidadão responde

| Tool out | Inbound shape |
|---|---|
| send_whatsapp_buttons | `message_type=interactive` com `interactive.button_reply.id` = `id` que você setou |
| send_whatsapp_list | `message_type=interactive` com `interactive.list_reply.id` = `id` da row escolhida |
| send_whatsapp_flow | `message_type=interactive` com `interactive.nfm_reply.response_json` = JSON dos campos preenchidos. Vai pra `whatsapp_flow_inbound` protocolo (ADR-024). |

O LLM decide o próximo passo baseado no `id` retornado — geralmente avança o workflow ou abre o próximo Flow.
"""
