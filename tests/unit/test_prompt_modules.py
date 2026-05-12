"""
Testes do mecanismo de composição de prompt modules
(``src.prompt_modules``).

Estes testes não dependem da API de prompt (``EAI_AGENT_URL``) e não exigem
credenciais GCP — exercitam apenas a lógica de composição pura. Para validar
o end-to-end (prompt fetched → composto → entregue ao agent), usar smoke
tests pós-deploy em staging.
"""

from src.prompt_modules import compose, ENABLED_MODULES
from src.prompt_modules import media_inbound


# ---------- compose() — comportamento básico ----------


def test_compose_returns_pair_of_strings():
    augmented, version = compose("BASE", "v1.0")
    assert isinstance(augmented, str)
    assert isinstance(version, str)


def test_compose_preserves_base_prompt_content():
    base = "Você é assistente da Prefeitura."
    augmented, _ = compose(base, "v1.0")
    assert base in augmented, "Conteúdo do prompt base não pode ser perdido"


def test_compose_appends_modules_after_base():
    base = "Base do prompt."
    augmented, _ = compose(base, "v1.0")
    # módulos aparecem depois do base
    base_idx = augmented.index(base)
    for mod in ENABLED_MODULES:
        mod_idx = augmented.index(mod.MODULE_PROMPT)
        assert mod_idx > base_idx, f"Módulo {mod.MODULE_NAME} apareceu antes do base"


def test_compose_separates_with_blank_line():
    base = "Base."
    augmented, _ = compose(base, "v1.0")
    # Cada módulo deve estar separado por linha em branco (markdown sectioning)
    assert "\n\n" in augmented


def test_compose_version_appends_module_names():
    _, version = compose("BASE", "v1.0")
    assert version.startswith("v1.0+")
    for mod in ENABLED_MODULES:
        assert mod.MODULE_NAME in version


def test_compose_version_order_matches_modules_order():
    _, version = compose("BASE", "v1.0")
    expected_suffix = "+".join(m.MODULE_NAME for m in ENABLED_MODULES)
    assert version == f"v1.0+{expected_suffix}"


# ---------- compose() — edge cases ----------


def test_compose_with_fallback_version_string():
    """Se a API estiver fora e o base for o fallback, version segue compose."""
    _, version = compose("fallback prompt", "FallBack")
    assert version.startswith("FallBack+")


def test_compose_with_empty_base_prompt():
    """Caller pode passar string vazia (cenário improvável mas defensivo)."""
    augmented, _ = compose("", "v0")
    # Não dá erro; resultado começa com \n\n + módulos
    for mod in ENABLED_MODULES:
        assert mod.MODULE_PROMPT in augmented


def test_compose_with_no_modules_is_passthrough(monkeypatch):
    """
    Se ``ENABLED_MODULES`` for esvaziado (todos os módulos desligados),
    compose vira pass-through completo: prompt e version inalterados.
    """
    import src.prompt_modules as mods

    monkeypatch.setattr(mods, "ENABLED_MODULES", [])
    augmented, version = mods.compose("BASE", "v1.0")
    assert augmented == "BASE"
    assert version == "v1.0"


# ---------- contract dos módulos individuais ----------


def test_media_inbound_module_has_required_attributes():
    """Cada módulo deve expor ``MODULE_NAME`` e ``MODULE_PROMPT`` (contrato
    consumido por ``compose``)."""
    assert hasattr(media_inbound, "MODULE_NAME")
    assert hasattr(media_inbound, "MODULE_PROMPT")
    assert isinstance(media_inbound.MODULE_NAME, str)
    assert isinstance(media_inbound.MODULE_PROMPT, str)


def test_media_inbound_module_name_is_stable():
    """``MODULE_NAME`` vira sufixo no version do prompt — não pode mudar
    silenciosamente porque quebra dashboards/logs OTel que filtram por
    version."""
    assert media_inbound.MODULE_NAME == "media_inbound"


