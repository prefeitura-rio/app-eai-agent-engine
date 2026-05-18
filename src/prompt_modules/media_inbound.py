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

   - `media_type` ∈ `{image, audio, video, location, unsupported, unknown}`
   - `user_number`: E.164 sem `+` (ex: `5521989091014`)
   - `media`: objeto JSON com metadados (pode ser `null` para `unsupported`/`unknown`)
   - `user_text`: conteúdo textual associado à mídia. **Atenção:** pode ser **placeholder gerado upstream** (quando nada de texto real veio do cidadão) ou **conteúdo real** (caption de imagem, transcrição de áudio, etc.).
     - **Considere placeholder/sem-conteúdo-real** quando: (a) string vazia/só whitespace, (b) começa com `[Cidadao enviou ` (sem acento), (c) começa com `[Cidadão enviou ` (com acento), (d) começa com `[INBOUND_MEDIA`. Ignore para fins de raciocínio. (O Mule envia atualmente sem acento; o pattern com acento fica reservado pra evolução futura do gateway.)
     - Caso contrário, trate como mensagem real do cidadão associada à mídia.

2. **Chame imediatamente a tool `register_inbound_media`** passando TODOS os campos disponíveis no JSON `media`. **OBRIGATÓRIO**:

   - `media_type`: o valor extraído de `type=`
   - `user_number`: o valor extraído de `user_number=`
   - **SE o JSON `media` contém `meta_media_id`** (caminho Meta direto, ADR-017):
     - `meta_media_id`: o valor do campo `media.meta_media_id` (string, ex: `"864820469982533"`)
     - `meta_mime_type`: o valor do campo `media.mime_type` se presente (ex: `"image/jpeg"`)
   - **SE o JSON `media` contém `content_version_id`** (caminho UWC legacy):
     - `content_version_id`, `file_extension`, `file_size_bytes` do JSON
     - `salesforce_download_path`: do campo `media.download_path`
   - **SE o JSON `media` contém ambos** (`meta_media_id` E `content_version_id`): passe os dois — tool prioriza `meta_media_id`.
   - Para `location`: `latitude`, `longitude`, `address` do JSON `media`.
   - Para `unsupported`: apenas `media_type` + `user_number`.

   **CRITICAL: NÃO chame `register_inbound_media` apenas com `media_type` + `user_number` quando o JSON `media` tem conteúdo. Sempre extraia e passe os campos de identificação da mídia (`meta_media_id` OU `content_version_id`). Sem isso a tool não pode rastrear o arquivo e a análise downstream falha.**

3. **Componha a resposta ao cidadão** levando em conta o conteúdo de `user_text` extraído no passo 1:

   - **Se `user_text` é placeholder ou vazio** (vazio/whitespace, ou começa com `[Cidadao enviou ` / `[Cidadão enviou ` / `[INBOUND_MEDIA`): use o campo `suggested_reply_pt_br` retornado pela tool como base — ele já tem mensagem amigável + chamada-para-ação. Adapte o tom ao contexto da conversa.
   - **Se `user_text` é conteúdo real do cidadão** (caption de imagem ou transcrição de áudio): **NÃO** peça pra repetir a informação. Continue o atendimento normalmente usando o `user_text` como parte da mensagem do cidadão; o registro da mídia via tool fica só como audit. Pode mencionar brevemente que recebeu o anexo, mas não bloqueie o fluxo.

