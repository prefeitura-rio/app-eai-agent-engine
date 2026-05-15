"""
Template generator pra módulos de prompt de mídia analisável.

Atualmente reusado por `vision_inbound` (imagens) e `audio_inbound` (áudios).
Adicionar suporte futuro a vídeo (ou outro tipo analisável via Gemini multimodal)
vira: criar nova `AnalyzableMediaSpec` + arquivo `<tipo>_inbound.py` que chama
`render_module_prompt(spec)`.

Por que template-driven em vez de copy-paste:
- Garante que mudanças de protocolo (ex: novo arg `meta_mime_type`, nova
  prioridade de fonte) propaguem pra todos os tipos simultaneamente.
- Mantém wording-sensitive sections (regras de classificação) específicas de
  cada tipo no próprio arquivo, evitando sobre-abstração.

Por que NÃO um único arquivo "media_analysis_module.py" gerando tudo:
- Cada arquivo de tipo (vision_inbound, audio_inbound) carrega a sua
  `MODULE_NAME` única — exigida pelo composer (`prompt_modules/__init__.py`)
  pra entrar no version suffix observável (`v179+media_inbound+vision_inbound`).
- Permite ENABLED_MODULES desligar um tipo sem afetar outro.

ADR-018, 2026-05-14 noite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class AnalyzableMediaSpec:
    """Configuração imutável por tipo de mídia analisável.

    Cada `<tipo>_inbound.py` cria uma instância e chama `render_module_prompt`.
    """

    # Identificador único — vira `MODULE_NAME` (aparece no version suffix).
    module_name: str
    # Tipo no prefix do gateway (`[INBOUND_MEDIA] type=<media_type>`).
    media_type: str
    # Nome da tool MCP correspondente.
    analyze_tool: str
    # Domínio textual usado em frases ("imagem"/"foto" vs "áudio"/"voz").
    domain_noun_singular: str  # "imagem", "áudio"
    domain_noun_indefinite: str  # "uma imagem", "um áudio"
    domain_action: str  # "analisar" (image) vs "ouvir/transcrever" (audio)
    domain_action_present: str  # "análise" vs "transcrição"
    # Allowlist de extensions aceitas pela tool (afeta o gate decision).
    accepted_extensions: Sequence[str]
    # Extensions NÃO aceitas mas conhecidas (mencionadas pra LLM saber rejeitar).
    rejected_extensions_note: Optional[str] = None
    # Nome do arg de bytes inline (`image_bytes_base64` vs `audio_bytes_base64`).
    # Test contract exige esse nome literal no prompt.
    bytes_base64_arg_name: str = "bytes_base64"
    # Nome do arg de caminho local (`local_image_path` vs `local_audio_path`).
    local_path_arg_name: str = "local_path"
    # Env var que controla o opt-in da tool no MCP. NÃO derivável de
    # media_type — vision usa ENABLE_VISION_ADDENDUM, audio usa
    # ENABLE_AUDIO_ADDENDUM (e não ENABLE_IMAGE_*/ENABLE_AUDIO_*). Quando
    # adicionar tipo novo, defina aqui pra bater com o flag real no MCP.
    enable_env_var: str = "ENABLE_MEDIA_ADDENDUM"
    # Se `True`, prompt instrui pular `{analyze_tool}` quando `user_text`
    # vier com conteúdo real (caption/transcription upstream). Adequado pra
    # áudio (transcription real torna análise redundante) mas NÃO pra
    # imagem (caption não substitui análise visual).
    skip_analyze_on_real_user_text: bool = False
    # Seção markdown adicional após "Quando AS DUAS condições passam".
    # Contém o schema do JSON de análise + regras de interpretação.
    type_specific_guidance: str = ""
    # Exemplo de chamada Meta direto (mostra como passar args).
    example_meta_direct_call: str = ""
    # Exemplo de chamada Salesforce UWC (legacy fallback).
    example_uwc_call: str = ""


# ----------------------------------------------------------------------------
# Renderers de seções
# ----------------------------------------------------------------------------


def _render_header(spec: AnalyzableMediaSpec) -> str:
    return f"## Análise de {spec.domain_noun_singular} inbound (`{spec.analyze_tool}`)"


def _render_opt_in_gate(spec: AnalyzableMediaSpec) -> str:
    return f"""\
### Decisão: chamar `{spec.analyze_tool}` ou pular?

Chamar a tool **somente quando AS DUAS** condições abaixo passarem:

(a) A tool `{spec.analyze_tool}` está disponível no seu toolset
    (opt-in via `{spec.enable_env_var}=true` no MCP — se a tool
    não estiver listada, ela não está disponível).

(b) Você tem ao menos UMA destas fontes de bytes do {spec.domain_noun_singular}
    (em ordem de preferência):

    - `meta_media_id` no JSON do prefix `[INBOUND_MEDIA]` (campo
      `media.meta_media_id`). **Caminho canônico atual em produção
      (ADR-017)** — cidadão veio via Meta webhook direto pro Mule.
      A tool faz 2 GETs no Graph API (metadata + signed CDN URL) com
      `WA_TOKEN`.
    - `salesforce_download_path` no JSON do prefix `[INBOUND_MEDIA]`
      (campo `media.download_path`). Caminho UWC legacy — cidadão veio
      via Salesforce UWC. A tool autentica via OAuth Client Credentials
      e baixa direto do Salesforce REST API.
    - `{spec.bytes_base64_arg_name}` no contexto (raro em produção; LLM trunca >~10KB;
      útil só pra testes manuais).
    - `{spec.local_path_arg_name}` no JSON do prefix (sandbox `/tmp` com `IS_LOCAL=true`).

