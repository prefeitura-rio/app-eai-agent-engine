"""
Testes do mecanismo de composição de prompt modules
(``src.prompt_modules``).

Estes testes não dependem da API de prompt (``EAI_AGENT_URL``) e não exigem
credenciais GCP — exercitam apenas a lógica de composição pura. Para validar
o end-to-end (prompt fetched → composto → entregue ao agent), usar smoke
tests pós-deploy em staging.
"""

from src.prompt_modules import compose, ENABLED_MODULES
from src.prompt_modules import (
    audio_inbound,
    govbr_auth_gating,
    interactive_response,
    media_inbound,
    session_close,
    session_reset,
    vision_inbound,
    workflow_continuation,
)


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


# ---------- govbr_auth_gating (auth gov.br) ----------


def test_govbr_auth_gating_module_name_is_stable():
    """``MODULE_NAME`` vira sufixo no version — não pode mudar silenciosamente."""
    assert govbr_auth_gating.MODULE_NAME == "govbr_auth_gating"
    assert isinstance(govbr_auth_gating.MODULE_PROMPT, str)


def test_govbr_auth_gating_prompt_mentions_the_three_tools():
    """Guard contra deleção dos nomes EXATOS das tools MCP — se o prompt não
    citar, o LLM não sabe o que chamar."""
    p = govbr_auth_gating.MODULE_PROMPT
    assert "govbr_auth_status" in p
    assert "govbr_auth_init" in p
    assert "govbr_logout" in p


def test_govbr_auth_gating_checks_status_before_init():
    """Política: checar status ANTES de pedir login — não obrigar re-auth de
    quem já está autenticado (gating idempotente)."""
    p = govbr_auth_gating.MODULE_PROMPT
    assert p.index("govbr_auth_status") < p.index("govbr_auth_init")


def test_govbr_auth_gating_lists_restricted_and_public_scope():
    """Sanity da política aprovada: serviços restritos (CPF-bound) + exceção
    pública (zeladoria anônima)."""
    p = govbr_auth_gating.MODULE_PROMPT.lower()
    assert "iptu" in p and "multas" in p, "serviços restritos ausentes"
    assert "anônim" in p, "exceção de zeladoria anônima ausente"


def test_govbr_auth_gating_on_by_default():
    """Default ON (opt-out): o módulo entra em ENABLED_MODULES a menos que
    ENABLE_GOVBR_AUTH=false explícito. O flag do Infisical não chegava ao env do
    DEPLOY (root não-recursivo), então o gating é ligado em código; só ``false``
    explícito desliga. Usa o MESMO source que o gate de produção
    (getenv_or_action lê root .env + os.environ). Pula se o ambiente desliga
    explicitamente."""
    from src.utils.infisical import getenv_or_action

    explicitly_off = (
        getenv_or_action("ENABLE_GOVBR_AUTH", action="ignore", default="") or ""
    ).strip().lower() == "false"
    if explicitly_off:
        import pytest

        pytest.skip("ENABLE_GOVBR_AUTH=false (via env/.env) — desligado explicitamente")
    assert govbr_auth_gating in ENABLED_MODULES


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


def test_interactive_response_prefills_qty_pattern():
    """O exemplo canônico do Flow e a regra de pré-preenchimento devem cobrir
    `qty_pattern` (não só defect_type/location) — senão o modelo imita o exemplo
    e nunca extrai quantidade (logs live: prefill_keys=['defect_type','location'])."""
    p = interactive_response.MODULE_PROMPT
    assert "qty_pattern" in p, "qty_pattern ausente na guidance de prefill"
    # o exemplo canônico precisa demonstrar o prefill da quantidade
    assert '"qty_pattern": "uma"' in p, (
        "exemplo canônico do build_whatsapp_flow_envelope não prefilla qty_pattern"
    )
    # mapeamento de linguagem natural pros IDs canônicos
    for canonical in ("uma", "bloco", "intercaladas"):
        assert canonical in p, f"ID canônico de quantidade '{canonical}' ausente"


def test_interactive_response_scope_is_luminaria_first_not_global_menu():
    """Interativo não deve virar padrão global para todos os serviços."""
    p = interactive_response.MODULE_PROMPT
    assert "Resposta interativa focada em `reparo_luminaria`" in p
    assert "Use resposta interativa proativamente apenas quando ela é necessária" in p
    assert "Fora desse fluxo" in p
    assert "respostas textuais" in p
    assert "Matriz de escolha restrita" in p
    assert "NÃO use" in p
    assert "botões/listas para triagem genérica de serviços" in p
    assert "O service registrado" in p
    assert "coberto por este módulo é `reparo_luminaria`" in p
    assert "Quando o cidadão precisa escolher entre opções discretas, **prefira mensagens interativas**" not in p
    assert "Menu de serviços" not in p