def test_media_inbound_prompt_mentions_protocol_keywords():
    """Sanity: o prompt deve instruir sobre os 3 elementos essenciais
    (prefix, tool e campo de resposta sugerida). Não é teste de conteúdo
    pleno — é guard contra deleção acidental dos pilares."""
    p = media_inbound.MODULE_PROMPT
    assert "[INBOUND_MEDIA]" in p, "Prefix de detecção ausente"
    assert "register_inbound_media" in p, "Nome da tool MCP ausente"
    assert "suggested_reply_pt_br" in p, "Campo de resposta sugerida ausente"


def test_media_inbound_prompt_lists_all_media_types():
    """Os 5 valores válidos de ``media_type`` que o tool MCP aceita devem
    aparecer no prompt — senão o LLM pode rejeitar ou usar tipo errado."""
    p = media_inbound.MODULE_PROMPT
    for media_type in ["image", "audio", "location", "unsupported", "unknown"]:
        assert media_type in p, f"media_type '{media_type}' não documentado"


def test_media_inbound_prompt_distinguishes_placeholder_vs_real_user_text():
    """user_text pode ser placeholder (descartável) OU conteúdo real
    (caption/transcrição). Sem essa distinção no prompt, o LLM pediria pro
    cidadão repetir texto já transcrito upstream — UX ruim. Verifica que o
    prompt instrui distinguir os dois casos."""
    p = media_inbound.MODULE_PROMPT
    # Instrução pra NÃO pedir repetição quando user_text é real
    assert "NÃO" in p.upper() or "não peça" in p.lower(), (
        "Falta instrução pra não pedir repetição em conteúdo real"
    )


def test_media_inbound_prompt_handles_empty_user_text_as_placeholder():
    """Quando gateway aceita media-only sem caption, prefix vira
    `... | user_text=`. Sem instrução explícita, esse vazio cairia pra
    branch de "conteúdo real" — LLM ignoraria suggested_reply_pt_br."""
    p = media_inbound.MODULE_PROMPT.lower()
    assert "vazio" in p or "vazia" in p, (
        "Prompt não trata user_text vazio como placeholder — "
        "media-only sem caption vai pra branch errada"
    )


def test_media_inbound_prompt_covers_both_placeholder_spellings():
    """O Mule sc-inbound-flow.xml hoje envia `[Cidadao enviou` (sem acento)
    por causa do encoding DataWeave. O prompt precisa reconhecer ESSA forma —
    e idealmente a com acento também, pra ficar resiliente a evoluções
    futuras do gateway. Sem o pattern sem-acento, todo o fluxo média-only
    cai pra branch de "user_text real" e o LLM ignora suggested_reply_pt_br."""
    p = media_inbound.MODULE_PROMPT
    assert "[Cidadao enviou " in p, (
        "Pattern sem acento (atual do Mule) não documentado — "
        "media-only flow vai cair pra branch errada"
    )
    assert "[Cidadão enviou " in p, (
        "Pattern com acento não documentado — resiliência futura quebrada"
    )


def test_media_inbound_prompt_omits_unsupported_tool_params_in_call():
    """O tool MCP `register_inbound_media` não aceita `content_document_id`
    como parâmetro (apenas `content_version_id`). O prompt pode mencionar
    `content_document_id` no JSON de entrada do prefix (lá ele aparece como
    metadata bruta vinda do gateway), mas **NÃO** pode aparecer como
    keyword argument na chamada de exemplo da tool — risco de o LLM emitir
    tool call inválido.

    Pattern verificado: ``content_document_id=`` (com sinal de igualdade,
    indicando keyword arg Python-like) não pode existir no prompt."""
    p = media_inbound.MODULE_PROMPT
    forbidden = "content_document_id="
    assert forbidden not in p, (
        f"Prompt usa {forbidden!r} em chamada da tool, "
        "mas a tool não aceita esse parâmetro"
    )


# ---------- regressão: idempotência de chamada ----------


def test_compose_is_pure_and_idempotent():
    """Chamar compose 2x com mesmos argumentos retorna mesmo resultado
    byte-a-byte (sem efeitos colaterais em estado de módulo)."""
    a1, v1 = compose("BASE", "v1")
    a2, v2 = compose("BASE", "v1")
    assert a1 == a2
    assert v1 == v2
