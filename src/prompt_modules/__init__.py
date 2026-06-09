"""
Prompt modules — instruções de system prompt mantidas em código (vs no backing
store da API `/eai-agent/api/v1/system-prompt`).

Cada módulo é um arquivo Python que expõe duas constantes:

    MODULE_NAME: str
        Identificador único do módulo (ex: ``"media_inbound"``). Aparece no
        version do prompt final (ex: ``"2026.05.12.1+media_inbound"``) pra
        tornar a composição visível em logs e métricas OTel.
    MODULE_PROMPT: str
        Markdown a ser appendado ao prompt base, separado por ``\\n\\n``.

A função :func:`compose` aplica os módulos listados em ``ENABLED_MODULES``
nessa ordem em cima do prompt base obtido da API.

Por que módulos em código (e não no backing store):

* **Versionável via git**: cada mudança gera diff revisável em PR.
* **Acoplado ao código que ele exige**: instruções pra chamar uma tool MCP
  mudam junto com a versão da tool (ex: novo campo na assinatura).
* **Não exige write-access ao backing store**: equipes downstream
  conseguem evoluir as instruções sem dependência da equipe que mantém a
  API de prompts.

O prompt base continua sendo a fonte autoritativa de comportamento geral do
agente (tom, escopo, fallbacks). Os módulos cobrem apenas integrações
específicas que devem viver ao lado do código de tools.
"""

from typing import Tuple

from loguru import logger

from src.prompt_modules import (
    audio_inbound,
    audio_response,
    emoji_input,
    govbr_auth_gating,
    interactive_general,
    interactive_response,
    luminaria_service_facts,
    media_inbound,
    media_response,
    session_close,
    session_reset,
    video_inbound,
    vision_inbound,
    workflow_continuation,
    whatsapp_flow_inbound,
)

# Ordem importa — define a sequência em que cada módulo aparece no prompt
# final. Pra desabilitar um módulo, removê-lo desta lista (não comentar
# import, pra evitar drift).
#
# vision_inbound e audio_inbound dependem semanticamente de media_inbound
# (referem o protocolo do ``[INBOUND_MEDIA]`` definido lá), portanto vêm
# DEPOIS. O suggested_reply de analyze_inbound_image/_audio substitui o do
# register_inbound_media — a ordem das instruções no prompt importa pro LLM
# resolver o "qual usar".
#
# whatsapp_flow_inbound é independente dos demais (próprio protocolo
# `[FLOW_COMPLETION]`, próprio dispatcher MCP). Ordenado por último —
# media_inbound prefix dá precedência em casos ambíguos (improvável mas
# concebível se um flow_name fizer match com palavra de prefix media).
# audio_response só entra na lista quando a tool MCP correspondente
# (`generate_audio_response`) está disponível em runtime. Lê via
# `getenv_or_action` com `action='ignore'` pra honrar as MESMAS fontes
# que `src.config.env` (root .env + os.environ) sem fail-fast em testes
# que não tem deployment vars setadas. Dois sinais desligam:
#   1. Kill switch coarse: ENABLE_TTS_ADDENDUM=false.
#   2. Exclusão fina: 'generate_audio_response' em MCP_EXCLUDED_TOOLS.
# Sem checagens: o LLM seria instruído a chamar tool não-bound e turns
# explícitos de áudio quebrariam.
from src.utils.infisical import getenv_or_action as _getenv_or_action