**Se qualquer uma das 2 condições falhar, NÃO chame a tool.** Volte
inteiramente ao protocolo do módulo "Recepção de mídia" — ele já trata
corretamente a distinção entre placeholder (use `suggested_reply_pt_br`
do registro) vs `user_text` real (use o `user_text` como mensagem do
cidadão, sem pedir pra ele repetir).

> Em produção, **sempre passe `meta_media_id` ou `salesforce_download_path`**
> quando ele estiver presente no prefix `[INBOUND_MEDIA]`. A tool baixa
> bytes sem você precisar copiar string longa via args (que o modelo
> tende a truncar).
"""


def _render_skip_exception(spec: AnalyzableMediaSpec) -> str:
    """Renderiza a exceção "pular analyze se user_text é real" — APENAS pra
    tipos onde user_text upstream substitui o sinal da análise (ex: audio
    com transcrição já feita). Imagem NÃO entra aqui porque caption ≠
    visualização. Codex review 2026-05-15."""
    if not spec.skip_analyze_on_real_user_text:
        return ""
    return f"""

   **EXCEÇÃO — `user_text` real ({spec.domain_noun_singular}):** se `user_text`
   no prefix NÃO é placeholder (vazio/`[Cidadao enviou `/`[Cidadão enviou `/
   `[INBOUND_MEDIA`) e tem conteúdo significativo (transcrição upstream do
   {spec.domain_noun_singular}), o cidadão já forneceu a informação por texto —
   `register` suficiente. **Não force `{spec.analyze_tool}` nesse caso**, use o
   `user_text` como a mensagem real e siga o fluxo. Evita chamada Gemini
   desnecessária."""


def _render_call_section(spec: AnalyzableMediaSpec) -> str:
    ext_note = (
        f"\n     **Allowlist Gemini**: {', '.join(f'`{e}`' for e in spec.accepted_extensions)}."
        if spec.accepted_extensions
        else ""
    )
    rejected = (
        f"\n     {spec.rejected_extensions_note}"
        if spec.rejected_extensions_note
        else ""
    )
    return f"""\
### Quando AS DUAS condições passam, executar análise

1. **Chamar `{spec.analyze_tool}`** logo após o `register_inbound_media`.
   **OBRIGATÓRIO** — sem isso o cidadão recebe apenas o fallback genérico
   do `register_inbound_media`, que NÃO É a resposta desejada quando há
   {spec.domain_noun_indefinite} real:

   - `user_number`: mesmo valor extraído do prefix `[INBOUND_MEDIA]`
   - `message_id`: do prefix se disponível
   - **SE o JSON `media` tem `meta_media_id`** (canal canônico Meta direto, ADR-017):
     - `meta_media_id`: o valor (string) do campo `media.meta_media_id`
     - Não precisa de `file_extension` — tool deriva do MIME real do
       Graph API.
   - **SE o JSON `media` tem `content_version_id`** (UWC legacy):
     - `content_version_id`: `media.content_version_id`
     - `file_extension`: `media.file_extension`{ext_note}{rejected}
     - `salesforce_download_path`: `media.download_path`
   - **SE ambos presentes**: passe `meta_media_id` (a tool prioriza esse caminho).

   **REGRA CRÍTICA:** Quando o prefix `[INBOUND_MEDIA] type={spec.media_type}`
   chegar, você TEM que chamar `{spec.analyze_tool}` ALÉM de
   `register_inbound_media`. Chamar APENAS `register_inbound_media` resulta
   em resposta genérica — isso é regressão.{_render_skip_exception(spec)}

2. **Usar a resposta da {spec.domain_action_present}.** O retorno contém
   `analysis` com os campos específicos do tipo (ver schema abaixo) +
   `suggested_reply_pt_br` baseado na análise. Use **esse**
   `suggested_reply_pt_br` (da análise) como base da resposta ao cidadão —
   NÃO o do `register_inbound_media`, que é genérico.

3. **Iniciar workflow se aplicável** com base em `analysis.workflow_sugerido`
   e `analysis.confianca` (ver type_specific_guidance abaixo).

4. **Fallback se análise falha ou é inconclusiva.** Se a tool retornar erro,
   `problema_detectado=false`/`intencao_detectada=false` com
   `categoria=nao_aplica`, ou `confianca=baixa`, **volte ao protocolo do
   módulo "Recepção de mídia"**.
"""


def _render_examples(spec: AnalyzableMediaSpec) -> str:
    if not (spec.example_meta_direct_call or spec.example_uwc_call):
        return ""
    parts = ["### Exemplos de chamada"]
    if spec.example_meta_direct_call:
        parts.append(f"**Meta webhook direto (canal canônico):**\n```\n{spec.example_meta_direct_call}\n```")
    if spec.example_uwc_call:
        parts.append(f"**UWC legacy (Salesforce ContentVersion):**\n```\n{spec.example_uwc_call}\n```")
    return "\n\n".join(parts)


def render_module_prompt(spec: AnalyzableMediaSpec) -> str:
    """Renderiza o `MODULE_PROMPT` completo a partir da spec.

    Junta header + opt-in gate + call section + type-specific guidance +
    examples na ordem que o LLM espera ler.
    """
    sections = [
        _render_header(spec),
        _render_opt_in_gate(spec),
        _render_call_section(spec),
    ]
    if spec.type_specific_guidance:
        sections.append(spec.type_specific_guidance.rstrip())
    examples = _render_examples(spec)
    if examples:
        sections.append(examples)
    return "\n\n".join(s.rstrip() for s in sections) + "\n"
