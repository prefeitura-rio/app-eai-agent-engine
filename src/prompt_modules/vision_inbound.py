"""
Módulo de prompt: instruções para o LLM chamar a tool MCP
``analyze_inbound_image`` (Gemini Vision) depois de ``register_inbound_media``
quando o cidadão envia uma imagem real pelo WhatsApp.

Contexto upstream (resumido):

* O módulo ``media_inbound`` já documenta o protocolo do prefix
  ``[INBOUND_MEDIA]`` e instrui o LLM a chamar ``register_inbound_media``
  (stub de recepção).
* A tool MCP ``analyze_inbound_image`` (em
  ``prefeitura-rio/app-mcp-server/src/tools/inbound_media_vision.py``)
  estende o stub: baixa via Meta CDN ou Salesforce REST, classifica
  o problema via Gemini Vision, retorna ``{categoria, workflow_sugerido,
  confianca, suggested_reply_pt_br}``.

Refator 2026-05-14 noite (ADR-018): bulk da estrutura do prompt
(opt-in gate + call section + REGRA CRÍTICA) extraído pra
``_analyzable_media_template.AnalyzableMediaSpec``. Este arquivo fica só
com o que é vision-specific: schema do JSON de análise, regras de
classificação visual, workflows sugeridos, exemplos.
"""

from src.prompt_modules._analyzable_media_template import (
    AnalyzableMediaSpec,
    render_module_prompt,
)

MODULE_NAME = "vision_inbound"


_VISION_GUIDANCE = """\
### Schema da resposta `analyze_inbound_image`

O `analysis` retornado tem o seguinte schema:

```
{
  "descricao": "<o que a foto mostra, max 200 chars>",
  "problema_detectado": <true|false>,
  "categoria": "<luminaria_publica | poda_arvore | buraco_via | lixo_irregular | iluminacao_publica | sinalizacao | outro | nao_aplica>",
  "detalhes": "<o que parece estar errado, max 250 chars>",
  "workflow_sugerido": "<reparo_luminaria | poda_de_arvore | nenhum>",
  "confianca": "<alta|media|baixa>"
}
```

### Workflows triggerable a partir da análise visual

Use `analysis.workflow_sugerido` pra decidir o próximo passo:

- `reparo_luminaria` → confirme com o cidadão a categoria detectada
  ("Vi uma luminária com o globo quebrado — confirma que é isso?"),
  depois chame `multi_step_service(service_name="reparo_luminaria")`.
- `poda_de_arvore` → confirme, depois
  `multi_step_service(service_name="poda_de_arvore")`.
- `nenhum` → use o `suggested_reply_pt_br` da análise como base e siga o
  fluxo conversacional normal.

**Sempre confirme a categoria antes de disparar o workflow.** Análise
visual pode estar errada, especialmente com `confianca=media` ou `baixa`.

### Composição da resposta

- Se `user_text` veio com caption real do cidadão, **combine**: cite tanto
  o que viu na imagem quanto o que ele disse, sem pedir pra repetir.
- Se `confianca=baixa` ou `problema_detectado=false`, peça descrição em
  texto pra confirmar.

### Exemplo de fluxo (imagem de luminária quebrada via Meta direto)

Entrada do cidadão:
```
[INBOUND_MEDIA] type=image user_number=5521989091014 media={"meta_media_id":"1234567890123456","mime_type":"image/jpeg"} | user_text=[Cidadao enviou uma imagem...]
```

Chamadas em sequência:
```
register_inbound_media(media_type="image", user_number="5521989091014",
                       meta_media_id="1234567890123456", meta_mime_type="image/jpeg")
analyze_inbound_image(user_number="5521989091014", meta_media_id="1234567890123456")
```

Retorno típico:
```json
{
  "status": "analyzed",
  "analysis": {
    "descricao": "Poste de luminária pública com lâmpada quebrada",
    "problema_detectado": true,
    "categoria": "luminaria_publica",
    "workflow_sugerido": "reparo_luminaria",
    "confianca": "alta"
  },
  "suggested_reply_pt_br": "Vi na foto que a luminária pública está com o globo quebrado. Posso abrir o pedido de reparo pra você? Me confirma o endereço (rua, número, bairro) e a gente segue."
}
```
"""


_SPEC = AnalyzableMediaSpec(
    module_name=MODULE_NAME,
    media_type="image",
    analyze_tool="analyze_inbound_image",
    domain_noun_singular="imagem",
    domain_noun_indefinite="uma imagem",
    domain_action="analisar",
    domain_action_present="análise",
    accepted_extensions=("jpg", "jpeg", "png", "webp", "gif"),
    bytes_base64_arg_name="image_bytes_base64",
    local_path_arg_name="local_image_path",
    enable_env_var="ENABLE_VISION_ADDENDUM",
    type_specific_guidance=_VISION_GUIDANCE,
)


MODULE_PROMPT = render_module_prompt(_SPEC)
