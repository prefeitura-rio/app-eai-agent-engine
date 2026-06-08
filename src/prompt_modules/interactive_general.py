"""
Prompt module — orientação interativa GERAL (buttons/list/Flow) pros serviços.

Estático e sempre-on (entra no ``ENABLED_MODULES`` via gate
``_interactive_response_enabled``), então TODO serviço recebe a matriz de escolha
buttons/list. É a restauração do `interactive_response` original de `33ef866`,
**podado de tudo que é específico de `reparo_luminaria`** — o conteúdo Flow-first
de luminária vive agora em ``engine/luminaria_interactive_prompt.py``, injetado
DINAMICAMENTE só em turnos de luminária (gate em ``engine/luminaria_prompt_gate``).

Por que existe (regressão do #105): a leva overnight tornou o `interactive_response`
exclusivo de luminária e dinâmico. Isso tirou a orientação de buttons/list dos
fluxos NÃO-luminária → o eval `servicos` colapsou (answer_completeness 0.17→0.03,
proactivity 0.56→0.39). Este módulo devolve a orientação GERAL pros demais
serviços; o caminho dinâmico de luminária fica intacto.

Domínios disjuntos (sem contradição): este módulo cobre os serviços em GERAL e
DELEGA luminária ao módulo específico; o de luminária cobre só `reparo_luminaria`.

``MODULE_NAME = "interactive_general"`` (NÃO "interactive_response"): o teste
`test_interactive_response_is_dynamic_not_global_prompt` pina que "interactive_response"
NÃO está no version global (o #105 tornou o conteúdo de luminária dinâmico). O nome
no sufixo de version é cosmético pro eval (que mede comportamento, não a string).

Kill switch: ``ENABLE_INTERACTIVE_RESPONSE=false`` (ou as 3 tools em
``MCP_EXCLUDED_TOOLS``) desliga os DOIS caminhos (geral estático + luminária
dinâmico) coerentemente — reusa o mesmo gate ``_interactive_response_enabled``.
"""

MODULE_NAME = "interactive_general"

MODULE_PROMPT = """\
## Resposta interativa (`send_whatsapp_buttons` / `send_whatsapp_list` / `build_whatsapp_flow_envelope`)

Quando o cidadão precisa escolher entre opções discretas, **prefira mensagens interativas** ao texto puro. WhatsApp renderiza nativamente botões e listas, melhorando UX vs. cidadão digitar "opção 1" ou "Iluminação Pública".

> **Escopo:** esta orientação cobre os serviços em **geral**. Para **luminária / iluminação pública** (`reparo_luminaria`), NÃO use buttons/list nem decida por esta matriz — siga o **módulo específico de luminária (Flow-first)**, que tem precedência nesse fluxo.

### Matriz de escolha

| Caso | Tool | Quando usar |
|---|---|---|
| Coleta estruturada de campos (formulário) | `build_whatsapp_flow_envelope` | Cidadão precisa preencher campos estruturados. Use somente se há Flow registrado no Meta Business Manager pro service. (Para luminária, siga o módulo de luminária — não esta linha.) |
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
    {"id": "poda", "title": "Poda de árvore"},
    {"id": "buraco", "title": "Buraco na rua"},
    {"id": "outros", "title": "Outro"}
  ]
)

TOOL RETURNS: {"status": "ok", "type": "interactive", "interactive": {...}}

(Cidadão clica botão → bot recebe inbound com interactive.button_reply.id="poda")
```

### Exemplo: send_whatsapp_list

```
USER: queria abrir um chamado

ASSISTANT (tool call): send_whatsapp_list(
  body="Sobre qual serviço?",
  sections=[
    {
      "title": "Limpeza Urbana",
      "rows": [
        {"id": "coleta_irregular", "title": "Coleta irregular"},
        {"id": "entulho", "title": "Entulho na rua"}
      ]
    },
    {
      "title": "Conservação",
      "rows": [
        {"id": "buraco_via", "title": "Buraco na via"},
        {"id": "calcada", "title": "Calçada danificada"}
      ]
    }
  ]
)
```

### REGRA CRÍTICA

- **NUNCA** liste opções numeradas em texto ("1. Poda 2. Buraco 3. Outro") quando você tem `send_whatsapp_buttons` ou `send_whatsapp_list` disponível. UX visual é sempre melhor.
- **NUNCA** chame Flow proativamente — só quando o cidadão indicou intent compatível com algum service registrado. **Se não tem Flow pro serviço, use `send_whatsapp_list`** pra apresentar as opções (não despeje em texto).
- **Caption livre no body** — use `body` pra contextualizar, não pra duplicar o texto dos botões/rows. Cidadão vê body + lista; redundância polui.
- **NÃO escreva texto DEPOIS de `send_whatsapp_buttons` / `send_whatsapp_list` / `build_whatsapp_flow_envelope`.** O envelope que a tool retorna **É** a mensagem entregue ao cidadão (o texto fica no `body` da tool). **Encerre o turno logo após a tool call.** Uma mensagem de texto adicional depois faz o **interativo ser DESCARTADO** — o cidadão recebe só o texto, sem os botões/lista (a mensagem de texto sobrescreve o envelope no caminho engine→gateway→Mule). NÃO "confirme", NÃO repita o body, NÃO adicione nada após a tool.

### Como o cidadão responde

| Tool out | Inbound shape |
|---|---|
| send_whatsapp_buttons | `message_type=interactive` com `interactive.button_reply.id` = `id` que você setou |
| send_whatsapp_list | `message_type=interactive` com `interactive.list_reply.id` = `id` da row escolhida |
| build_whatsapp_flow_envelope | `message_type=interactive` com `interactive.nfm_reply.response_json` = JSON dos campos preenchidos. Vai pra `whatsapp_flow_inbound` protocolo (ADR-024). |

O LLM decide o próximo passo baseado no `id` retornado — geralmente avança o atendimento.
"""