def test_interactive_response_maps_wire_theft_to_valid_defect_type():
    """Furto/cabo/fios deve usar ID canônico do Flow, não valor inventado."""
    p = interactive_response.MODULE_PROMPT
    assert 'defect_type="Danificada"' in p
    assert "furto/roubo" in p
    assert "Nunca use `defect_type` fora dessa lista" in p


def test_interactive_response_wire_theft_is_flow_first():
    """Roubo/furto de fios de poste não deve desviar só para denúncia."""
    p = interactive_response.MODULE_PROMPT
    assert "cabo/fios/furto/roubo de fios" in p
    assert "reparo de luminária Flow-first" in p
    assert "não substitua por" in p
    assert "`google_search`" in p
    assert "nem responda só com Disque Denúncia" in p


def test_interactive_response_wire_hazard_preempts_flow():
    """Fio perigoso deve orientar segurança antes de qualquer formulário."""
    p = interactive_response.MODULE_PROMPT
    assert "Perigo elétrico" in p
    for hazard in ("fio caído", "exposto", "energizado", "faísca", "choque", "poste caído"):
        assert hazard in p
    assert "Bombeiros (193)" in p
    assert "Polícia Militar (190)" in p
    assert "Defesa Civil (199)" in p
    assert "Light (0800 0210196)" in p
    assert "Eu não consigo acionar socorro por você" in p
    assert "preempta out-of-scope, implantação e Flow" in p
    assert "Reparo de poste ou tampão da Rioluz dando choque" in p
    assert "até 6 horas" in p
    assert "Serviço: Reparo de poste ou tampão da Rioluz dando choque" in p
    assert "templates oficiais" in p
    assert "Para risco imediato: Bombeiros (193), Polícia Militar (190), Defesa Civil (199) e Light (0800 0210196)." in p
    assert "socorro por você.\nPara risco imediato: Bombeiros (193)" in p
    assert "ponto de referência.\nServiço: Reparo de poste ou tampão da Rioluz dando choque" in p
    assert "Bombeiros (193), Polícia Militar (190), Defesa Civil (199) e Light (0800 0210196)" in p
    assert "Remoção do risco em até 6 horas" in p
    assert "Light/distribuição elétrica" in p
    assert "concessionária responsável" in p


def test_interactive_response_routes_luminaria_out_of_scope_before_flow():
    """Falta de energia/semáforo não deve abrir Flow de luminária."""
    p = interactive_response.MODULE_PROMPT
    assert "Fora de escopo de luminária" in p
    assert "falta de energia" in p
    assert "semáforo apagado" in p
    assert "0800 0210196" in p
    assert "Nestes casos específicos" in p
    assert "responda direto sem `google_search`" in p
    assert "não abra Flow" in p


def test_interactive_response_distinguishes_light_grid_from_public_lighting():
    """Rede elétrica da Light não deve virar implantação municipal."""
    p = interactive_response.MODULE_PROMPT
    assert "terreno/loteamento sem rede elétrica" in p
    assert "ligação nova" in p
    assert "energia para" in p and "imóvel" in p
    assert "medidor" in p
    assert "padrão de entrada" in p
    assert "instalação de rede/postes de" in p
    assert "distribuição pela Light" in p
    assert "não é `reparo_luminaria`" in p
    assert "não abra Flow" in p
    assert "Light/concessionária" in p
    assert "0800 0210196" in p
    assert "salvo se a mesma mensagem também trouxer" in p
    assert "problema claro de iluminação pública" in p


def test_interactive_response_routes_luminaria_implantation_before_repair_flow():
    """Novo ponto/poste/luz mais forte é implantação, não Flow de reparo."""
    p = interactive_response.MODULE_PROMPT
    assert "Implantação" in p
    assert "novo ponto de luz" in p
    assert "mais postes" in p
    assert "luz mais forte" in p
    assert "Implantação de iluminação pública" in p
    assert "Não abra Flow de reparo" in p
    assert "Serviço: Implantação de iluminação pública" in p
    assert "A primeira linha da resposta deve ser exatamente" in p
    assert "não use `google_search` salvo" in p
    assert "pedir link/URL direto" in p
    assert "endereço completo + ponto de referência" in p
    assert "Rioluz avalia/executa" in p
    assert "Reinstalação de ponto de luz" in p


