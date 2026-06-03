"""Boundary de sessão — reset real do atendimento ao encerrar.

O módulo de prompt ``session_close`` faz o bot se despedir, mas é puramente
conversacional: não reseta estado nenhum. Como o ``thread_id`` é o telefone
(fixo) e o checkpointer persiste tudo, a conversa seguinte continua o MESMO
thread — então preferências (ex.: modo áudio contínuo), contexto e workflow
"vazam" pro próximo atendimento mesmo depois de um "encerrar".

Este módulo dá um reset **comportamental** determinístico, no Engine, sem
tocar Gateway nem deletar Postgres:

- ``detect_close_intent`` reconhece a intenção clara de encerrar (conservador —
  prefere não detectar a detectar errado, pra nunca apagar contexto no meio de
  uma conversa por engano).
- ``current_session_messages`` devolve só as mensagens do atendimento ATUAL —
  ou seja, a partir da primeira mensagem do cidadão DEPOIS do último
  encerramento já respondido. O ``pre_model_hook`` usa isso pra truncar o
  ``llm_input_messages`` (canal não-persistente) e o ``audio_mode`` deriva a
  preferência só dessa fatia. Resultado: depois de "tchau", a próxima mensagem
  começa limpa (contexto + áudio resetados); a memória de longo prazo (injetada
  à parte como SystemMessage) persiste por design.

Reset "duro" (rotacionar thread_id no Gateway + limpar checkpoints) fica como
follow-up — resolve também o crescimento de storage do thread.
"""

import re
from typing import Any, List, Mapping, Sequence

from langchain_core.messages import SystemMessage

from engine.text_match import is_human, message_text, normalize

# Sinais de encerramento (normalizados, sem acento). Conservador de propósito:
# frases claras de "acabou", não meras gratidões ("obrigado"/"valeu" sozinhos),
# pra evitar falso-positivo que truncaria contexto no meio do atendimento.
# Substantivos que tornam "encerrar X" um PEDIDO DE SERVIÇO, não fim de sessão
# (ex.: "quero encerrar minha conta de luz" / "vou encerrar a matrícula"). O
# padrão de "encerrar" abaixo usa negative-lookahead pra NÃO casar esses casos.
_SERVICE_NOUNS = (
    r"conta|contrato|matricula|inscricao|cadastro|plano|empresa|negocio|mei|"
    r"servico|chamado|protocolo|pedido|solicitacao|assinatura|beneficio|linha|"
    r"cartao|divida|debito|parcelamento|fila"
)
_CLOSE_PATTERNS = [
    r"\btchau\b",
    r"era so isso",
    r"so isso mesmo",
    # "encerrar" como fim de atendimento ("pode encerrar", "quero encerrar",
    # "encerrar atendimento/conversa"), mas NÃO "encerrar <serviço>".
    rf"\bencerrar\b(?!\s+(a |o |um |uma |uns |umas |minha |meu |meus |minhas |esse |este |essa |esta )*({_SERVICE_NOUNS}))",
    r"finalizar (o |a )?atendimento",
    r"\bate (mais|logo|a proxima|breve)\b",
    # "não preciso de mais nada" como fim, mas não "...nada além do boleto".
    r"nao preciso (de )?mais nada(?!\s+(alem|que|fora|exceto|a nao ser|so))",
    r"nao preciso de mais ajuda",
    # "sair" como fim de atendimento ("quero sair", "sair"), com o MESMO
    # negative-lookahead de servico de "encerrar" — pra NAO casar "sair da
    # conta/cadastro/fila/chamado" (pedido de servico, nao fim de sessao).
    rf"\bsair\b(?!\s+(da |do |de |a |o |um |uma |minha |meu |meus |minhas |esse |este |essa |esta )*({_SERVICE_NOUNS}))",
    # "parar/cancelar atendimento|conversa" EXPLICITO. Bare "parar"/"cancelar"
    # ficam de fora de proposito: colidiriam com comandos de audio ("parar o
    # audio", "cancela audio" — ver engine/audio_mode.py) e com "cancelar o
    # chamado" (pedido de servico).
    r"\b(parar|cancelar)\s+(o |a |esse |este |meu |minha )?(atendimento|conversa)\b",
]
_CLOSE_RE = [re.compile(p) for p in _CLOSE_PATTERNS]


def detect_close_intent(text: str) -> bool:
    """True quando o texto do cidadão sinaliza encerrar o atendimento."""
    norm = normalize(text)
    return bool(norm) and any(rx.search(norm) for rx in _CLOSE_RE)


# Respostas curtas que RESOLVEM o handshake de encerramento ("quer cancelar ou
# concluir?"). Formas normalizadas (sem acento, minúsculas — ver `normalize`).
# Conservador de propósito: uma confirmação fora desta lista (rara) é tratada
# como sessão nova — pior caso é perder 1 turno de contexto, NÃO vazar pra
# sempre. O objetivo é só não orfanar o "sim"/"cancelar" comum.
_CLOSE_ANSWER = {
    "sim", "s", "isso", "isso mesmo", "isso ai", "claro", "ok", "okay",
    "pode", "pode sim", "aham", "uhum", "positivo", "confirmo", "confirma",
    "nao", "n", "negativo",
    "cancelar", "cancela", "pode cancelar", "quero cancelar", "sim cancelar",
    "concluir", "quero concluir", "continuar", "manter", "completar",
    "nao quero", "sim quero", "quero",
}


