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

from src.prompt_modules import (
    audio_inbound,
    media_inbound,
    video_inbound,
    vision_inbound,
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
ENABLED_MODULES = [
    media_inbound,
    vision_inbound,
    audio_inbound,
    video_inbound,
    whatsapp_flow_inbound,
]


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


__all__ = ["compose", "ENABLED_MODULES"]