def test_interactive_response_enriches_luminaria_flow_body():
    """O body do Flow deve carregar serviço/canal/prazo/link antes da tool."""
    p = interactive_response.MODULE_PROMPT
    assert "Body oficial em `reparo_luminaria`" in p
    assert "Body genérico" in p
    assert "Defeito comum" in p
    assert "body=\"Reparo de Luminária (Rioluz)" in p
    assert "Reparo de Luminária" in p
    assert (
        "https://www.1746.rio/hc/pt-br/articles/14187518715931-"
        "Reparo-de-Lumin%C3%A1ria"
    ) in p
    assert "não abra Flow" in p
    assert "Informativo de luminária" in p
    assert "não usa `google_search` nem Flow" in p
    assert "mensagem pedir abertura de chamado para local concreto" in p
    assert "Toda resposta informativa de" in p
    assert "linha literal `Serviço: ...`" in p
    assert "canal/prazo/link sem" in p
    assert "Serviço: Reparo de cabo de iluminação pública" in p
    assert "3460-1746.\nServiço: Reparo de Luminária, da Rioluz." in p
    assert "Rioluz.\nPrazo para defeitos comuns: até 3 dias corridos." in p
    assert "Serviço: Reparo de cabo de iluminação pública.\nTelefone: 1746" in p
    assert "Prazo para defeitos comuns: até 3 dias corridos" in p
    assert "site ou app 1746" in p
    assert "Acesa de dia" in p
    assert "bloco apagado" in p
    assert "Reparo de cabo de iluminação pública" in p
    assert "Não altere os títulos oficiais" in p
    assert "body=\"Reparo de cabo de iluminação pública (Rioluz)" in p
    assert "Serviço: Reparo de cabo de iluminação pública" in p
    assert 'prefill_data={"defect_type": "Danificada"}' in p
    assert "Informe endereço completo e ponto de referência" in p
    assert (
        "https://www.1746.rio/hc/pt-br/articles/14191400984987-"
        "Reparo-de-cabo-de-ilumina%C3%A7%C3%A3o-p%C3%BAblica"
    ) in p
    assert "de forma anônima" in p
    assert "Telefone: 1746; de fora do município, (21) 3460-1746" in p
    assert "retirada de risco imediata" in p
    assert "Rioluz" in p
    assert "até 3 dias corridos" in p
    assert "até 4 dias corridos" in p


def test_workflow_continuation_anchors_luminaria_deadlines_compactly():
    """Prazos de luminaria ficam ancorados fora do gate interativo."""
    interactive = interactive_response.MODULE_PROMPT
    assert "Informativo" in interactive
    assert "não usa `google_search` nem Flow" in interactive

    p = workflow_continuation.MODULE_PROMPT
    assert "ate 3 dias corridos" in p
    assert "ate 4 dias corridos" in p
    assert "furto/roubo" in p
    assert "retirada de risco imediata" in p
    assert "Nao aplique a outros servicos" in p
    assert "responda sem\n`google_search`" in p


def test_workflow_continuation_routes_luminaria_out_of_scope_text():
    """Triagem textual fora de escopo deve existir mesmo sem interativos."""
    assert "Fora de escopo" in interactive_response.MODULE_PROMPT
    p = workflow_continuation.MODULE_PROMPT
    assert "falta de energia" in p
    assert "semaforo apagado" in p
    assert "0800 0210196" in p
    assert "nao abrir\nchamado de luminaria" in p


def test_vision_inbound_prompt_has_safety_and_out_of_scope_routing():
    """A análise visual pode revelar perigo (poste caído/fios) ou caso fora de
    escopo (falta de energia/semáforo). O prompt deve rotear pra Defesa Civil
    (199) e Light (0800 0210196) ANTES de sugerir abrir chamado — paridade com
    a guidance do caminho de texto."""
    p = vision_inbound.MODULE_PROMPT
    assert "199" in p, "Defesa Civil (199) ausente na guidance de visão"
    assert "0800 0210196" in p, "Light (0800 0210196) ausente na guidance de visão"
    low = p.lower()
    assert "risco iminente" in low or "perigo elétrico" in low, (
        "Falta a noção de risco iminente / perigo na análise visual"
    )
    assert "escopo" in low, "Falta a noção de fora de escopo na análise visual"


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