def _ends_with_question(text: str) -> bool:
    """True se a mensagem termina numa PERGUNTA (último bloco de pontuação de
    frase contém '?'), ignorando espaços/emoji finais. Trata '?', '? 🤔',
    '?!', '?...'. Usado pra detectar que o turno anterior do bot foi pergunta.
    """
    s = (text or "").rstrip()
    while s and not (s[-1].isalnum() or s[-1] in "?!."):
        s = s[:-1].rstrip()
    trailing = ""
    while s and s[-1] in "?!.":
        trailing = s[-1] + trailing
        s = s[:-1]
    return "?" in trailing


def _resolves_close_handshake(prev: Any, human_text: str) -> bool:
    """O cidadão está RESPONDENDO a uma pergunta de confirmação de encerramento?

    True quando o turno anterior do bot (``prev``) é uma PERGUNTA e a mensagem do
    cidadão é uma resposta de handshake (confirmar/cancelar) — caso em que ela
    NÃO inicia sessão nova. Restrito a respostas curtas conhecidas (ou outro
    sinal de encerrar) pra não engolir um pedido novo legítimo que por acaso
    venha depois de uma pergunta de cortesia do bot.
    """
    if prev is None or is_human(prev) or not _ends_with_question(message_text(prev)):
        return False
    # `normalize` só minúscula + tira acento — NÃO tira pontuação/emoji/espaço.
    # Tira das pontas pra casar as formas mais comuns no WhatsApp: "Sim.",
    # "Sim!", "Sim 👍", "claro!", "👍 sim". Espaço interno preservado
    # ("pode cancelar" continua casando).
    norm = normalize(human_text).strip()
    while norm and not norm[-1].isalnum():
        norm = norm[:-1].rstrip()
    while norm and not norm[0].isalnum():
        norm = norm[1:].lstrip()
    return norm in _CLOSE_ANSWER or detect_close_intent(human_text)


def current_session_messages(messages: Sequence[Any]) -> List[Any]:
    """Mensagens do atendimento ATUAL (após o último encerramento já respondido).

    Um encerramento "completo" é uma mensagem do cidadão com intenção de fechar
    que **já foi seguida** por uma nova mensagem do cidadão (o próximo
    atendimento). Devolve a fatia a partir dessa nova mensagem. Se o
    encerramento é a última mensagem do cidadão (turno de despedida em si, sem
    follow-up), devolve tudo — pra a despedida ser contextual. Sem encerramento,
    devolve tudo.
    """
    msgs = list(messages)
    close_idxs = [
        i
        for i, m in enumerate(msgs)
        if is_human(m) and detect_close_intent(message_text(m))
    ]
    if not close_idxs:
        return msgs
    # Do encerramento mais recente pro mais antigo: o primeiro que tiver uma
    # mensagem do cidadão depois dele marca o início do atendimento atual.
    #
    # EXCEÇÃO (handshake de encerramento): quando há workflow ativo, o
    # ``session_close`` faz o bot CONFIRMAR antes ("quer concluir ou cancelar?").
    # A resposta do cidadão ("sim"/"cancelar") NÃO inicia sessão nova — ela
    # resolve o encerramento. Sem este guard, o "sim" era truncado pra fora do
    # contexto e o LLM via um "sim" órfão ("Sim, mas sim o quê?"). Regra: só
    # inicia sessão nova no 1º humano cujo turno anterior do bot NÃO foi pergunta.
    for close_idx in reversed(close_idxs):
        for j in range(close_idx + 1, len(msgs)):
            if not is_human(msgs[j]):
                continue
            prev = msgs[j - 1] if j > 0 else None
            if _resolves_close_handshake(prev, message_text(msgs[j])):
                # cidadão confirmando/cancelando o encerramento — handshake em
                # curso, NÃO é sessão nova. Um pedido novo legítimo (fora do set
                # de respostas curtas) cai fora e inicia sessão normalmente.
                continue
            return msgs[j:]
    # Encerramento é o último turno do cidadão → ainda não resetou.
    return msgs


def apply_session_reset(state: Mapping[str, Any], final_state: dict) -> dict:
    """Trunca o input do LLM pro atendimento atual quando houve um encerramento.

    Lê o histórico **persistido** (``state['messages']``); se um encerramento já
    foi seguido por nova mensagem, reconstrói ``llm_input_messages`` =
    SystemMessages (memória de longo prazo / system, preservados) + as mensagens
    de conversa do atendimento atual. Não mexe em ``messages`` (canal
    persistido). No-op quando não há reset.
    """
    full = list(state.get("messages", []))
    session = current_session_messages(full)
    if len(session) >= len(full):
        return final_state  # sem encerramento completo → nada a truncar

    current = final_state.get("llm_input_messages")
    if current is None:
        current = final_state.get("messages") or full

    system_msgs = [m for m in current if isinstance(m, SystemMessage)]
    session_conv = [m for m in session if not isinstance(m, SystemMessage)]
    return {**final_state, "llm_input_messages": [*system_msgs, *session_conv]}
