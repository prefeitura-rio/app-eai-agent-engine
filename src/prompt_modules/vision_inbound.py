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

### ⚠️ Segurança e fora de escopo (avaliar ANTES de sugerir workflow)

Olhe o que a foto mostra do ponto de vista de **risco** e **escopo** antes de
qualquer coisa. Estas situações têm PRECEDÊNCIA — **não** mande o Flow nem abra
chamado de luminária, independentemente do `workflow_sugerido`:

- **Risco iminente / perigo elétrico** — se a imagem indica poste caído, fios
  partidos ou expostos, faíscas, fiação na água, incêndio, estrutura desabando
  ou pessoa em perigo: NÃO trate como reparo. Com tom acolhedor e direto, oriente
  o cidadão a se afastar e acionar imediatamente a **Defesa Civil (199)**, e a
  **Light (0800 0210196)** quando envolver a rede elétrica (poste/fios da
  concessionária). Deixe claro que é prioridade de emergência, não um chamado comum.
- **Fora do escopo deste serviço** — se a imagem é de **falta de energia**, luz
  apagada **dentro de casa/imóvel**, **semáforo** apagado, ou cabo/fio de
  **internet, telefonia, TV a cabo, fibra ou operadora**: o reparo de iluminação
  pública NÃO cobre esses casos. Oriente a acionar a **Light pelo 0800 0210196**
  (energia/semáforo) ou a operadora responsável (telecom/fibra) e não abra chamado de luminária.
- **Ativo privado** — luminária/lâmpada/luz/refletor de loja, mercado, bar,
  restaurante, shopping, escritório, clínica, prédio, garagem, portaria,
  quintal, sala, quarto, cozinha, varanda ou fachada privada NÃO é reparo de
  iluminação pública. Não trate como `reparo_luminaria` e não mande Flow. Só trate como luminária quando for luz pública/Rioluz,
  poste da rua, calçada, praça, via pública ou em frente/perto de um ponto
  privado mas claramente no espaço público.

Só siga pro `workflow_sugerido` quando a foto for de fato **iluminação pública**
(poste/luminária da via apagada, piscando, com ruído ou danificada) **sem** risco iminente.

### Workflows triggerable a partir da análise visual

Use `analysis.workflow_sugerido` pra decidir o próximo passo:

- `reparo_luminaria` → confirme a categoria detectada e **mande o Flow primeiro**:
  `build_whatsapp_flow_envelope` prefillado com o defeito/local que a foto indicar
  (ver REGRA CRÍTICA em "Resposta interativa"). **NÃO** chame `multi_step_service`
  direto nem peça o endereço: o workflow (e o endereço) só vêm depois do `nfm_reply`
  do Flow. (Só se não houver Flow disponível pro service, aí sim
  `multi_step_service(service_name="reparo_luminaria")`.)
  Se caption, OCR ou contexto textual mencionar barulho/ruído/chiado/zumbido/
  estalo em luminária pública, preencha `defect_type="Com ruído"`.
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
  "suggested_reply_pt_br": "Vi na foto que a luminária pública está com o globo quebrado. Vou te mandar um formulário rapidinho pra confirmar os dados (o endereço eu pergunto depois)."
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
