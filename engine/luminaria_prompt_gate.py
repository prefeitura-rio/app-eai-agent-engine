"""Pure local gate for the dynamic `reparo_luminaria` prompt."""

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from engine.luminaria_interactive_prompt import (
    MODULE_PROMPT as INTERACTIVE_RESPONSE_PROMPT,
    interactive_response_dynamic_enabled,
)


_LUMINARIA_PUBLIC_PLACE_PATTERN = (
    r"ruas?|avenidas?|travessas?|estradas?|alamedas?|"
    r"logradouros?|becos?|vielas?|cal[cç]adas?|"
    r"pra[cç]as?|parques?|quadras?|quarteir(?:[aã]o|[õo]es)|"
    r"vias?\s+p[uú]blicas?|"
    r"t[uú]ne(?:l|is)|viadutos?|passarelas?|ciclovias?|escadarias?|orlas?|"
    r"rotat[oó]rias?|"
    r"esquinas?|"
    r"pontos?\s+de\s+[ôo]nibus|"
    r"esta[cç][aã]o\s+(?:do|de)\s+brt|"
    r"esta[cç][õo]es\s+(?:do|de)\s+brt"
)


_LUMINARIA_CORE_TRIGGER_RE = re.compile(
    rf"(?i)\b("
    rf"lumin[aá]rias?|rio\s*-?\s*luz|rioluz|"
    rf"ilumina[cç][aã]o\s+p[uú]blica|"
    rf"luz\s+p[uú]blica|"
    rf"(?:{_LUMINARIA_PUBLIC_PLACE_PATTERN})"
    rf"\s+(?:(?:est[aá]|est[aã]o|t[aá]|ficou|ficaram|ficam|fica)\s+)?"
    rf"escur[ao]s?"
    rf")\b"
)
_LUMINARIA_NAMED_DARK_PUBLIC_PLACE_RE = re.compile(
    rf"(?i)\b(?:{_LUMINARIA_PUBLIC_PLACE_PATTERN})"
    rf"(?:\s+(?!n[aã]o\b|est[aá]\b|est[aã]o\b|t[aá]\b|"
    rf"ficou\b|ficaram\b|ficam\b|fica\b|sem\b|escur[ao]s?\b|"
    rf"no\b|[àa]s\b|mal\b)[\wÀ-ÿ0-9.-]+){{0,6}}"
    rf"\s+(?:(?:est[aá]|est[aã]o|t[aá]|ficou|ficaram|ficam|fica)\s+"
    rf"(?:muito\s+)?)?"
    rf"(?:escur[ao]s?|no\s+escuro|[àa]s\s+escuras|"
    rf"sem\s+(?:ilumina[cç][aã]o|luz)|mal\s+iluminad[ao]s?)\b"
)
_LUMINARIA_LAMP_TRIGGER_RE = re.compile(r"(?i)\bl[aâ]mpadas?\b")
_LUMINARIA_POST_TRIGGER_RE = re.compile(r"(?i)\bpostes?\b")
_LUMINARIA_LIGHT_TRIGGER_RE = re.compile(
    r"(?i)\b(luz(?:es)?|ilumina[cç][aã]o)\b"
)
_LUMINARIA_FIXTURE_TRIGGER_RE = re.compile(
    r"(?i)\b("
    r"bra[cç]os?|hastes?|suportes?|globos?|tampas?|refletor(?:es)?|"
    r"fotoc[eé]lulas?|rel[eé]s?|reator(?:es)?|boca(?:l|is)|soquetes?"
    r")\b"
)
_LUMINARIA_PUBLIC_LOCATION_RE = re.compile(
    rf"(?i)\b(postes?|{_LUMINARIA_PUBLIC_PLACE_PATTERN}|rio\s*-?\s*luz|rioluz)\b"
)
_LUMINARIA_PUBLIC_PLACE_RE = re.compile(
    rf"(?i)\b("
    rf"postes?|{_LUMINARIA_PUBLIC_PLACE_PATTERN}|"
    rf"luz\s+p[uú]blica|ilumina[cç][aã]o|p[uú]blic[ao]|"
    rf"rio\s*-?\s*luz|rioluz"
    rf")\b"
)
_LUMINARIA_ASSET_CONTEXT_RE = re.compile(
    rf"(?i)\b("
    rf"{_LUMINARIA_PUBLIC_PLACE_PATTERN}|"
    rf"luz(?:es)?|ilumina[cç][aã]o|p[uú]blic[ao]|rio\s*-?\s*luz|rioluz|"
    rf"apagad[ao]s?|"
    rf"apagou|apagando|apaga|acende\s+e\s+apaga|"
    rf"queimad[ao]|queimou|piscando|piscou|oscilando|intermitente|"
    rf"meia\s+(?:luz|fase)|aces[ao]|"
    rf"barulho|ru[ií]do|zumbido|chiando|chiou|estalo|estalando|roncando|"
    rf"frac[ao]s?|mal\s+iluminad[ao]s?|"
    rf"pendurad[ao]|danificad[ao]|defeito|defeituos[ao]s?|"
    rf"ca[ií]d[ao]|caiu|quebrad[ao]s?|quebrou|"
    rf"expost[ao]s?|energizad[ao]s?|curto(?:-|\s)?circuito|dando\s+curto|"
    rf"solt[ao]s?|soltou|entortad[ao]s?|entortou|"
    rf"balan[cç]ando|bamb[ao]s?|inst[aá]ve(?:l|is)|"
    rf"(?:prestes\s+a|quase)\s+cair|"
    rf"troca|trocar|substitui(?:r|[cç][aã]o)|"
    rf"repor|reposi[cç][aã]o|"
    rf"n[aã]o\s+(?:acende|liga|funciona|est[aá]\s+funcionando)|"
    rf"escur[ao]s?|sem\s+(?:luz|tampa)"
    rf")\b"
)
_LUMINARIA_PROXIMITY_CONTEXT_RE = re.compile(
    r"(?i)\b("
    r"em\s+frente\s+(?:a|ao|[àa]|da|do|de)\s+(?:minha\s+)?(?:casa|"
    r"n[uú]mero|num(?:ero)?|mercado|bar|loja|com[eé]rcio|"
    r"restaurante|igreja|farm[aá]cia|padaria|creche|upa|"
    r"escola|hospital|posto|cl[ií]nica|pr[eé]dio|condom[ií]nio)|"
    r"perto\s+(?:da|do|de)\s+(?:minha\s+)?(?:casa|mercado|bar|loja|"
    r"com[eé]rcio|restaurante|igreja|farm[aá]cia|padaria|creche|upa|"
    r"escola|hospital|posto|cl[ií]nica|pr[eé]dio|condom[ií]nio)"
    r")\b"
)
_LUMINARIA_RISK_TRIGGER_RE = re.compile(
    r"(?i)\b("
    r"fio(?:s)?|fia[cç][aã]o|cabo(?:s)?|f[aá]isca|choque|"
    r"expost[ao]s?|energizad[ao]s?|curto(?:-|\s)?circuito|dando\s+curto"
    r")\b"
)
_LUMINARIA_PUBLIC_CONTEXT_RE = re.compile(
    rf"(?i)\b("
    rf"lumin[aá]rias?|ilumina[cç][aã]o|rio\s*-?\s*luz|rioluz|"
    rf"l[aâ]mpadas?|postes?|luz\s+p[uú]blica|"
    rf"{_LUMINARIA_PUBLIC_PLACE_PATTERN}"
    rf")\b"
)
_NON_LUMINARIA_TELECOM_RE = re.compile(
    r"(?i)\b("
    r"internet|telefon(?:e|ia)|tv\s+a\s+cabo|fibra(?:\s+[óo]ptica)?|"
    r"banda\s+larga|provedor|operadora|"
    r"(?:cabo|fio)s?\s+(?:da|do|de)\s+(?:claro|net|vivo|tim|oi)|"
    r"(?:claro|net|vivo|tim|oi)\s+(?:fibra|internet|telefone|tv|cabo)"
    r")\b"
)
_NON_LUMINARIA_DISTRIBUTION_RE = re.compile(
    r"(?i)\b("
    r"light|concession[aá]ria|rede\s+el[eé]trica|energia|"
    r"medidor|padr[aã]o\s+de\s+entrada|liga[cç][aã]o\s+nova"
    r")\b"
)
_NON_LUMINARIA_POWER_OUTAGE_RE = re.compile(
    r"(?i)\b("
    r"(?:falta(?:ndo)?|acabou|queda)\s+(?:de\s+)?(?:luz|energia)|"
    r"sem\s+energia|falta\s+de\s+energia"
    r")\b"
)
_NON_LUMINARIA_PRIVATE_PLACE_RE = re.compile(
    r"(?i)\b("
    r"condom[ií]nio|garagem|estacionamento\s+privado|portaria|"
    r"[aá]rea\s+comum|jardim\s+(?:de\s+)?casa|quintal|"
    r"corredor\s+do\s+pr[eé]dio|p[aá]tio\s+da\s+escola|"
    r"salas?(?:\s+de\s+aula)?|quartos?|cozinhas?|banheiros?|"
    r"varandas?|[aá]rea\s+de\s+servi[cç]o"
    r")\b"
)
_NON_LUMINARIA_PRIVATE_ASSET_RE = re.compile(
    r"(?i)\b("
    r"lumin[aá]rias?|l[aâ]mpadas?|luz(?:es)?|ilumina[cç][aã]o|"
    r"refletor(?:es)?|fotoc[eé]lulas?|rel[eé]s?|reator(?:es)?|"
    r"boca(?:l|is)|soquetes?"
    r")\s+(?:da|do|de|na|no|nas|nos)\s+("
    r"lojas?|mercados?|bares?|restaurantes?|farm[aá]cias?|padarias?|"
    r"igrejas?|creches?|upas?|shoppings?|escrit[oó]rios?|"
    r"cl[ií]nicas?|pr[eé]dios?|"
    r"salas?(?:\s+de\s+aula)?|quartos?|cozinhas?|banheiros?|"
    r"varandas?|garagens?|portarias?|quintais?|"
    r"jardim\s+(?:de\s+)?casa"
    r")\b"
)
_NON_LUMINARIA_POST_ASSET_RE = re.compile(
    r"(?i)\bpostes?\s+(?:da|do|de|na|no|nas|nos)\s+("
    r"(?:madeira\s+(?:da|do|de)\s+)?"
    r"(?:cercas?|var(?:al|ais)|antenas?|placas?|alambrados?|"
    r"redes?\s+de\s+v[oô]lei|s[ií]tios?|fazendas?|"
    r"terrenos?|lotes?|quintais?|port[õo]es?|jardins?"
    r"))\b"
)
_TELECOM_WITH_LUMINARIA_OVERRIDE_RE = re.compile(
    r"(?i)\b("
    r"lumin[aá]rias?|l[aâ]mpadas?|"
    r"luz\s+p[uú]blica|ilumina[cç][aã]o\s+p[uú]blica"
    r")\b"
)
_PRIVATE_PLACE_WITH_LUMINARIA_OVERRIDE_RE = re.compile(
    r"(?i)\b("
    r"rio\s*-?\s*luz|rioluz|luz\s+p[uú]blica|"
    r"ilumina[cç][aã]o\s+p[uú]blica|rua|cal[cç]ada"
    r")\b"
)
_POWER_OUTAGE_WITH_LUMINARIA_OVERRIDE_RE = re.compile(
    r"(?i)\b("
    r"lumin[aá]rias?|l[aâ]mpadas?|postes?|rio\s*-?\s*luz|rioluz|"
    r"luz\s+p[uú]blica|ilumina[cç][aã]o\s+p[uú]blica"
    r")\b"
)
_NON_LUMINARIA_SERVICE_RE = re.compile(
    r"(?i)\b([aá]rvore|poda|galho|sem[aá]foro|internet|telefone|tv\s+a\s+cabo)\b"
)
_LUMINARIA_RISK_OVERRIDE_RE = re.compile(r"(?i)\b(f[aá]isca|choque|rioluz)\b")
_LUMINARIA_SCOPE_NEGATION_RE = re.compile(
    r"(?i)\b("
    r"n[aã]o\s+(?:[eé]|eh)\s+"
    r"(?:luz|ilumina[cç][aã]o|lumin[aá]rias?)\s+p[uú]blic[ao]|"
    r"n[aã]o\s+quero\s+(?:abrir\s+)?"
    r"(?:reparo|conserto|chamado)\s+(?:de\s+)?"
    r"(?:lumin[aá]rias?|luz\s+p[uú]blica|ilumina[cç][aã]o\s+p[uú]blica)"
    r")\b"
)
_LUMINARIA_NEGATED_NO_ISSUE_RE = re.compile(
    rf"(?i)\b("
    rf"n[aã]o\s+(?:est[aá]|est[aã]o|t[aá]|ficou|ficaram|fica|ficam)\s+"
    rf"(?:sem\s+(?:ilumina[cç][aã]o|luz)|escur[ao]s?|"
    rf"no\s+escuro|[àa]s\s+escuras|mal\s+iluminad[ao]s?)|"
    rf"(?:{_LUMINARIA_PUBLIC_PLACE_PATTERN})"
    rf"(?:\s+[\wÀ-ÿ0-9.-]+){{0,6}}\s+"
    rf"n[aã]o\s+precisa\s+de\s+"
    rf"(?:ilumina[cç][aã]o|luz|mais\s+postes?)"
    rf")\b"
)
_WHATSAPP_FLOW_SUBMISSION_RE = re.compile(
    r"(?i)^\s*\[SYSTEM\]\s*O cidad[aã]o preencheu o formul[aá]rio WhatsApp"
)


