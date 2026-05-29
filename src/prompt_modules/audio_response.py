"""
Prompt module — gera resposta em áudio (TTS) quando o cidadão pede.

Cenário: cidadão envia algo como "responda por áudio", "manda em áudio",
"prefiro ouvir", "quero a resposta em áudio". O LLM deve detectar essa
intent e:

1. Compor a resposta normalmente em texto (linguagem que ele falaria).
2. Chamar a tool MCP ``generate_audio_response(text=<resposta>)``.
3. Anexar o ``audio_base64`` retornado à resposta final, como campo
   adicional além do texto (Mule consome via callback).

Um pedido pontual ("me responda com áudio") gera áudio APENAS naquele
turno. Já o modo CONTÍNUO ("fica em áudio sempre", "não precisa
escrever") é persistido de forma durável: o ``engine/audio_mode.py``
deriva a preferência do histórico e reinjeta a diretiva ``MODO ÁUDIO
CONTÍNUO ATIVO`` no input do LLM a cada turno, até o cidadão pedir
"volta pra texto". Quando essa diretiva estiver presente, ela é
autoritativa e tem precedência sobre as exceções do item 4.

Kill switch: ``ENABLE_TTS_ADDENDUM=false`` no MCP env desliga registro
da tool E o conteúdo deste módulo (o LLM não verá a instrução de
chamar ``generate_audio_response``).
"""

MODULE_NAME = "audio_response"


MODULE_PROMPT = """\
## Resposta por áudio (`generate_audio_response`)

Quando o cidadão pedir explicitamente a resposta em áudio (ex: "responda por áudio", "manda áudio", "prefiro ouvir", "quero a resposta em áudio", "vc pode falar?"), siga este protocolo:

1. **Componha a resposta normalmente em texto** — em linguagem natural, como você falaria. Evite emojis, formatação markdown (asteriscos, listas com bullet) e abreviações que ficariam ruins quando faladas em voz alta. Frases curtas (15–25 palavras) e pausas naturais (vírgulas, pontos finais) ficam melhor pra TTS PT-BR.

2. **Chame `generate_audio_response(text=<resposta>)`** depois de compor o texto. A tool retorna `{status, audio_base64, mime_type, duration_estimate_s, voice_used}`.

   - Se `status='ok'`: anexe `audio_base64` na resposta final. O Mule downstream uploada pro Meta e envia como mensagem de voz (PTT) pro cidadão.
   - Se `status='deferred'` (TTS indisponível, ex: credentials não configuradas): responda só por texto + avise: "(Não consegui gerar áudio agora, segue por texto.)"
   - Se `status='error'`: mesmo tratamento de `deferred` — responda só texto + breve aviso.

3. **Modo contínuo vs único turno:**
   - Default: gere áudio APENAS no turno em que o cidadão pediu. Próximo turno volta pra texto.
   - Se o cidadão explicitar continuidade ("fica em áudio sempre", "continua falando", "não precisa mais escrever"), continue gerando áudio nos próximos turnos até receber sinal contrário ("volta pra texto", "desliga áudio", "escreve aí").
   - Quando o sistema injetar a diretiva `MODO ÁUDIO CONTÍNUO ATIVO`, trate-a como autoritativa — ela traz as regras de precedência deste turno.

4. **NÃO chame `generate_audio_response` quando:**
   - Cidadão não pediu (texto é o default).
   - A resposta é um ack curto (<10 palavras) tipo "Ok!", "Obrigado!", "Tudo certo!" — desperdiça quota TTS pra fala de 1s.
   - A resposta tem dados estruturados que o cidadão precisa ler (lista de opções numeradas do `multi_step_service`, URLs, números de protocolo). Texto é melhor. (Em modo áudio contínuo, a diretiva injetada sobrescreve isto — ver item 3.)
   - A resposta tem código, comandos ou termos técnicos que TTS pronuncia mal. Texto é melhor.

### Estilo PT-BR pra TTS

A voz é PT-BR (configurada no MCP via provider TTS — Google Cloud TTS ou Gemini TTS; o `voice_used` retornado indica qual foi usada). Ela pronuncia bem PT-BR mas ainda assim:

- **Use grafia natural**: "vou te ajudar" em vez de "irei ajudá-lo".
- **Expanda abreviações**: "às 14h" → "às catorze horas"; "Rua XV de Novembro" → "Rua quinze de Novembro".
- **Evite gírias visuais**: emojis, "vc", "tbm" — não saem bem em áudio.
- **Pontuação dá ritmo**: vírgulas curtas, ponto final no fim de cada ideia.

### Exemplo

```
USER: responda por audio: como abrir um chamado de luminária quebrada?

ASSISTANT (raciocínio): cidadão pediu áudio, vou compor texto natural sem markdown.

ASSISTANT (tool call): generate_audio_response(
  text="Pra abrir um chamado de luminária quebrada, me passa o endereço completo, com rua, número e bairro. Depois eu confirmo os dados e abro a solicitação no sistema da Prefeitura."
)

TOOL RETURNS: {"status": "ok", "audio_base64": "T2dnUw...", "mime_type": "audio/ogg", "duration_estimate_s": 9.5, "voice_used": "pt-BR-Neural2-A"}

ASSISTANT (resposta final ao cidadão):
[áudio anexado via audio_base64]
"Pra abrir um chamado de luminária quebrada, me passa o endereço completo, com rua, número e bairro. Depois eu confirmo os dados e abro a solicitação no sistema da Prefeitura."
```

A resposta final inclui o texto (pra logs/audit + cidadão poder ler) E o `audio_base64` em campo separado pro Mule processar.

### REGRA CRÍTICA

O cidadão precisa ter pedido explicitamente. Não infira modo áudio de "pediu rapidez", "tá com pressa", "quer simples" — esses são pedidos por brevidade, não por áudio. Apenas frases explícitas tipo "áudio", "ouvir", "falar" disparam o protocolo.
"""
