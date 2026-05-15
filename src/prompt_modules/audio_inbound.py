"""
Módulo de prompt: instruções para o LLM chamar a tool MCP
``analyze_inbound_audio`` (Gemini multimodal) depois de
``register_inbound_media`` quando o cidadão envia áudio via WhatsApp.

Contexto:

* :mod:`src.prompt_modules.media_inbound` já instrui o LLM a chamar
  ``register_inbound_media`` (stub de recepção/audit) quando vê o prefix
  ``[INBOUND_MEDIA]``. Esse stub registra mas não transcreve.
* A tool MCP ``analyze_inbound_audio`` (em
  ``prefeitura-rio/app-mcp-server``, arquivo
  ``src/tools/inbound_media_audio.py``) faz transcrição real via Gemini
  multimodal e classifica em workflows (``reparo_luminaria``,
  ``poda_de_arvore``, ``nenhum``). É **opt-in** no MCP via flag
  ``ENABLE_AUDIO_ADDENDUM=true`` (default-on) — sem o flag a tool não é
  registrada e o LLM nem a vê (instruções abaixo viram no-op).

Refs:
    - ``prefeitura-rio/app-mcp-server`` PR feat/audio-transcription-via-gemini
    - ``prefeitura-rio/study-sf-whatsapp-poc1`` ADR-015 (entrega audio E2E)
    - ``src/prompt_modules/vision_inbound.py`` (módulo sibling pra imagem)
"""

MODULE_NAME = "audio_inbound"

