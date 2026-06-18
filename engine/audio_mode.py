"""Modo áudio contínuo — preferência durável derivada do histórico.

O cidadão pode pedir para receber as respostas **sempre** em áudio (preferência
contínua) ou voltar para texto. O Engine não tem um store de configuração por
usuário, então a preferência é derivada **deterministicamente** do histórico de
conversa persistido (a diretiva mais recente vence) e **reinjetada todo turno**
no input do LLM pelo ``pre_model_hook`` do agente.

Por que assim:
- **Durável**: o checkpointer já persiste as mensagens, então a diretiva
  sobrevive entre turnos sem precisar de um campo novo no schema de estado.
- **Confiável**: a diretiva é reaplicada a cada turno (não depende do LLM
  "lembrar" de uma instrução antiga), e a injeção é determinística, não
  inferência do modelo.
- **Não-persistente**: a diretiva entra só em ``llm_input_messages`` (o canal
  que o agente usa para o input do LLM sem gravar no histórico), igual ao
  filtro de memória de curto prazo.

Distinção importante: um pedido pontual ("me responde com áudio") **não** liga o
modo contínuo — isso é tratado por turno pelo prompt module ``audio_response``.
O modo contínuo liga com marcadores de continuidade ("sempre", "fica",
"continua", "só áudio", "não precisa escrever") OU com sinais de acessibilidade
("não sei ler", "analfabeto", "deficiente visual" — o cidadão que não lê precisa
de áudio por necessidade, não preferência).
"""

import re
from typing import Any, Mapping, Sequence

from langchain_core.messages import SystemMessage

from engine.session_boundary import current_session_messages
from engine.text_match import is_human, message_text, normalize

# Diretiva reinjetada todo turno quando o modo contínuo está ligado. Embute a regra
# crítica (Feature 2b): em modo áudio o WhatsApp entrega o áudio ISOLADO — o texto
# que acompanha a resposta NÃO chega ao cidadão (Mule, webhook-flow.xml: áudio sem
# prelúdio textual). Logo a resposta COMPLETA precisa estar falada no áudio; não
# adianta resumir e deixar os detalhes no texto (eles se perderiam). Isso também
# resolve o conflito com a regra "conteúdo estruturado vai em texto" do prompt module
# (aqui a diretiva tem precedência). O 2º balão de texto pra dado crítico
# (protocolo/URL) é trabalho deferido (gargalo Meta: 1 tipo por mensagem) — por ora
# o próprio áudio carrega tudo.
AUDIO_MODE_DIRECTIVE = (
    "MODO ÁUDIO CONTÍNUO ATIVO. O cidadão pediu para receber as respostas SEMPRE "
    "em áudio até pedir o contrário (ex.: 'volta pra texto'). Neste modo o ÁUDIO é a "
    "ÚNICA mensagem entregue ao cidadão — o texto que acompanha a resposta NÃO chega "
    "(o WhatsApp entrega o áudio isolado). Por isso: componha a resposta COMPLETA em "
    "texto natural falável (sem markdown nem emoji) e chame "
    "generate_audio_response(text=<resposta completa>), anexando o audio_base64. "
    "TUDO que o cidadão precisa saber tem que estar FALADO no áudio — NÃO mande um "
    "resumo curto deixando os detalhes só no texto, eles se perderiam. Se houver "
    "dado crítico (número de protocolo, CEP, link), fale-o de forma clara e pausada "
    "no próprio áudio (ex.: protocolo dígito a dígito). Só pare de gerar áudio "
    "quando o cidadão pedir explicitamente."
)