_excluded_tools = {
    t.strip()
    for t in (_getenv_or_action("MCP_EXCLUDED_TOOLS", action="ignore", default="") or "").split(",")
    if t.strip()
}
_audio_response_enabled = (
    (_getenv_or_action("ENABLE_TTS_ADDENDUM", action="ignore", default="true") or "true").lower() != "false"
    and "generate_audio_response" not in _excluded_tools
)
# `media_response` (ADR-022) gate: registra a instrução pra send_whatsapp_media
# apenas quando a tool MCP correspondente está bound. Mesma estratégia do
# audio_response — sem checagens, LLM seria instruído a chamar tool não-bound
# e turns com pedido de mídia produziriam erro de tool unknown.
_media_response_enabled = (
    (_getenv_or_action("ENABLE_MEDIA_RESPONSE", action="ignore", default="true") or "true").lower() != "false"
    and "send_whatsapp_media" not in _excluded_tools
)
# `interactive_response` (ADR-024) gate: registra instruções pros tools
# build_whatsapp_flow_envelope/send_whatsapp_buttons/send_whatsapp_list.
# (MCP server renomeou em 2026-05-18 a versão low-level pra
# build_whatsapp_flow_envelope; o nome send_whatsapp_flow agora é da
# variante high-level que requer user_number — não usada por este prompt.)
# Módulo é desabilitado quando o kill-switch ENABLE_INTERACTIVE_RESPONSE
# vira "false" OU todas as 3 tools que ele orienta estão bloqueadas em
# MCP_EXCLUDED_TOOLS. Pra migration compat, aceita `send_whatsapp_flow`
# como alias do antigo nome low-level (deployments preexistentes que
# excluíam o nome antigo continuam desativando o módulo como esperado).
_flow_builder_blocked = (
    "build_whatsapp_flow_envelope" in _excluded_tools
    or "send_whatsapp_flow" in _excluded_tools  # legacy alias do low-level
)
_interactive_response_enabled = (
    (_getenv_or_action("ENABLE_INTERACTIVE_RESPONSE", action="ignore", default="true") or "true").lower() != "false"
    and not (
        _flow_builder_blocked
        and "send_whatsapp_buttons" in _excluded_tools
        and "send_whatsapp_list" in _excluded_tools
    )
)

# `govbr_auth_gating` gate: ATIVADO POR PADRÃO (opt-out), mesmo padrão dos gates
# acima (``!= "false"``). Antes era opt-in (exigia ENABLE_GOVBR_AUTH=true), mas o
# flag nunca chegava ao env do DEPLOY: o deploy lê o Infisical em root
# NÃO-recursivo e a var ficava em subpasta (o runtime k8s, recursivo, a via; o
# deploy não), então o módulo ficava sempre OFF apesar de ``true`` no UI. Agora
# liga por padrão; só ``ENABLE_GOVBR_AUTH=false`` explícito desliga (kill-switch
# em código). A preocupação de "instruir tool não-bound" é tratada no PRÓPRIO
# prompt do módulo (instrui o LLM a não chamar uma tool govbr indisponível).
_govbr_auth_raw = _getenv_or_action("ENABLE_GOVBR_AUTH", action="ignore", default="")
_govbr_auth_enabled = (_govbr_auth_raw or "").strip().lower() != "false"

# `session_reset` gate: registra a INSTRUÇÃO pra o LLM chamar a tool MCP
# `reset_session_state` no encerramento. Mesma estratégia de
# audio_response/media_response — sem o gate, o LLM seria instruído a chamar tool
# não-bound e o turno de encerramento produziria erro de tool unknown. Por isso
# este módulo é separado do `session_close` (sempre ativo, deliberadamente
# sem-tool): a despedida continua funcionando mesmo sem a instrução de limpeza.
#
# Dois níveis de desligamento, com semânticas DIFERENTES (igual aos gates acima):
#   1. 'reset_session_state' em MCP_EXCLUDED_TOOLS → desbinda a tool no deploy E
#      remove o módulo: limpeza totalmente desligada.
#   2. ENABLE_SESSION_RESET=false → remove só a INSTRUÇÃO do prompt. A tool, se
#      ainda bound, segue chamável pelo modelo (a própria descrição dela orienta
#      o uso) — é um "soft off" do nudge, não um unbind. Pra desligar de vez,
#      use o nível 1.
_session_reset_enabled = (
    (_getenv_or_action("ENABLE_SESSION_RESET", action="ignore", default="true") or "true").lower() != "false"
    and "reset_session_state" not in _excluded_tools
)

# `luminaria_service_facts`: fatos oficiais do reparo de luminaria (prazos 3/4
# dias corridos, Light 0800 p/ falta de energia, e — central — preservar
# LITERALMENTE prazo/defeito/local/quantidade/endereco em retomadas). ESTÁTICO e
# sempre-on, e ANTES de workflow_continuation, pra que retomadas factuais ("qual o
# prazo mesmo?") peguem o fix mesmo fora do gate dinâmico de luminária. Conteúdo
# auto-escopado por contexto ("use quando o contexto recente for luminária";
# "se a retomada falar de outro serviço, não aplique"). Re-land do #104 — fix do
# `critical_fact_accuracy` (eval #104: 0.70-0.73 vs baseline 0.68 sobre o mesmo
# v180; o engine sem ele ficava em 0.60).
ENABLED_MODULES = [
    luminaria_service_facts,
    workflow_continuation,
    session_close,
    emoji_input,
    media_inbound,
    vision_inbound,
    audio_inbound,
    video_inbound,
    whatsapp_flow_inbound,
]
if _audio_response_enabled:
    ENABLED_MODULES.append(audio_response)