def _message_text_for_prompt_gate(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _should_inject_interactive_response_prompt(messages: list[Any]) -> bool:
    if not interactive_response_dynamic_enabled():
        return False
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = _message_text_for_prompt_gate(message.content)
            if _WHATSAPP_FLOW_SUBMISSION_RE.search(text):
                return False
            has_immediate_public_risk = (
                _LUMINARIA_RISK_OVERRIDE_RE.search(text)
                and _LUMINARIA_PUBLIC_CONTEXT_RE.search(text)
            )
            if (
                _NON_LUMINARIA_TELECOM_RE.search(text)
                and not _TELECOM_WITH_LUMINARIA_OVERRIDE_RE.search(text)
            ):
                return False
            if (
                _NON_LUMINARIA_DISTRIBUTION_RE.search(text)
                and not _TELECOM_WITH_LUMINARIA_OVERRIDE_RE.search(text)
                and not has_immediate_public_risk
            ):
                return False
            if (
                _NON_LUMINARIA_POWER_OUTAGE_RE.search(text)
                and not _POWER_OUTAGE_WITH_LUMINARIA_OVERRIDE_RE.search(text)
            ):
                return False
            if (
                (
                    _NON_LUMINARIA_PRIVATE_PLACE_RE.search(text)
                    or _NON_LUMINARIA_PRIVATE_ASSET_RE.search(text)
                    or _NON_LUMINARIA_POST_ASSET_RE.search(text)
                )
                and not _PRIVATE_PLACE_WITH_LUMINARIA_OVERRIDE_RE.search(text)
            ):
                return False
            if _LUMINARIA_SCOPE_NEGATION_RE.search(text):
                return False
            if (
                _LUMINARIA_CORE_TRIGGER_RE.search(text)
                or _LUMINARIA_NAMED_DARK_PUBLIC_PLACE_RE.search(text)
            ):
                return True
            has_public_lighting_context = (
                _LUMINARIA_LIGHT_TRIGGER_RE.search(text)
                and _LUMINARIA_PUBLIC_LOCATION_RE.search(text)
            )
            has_lamp_public_context = (
                _LUMINARIA_LAMP_TRIGGER_RE.search(text)
                and _LUMINARIA_PUBLIC_PLACE_RE.search(text)
            )
            has_lamp_proximity_context = (
                _LUMINARIA_LAMP_TRIGGER_RE.search(text)
                and _LUMINARIA_PROXIMITY_CONTEXT_RE.search(text)
                and _LUMINARIA_ASSET_CONTEXT_RE.search(text)
            )
            has_light_proximity_context = (
                _LUMINARIA_LIGHT_TRIGGER_RE.search(text)
                and _LUMINARIA_PROXIMITY_CONTEXT_RE.search(text)
                and _LUMINARIA_ASSET_CONTEXT_RE.search(text)
            )
            has_post_context = (
                _LUMINARIA_POST_TRIGGER_RE.search(text)
                and _LUMINARIA_ASSET_CONTEXT_RE.search(text)
            )
            has_fixture_public_context = (
                _LUMINARIA_FIXTURE_TRIGGER_RE.search(text)
                and _LUMINARIA_PUBLIC_PLACE_RE.search(text)
                and _LUMINARIA_ASSET_CONTEXT_RE.search(text)
            )
            if (
                (
                    has_public_lighting_context
                    or has_lamp_public_context
                    or has_lamp_proximity_context
                    or has_light_proximity_context
                    or has_post_context
                    or has_fixture_public_context
                )
                and not _NON_LUMINARIA_SERVICE_RE.search(text)
                and not _LUMINARIA_NEGATED_NO_ISSUE_RE.search(text)
            ):
                return True
            return bool(
                _LUMINARIA_RISK_TRIGGER_RE.search(text)
                and _LUMINARIA_PUBLIC_CONTEXT_RE.search(text)
                and not (
                    _NON_LUMINARIA_SERVICE_RE.search(text)
                    and not _LUMINARIA_RISK_OVERRIDE_RE.search(text)
                )
            )
    return False


def _inject_interactive_response_prompt(messages: list[Any]) -> list[Any]:
    if any(
        isinstance(message, SystemMessage)
        and message.content == INTERACTIVE_RESPONSE_PROMPT
        for message in messages
    ):
        return messages

    injected = SystemMessage(content=INTERACTIVE_RESPONSE_PROMPT)
    insert_at = 0
    for index, message in enumerate(messages):
        if not isinstance(message, SystemMessage):
            break
        insert_at = index + 1
    return [*messages[:insert_at], injected, *messages[insert_at:]]