def test_audio_inbound_prompt_continues_active_workflow_on_cpf_refusal():
    """Quando áudio responde a uma etapa ativa, especialmente recusa de CPF,
    prompt deve mandar continuar via multi_step_service em vez de só dar ack."""
    p = audio_inbound.MODULE_PROMPT.lower()
    assert "workflow ativo" in p, "Regra de continuação de workflow ativo ausente"
    assert "cpf" in p, "Recusa de CPF não documentada"
    assert "não quero me identificar" in p, "Exemplo de recusa por áudio ausente"
    assert "multi_step_service" in p, "Continuação via tool não documentada"
    assert "sem chamar a tool" in p, "Regra anti-ack-only ausente"


def test_workflow_continuation_module_is_enabled_before_media_modules():
    """Regra geral de continuar workflow ativo deve entrar no prompt composto,
    antes dos modulos de midia que podem produzir respostas de etapa."""
    names = [m.MODULE_NAME for m in ENABLED_MODULES]
    assert "workflow_continuation" in names
    assert names.index("workflow_continuation") < names.index("media_inbound")


def test_workflow_continuation_prompt_handles_cpf_refusal():
    """Recusa de CPF por texto deve continuar workflow ativo via tool."""
    p = workflow_continuation.MODULE_PROMPT.lower()
    assert "workflow ativo" in p
    assert "continuar sem cpf" in p
    assert "nao quero me identificar" in p
    assert "cpf ausente/recusado" in p
    assert "multi_step_service" in p
    assert "sem chamar a tool" in p


def test_workflow_continuation_prompt_handles_sgrc_retry():
    """Retry após erro do SGRC ("tentar novamente") continua o workflow ativo
    (open_ticket idempotente), NUNCA reabre o Flow — raiz do bug de retry."""
    p = workflow_continuation.MODULE_PROMPT.lower()
    assert "retry" in p
    assert "tentar novamente" in p or "tenta de novo" in p
    assert "idempotente" in p
    assert "multi_step_service" in p
    assert "nunca volte pro flow" in p  # proíbe explicitamente reabrir o Flow


def test_interactive_response_continuation_precedence_over_flow_first():
    """O Flow-first NÃO pode reabrir o Flow quando há atendimento de luminária
    em curso (pós-nfm_reply): a continuação tem precedência."""
    p = interactive_response.MODULE_PROMPT
    low = p.lower()
    assert "continuação de workflow tem precedência" in low or (
        "continuação" in low and "precedência" in low
    ), "Falta a regra de precedência da continuação sobre o Flow-first"
    assert "mesmo atendimento" in low, "Falta o conceito de atendimento em curso"
    assert "nfm_reply" in p, "Falta o sinal de submissão do Flow (nfm_reply)"
    assert "tentar novamente" in low or "tenta de novo" in low, (
        "Falta o caso de retry na precedência da continuação"
    )


# ---------- regressão: idempotência de chamada ----------


def test_compose_is_pure_and_idempotent():
    """Chamar compose 2x com mesmos argumentos retorna mesmo resultado
    byte-a-byte (sem efeitos colaterais em estado de módulo)."""
    a1, v1 = compose("BASE", "v1")
    a2, v2 = compose("BASE", "v1")
    assert a1 == a2
    assert v1 == v2


# ---------- session_close (encerramento de atendimento) ----------


def test_session_close_module_has_required_attributes():
    """session_close segue o contrato MODULE_NAME/MODULE_PROMPT."""
    assert hasattr(session_close, "MODULE_NAME")
    assert hasattr(session_close, "MODULE_PROMPT")
    assert isinstance(session_close.MODULE_NAME, str)
    assert isinstance(session_close.MODULE_PROMPT, str)


def test_session_close_module_name_is_stable():
    """MODULE_NAME vira sufixo no version (e em logs OTel) — não pode mudar
    silenciosamente."""
    assert session_close.MODULE_NAME == "session_close"


def test_session_close_enabled_by_default():
    """Sempre ativo (sem flag): não chama tool, não há risco de tool não-bound
    — mesmo critério de workflow_continuation."""
    assert session_close in ENABLED_MODULES


def test_session_close_prompt_recognizes_end_intent():
    """Guard contra deleção dos gatilhos de encerramento — sem eles o LLM não
    reconhece a intenção de finalizar."""
    p = session_close.MODULE_PROMPT.lower()
    assert "encerrar" in p
    assert "tchau" in p or "era só isso" in p


