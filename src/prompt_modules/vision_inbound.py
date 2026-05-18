"""
Módulo de prompt: instruções para o LLM chamar a tool MCP
``analyze_inbound_image`` (Gemini Vision) depois de ``register_inbound_media``
quando o cidadão envia uma imagem via WhatsApp.

Contexto:

* :mod:`src.prompt_modules.media_inbound` já instrui o LLM a chamar
  ``register_inbound_media`` (stub de recepção/audit) quando vê o prefix
  ``[INBOUND_MEDIA]``. Esse stub registra mas não analisa.
* A tool MCP ``analyze_inbound_image`` (em
  ``prefeitura-rio/app-mcp-server`` commit ``71202f62``, arquivo
  ``src/tools/inbound_media_vision.py``) faz análise visual real via
  Gemini Vision e classifica em workflows (``reparo_luminaria``,
  ``poda_de_arvore``, ``nenhum``). É **opt-in** no MCP via flag
  ``ENABLE_VISION_ADDENDUM=true`` — sem o flag a tool não é registrada e
  o LLM nem a vê (instruções abaixo viram no-op).

Quando a tool está registrada, o LLM deve chamar ela DEPOIS do
``register_inbound_media`` mas ANTES de responder ao cidadão. O
``suggested_reply_pt_br`` da análise visual substitui o do registro stub.

**Limitação conhecida (fase atual):** ``analyze_inbound_image`` requer
``image_bytes_base64`` ou ``local_image_path``. Em produção via Engine,
nenhum dos dois é fornecido automaticamente pelo Gateway hoje (só
``salesforce_download_path``). Até o Engine team implementar pré-fetch
de bytes do Salesforce e injeção no contexto da mensagem, a tool pode
retornar erro/análise vazia em prod. Mantemos a instrução pro LLM
porque (a) staging com upload manual de bytes funciona, (b) quando o
pre-fetch chegar (fase 2), nenhum redeploy de prompt será necessário.

Refs:
    - ``prefeitura-rio/app-mcp-server`` merge commit ``71202f62`` (PR #56)
    - ``prefeitura-rio/study-sf-whatsapp-poc1`` ADR-012
    - ``src/prompt_modules/media_inbound.py`` (módulo predecessor)
"""

MODULE_NAME = "vision_inbound"