if _media_response_enabled:
    ENABLED_MODULES.append(media_response)
if _govbr_auth_enabled:
    ENABLED_MODULES.append(govbr_auth_gating)
if _session_reset_enabled:
    ENABLED_MODULES.append(session_reset)
# `interactive_general`: orientação interativa GERAL (matriz buttons/list,
# Flow genérico, anti-drop) — ESTÁTICA e sempre-on, pra TODOS os serviços. Restaura
# o comportamento do baseline `33ef866` que o #105 perdeu ao tornar o
# interactive_response exclusivo de luminária (regressão `servicos`:
# answer_completeness 0.17→0.03, proactivity 0.56→0.39). Não contém conteúdo de
# luminária — DELEGA luminária ao módulo dinâmico (abaixo). Mesmo gate dos demais
# (`_interactive_response_enabled`) → kill-switch coerente entre os dois caminhos.
if _interactive_response_enabled:
    ENABLED_MODULES.append(interactive_general)

# `interactive_response` (conteúdo LUMINÁRIA, em luminaria_interactive_prompt) é
# carregado DINAMICAMENTE pelo pre_model_hook apenas em turnos de luminária. Manter
# o conteúdo PESADO de luminária fora do prompt global evita contaminação de
# `servicos`/`memory`/demais domínios — enquanto o `interactive_general`
# acima devolve a orientação GERAL (não-luminária) ao prompt global.
INTERACTIVE_RESPONSE_DYNAMIC_ENABLED = _interactive_response_enabled

# Observability — os gates opcionais resolvem em import-time e ficam invisíveis
# fora do sufixo de version. Logar a decisão (+ presença do flag govbr, SEM o
# valor) torna o deploy diagnosticável. Com o opt-out, ``govbr_auth_gating=True``
# é o esperado mesmo com ``present=False`` (flag ausente → default ON); só
# ``present=True`` + ``govbr_auth_gating=False`` indica desligamento explícito
# (ENABLE_GOVBR_AUTH=false).
logger.info(
    "prompt_modules optional gates: audio_response={} media_response={} "
    "interactive_response={} govbr_auth_gating={} session_reset={} "
    "(ENABLE_GOVBR_AUTH present={})",
    _audio_response_enabled,
    _media_response_enabled,
    _interactive_response_enabled,
    _govbr_auth_enabled,
    _session_reset_enabled,
    bool((_govbr_auth_raw or "").strip()),
)


def compose(base_prompt: str, base_version: str) -> Tuple[str, str]:
    """
    Append os módulos enabled ao prompt base e retorna prompt+version composto.

    Args:
        base_prompt: conteúdo bruto retornado pela API de system prompt.
        base_version: versão retornada pela API (ex: ``"2026.05.12.1"`` ou
            ``"FallBack"`` quando a API falha).

    Returns:
        Tuple ``(augmented_prompt, augmented_version)``.

        Quando ``ENABLED_MODULES`` está vazio, retorna o par original sem
        alteração (backward-compat se todos os módulos forem desligados).

        Quando há módulos, ``augmented_version`` ganha sufixo no formato
        ``"<base_version>+<mod1>+<mod2>+..."`` na ordem de ``ENABLED_MODULES``.
    """
    if not ENABLED_MODULES:
        return base_prompt, base_version

    parts = [base_prompt]
    suffixes = []
    for mod in ENABLED_MODULES:
        parts.append(mod.MODULE_PROMPT)
        suffixes.append(mod.MODULE_NAME)

    augmented_prompt = "\n\n".join(parts)
    augmented_version = f"{base_version}+{'+'.join(suffixes)}"
    return augmented_prompt, augmented_version


__all__ = [
    "compose",
    "ENABLED_MODULES",
    "INTERACTIVE_RESPONSE_DYNAMIC_ENABLED",
    "interactive_general",
    "interactive_response",
]