# Padrões normalizados (sem acento, minúsculo). OFF é checado antes de ON por
# mensagem, e os conjuntos são disjuntos por construção (ver testes).
_ON_PATTERNS = [
    r"sempre.{0,15}(audio|falando|voz|fala\b)",
    r"(audio|falando|voz).{0,15}sempre",
    r"(fica|ficar|continua|continuar|deixa).{0,15}(no |em |de )?(audio|falando|voz)",
    r"\bso\b.{0,6}(audio|voz|falando)",
    r"tudo.{0,10}(audio|voz|falando)",
    r"nao precisa.{0,12}escrever",
    r"para de escrever",
    r"(responde|responda|me responde|fala).{0,15}sempre.{0,15}(falando|audio|voz)",
    # Acessibilidade: cidadão que NÃO LÊ (analfabetismo / baixa visão) precisa de
    # áudio CONTÍNUO — é necessidade, não preferência pontual, por isso liga o modo
    # durável (reinjetado todo turno, não "reverte sozinho"). Viés pró-áudio é
    # proposital num serviço público: o custo de não atender quem não lê supera o
    # de gerar um áudio a mais (reversível com "volta pra texto"). POC1 #296.
    r"nao sei ler\b",
    r"nao sei le\b",  # coloquial "não sei lê"
    r"nao consigo ler\b",
    r"\bnao leio\b",
    r"\banalfabet",  # analfabeto/a/ismo
    r"dificuldade.{0,15}(de |pra |para )?ler\b",
    # "deficiente visual" é inequívoco; deliberadamente NÃO incluímos "nao enxergo"
    # — neste bot (luminária) "não enxergo nada na rua" descreve o escuro do poste,
    # não dificuldade de leitura → seria falso-positivo no fluxo principal.
    r"deficiente visual",
]

_OFF_PATTERNS = [
    r"volta.{0,15}(texto|escrev|escrit|ler)",
    r"(para|parar|chega|pode parar|desliga|cancela).{0,10}(de |com |o )?audio",
    r"sem audio",
    r"nao precisa.{0,12}audio",
    r"(manda|responde|responda|prefiro|quero).{0,15}(texto|escrito|escrevendo|por escrito)",
    r"prefiro ler",  # "ler" só como OFF explícito — evita casar "quero ler o edital"
    r"escreve (ai|pra mim|aqui)",
    r"pode escrever",
]

_ON_RE = [re.compile(p) for p in _ON_PATTERNS]
_OFF_RE = [re.compile(p) for p in _OFF_PATTERNS]


def derive_audio_mode(messages: Sequence[Any]) -> bool:
    """Deriva o modo áudio contínuo do histórico (diretiva mais recente vence).

    Varre as mensagens do cidadão da mais nova para a mais antiga. A primeira que
    casar uma diretiva decide: OFF (voltar a texto) → ``False``; ON (sempre áudio)
    → ``True``. Sem diretiva → ``False`` (texto é o default).

    Por mensagem, OFF é avaliado antes de ON; os conjuntos são disjuntos, então a
    ordem só importa em mensagens contraditórias (raro), onde texto vence por
    segurança.
    """
    for message in reversed(list(messages)):
        if not is_human(message):
            continue
        text = normalize(message_text(message))
        if not text:
            continue
        if any(rx.search(text) for rx in _OFF_RE):
            return False
        if any(rx.search(text) for rx in _ON_RE):
            return True
    return False


def audio_mode_directive_message() -> SystemMessage:
    """SystemMessage com a diretiva de modo áudio contínuo (reinjetada por turno)."""
    return SystemMessage(content=AUDIO_MODE_DIRECTIVE)


def inject_audio_directive(state: Mapping[str, Any], final_state: dict) -> dict:
    """Anexa a diretiva de áudio ao input do LLM quando o modo contínuo está ON.

    Pura e idempotente por turno. Lê a preferência só do atendimento ATUAL
    (``current_session_messages`` — reseta após um encerramento), e injeta a
    diretiva no canal não-persistente ``llm_input_messages``, preservando
    qualquer transformação anterior (memória, filtro, thread_id, reset de
    sessão) já aplicada em ``final_state``. Não mexe em ``messages`` (o canal
    persistido).
    """
    if not derive_audio_mode(current_session_messages(state.get("messages", []))):
        return final_state

    base = final_state.get("llm_input_messages")
    if base is None:
        base = final_state.get("messages") or list(state.get("messages", []))

    return {
        **final_state,
        "llm_input_messages": [*base, audio_mode_directive_message()],
    }
