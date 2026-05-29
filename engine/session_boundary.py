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
    r"cartao|divida|debito|parcelamento"
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
]
_CLOSE_RE = [re.compile(p) for p in _CLOSE_PATTERNS]


def detect_close_intent(text: str) -> bool:
    """True quando o texto do cidadão sinaliza encerrar o atendimento."""
    norm = normalize(text)
    return bool(norm) and any(rx.search(norm) for rx in _CLOSE_RE)


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
    for close_idx in reversed(close_idxs):
        for j in range(close_idx + 1, len(msgs)):
            if is_human(msgs[j]):
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