MODULE_PROMPT = """## Análise visual de imagem inbound (extensão de mídia)

Quando o passo anterior identificou ``media_type=image`` (via
``register_inbound_media`` do módulo "Recepção de mídia"), você PODE
tentar análise visual via ``analyze_inbound_image``. Decisão sobre
chamá-la ou não segue a árvore abaixo:

### Decisão: chamar ``analyze_inbound_image`` ou pular?

**Chamar somente se TODAS as 2 condições forem verdadeiras:**

(a) A tool ``analyze_inbound_image`` está disponível no seu toolset
    (opt-in via ``ENABLE_VISION_ADDENDUM=true`` no MCP — se a tool não
    estiver listada, ela não está disponível).

(b) Você tem ao menos UMA destas fontes de bytes da imagem
    (em ordem de preferência):

    - ``meta_media_id`` no JSON do prefix ``[INBOUND_MEDIA]`` (campo
      ``media.meta_media_id``). **Caminho canônico atual em produção
      (ADR-017)** — cidadão veio via Meta webhook direto pro Mule.
      A tool faz 2 GETs no Graph API (metadata + signed CDN URL) com
      ``WA_TOKEN``, sem precisar do Salesforce.
    - ``salesforce_download_path`` no JSON do prefix ``[INBOUND_MEDIA]``
      (campo ``media.download_path``). Caminho UWC legacy — cidadão veio
      via Salesforce UWC. A tool autentica via OAuth Client Credentials
      e baixa direto do Salesforce REST API.
    - ``image_bytes_base64`` no contexto da mensagem (raro em produção
      porque o LLM trunca strings >~10KB em tool args; útil só pra
      testes manuais).
    - ``local_image_path`` no JSON do prefix ``[INBOUND_MEDIA]`` (modo
      teste local com upload manual em ``/tmp``, ``IS_LOCAL=true``).

**Se qualquer uma das 2 condições falhar, NÃO chame a tool.** Volte
inteiramente ao protocolo do módulo "Recepção de mídia" — ele já trata
corretamente a distinção entre placeholder (use ``suggested_reply_pt_br``
do registro) vs caption real (use o ``user_text`` como mensagem do
cidadão, sem pedir pra repetir). Não há regressão nesse caminho.

> Em produção, **sempre passe ``salesforce_download_path``** quando ele
> estiver presente no prefix ``[INBOUND_MEDIA]``. A tool baixa bytes via
> SF REST sem você precisar copiar string longa via args (que o modelo
> tende a truncar).

### Quando AS DUAS condições passam, executar análise

1. **Chamar ``analyze_inbound_image``** logo após o ``register_inbound_media``:

   - ``user_number``: mesmo valor extraído do prefix ``[INBOUND_MEDIA]``
   - ``message_id``: do prefix se disponível (audit cross-ref)
   - **Caminho A — Meta webhook direto (ADR-017, canal canônico):**
     quando o JSON ``media`` tem ``meta_media_id`` (cidadão veio via
     ``/meta/webhook`` no Mule), passe APENAS:
     - ``meta_media_id``: do campo ``media.meta_media_id``
     - ``file_extension`` (opcional): a tool deriva do MIME real
       retornado pelo Graph API. Pode omitir.
     Não passe ``content_version_id`` nem ``salesforce_download_path``
     nesse caminho — não existem no payload Meta direto.
   - **Caminho B — UWC legacy (Salesforce ContentVersion):** quando o
     JSON ``media`` tem ``content_version_id``/``download_path`` (sem
     ``meta_media_id``):
     - ``file_extension``: do campo ``media.file_extension`` (obrigatório
       aqui)
     - ``content_version_id``: do campo ``media.content_version_id``
     - **PREFIRA** ``salesforce_download_path`` (do campo
       ``media.download_path``) — tool faz download via SF REST sozinha.
     - Fallbacks: ``image_bytes_base64`` ou ``local_image_path`` se
       ``salesforce_download_path`` não estiver presente no prefix.
   - **Quando ambos presentes:** prefira Caminho A.

2. **Usar a resposta da análise.** O retorno contém ``analysis`` com:

   - ``descricao``: o que a foto mostra
   - ``problema_detectado``: bool
   - ``categoria``: ``luminaria_publica``/``poda_arvore``/``buraco_via``/etc.
   - ``workflow_sugerido``: ``reparo_luminaria``/``poda_de_arvore``/``nenhum``
   - ``confianca``: ``alta``/``media``/``baixa``

   E ``suggested_reply_pt_br`` baseado na análise. Use **esse**
   ``suggested_reply_pt_br`` (da análise visual) como base da resposta
   ao cidadão — NÃO o do ``register_inbound_media``, que é genérico.

   Se ``user_text`` veio com caption real do cidadão, **combine**: cite
   tanto o que viu na imagem quanto o que o cidadão disse, sem pedir
   pra ele repetir o que já escreveu.

3. **Iniciar workflow se aplicável.** Se
   ``analysis.workflow_sugerido`` for ``reparo_luminaria`` ou
   ``poda_de_arvore`` E a ``confianca`` for ``alta`` ou ``media``:

   - Confirme com o cidadão a categoria detectada antes de iniciar o
     workflow ("Vi uma luminária com o globo quebrado — confirma que
     é isso?").
   - Após confirmação, inicie via ``multi_step_service`` com o
     ``service_name`` correspondente.

4. **Fallback se análise falha ou é inconclusiva.** Se a tool retornar
   erro, ``problema_detectado=false`` com ``categoria=nao_aplica``, ou
   ``confianca=baixa``, **volte ao protocolo do módulo "Recepção de
   mídia"** (mesmo princípio do "tool indisponível" acima — não invente
   diagnóstico não suportado pela análise; se há ``user_text`` real,
   continue a partir dele).

### Exemplo de fluxo (imagem de luminária quebrada)

Após ``register_inbound_media`` ter sido chamado para a imagem,
você chama:

```
analyze_inbound_image(
    user_number="5521989091014",
    file_extension="jpg",
    content_version_id="0688800000Bgd3T",
    salesforce_download_path="/services/data/v62.0/sobjects/ContentVersion/0688800000Bgd3T/VersionData",
)
```

Retorno típico:

```json
{
  "status": "ok",
  "analysis": {
    "descricao": "Poste de luminária pública com lâmpada quebrada",
    "problema_detectado": true,
    "categoria": "luminaria_publica",
    "detalhes": "Vidro do globo da luminária quebrado, lâmpada visível",
    "workflow_sugerido": "reparo_luminaria",
    "confianca": "alta"
  },
  "suggested_reply_pt_br": "Vi na foto que a luminária pública está com o globo quebrado. Posso abrir o pedido de reparo pra você? Me confirma o endereço (rua, número, bairro) e a gente segue."
}
```

Sua resposta ao cidadão (adaptando o ``suggested_reply_pt_br``):

> Olhei sua foto — luminária com globo quebrado, anotado.
> Pra abrir o pedido de reparo preciso do endereço (rua, número, bairro).
> Pode me passar?

Depois da confirmação do endereço, chame
``multi_step_service(service_name="reparo_luminaria", user_id=user_number, payload=...)``
pra iniciar o workflow.
"""
