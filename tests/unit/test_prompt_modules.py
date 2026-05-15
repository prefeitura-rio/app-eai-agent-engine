"""
Testes do mecanismo de composição de prompt modules
(``src.prompt_modules``).

Estes testes não dependem da API de prompt (``EAI_AGENT_URL``) e não exigem
credenciais GCP — exercitam apenas a lógica de composição pura. Para validar
o end-to-end (prompt fetched → composto → entregue ao agent), usar smoke
tests pós-deploy em staging.
"""

from src.prompt_modules import compose, ENABLED_MODULES
from src.prompt_modules import audio_inbound, media_inbound, vision_inbound


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
        assert mod_idx > base_idx, (
            f"Módulo {mod.MODULE_NAME} apareceu antes do base"
        )


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


# ---------- módulo vision_inbound ----------


def test_vision_inbound_module_has_required_attributes():
    """vision_inbound deve seguir o mesmo contrato dos outros módulos."""
    assert hasattr(vision_inbound, "MODULE_NAME")
    assert hasattr(vision_inbound, "MODULE_PROMPT")
    assert isinstance(vision_inbound.MODULE_NAME, str)
    assert isinstance(vision_inbound.MODULE_PROMPT, str)


def test_vision_inbound_module_name_is_stable():
    """MODULE_NAME do vision_inbound vira sufixo no version (e em logs OTel)."""
    assert vision_inbound.MODULE_NAME == "vision_inbound"


def test_vision_inbound_prompt_mentions_analyze_tool():
    """Sanity: prompt deve nomear a tool MCP `analyze_inbound_image` que
    deve ser chamada — sem isso, o LLM não sabe o nome exato e pode
    chutar ou nem tentar."""
    p = vision_inbound.MODULE_PROMPT
    assert "analyze_inbound_image" in p, "Nome da tool MCP de visão ausente"
    assert "register_inbound_media" in p, "Referência à tool antecedente ausente"


def test_vision_inbound_prompt_handles_opt_in_fallback():
    """A tool é opt-in (ENABLE_VISION_ADDENDUM=true no MCP). Quando não
    registrada, LLM nem vê o nome. Mas o prompt precisa instruir o
    fallback explícito pra esse caso pra evitar travamento."""
    p = vision_inbound.MODULE_PROMPT.lower()
    assert "indisponível" in p or "indisponivel" in p or "disponível" in p, (
        "Falta instrução sobre comportamento quando tool não está registrada"
    )


def test_vision_inbound_prompt_warns_about_missing_bytes():
    """analyze_inbound_image NÃO baixa do Salesforce — precisa de
    image_bytes_base64 OU local_image_path. Sem nenhum dos dois, ela
    falha. Prompt deve avisar pra LLM não chamar sem bytes."""
    p = vision_inbound.MODULE_PROMPT
    assert "salesforce_download_path" in p, "Path do SF não documentado"
    assert "image_bytes_base64" in p, "Bytes em base64 não documentados"
    assert "local_image_path" in p, "Path local não documentado"


def test_vision_module_appears_after_media_module_in_enabled():
    """vision_inbound depende semanticamente de media_inbound — a ordem
    das instruções no prompt importa pro LLM resolver "qual reply usar"
    (vision suggested_reply substitui o do register stub)."""
    names = [m.MODULE_NAME for m in ENABLED_MODULES]
    assert "media_inbound" in names
    assert "vision_inbound" in names
    assert names.index("media_inbound") < names.index("vision_inbound"), (
        "vision_inbound deve vir DEPOIS de media_inbound em ENABLED_MODULES"
    )


def test_vision_inbound_workflow_suggestions_in_prompt():
    """Os workflows que a análise visual pode sugerir devem estar
    documentados no prompt pra o LLM saber qual chamar via
    `multi_step_service`."""
    p = vision_inbound.MODULE_PROMPT
    for workflow in ["reparo_luminaria", "poda_de_arvore"]:
        assert workflow in p, f"workflow '{workflow}' não documentado"


# ---------- módulo audio_inbound ----------


def test_audio_inbound_module_has_required_attributes():
    """audio_inbound deve seguir o mesmo contrato dos outros módulos."""
    assert hasattr(audio_inbound, "MODULE_NAME")
    assert hasattr(audio_inbound, "MODULE_PROMPT")
    assert isinstance(audio_inbound.MODULE_NAME, str)
    assert isinstance(audio_inbound.MODULE_PROMPT, str)


def test_audio_inbound_module_name_is_stable():
    """MODULE_NAME do audio_inbound vira sufixo no version (e em logs OTel)."""
    assert audio_inbound.MODULE_NAME == "audio_inbound"


