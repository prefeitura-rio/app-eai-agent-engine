"""
Módulo de prompt: instruções para o LLM chamar a tool MCP
``analyze_inbound_video`` (Gemini multimodal video) depois de
``register_inbound_media`` quando o cidadão envia um vídeo pelo WhatsApp.

Estrutura espelha ``vision_inbound`` / ``audio_inbound`` via
``AnalyzableMediaSpec`` (ADR-018). Este arquivo fica só com o que é
video-specific: schema do JSON de análise, regras de classificação
visual/auditiva, workflows sugeridos.
"""

from src.prompt_modules._analyzable_media_template import (
    AnalyzableMediaSpec,
    render_module_prompt,
)

MODULE_NAME = "video_inbound"


_VIDEO_GUIDANCE = """\
### Schema da resposta `analyze_inbound_video`

O `analysis` retornado tem o seguinte schema:

```
{
  "descricao": "<o que o video mostra, max 250 chars>",
  "problema_detectado": <true|false>,
  "categoria": "<luminaria_publica | poda_arvore | buraco_via | lixo_irregular | iluminacao_publica | sinalizacao | enchente_alagamento | outro | nao_aplica>",
  "detalhes": "<o que parece estar errado, max 300 chars>",
  "transcricao_audio": "<transcricao fiel do que o cidadao falou, max 500 chars; vazio se nao ha fala>",
  "workflow_sugerido": "<reparo_luminaria | poda_de_arvore | nenhum>",
  "confianca": "<alta|media|baixa>"
}
```

### Workflows triggerable a partir da análise do vídeo

Use `analysis.workflow_sugerido` pra decidir o próximo passo:

- `reparo_luminaria` → confirme e **mande o Flow primeiro**:
  `build_whatsapp_flow_envelope` prefillado com defeito/qtd/local extraídos do vídeo
  (ver REGRA CRÍTICA em "Resposta interativa"). **NÃO** chame `multi_step_service`
  direto nem valide endereço antes: o workflow (e o endereço, mesmo o que o vídeo
  mencionar) só vêm depois do `nfm_reply` do Flow. (Só se não houver Flow disponível,
  aí sim `multi_step_service(service_name="reparo_luminaria")`.)
- `poda_de_arvore` → confirme + chame
  `multi_step_service(service_name="poda_de_arvore")`.
- `nenhum` → use `analysis.descricao` (e `transcricao_audio` se houver)
  como mensagem real do cidadão. **NÃO** peça pra repetir em texto o
  que já foi mostrado/falado no vídeo. Continue o atendimento normal
  baseado no contexto.

### Confiança como guia

- `alta` → siga sem pedir confirmação extra.
- `media` → confirme a interpretação com o cidadão antes de abrir
  chamado ("Pelo vídeo entendi X — confirma?").
- `baixa` → peça mais detalhes ou outra foto/ângulo se relevante.

### Exemplo de uso

Cidadão envia vídeo de luminária piscando à noite, com áudio
"essa luminária na frente do número 30 está piscando há dias":

```
analysis = {
  "descricao": "Vídeo noturno mostrando poste com luminária piscando intermitentemente",
  "problema_detectado": true,
  "categoria": "luminaria_publica",
  "detalhes": "Luminária piscando, falha intermitente; cidadão menciona endereço",
  "transcricao_audio": "essa luminária na frente do número 30 está piscando há dias",
  "workflow_sugerido": "reparo_luminaria",
  "confianca": "alta"
}
```

Próximo passo do LLM: manda o Flow prefillado (`build_whatsapp_flow_envelope`, `service_type="reparo_luminaria"`, `prefill_data={"defect_type": "Piscando"}`) com um body curto ("Recebi seu vídeo — confirma os dados da luminária no formulário."). O endereço (número 30) **não** vai no Flow — é coletado depois do `nfm_reply`.
"""


_SPEC = AnalyzableMediaSpec(
    module_name=MODULE_NAME,
    media_type="video",
    analyze_tool="analyze_inbound_video",
    domain_noun_singular="vídeo",
    domain_noun_indefinite="um vídeo",
    domain_action="analisar",
    domain_action_present="análise",
    accepted_extensions=("mp4", "m4v", "mov", "3gp", "3gpp", "webm"),
    bytes_base64_arg_name="video_bytes_base64",
    local_path_arg_name="local_video_path",
    enable_env_var="ENABLE_VIDEO_ADDENDUM",
    skip_analyze_on_real_user_text=False,  # caption não substitui análise visual+audio
    type_specific_guidance=_VIDEO_GUIDANCE,
)


MODULE_PROMPT = render_module_prompt(_SPEC)
