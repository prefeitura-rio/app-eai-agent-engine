"""Helpers de matching de texto PT-BR compartilhados pelos detectores
determinísticos de intenção (``audio_mode``, ``session_boundary``).

Pequenos, puros e sem estado — extraídos pra um só lugar pra os dois
detectores normalizarem e lerem mensagens da mesma forma (acento-insensível,
tolerante a content em str ou lista de blocos, e a mensagens humano/dict).
"""

import unicodedata
from typing import Any, Mapping

from langchain_core.messages import HumanMessage


def normalize(text: str) -> str:
    """Minúsculo + sem acentos, pra casar frases independente de grafia."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower()


def message_text(message: Any) -> str:
    """Extrai o texto de uma mensagem (content str ou lista de blocos)."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return " ".join(parts)
    return str(content) if content is not None else ""


def is_human(message: Any) -> bool:
    """True se a mensagem é do cidadão (HumanMessage ou role/type human/user)."""
    if isinstance(message, HumanMessage):
        return True
    role = getattr(message, "type", None) or getattr(message, "role", None)
    if role is None and isinstance(message, Mapping):
        role = message.get("type") or message.get("role")
    return role in ("human", "user")
