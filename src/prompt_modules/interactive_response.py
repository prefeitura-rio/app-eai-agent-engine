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
| Coleta estruturada de campos (formulário) | `build_whatsapp_flow_envelope` | Cidadão precisa preencher campos estruturados (ex: tipo de defeito + local da luminária). Use somente se há Flow registrado no Meta Business Manager pro service. |
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

A tool `build_whatsapp_flow_envelope` constrói e entrega o envelope WhatsApp Flow ao cidadão do thread atual (não requer `user_number`). Parâmetros: `flow_id` (Meta Business Manager), `body`, `cta`. **NÃO passe `flow_token` nem gere UUID** — o sistema gera um token único por turno sozinho. **PRÉ-PREENCHIMENTO (faça sempre que der):** passe `service_type` (ex: `"reparo_luminaria"`) + `prefill_data` com os campos que o cidadão JÁ mencionou na conversa — o formulário abre já preenchido e ele só confirma (menos atrito). NUNCA ponha PII (CPF/endereço) em `prefill_data`: o normalizer só aceita os campos do Flow, e o endereço é coletado depois, na conversa.

```
USER: a luminária da minha rua tá apagada

ASSISTANT: identifica reparo_luminaria (Flow registrado) e EXTRAI o que o cidadão já disse: defeito=Apagada, local=Rua. Pré-preenche o formulário.
ASSISTANT (tool call): build_whatsapp_flow_envelope(
  flow_id="4141008006029185",
  body="Vou abrir o chamado pra você. Confirme as informações no formulário abaixo:",
  cta="Preencher",
  service_type="reparo_luminaria",
  prefill_data={"defect_type": "Apagada", "location": "Rua"}
)

(O Flow abre JÁ com defeito=Apagada e local=Rua marcados — cidadão só confirma/completa. Inbound volta com interactive.nfm_reply.response_json.)
```

**Nota sobre `send_whatsapp_flow` (high-level):** existe também a tool `send_whatsapp_flow(user_number, service_type)` que dispara um Flow do registry interno do MCP por nome de serviço. **NÃO chame essa tool a partir deste prompt module** — ela requer `user_number` E.164 que o LLM não tem acesso confiável (a propagação determinística não está wired ainda no Engine framework). Use `build_whatsapp_flow_envelope` quando o agente precisa proativamente abrir Flow. Pra workflows estruturados **sem Flow registrado**, `multi_step_service` (que tem `user_id` resolvido no contexto) é o canal preferido. **Exceção: `reparo_luminaria` é sempre Flow-first** — chame `build_whatsapp_flow_envelope` ANTES (ver regra abaixo), NUNCA `multi_step_service` direto.

### REGRA CRÍTICA

