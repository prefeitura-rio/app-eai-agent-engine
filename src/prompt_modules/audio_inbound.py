"""
Módulo de prompt: instruções para o LLM chamar a tool MCP
``analyze_inbound_audio`` (Gemini multimodal) depois de
``register_inbound_media`` quando o cidadão envia áudio real pelo WhatsApp.

Contexto upstream (resumido):

* O módulo ``media_inbound`` já documenta o protocolo do prefix
  ``[INBOUND_MEDIA]`` e instrui o LLM a chamar ``register_inbound_media``
  (stub de recepção).
* A tool MCP ``analyze_inbound_audio`` (em
  ``prefeitura-rio/app-mcp-server/src/tools/inbound_media_audio.py``)
  estende o stub: baixa via Meta CDN ou Salesforce REST, transcreve via
  Gemini multimodal, retorna ``{transcricao, intencao_detectada,
  endereco_mencionado, workflow_sugerido, suggested_reply_pt_br}``.

Refator 2026-05-14 noite (ADR-018): bulk extraído pra
``_analyzable_media_template.AnalyzableMediaSpec``. Aqui só audio-specific:
allowlist Gemini audio, schema de análise, regra de não-pedir-repetir.
"""

from src.prompt_modules._analyzable_media_template import (
    AnalyzableMediaSpec,
    render_module_prompt,
)

MODULE_NAME = "audio_inbound"


_AUDIO_GUIDANCE = """\
### Schema da resposta `analyze_inbound_audio`

```
{
  "transcricao": "<transcrição literal PT-BR>",
  "resumo": "<1-2 frases>",
  "idioma_detectado": "<pt-br|pt-pt|es|en|outro>",
  "intencao_detectada": <true|false>,
  "categoria": "<luminaria_publica|poda_arvore|buraco_via|lixo_irregular|iluminacao_publica|sinalizacao|endereco|duvida_geral|outro|nao_aplica>",
  "endereco_mencionado": "<rua/bairro/número, vazio se não>",
  "workflow_sugerido": "<reparo_luminaria | poda_de_arvore | nenhum>",
  "confianca": "<alta|media|baixa>"
}
```

### Allowlist Gemini audio input

Formatos suportados pela tool (espelhado do Gemini API):
`oga`/`ogg` (PTT WhatsApp container OGG-Opus), `aac`, `mp3`, `wav`, `flac`,
`aiff`/`aif`. **NÃO suportados**: `m4a` (MP4 audio), `amr` (codec deprecado).
Se `media.file_extension` cair fora desse allowlist, **não chame a tool** e
volte ao protocolo do módulo "Recepção de mídia".

### Workflows triggerable a partir da transcrição

Use `analysis.workflow_sugerido` pra decidir:

- `reparo_luminaria` → confirme se `confianca >= media` e **mande o Flow primeiro**:
  `build_whatsapp_flow_envelope` prefillado com defeito/qtd/local extraídos do áudio
  (ver REGRA CRÍTICA em "Resposta interativa"). **NÃO** chame `multi_step_service`
  direto daqui nem peça/valide o endereço: o workflow (e o endereço) só vêm depois do
  `nfm_reply` do Flow. (Só se não houver Flow disponível pro service, aí sim
  `multi_step_service(service_name="reparo_luminaria")`.)
- `poda_de_arvore` → confirme (se `confianca >= media`) e chame
  `multi_step_service(service_name="poda_de_arvore")` direto — poda **não** tem Flow.
- `nenhum` → use `analysis.transcricao` como mensagem real do cidadão e
  continue o fluxo normal.

### Áudio como resposta a etapa de workflow ativo

Se já existe um workflow ativo aguardando um campo, trate
`analysis.transcricao` como a resposta do cidadão para essa etapa antes de
responder em texto. Não encerre com apenas um acknowledgement.

Caso crítico observado em produção: se o workflow ativo pediu CPF e a
transcrição indicar recusa de identificação ("não quero me identificar",
"continuar sem CPF", "prefiro não informar CPF", "anônimo"), chame
`multi_step_service` no workflow ativo com payload marcando CPF ausente/recusado
(ex.: `cpf=null`, `identificacao_recusada=true` ou campo equivalente do
workflow) e use o retorno da tool para continuar. Não responda apenas
"vou seguir sem CPF" sem chamar a tool.

### REGRA: não pedir pro cidadão repetir o áudio em texto

`analysis.transcricao` é a mensagem real do cidadão — você acabou de
"ouvir" o que ele falou. **NÃO peça pra digitar em texto o que ele já
disse** ("manda em texto pra eu te ajudar"). Em vez disso, use a
transcrição diretamente como o turno do cidadão e responda como
responderia a texto.

Quando `analysis.endereco_mencionado` está preenchido, o cidadão já
forneceu o endereço por voz — pule a pergunta "qual o endereço?" e
chame `validate_address(address=<endereco_mencionado>)` direto pra
confirmar/geocodar antes de prosseguir com o workflow. **Exceção
`reparo_luminaria`:** NÃO valide o endereço antes do Flow — pra luminária o
endereço (mesmo dito por voz) só é tratado depois do `nfm_reply`; mande o Flow
primeiro (ver o bullet de `reparo_luminaria` acima).

### Exemplo de fluxo (PTT com pedido de reparo via Meta direto)

Entrada do cidadão:
```
[INBOUND_MEDIA] type=audio user_number=5521989091014 media={"meta_media_id":"9876543210987654","mime_type":"audio/ogg; codecs=opus"} | user_text=[Cidadao enviou uma mensagem de voz...]
```

Chamadas em sequência:
```
register_inbound_media(media_type="audio", user_number="5521989091014",
                       meta_media_id="9876543210987654", meta_mime_type="audio/ogg; codecs=opus")
analyze_inbound_audio(user_number="5521989091014", meta_media_id="9876543210987654")
```

Retorno típico:
```json
{
  "status": "transcribed",
  "analysis": {
    "transcricao": "tem uma luminária queimada na rua das laranjeiras 250 laranjeiras",
    "resumo": "Cidadão relata luminária pública queimada na Rua das Laranjeiras, 250.",
    "intencao_detectada": true,
    "categoria": "luminaria_publica",
    "endereco_mencionado": "Rua das Laranjeiras, 250, Laranjeiras",
    "workflow_sugerido": "reparo_luminaria",
    "confianca": "alta"
  },
  "suggested_reply_pt_br": "Ouvi seu áudio: Cidadão relata luminária pública queimada na Rua das Laranjeiras, 250. Vou te mandar um formulário rapidinho pra confirmar os dados da luminária (o endereço eu pergunto depois)."
}
```
"""


_SPEC = AnalyzableMediaSpec(
    module_name=MODULE_NAME,
    media_type="audio",
    analyze_tool="analyze_inbound_audio",
    domain_noun_singular="áudio",
    domain_noun_indefinite="um áudio",
    domain_action="ouvir e transcrever",
    domain_action_present="transcrição",
    accepted_extensions=("oga", "ogg", "aac", "mp3", "wav", "flac", "aiff", "aif"),
    rejected_extensions_note="**Não passa**: m4a (MP4 audio), amr (codec deprecado).",
    bytes_base64_arg_name="audio_bytes_base64",
    local_path_arg_name="local_audio_path",
    enable_env_var="ENABLE_AUDIO_ADDENDUM",
    skip_analyze_on_real_user_text=True,  # transcription upstream substitui análise
    type_specific_guidance=_AUDIO_GUIDANCE,
)


MODULE_PROMPT = render_module_prompt(_SPEC)