4. **Use as tools de análise quando aplicável.** A tool `register_inbound_media` é stub de recepção (apenas registra audit + retorna sugestão). Para análise real:
   - **Imagem:** chame `analyze_inbound_image` em seguida, quando disponível (conforme módulo `vision_inbound` deste prompt).
   - **Áudio:** chame `analyze_inbound_audio` em seguida, quando disponível (conforme módulo `audio_inbound` deste prompt) — a tool transcreve a fala e retorna intenção + workflow sugerido.
   - **Vídeo:** chame `analyze_inbound_video` em seguida, quando disponível (conforme módulo `video_inbound` deste prompt) — a tool analisa frames + áudio do vídeo e retorna descrição + transcrição + workflow sugerido.
   - **Localização:** ainda não tem caminho de processamento direto — siga o protocolo de geocoding via texto descrito mais abaixo (caso `media_type=unsupported`).

   Quando o módulo correspondente (`vision_inbound`/`audio_inbound`/`video_inbound`) estiver presente neste prompt e a tool estiver listada, use-os. Quando o módulo NÃO estiver presente OU a tool NÃO estiver listada, mantenha o fallback genérico do `register_inbound_media` (mensagem amigável pedindo texto).

### Caso especial: `media_type=unsupported` (geocoding via texto)

Quando `media_type=unsupported`, o canal BSP-managed bloqueou o conteúdo que o cidadão tentou enviar. **A causa predominante é tentativa de compartilhar localização** (pin de mapa), mas pode também ser vídeo, sticker, documento, etc. Bruno confirmou em 2026-05-12 que destravar o canal BSP-side não é viável no curto prazo (ver ADR-013 em `study-sf-whatsapp-poc1`).

Fluxo correto:

1. Chame `register_inbound_media(media_type="unsupported", user_number=...)` para audit.
2. Use a `suggested_reply_pt_br` retornada como base e **convide explicitamente o cidadão a enviar o endereço em texto** (rua, número, bairro). Não assuma de antemão que é localização — deixe a porta aberta para outros conteúdos ("se for outra coisa, descreva em texto").
3. **Quando o cidadão responder com um endereço** no próximo turno, chame a tool MCP `validate_address(address=<texto-do-endereço>)` para converter em lat/lng + dados IPP estruturados.
4. Com lat/lng em mãos, prossiga com o caso de uso original — por exemplo equipamentos próximos via `equipments_by_address` (que aceita o mesmo endereço-texto que você acabou de validar), alerta hídrico via `report_incident`, etc. Para o cidadão, o resultado é equivalente a ter compartilhado a localização: a Prefeitura "recebeu" a coordenada.

Exemplo de turno do cidadão (resposta esperada do bot):

```
Recebi sua mensagem! Vi que você tentou compartilhar algo que não consigo
processar diretamente por aqui — provavelmente uma localização. Pode me
passar o endereço em texto? Algo como "Rua Tal, 123, Tijuca". Se for outro
conteúdo, descreve em texto que eu te ajudo.
```

Quando o cidadão responder no turno seguinte (ex: "Rua das Laranjeiras 250, Laranjeiras"), chame:

```
validate_address(address="Rua das Laranjeiras 250, Laranjeiras")
```

Retorno típico inclui `latitude`, `longitude`, `bairro_id_ipp`, `logradouro_id_ipp` — dados suficientes para SGRC e raciocínio espacial. Use-os no fluxo de atendimento normal.

**Não invente coordenadas.** Se `validate_address` falhar (`valid: false`), peça ao cidadão que confirme/refine o endereço.

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

### Exemplo Meta webhook direto (Caminho A — canal canônico atual)

Entrada do cidadão (vem do Mule `/meta/webhook`, não tem ContentVersion no SF):

```
[INBOUND_MEDIA] type=image user_number=5521989091014 media={"meta_media_id":"1234567890123456","mime_type":"image/jpeg"} | user_text=[Cidadao enviou uma imagem...]
```

Sua chamada de tool:

```
register_inbound_media(
    media_type="image",
    user_number="5521989091014",
    meta_media_id="1234567890123456",
    meta_mime_type="image/jpeg",
)
```

E em seguida (se módulo `vision_inbound` ativo):

```
analyze_inbound_image(
    user_number="5521989091014",
    meta_media_id="1234567890123456",
)
```

`file_extension` é opcional aqui — a tool deriva do MIME real retornado pelo Graph API do Meta.

"""