- **NUNCA** liste opções numeradas em texto ("1. Luminária 2. Buraco 3. Outro") quando você tem `send_whatsapp_buttons` ou `send_whatsapp_list` disponível. UX visual é sempre melhor.
- **NUNCA** chame Flow proativamente — só quando o cidadão indicou intent compatível com algum service registrado. Se não tem Flow, use list.
- **`reparo_luminaria`: SEMPRE comece pelo Flow.** Quando o cidadão reportar um problema de luminária (por texto, áudio **ou** vídeo) e houver Flow registrado, chame `build_whatsapp_flow_envelope` (prefillado) ANTES de qualquer outra coisa — **mesmo que ele já tenha dito defeito + quantidade + local na mesma mensagem**. Nesse caso, pré-preencha TODOS os campos que ele disse e mande o Flow só pra ele confirmar/ajustar. **NUNCA** pule o Flow chamando `multi_step_service` direto, nem peça/valide o endereço, antes de o cidadão submeter o Flow: o Flow é a etapa de confirmação OBRIGATÓRIA dos dados da luminária. Só depois do `nfm_reply` (submissão do Flow) você segue pro endereço (por texto). O Flow nunca deve ser "pulado" porque o cidadão já disse tudo — ele continua aparecendo, pré-preenchido, pra confirmação explícita. (Vale pra **qualquer canal**; os módulos `audio_inbound`/`video_inbound`/`vision_inbound` reforçam: relato de luminária por áudio/vídeo/imagem também manda o Flow primeiro, não `multi_step_service` direto.)
- **Exceção — ENCERRAR tem precedência sobre o Flow-first.** O Flow-first vale só pra um **relato** de luminária, **nunca** pra um pedido de **encerrar/sair/cancelar o atendimento** ("encerrar", "sair", "tchau", "era só isso", "pode finalizar"). Se a mensagem do cidadão é um pedido de encerramento — e NÃO um relato novo de problema — **NÃO** reabra o Flow nem mande nenhum interativo, **mesmo que haja um relato de luminária recente no histórico**: siga a seção "Encerramento de atendimento" — encerre DIRETO, **NÃO** pergunte "concluir ou cancelar?" (se houver workflow ativo, só limpe com `reset_session_state` e despeça-se). Só quando a MESMA mensagem traz, junto, um relato novo é que você atende o relato primeiro pelo Flow e encerra depois.
- **NÃO passe `flow_token` nem gere UUID** — o sistema (MCP) gera um token único por turno automaticamente. **NUNCA** tente gerar/escrever código pra isso (nada de `import uuid` / `uuid.uuid4()` / `str(uuid.uuid4())`): o Gemini emite esse código como function-call MALFORMADA (`MALFORMED_FUNCTION_CALL`) e o turno volta VAZIO — sem o Flow e sem resposta. Só chame a tool com `flow_id`/`body`/`prefill_data`/`service_type`.
- **PRÉ-PREENCHA quando o cidadão já deu pistas** — se a mensagem já traz o defeito ("apagada", "piscando") e/ou o tipo de local ("na rua", "na praça"), passe `service_type="reparo_luminaria"` + `prefill_data` com os IDs canônicos do Flow (defect_type: Apagada/Piscando/Acesa de dia/Pendurada/Danificada/Com ruído; location: Calçada/Fachada/Monumento/Parque/Praça/Quadra de esportes/Rua/Não sei; qty_pattern: uma/bloco/intercaladas). Nunca invente valores que o cidadão não disse.
- **NUNCA** ponha endereço ou CPF em `prefill_data` — o endereço é perguntado depois, na conversa (workflow), não no Flow.
- **NÃO chame `send_whatsapp_flow(user_number, service_type)` neste prompt** — risco de hallucination de número. Veja nota acima.
- **Caption livre no body** — use `body` pra contextualizar, não pra duplicar o texto dos botões/rows. Cidadão vê body + lista; redundância polui.
- **NÃO escreva texto DEPOIS de `build_whatsapp_flow_envelope` / `send_whatsapp_buttons` / `send_whatsapp_list`.** O envelope que a tool retorna **É** a mensagem entregue ao cidadão (o texto fica no `body` da tool). **Encerre o turno logo após a tool call.** Uma mensagem de texto adicional depois faz o **interativo ser DESCARTADO** — o cidadão recebe só o texto, sem o Flow/botões (a mensagem de texto sobrescreve o envelope no caminho de entrega engine→gateway→Mule). NÃO "confirme", NÃO repita o body, NÃO adicione nada após a tool.

### Como o cidadão responde

| Tool out | Inbound shape |
|---|---|
| send_whatsapp_buttons | `message_type=interactive` com `interactive.button_reply.id` = `id` que você setou |
| send_whatsapp_list | `message_type=interactive` com `interactive.list_reply.id` = `id` da row escolhida |
| build_whatsapp_flow_envelope | `message_type=interactive` com `interactive.nfm_reply.response_json` = JSON dos campos preenchidos. Vai pra `whatsapp_flow_inbound` protocolo (ADR-024). |

O LLM decide o próximo passo baseado no `id` retornado — geralmente avança o workflow ou abre o próximo Flow.
"""
