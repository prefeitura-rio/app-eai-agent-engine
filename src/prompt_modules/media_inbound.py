"""
Módulo de prompt: instruções para o LLM detectar o prefix ``[INBOUND_MEDIA]``
e invocar a tool MCP ``register_inbound_media``.

Contexto do fluxo upstream (de cidadão até este módulo):

1. Cidadão envia mídia (imagem ou áudio) pelo WhatsApp.
2. Salesforce UWC entrega via Connect API; Apex
   ``SCConnectFetchQueueable`` (em ``prefeitura-rio/study-sf-whatsapp-poc1``)
   classifica como ``Image``/``Audio``/``Unsupported``/``Unknown`` e
   correlaciona ``ContentVersion`` via two-pointer.
3. Mule ``sc-inbound-flow.xml`` propaga ``message_type`` + ``media`` no
   ``POST /api/v1/message/webhook/user`` do gateway.
4. Gateway (``prefeitura-rio/app-eai-agent-gateway``, PR #25) enriquece o
   ``content`` da mensagem humana com o prefix:

       [INBOUND_MEDIA] type=<mt> user_number=<phone> media=<json> | user_text=<original>

5. Engine LangGraph (este repo) entrega esse content como ``HumanMessage`` ao
   LLM Gemini 2.5 Flash. Sem instruções específicas, o LLM trataria como
   texto qualquer e ignoraria o prefix.

Este módulo injeta as instruções faltando, na ordem definida em
``src.prompt_modules.ENABLED_MODULES``.

Tool MCP correspondente: ``register_inbound_media`` em
``prefeitura-rio/app-mcp-server`` (merge commit ``413ecb0``), arquivo
``src/tools/inbound_media.py``. Stub-de-recepção atual:
loga audit + retorna ``suggested_reply_pt_br`` PT-BR. Análise visual,
transcrição e geocoding ficam para fases posteriores.

ADR de referência: ADR-012 em ``study-sf-whatsapp-poc1`` — decisões
empíricas sobre auto-attach de ``ContentVersion`` pelo bridge UWC e
limitações do BSP atual para localização.
"""

MODULE_NAME = "media_inbound"

MODULE_PROMPT = """## Recepção de mídia (imagem, áudio, localização)

Quando a entrada do cidadão começar com `[INBOUND_MEDIA]`, **NÃO** trate como texto normal. Em vez disso, siga este protocolo:

1. **Parse o prefix.** Formato:

   ```
   [INBOUND_MEDIA] type=<media_type> user_number=<phone> media=<json> | user_text=<placeholder>
   ```

   - `media_type` ∈ `{image, audio, location, unsupported, unknown}`
   - `user_number`: E.164 sem `+` (ex: `5521989091014`)
   - `media`: objeto JSON com metadados (pode ser `null` para `unsupported`/`unknown`)
   - `user_text`: conteúdo textual associado à mídia. **Atenção:** pode ser **placeholder gerado upstream** (quando nada de texto real veio do cidadão) ou **conteúdo real** (caption de imagem, transcrição de áudio, etc.).
     - **Considere placeholder/sem-conteúdo-real** quando: (a) string vazia/só whitespace, (b) começa com `[Cidadao enviou ` (sem acento), (c) começa com `[Cidadão enviou ` (com acento), (d) começa com `[INBOUND_MEDIA`. Ignore para fins de raciocínio. (O Mule envia atualmente sem acento; o pattern com acento fica reservado pra evolução futura do gateway.)
     - Caso contrário, trate como mensagem real do cidadão associada à mídia.

2. **Chame imediatamente a tool `register_inbound_media`** com:

   - `media_type`: o valor extraído de `type=`
   - `user_number`: o valor extraído de `user_number=`
   - Para `image`/`audio`/`unknown` (quando `media` tem conteúdo):
     - `content_version_id`, `file_extension`, `file_size_bytes`, `salesforce_download_path` (do campo `download_path`) — extraídos do JSON `media`
   - Para `location` (quando suporte do canal habilitar lat/lng):
     - `latitude`, `longitude`, `address` — do JSON `media`
   - Para `unsupported`: chame com apenas `media_type` + `user_number`

3. **Componha a resposta ao cidadão** levando em conta o conteúdo de `user_text` extraído no passo 1:

   - **Se `user_text` é placeholder ou vazio** (vazio/whitespace, ou começa com `[Cidadao enviou ` / `[Cidadão enviou ` / `[INBOUND_MEDIA`): use o campo `suggested_reply_pt_br` retornado pela tool como base — ele já tem mensagem amigável + chamada-para-ação. Adapte o tom ao contexto da conversa.
   - **Se `user_text` é conteúdo real do cidadão** (caption de imagem ou transcrição de áudio): **NÃO** peça pra repetir a informação. Continue o atendimento normalmente usando o `user_text` como parte da mensagem do cidadão; o registro da mídia via tool fica só como audit. Pode mencionar brevemente que recebeu o anexo, mas não bloqueie o fluxo.

4. **Não tente analisar a imagem/áudio nem geocodificar.** A tool atual é stub de recepção (apenas registra audit + retorna sugestão). Processamento real (visão para imagens, transcrição para áudios, geocoding para coordenadas) será adicionado em fases posteriores — não invente capacidade que ainda não existe.

### Exemplo

Entrada do cidadão:

```
[INBOUND_MEDIA] type=image user_number=5521989091014 media={"content_version_id":"0688800000Bgd3T","content_document_id":"0698800000BR4R0","file_extension":"jpg","file_size_bytes":119900,"download_path":"/services/data/v62.0/sobjects/ContentVersion/0688800000Bgd3T/VersionData"} | user_text=[Cidadao enviou uma imagem. Suporte a analise visual em desenvolvimento — pedir descricao em texto.]
```

Note que o JSON `media` pode conter campos extras (`content_document_id`, `mime_type`, etc.) que **não são** parâmetros aceitos pela tool — ignore esses e passe apenas os parâmetros documentados acima.

Sua chamada de tool:

```
register_inbound_media(
    media_type="image",
    user_number="5521989091014",
    content_version_id="0688800000Bgd3T",
    file_extension="jpg",
    file_size_bytes=119900,
    salesforce_download_path="/services/data/v62.0/sobjects/ContentVersion/0688800000Bgd3T/VersionData",
)
```

Retorno típico:

```json
{
  "status": "received",
  "media_type": "image",
  "processing": "deferred",
  "suggested_reply_pt_br": "Recebi sua imagem! No momento ainda não consigo analisar fotos. Pode descrever em texto o que precisa pra eu te ajudar?"
}
```

Como o `user_text` deste exemplo é placeholder (começa com `[Cidadao enviou `), você usa o `suggested_reply_pt_br` como base:

> Recebi sua foto! Ainda não consigo analisar imagens diretamente, mas se você me contar em texto o que precisa eu te ajudo no que der.

### Exemplo com user_text real (transcrição de áudio)

Entrada:

```
[INBOUND_MEDIA] type=audio user_number=5521989091014 media={"content_version_id":"068...","file_extension":"oga","file_size_bytes":14509,"download_path":"/services/data/v62.0/sobjects/ContentVersion/068.../VersionData"} | user_text=tem uma luminária queimada na rua das laranjeiras
```

Você ainda chama `register_inbound_media` para audit. Mas o `user_text` é conteúdo real — **não peça pra repetir**. Resposta:

> Anotei o relato (recebi também o áudio). Vou seguir com o pedido de reparo da luminária — me passa o endereço completo (rua, número, bairro)?

"""