def test_audio_inbound_prompt_mentions_analyze_tool():
    """Sanity: prompt deve nomear a tool MCP `analyze_inbound_audio` que
    deve ser chamada — sem isso, o LLM não sabe o nome exato."""
    p = audio_inbound.MODULE_PROMPT
    assert "analyze_inbound_audio" in p, "Nome da tool MCP de audio ausente"
    assert "register_inbound_media" in p, "Referência à tool antecedente ausente"


def test_audio_inbound_prompt_handles_opt_in_fallback():
    """Tool é opt-in (ENABLE_AUDIO_ADDENDUM=true no MCP). Quando não
    registrada, LLM nem vê o nome. Mas o prompt precisa instruir o
    fallback explícito pra esse caso."""
    p = audio_inbound.MODULE_PROMPT.lower()
    assert "indisponível" in p or "indisponivel" in p or "disponível" in p, (
        "Falta instrução sobre comportamento quando tool não está registrada"
    )


def test_audio_inbound_prompt_documents_byte_sources():
    """analyze_inbound_audio aceita salesforce_download_path (prod),
    audio_bytes_base64 (teste) ou local_audio_path (sandbox). Prompt
    precisa documentar os 3 pra o LLM saber qual usar."""
    p = audio_inbound.MODULE_PROMPT
    assert "salesforce_download_path" in p, "Path do SF não documentado"
    assert "audio_bytes_base64" in p, "Bytes em base64 não documentados"
    assert "local_audio_path" in p, "Path local não documentado"


def test_audio_inbound_prompt_lists_accepted_extensions():
    """O cidadão pode enviar PTT (.oga) ou áudios do menu (.m4a, .mp3 etc.).
    Prompt deve documentar as extensões aceitas pra orientar o LLM."""
    p = audio_inbound.MODULE_PROMPT
    assert "oga" in p, "Extensão PTT WhatsApp (.oga) não documentada"
    # Outras extensões aceitas pela tool — pelo menos uma delas no prompt
    assert any(ext in p for ext in ["m4a", "mp3", "aac", "wav"]), (
        "Nenhuma extensão alternativa de audio documentada"
    )


def test_audio_module_appears_after_media_module_in_enabled():
    """audio_inbound depende semanticamente de media_inbound — a ordem das
    instruções no prompt importa pro LLM resolver "qual reply usar"
    (audio suggested_reply substitui o do register stub)."""
    names = [m.MODULE_NAME for m in ENABLED_MODULES]
    assert "media_inbound" in names
    assert "audio_inbound" in names
    assert names.index("media_inbound") < names.index("audio_inbound"), (
        "audio_inbound deve vir DEPOIS de media_inbound em ENABLED_MODULES"
    )


def test_audio_inbound_workflow_suggestions_in_prompt():
    """Os workflows que a transcrição pode sugerir devem estar documentados
    no prompt pra o LLM saber qual chamar via `multi_step_service`."""
    p = audio_inbound.MODULE_PROMPT
    for workflow in ["reparo_luminaria", "poda_de_arvore"]:
        assert workflow in p, f"workflow '{workflow}' não documentado"


def test_audio_inbound_prompt_instructs_not_to_ask_repeat():
    """analysis.transcricao é mensagem real do cidadão — LLM não deve pedir
    pra repetir em texto. Sem essa instrução, o LLM joga fora a transcrição
    e força fricção desnecessária ('manda em texto pra eu te ajudar')."""
    p = audio_inbound.MODULE_PROMPT.lower()
    assert "não peça" in p or "nao peça" in p or "não pedir" in p, (
        "Falta instrução pra não pedir repetição da transcrição"
    )


def test_audio_inbound_prompt_short_circuits_address_when_available():
    """Se analysis.endereco_mencionado vier preenchido, prompt orienta a
    chamar validate_address direto em vez de pedir o endereço de novo —
    atalho importante de UX."""
    p = audio_inbound.MODULE_PROMPT
    assert "validate_address" in p, "Atalho via validate_address não documentado"
    assert "endereco_mencionado" in p, "Field do atalho não referenciado"


# ---------- regressão: idempotência de chamada ----------


def test_compose_is_pure_and_idempotent():
    """Chamar compose 2x com mesmos argumentos retorna mesmo resultado
    byte-a-byte (sem efeitos colaterais em estado de módulo)."""
    a1, v1 = compose("BASE", "v1")
    a2, v2 = compose("BASE", "v1")
    assert a1 == a2
    assert v1 == v2