def test_session_close_cleans_active_workflow_without_confirm():
    """Encerrar é DIRETO: NÃO pergunta "concluir ou cancelar?". Se houver
    workflow ativo, só limpa chamando reset_session_state e despede."""
    p = session_close.MODULE_PROMPT.lower()
    assert "workflow" in p
    assert "reset_session_state" in p
    assert "não pergunte" in p  # encerra direto, sem confirmação
    # "concluir ou cancelar" aparece só pra PROIBIR a pergunta
    assert "concluir ou cancelar" in p


def test_session_close_defers_field_answer_to_workflow():
    """Não pode clobberar a regra de continuação: se a mensagem puder ser
    resposta de um campo, o workflow tem prioridade sobre o encerramento."""
    p = session_close.MODULE_PROMPT.lower()
    assert "priorize" in p and "campo" in p


def test_session_close_before_media_modules_in_enabled():
    """Mesma lógica de workflow_continuation: regra conversacional geral entra
    antes dos módulos de mídia que produzem respostas de etapa."""
    names = [m.MODULE_NAME for m in ENABLED_MODULES]
    assert "session_close" in names
    assert names.index("session_close") < names.index("media_inbound")


def test_session_close_logout_with_close():
    """Pra cidadão autenticado, o logout acontece JUNTO do encerramento — não há
    mais etapa de confirmar concluir/cancelar antes."""
    p = session_close.MODULE_PROMPT.lower()
    assert "logout" in p
    assert "junto do encerramento" in p


# ---------- session_reset (limpeza de estado de workflow ao encerrar) ----------


def test_session_reset_module_has_required_attributes():
    """session_reset segue o contrato MODULE_NAME/MODULE_PROMPT."""
    assert hasattr(session_reset, "MODULE_NAME")
    assert hasattr(session_reset, "MODULE_PROMPT")
    assert isinstance(session_reset.MODULE_NAME, str)
    assert isinstance(session_reset.MODULE_PROMPT, str)


def test_session_reset_module_name_is_stable():
    """MODULE_NAME vira sufixo no version (e em logs OTel) — não pode mudar
    silenciosamente."""
    assert session_reset.MODULE_NAME == "session_reset"


def test_session_reset_prompt_names_the_tool():
    """Guard contra deleção do nome EXATO da tool MCP — sem ele o LLM não sabe
    o que chamar pra limpar o estado de workflow."""
    assert "reset_session_state" in session_reset.MODULE_PROMPT


def test_session_reset_prompt_passes_user_id_like_other_tools():
    """O alvo é o telefone autenticado (o engine sobrescreve o user_id). O
    prompt deve instruir a passar user_id como nas demais tools — se instruísse
    a NÃO passar, a tool-call omitiria o campo e o engine não teria o que
    sobrescrever."""
    p = session_reset.MODULE_PROMPT.lower()
    assert "user_id" in p


def test_session_reset_prompt_is_internal_only():
    """O resultado da limpeza é interno — o prompt deve instruir a NÃO expor o
    status ao cidadão (evita 'limpei seu estado' na despedida)."""
    p = session_reset.MODULE_PROMPT.lower()
    assert "não mencione" in p or "interno" in p


def test_session_reset_prompt_calls_once_on_close_only():
    """Guard anti-spam: a tool só pode ser chamada no encerramento, uma única
    vez — não em respostas comuns nem no meio de um atendimento."""
    p = session_reset.MODULE_PROMPT.lower()
    assert "uma única vez" in p or "uma unica vez" in p
    assert "encerr" in p


def test_session_reset_enabled_by_default():
    """Default ON (opt-out), gated na tool bound — mesmo padrão de
    audio_response/govbr. Pula se o ambiente desliga via kill-switch ou exclui a
    tool, pra o teste refletir o gate real de runtime."""
    from src.utils.infisical import getenv_or_action

    explicitly_off = (
        getenv_or_action("ENABLE_SESSION_RESET", action="ignore", default="") or ""
    ).strip().lower() == "false"
    excluded = "reset_session_state" in (
        getenv_or_action("MCP_EXCLUDED_TOOLS", action="ignore", default="") or ""
    )
    if explicitly_off or excluded:
        import pytest

        pytest.skip("session_reset desligado via env (kill-switch ou tool excluída)")
    assert session_reset in ENABLED_MODULES


def test_session_reset_after_session_close_when_enabled():
    """Ordem semântica: quando ativo, session_reset vem DEPOIS de session_close
    (o LLM lê primeiro a regra de resolver workflow ativo, depois a limpeza)."""
    names = [m.MODULE_NAME for m in ENABLED_MODULES]
    if "session_reset" not in names:
        import pytest

        pytest.skip("session_reset desligado via env")
    assert names.index("session_close") < names.index("session_reset")