MODULE_PROMPT = """## Transcrição de áudio inbound (extensão de mídia)

Quando o passo anterior identificou ``media_type=audio`` (via
``register_inbound_media`` do módulo "Recepção de mídia"), você PODE
tentar transcrição via ``analyze_inbound_audio``. Decisão sobre chamá-la
ou não segue a árvore abaixo.

### Decisão: chamar ``analyze_inbound_audio`` ou pular?

**Chamar somente se TODAS as 2 condições forem verdadeiras:**

(a) A tool ``analyze_inbound_audio`` está disponível no seu toolset
    (opt-in via ``ENABLE_AUDIO_ADDENDUM=true`` no MCP — se a tool não
    estiver listada, ela não está disponível).

(b) Você tem ao menos UMA destas fontes de bytes do áudio
    (em ordem de preferência):

    - ``meta_media_id`` no JSON do prefix ``[INBOUND_MEDIA]`` (campo
      ``media.meta_media_id``). **Caminho canônico atual em produção
      (ADR-017)** — cidadão veio via Meta webhook direto pro Mule.
      A tool faz 2 GETs no Graph API (metadata + signed CDN URL) com
      ``WA_TOKEN``. Handle automaticamente ``audio/ogg; codecs=opus``
      (PTT WhatsApp).
    - ``salesforce_download_path`` no JSON do prefix ``[INBOUND_MEDIA]``
      (campo ``media.download_path``). Caminho UWC legacy — cidadão veio
      via Salesforce UWC. A tool autentica via OAuth Client Credentials
      e baixa direto do Salesforce REST API.
    - ``audio_bytes_base64`` no contexto da mensagem (raro em produção
      porque o LLM trunca strings >~10KB em tool args; útil só pra
      testes manuais).
    - ``local_audio_path`` no JSON do prefix (modo teste local com
      upload manual em ``/tmp``, ``IS_LOCAL=true``).

**Se qualquer condição falhar, NÃO chame a tool.** Volte inteiramente
ao protocolo do módulo "Recepção de mídia" — ele já trata corretamente
a distinção entre placeholder (use ``suggested_reply_pt_br`` do
``register_inbound_media``) vs ``user_text`` real (use o ``user_text``
como mensagem do cidadão, sem pedir pra ele repetir). Não há regressão
nesse caminho. **Especificamente: se ``user_text`` veio com transcrição
real upstream, NÃO chame ``analyze_inbound_audio`` nem peça pro cidadão
repetir** — siga a partir do ``user_text``.

> Em produção, **sempre passe ``salesforce_download_path``** quando ele
> estiver presente no prefix ``[INBOUND_MEDIA]``. A tool baixa bytes via
> SF REST sem você precisar copiar string longa via args.

### Quando AS DUAS condições passam, executar transcrição

1. **Chamar ``analyze_inbound_audio``** logo após o
   ``register_inbound_media``. **OBRIGATÓRIO** — sem isso o cidadão recebe
   apenas o fallback genérico "não consigo transcrever áudio" do
   ``register_inbound_media``, que NÃO É a resposta desejada quando há
   áudio real:

   - ``user_number``: mesmo valor extraído do prefix ``[INBOUND_MEDIA]``
   - ``message_id``: do prefix se disponível
   - **SE o JSON ``media`` tem ``meta_media_id``** (canal canônico Meta direto):
     - ``meta_media_id``: o valor (string) do campo ``media.meta_media_id``
     - Não precisa de ``file_extension`` — tool deriva do MIME real do
       Graph API (handle ``audio/ogg; codecs=opus`` automático).
   - **SE o JSON ``media`` tem ``content_version_id``** (UWC legacy):
     - ``file_extension``: do campo ``media.file_extension`` (**allowlist
       Gemini**: ``oga``/``ogg``/``aac``/``mp3``/``wav``/``flac``/``aiff``;
       NÃO ``m4a``/``amr``). Se fora do allowlist, NÃO chame a tool.
     - ``content_version_id``: ``media.content_version_id``
     - ``salesforce_download_path``: ``media.download_path``
   - **SE ambos presentes**: passe ``meta_media_id`` (a tool prioriza esse caminho).

   **REGRA CRÍTICA:** Quando o prefix `[INBOUND_MEDIA] type=audio` chegar, você TEM que chamar `analyze_inbound_audio` ALÉM de `register_inbound_media`. Chamar APENAS `register_inbound_media` resulta em resposta genérica "não consigo ouvir" — isso é regressão.

2. **Usar a resposta da transcrição.** Retorno contém ``analysis`` com:

   - ``transcricao``: o que o cidadão falou (literal, PT-BR)
   - ``resumo``: 1-2 frases resumindo o pedido
   - ``idioma_detectado``: ``pt-br``/``pt-pt``/``es``/``en``/``outro``
   - ``intencao_detectada``: bool
   - ``categoria``: ``luminaria_publica``/``poda_arvore``/``buraco_via``/
     ``endereco``/``duvida_geral``/etc.
   - ``endereco_mencionado``: endereço ou trecho identificado, ou ``""``
   - ``workflow_sugerido``: ``reparo_luminaria``/``poda_de_arvore``/``nenhum``
   - ``confianca``: ``alta``/``media``/``baixa``

   E ``suggested_reply_pt_br`` baseado na análise. Use **esse**
   ``suggested_reply_pt_br`` como base — NÃO o do
   ``register_inbound_media`` (que é genérico).

   **Trate ``analysis.transcricao`` como mensagem real do cidadão.**
   Mesmo princípio do ``user_text`` real do módulo "Recepção de mídia":
   não peça pra o cidadão repetir o que já falou em áudio.

3. **Iniciar workflow se aplicável.** Se ``analysis.workflow_sugerido``
   for ``reparo_luminaria`` ou ``poda_de_arvore`` E a ``confianca`` for
   ``alta`` ou ``media``:

   - Confirme com o cidadão o entendimento ("Ouvi que você está
     reportando luminária queimada na Rua das Laranjeiras — confirma?").
   - Se ``analysis.endereco_mencionado`` foi preenchido, **chame
     ``validate_address`` direto com esse endereço** em vez de pedir o
     endereço de novo (atalho importante — cidadão acabou de falar).
   - Após confirmação, inicie via ``multi_step_service`` com o
     ``service_name`` correspondente.

4. **Fallback se transcrição falha ou é inconclusiva.** Se a tool
   retornar erro, ``intencao_detectada=false``, ou ``confianca=baixa``,
   peça ao cidadão pra repetir em texto. Não invente conteúdo que a
   transcrição não revelou.

### Exemplo de fluxo (áudio sobre luminária queimada)

Entrada do cidadão:

```
[INBOUND_MEDIA] type=audio user_number=5521989091014 media={"content_version_id":"068xx00000Bgd3T","file_extension":"oga","file_size_bytes":14509,"download_path":"/services/data/v62.0/sobjects/ContentVersion/068xx00000Bgd3T/VersionData"} | user_text=[Cidadao enviou uma mensagem de voz...]
```

Após ``register_inbound_media``, chame:

```
analyze_inbound_audio(
    user_number="5521989091014",
    file_extension="oga",
    content_version_id="068xx00000Bgd3T",
    salesforce_download_path="/services/data/v62.0/sobjects/ContentVersion/068xx00000Bgd3T/VersionData",
)
```

Retorno típico:

```json
{
  "status": "transcribed",
  "analysis": {
    "transcricao": "tem uma luminária queimada na rua das laranjeiras",
    "resumo": "Reporte de luminária queimada na Rua das Laranjeiras",
    "idioma_detectado": "pt-br",
    "intencao_detectada": true,
    "categoria": "luminaria_publica",
    "endereco_mencionado": "rua das laranjeiras",
    "workflow_sugerido": "reparo_luminaria",
    "confianca": "alta"
  },
  "suggested_reply_pt_br": "Ouvi seu áudio: reporte de luminária queimada na Rua das Laranjeiras. Vou te ajudar a abrir um chamado de reparo de luminária — você confirma que quer prosseguir? Me passa o endereço (rua, número, bairro)."
}
```

Sua resposta ao cidadão:

> Entendi pelo áudio: luminária queimada na Rua das Laranjeiras.
> Posso abrir o chamado de reparo. Pra confirmar, me passa o número
> e o bairro completo?

Se o cidadão responder "150, Laranjeiras", chame direto
``validate_address(address="Rua das Laranjeiras 150, Laranjeiras")``
sem pedir o nome da rua de novo — ele já disse no áudio.
"""
