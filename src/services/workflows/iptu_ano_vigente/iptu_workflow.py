"""
Workflow IPTU Ano Vigente - Prefeitura do Rio de Janeiro

Implementa o fluxo completo de consulta e emissão de guias de IPTU
seguindo o fluxograma oficial da Prefeitura do Rio.
"""

import asyncio
from langgraph.graph import StateGraph, END

from src.services.core.base_workflow import BaseWorkflow, handle_errors
from src.services.core.models import ServiceState, AgentResponse

from src.services.workflows.iptu_ano_vigente.models import (
    InscricaoImobiliariaPayload,
    EscolhaAnoPayload,
    EscolhaGuiasIPTUPayload,
    EscolhaCotasParceladasPayload,
    EscolhaGuiaMesmoImovelPayload,
    EscolhaOutroImovelPayload,
    ConfirmacaoDadosPayload,
    DadosGuias,
)
from src.services.workflows.iptu_ano_vigente.api_service import IPTUAPIService


class IPTUAnoVigenteWorkflow(BaseWorkflow):
    """
    Workflow para consulta de IPTU da Prefeitura do Rio.

    Fluxo principal adaptado:
    1. Informar inscrição imobiliária
    2. Escolher ano de exercício (2024, 2025, 2026)
    3. Consultar guias de IPTU disponíveis para pagamento
    4. Escolher quais guias de IPTU quer pagar (múltipla seleção)
    5. Verifica se é cota única (informa forma de pagamento)
    6. Se parcelado: escolher cotas a pagar
    7. Deseja pagar as cotas em DARF separado?
    8. Confirmação dos dados coletados para pagamento
    9. Existe mais guia a pagar nesse imóvel?
    10. Deseja emitir guias para outro imóvel?
    """

    service_name = "iptu_ano_vigente"
    description = "Consulta e emissão de guias de IPTU - Prefeitura do Rio de Janeiro"

    def __init__(self):
        super().__init__()
        self.api_service = IPTUAPIService()

    # --- Nós do Grafo ---

    @handle_errors
    def _informar_inscricao_imobiliaria(self, state: ServiceState) -> ServiceState:
        """Coleta a inscrição imobiliária do usuário."""
        # Verifica se há uma nova inscrição no payload (diferente da atual)
        if "inscricao_imobiliaria" in state.payload:
            try:
                validated_data = InscricaoImobiliariaPayload.model_validate(
                    state.payload
                )
                nova_inscricao = validated_data.inscricao_imobiliaria
                inscricao_atual = state.data.get("inscricao_imobiliaria")

                # Se é uma nova inscrição diferente da atual, faz reset automático
                if inscricao_atual and nova_inscricao != inscricao_atual:
                    # Reset automático para nova inscrição
                    campos_limpar = [
                        "inscricao_imobiliaria",
                        "dados_guias",
                        "guia_escolhida",
                        "cotas_escolhidas",
                        "formato_pagamento",
                        "guias_geradas",
                    ]
                    for campo in campos_limpar:
                        state.data.pop(campo, None)

                    flags_limpar = [
                        "consulta_guias_realizada",
                        "dados_confirmados",
                        "fluxo_cota_unica",
                        "quer_mesma_guia",
                        "quer_outro_imovel",
                        "inscricao_invalida",
                    ]
                    # Limpa também todas as flags de consulta de cotas específicas
                    flags_cotas_para_limpar = [
                        key
                        for key in state.internal.keys()
                        if key.startswith("consulta_cotas_realizada_")
                    ]
                    flags_limpar.extend(flags_cotas_para_limpar)
                    for flag in flags_limpar:
                        state.internal.pop(flag, None)

                # Salva a nova inscrição
                state.data["inscricao_imobiliaria"] = nova_inscricao
                state.agent_response = None
                return state

            except Exception as e:
                response = AgentResponse(
                    description="📋 Para consultar o IPTU, informe a inscrição imobiliária do seu imóvel (14 a 16 dígitos).",
                    payload_schema=InscricaoImobiliariaPayload.model_json_schema(),
                    error_message=f"Inscrição imobiliária inválida: {str(e)}",
                )
                state.agent_response = response
                return state

        # Se já tem inscrição e não foi fornecida nova, continua
        if "inscricao_imobiliaria" in state.data:
            return state

        # Solicita inscrição se não tem nenhuma
        response = AgentResponse(
            description="📋 Para consultar o IPTU, informe a inscrição imobiliária do seu imóvel (14 a 16 dígitos).",
            payload_schema=InscricaoImobiliariaPayload.model_json_schema(),
        )
        state.agent_response = response

        return state

    @handle_errors
    def _escolher_ano_exercicio(self, state: ServiceState) -> ServiceState:
        """Coleta o ano de exercício para consulta do IPTU."""
        if "ano_exercicio" in state.payload:
            try:
                validated_data = EscolhaAnoPayload.model_validate(state.payload)
                state.data["ano_exercicio"] = validated_data.ano_exercicio
                state.agent_response = None
                return state
            except Exception as e:
                state.agent_response = AgentResponse(
                    description="📅 Escolha o ano de exercício para consulta do IPTU:",
                    payload_schema=EscolhaAnoPayload.model_json_schema(),
                    error_message=f"Ano inválido: {str(e)}",
                )
                return state

        # Se já tem ano escolhido, continua
        if "ano_exercicio" in state.data:
            return state

        # Solicita escolha do ano
        response = AgentResponse(
            description="📅 Escolha o ano de exercício para consulta do IPTU:",
            payload_schema=EscolhaAnoPayload.model_json_schema(),
        )
        state.agent_response = response
        return state

    @handle_errors
    def _consultar_guias_disponiveis(self, state: ServiceState) -> ServiceState:
        """Consulta as guias disponíveis para pagamento."""
        # Verifica se a consulta de guias já foi realizada para evitar chamadas duplicadas à API
        if (
            state.internal.get("consulta_guias_realizada", False)
            and "dados_guias" in state.data
        ):
            state.agent_response = None
            return state

        inscricao = state.data.get("inscricao_imobiliaria")

        if not inscricao:
            state.agent_response = AgentResponse(
                description="❌ Erro interno: inscrição imobiliária não encontrada.",
                error_message="Inscrição imobiliária não foi coletada corretamente",
            )
            return state

        # Obtém exercício (ano) escolhido pelo usuário
        exercicio = state.data.get("ano_exercicio")
        if not exercicio:
            state.agent_response = AgentResponse(
                description="❌ Erro interno: ano de exercício não foi escolhido.",
                error_message="Ano de exercício não foi coletado corretamente",
            )
            return state

        # Consulta guias via API (usa asyncio.run para executar código async)
        dados_guias = asyncio.run(
            self.api_service.consultar_guias(inscricao, exercicio)
        )

        if not dados_guias:
            # Para desenvolvimento/testes: criar dados simulados quando API não está disponível
            # Verifica se a inscrição tem formato válido (não remove dados do estado)
            if len(inscricao) >= 8 and inscricao.isdigit():
                # Cria dados simulados para teste
                dados_guias_simulados = DadosGuias(
                    inscricao_imobiliaria=inscricao,
                    exercicio=str(exercicio),
                    guias=[],
                    total_guias=0,
                    guias_em_aberto=[],
                    guias_quitadas=[],
                )

                # Salva dados das guias
                state.data["dados_guias"] = dados_guias_simulados.model_dump()
                state.internal["consulta_guias_realizada"] = True
                state.internal["dados_simulados"] = (
                    True  # Flag para indicar dados de teste
                )

                # Continua o fluxo
                state.agent_response = None
                return state
            else:
                # Inscrição com formato inválido - remove e pede nova
                state.agent_response = AgentResponse(
                    description="❌ Inscrição imobiliária não encontrada. Verifique o número e tente novamente.",
                    payload_schema=InscricaoImobiliariaPayload.model_json_schema(),
                )
                # Remove inscrição inválida para permitir nova entrada
                state.data.pop("inscricao_imobiliaria", None)
                return state

        # Salva dados das guias real
        state.data["dados_guias"] = dados_guias.model_dump()
        state.internal["consulta_guias_realizada"] = True

        # Não para o fluxo aqui - continua para mostrar as guias
        state.agent_response = None

        return state

    @handle_errors
    def _usuario_escolhe_guias_iptu(self, state: ServiceState) -> ServiceState:
        """Usuário escolhe qual guia de IPTU quer pagar (por número da guia)."""
        if "guia_escolhida" in state.payload:
            try:
                validated_data = EscolhaGuiasIPTUPayload.model_validate(state.payload)
                state.data["guia_escolhida"] = validated_data.guia_escolhida
                state.agent_response = None
                return state
            except Exception as e:
                guias_info = self._buscar_guias_detalhadas(state)
                state.agent_response = AgentResponse(
                    description=guias_info,
                    payload_schema=EscolhaGuiasIPTUPayload.model_json_schema(),
                    error_message=f"Seleção inválida: {str(e)}",
                )
                return state

        # Se já tem guia escolhida, continua
        if "guia_escolhida" in state.data:
            return state

        # Busca e apresenta informações detalhadas das guias
        guias_info = self._buscar_guias_detalhadas(state)

        response = AgentResponse(
            description=guias_info,
            payload_schema=EscolhaGuiasIPTUPayload.model_json_schema(),
        )
        state.agent_response = response
        return state

    def _buscar_guias_detalhadas(self, state: ServiceState) -> str:
        """Formata informações detalhadas das guias disponíveis usando dados já consultados."""
        dados_guias = state.data.get("dados_guias", {})

        # Se temos dados simulados, usa fallback simples
        if state.internal.get("dados_simulados", False):
            return self._guias_info_fallback(dados_guias)

        # Se não temos dados de guias, usa fallback
        if not dados_guias or "guias" not in dados_guias:
            return self._guias_info_fallback(dados_guias)

        # Exibe lista das guias disponíveis para seleção
        try:
            guias_disponiveis = dados_guias.get("guias", [])

            if not guias_disponiveis or len(guias_disponiveis) == 0:
                return self._guias_info_fallback(dados_guias)

            return self._formatar_lista_guias(dados_guias, guias_disponiveis)

        except Exception as e:
            # Fallback em caso de erro
            return self._guias_info_fallback(dados_guias)

    def _formatar_lista_guias(self, dados_guias: dict, guias_disponiveis: list) -> str:
        """Exibe lista das guias disponíveis para seleção do usuário."""
        response_text = f"""🏠 **Dados do Imóvel Encontrado:**
🆔 **Inscrição:** {dados_guias.get('inscricao_imobiliaria', '')}

📋 **Guias Disponíveis para IPTU {dados_guias.get('exercicio', '')}:**

"""

        # Lista todas as guias disponíveis
        for i, guia in enumerate(guias_disponiveis, 1):
            numero_guia = guia.get("numero_guia", "N/A")
            tipo_guia = guia.get("tipo", "IPTU").upper()
            valor_original = self.api_service._parse_brazilian_currency(
                guia.get("valor_iptu_original_guia", "0,00")
            )
            situacao = guia.get("situacao", {}).get("descricao", "EM ABERTO")

            response_text += f"""💳 **Guia {numero_guia}** - {tipo_guia}
• Valor: R$ {valor_original:.2f}
• Situação: {situacao}

"""

        # Coleta os números das guias disponíveis para mostrar no prompt
        numeros_disponiveis = [
            guia.get("numero_guia", "N/A") for guia in guias_disponiveis
        ]
        exemplos_reais = ", ".join([f'"{num}"' for num in numeros_disponiveis])

        response_text += f"""🎯 **Para continuar, selecione a guia desejada:**
Informe o número da guia ({exemplos_reais})"""

        return response_text

    def _guias_info_fallback(self, dados_guias: dict) -> str:
        """Informações básicas quando API não está disponível."""
        return f"""🏠 **Dados do Imóvel Encontrado:**
🆔 **Inscrição:** {dados_guias.get('inscricao_imobiliaria', '')}

💳 **Guias Disponíveis:**
• "00" - IPTU (Guia Principal)
• "01" - Taxa de Limpeza

🎯 **Para continuar, selecione a guia desejada:**
Informe o número da guia ("00", "01")"""

    @handle_errors
    def _verificar_tipo_cotas(self, state: ServiceState) -> ServiceState:
        """
        Verifica se a guia escolhida é cota única ou múltiplas cotas,
        e se já foi paga, conforme especificado no fluxo.
        """
        inscricao = state.data.get("inscricao_imobiliaria")
        exercicio = state.data.get("ano_exercicio")
        guia_escolhida = state.data.get("guia_escolhida")

        if not all([inscricao, exercicio, guia_escolhida]):
            state.agent_response = AgentResponse(
                description="❌ Erro interno: dados necessários para verificação não encontrados.",
                error_message="Inscrição, exercício ou guia escolhida não disponíveis",
            )
            return state

        # Verifica se a consulta de cotas para esta guia específica já foi realizada
        consulta_cotas_key = f"consulta_cotas_realizada_{guia_escolhida}"
        if (
            state.internal.get(consulta_cotas_key, False)
            and "dados_cotas" in state.data
        ):
            # Reutiliza dados já consultados, apenas redefine as flags de controle
            dados_cotas_dict = state.data.get("dados_cotas", {})
            if dados_cotas_dict.get("numero_guia") == guia_escolhida:
                # Os dados são da guia correta, continua o processamento sem nova consulta
                state.agent_response = None
                return state

        # Obtém tipo da guia dos dados já carregados (evita nova chamada API)
        dados_guias = state.data.get("dados_guias", {})
        guias_disponiveis = dados_guias.get("guias", [])

        tipo_guia = None
        for guia in guias_disponiveis:
            if guia.get("numero_guia") == guia_escolhida:
                tipo_guia = guia.get("tipo", "ORDINÁRIA")
                break

        if not tipo_guia:
            tipo_guia = "ORDINÁRIA"  # Fallback

        # Chama API para verificar cotas usando o método otimizado
        # Converte exercicio para int com fallback para ano atual se None
        exercicio_int = int(exercicio) if exercicio is not None else 2025
        dados_cotas = asyncio.run(
            self.api_service.obter_cotas(
                str(inscricao), exercicio_int, str(guia_escolhida), tipo_guia
            )
        )

        # Se não conseguiu obter dados de cotas (API indisponível), usa simulação
        if not dados_cotas:
            # Para desenvolvimento: simula uma cota única em aberto
            state.internal["fluxo_cota_unica"] = True
            state.internal["guia_paga"] = False
            # Marca que a consulta de cotas para esta guia específica foi realizada (mesmo simulada)
            consulta_cotas_key = f"consulta_cotas_realizada_{guia_escolhida}"
            state.internal[consulta_cotas_key] = True
            state.agent_response = None
            return state

        # Analisa os dados das cotas obtidos
        cotas = dados_cotas.cotas if hasattr(dados_cotas, "cotas") else []
        total_cotas = len(cotas)

        # Verifica se alguma cota está paga
        cotas_pagas = [c for c in cotas if c.esta_paga] if cotas else []
        todas_pagas = len(cotas_pagas) == total_cotas if cotas else False

        # Salva dados das cotas no state
        state.data["dados_cotas"] = dados_cotas.model_dump() if dados_cotas else {}

        # Marca que a consulta de cotas para esta guia específica foi realizada
        consulta_cotas_key = f"consulta_cotas_realizada_{guia_escolhida}"
        state.internal[consulta_cotas_key] = True

        # Determina o tipo de fluxo baseado no número de cotas
        if total_cotas <= 1:
            # É cota única
            state.internal["fluxo_cota_unica"] = True

            if todas_pagas:
                # Cota única já paga - retorna para escolha de guias
                state.internal["guia_paga"] = True
                state.agent_response = AgentResponse(
                    description=f"ℹ️ A guia {guia_escolhida} já foi quitada.\n\n"
                    "Por favor, selecione outra guia para pagamento.",
                    payload_schema=EscolhaGuiasIPTUPayload.model_json_schema(),
                )
                # Limpa guia escolhida para permitir nova seleção
                state.data.pop("guia_escolhida", None)
                return state
            else:
                # Cota única em aberto - continua para opções de pagamento
                state.internal["guia_paga"] = False
        else:
            # São múltiplas cotas - vai para seleção de cotas
            state.internal["fluxo_cota_unica"] = False
            state.internal["guia_paga"] = False

            if todas_pagas:
                # Todas as cotas já pagas - retorna para escolha de guias
                state.internal["guia_paga"] = True
                state.agent_response = AgentResponse(
                    description=f"ℹ️ Todas as cotas da guia {guia_escolhida} já foram quitadas.\n\n"
                    "Por favor, selecione outra guia para pagamento.",
                    payload_schema=EscolhaGuiasIPTUPayload.model_json_schema(),
                )
                # Limpa guia escolhida para permitir nova seleção
                state.data.pop("guia_escolhida", None)
                return state

        # Marca como verificado
        state.internal["cotas_verificadas"] = True
        state.agent_response = None
        return state

    @handle_errors
    def _escolher_cotas_pagar(self, state: ServiceState) -> ServiceState:
        """Para fluxo parcelado, permite escolher quais cotas pagar."""
        # Este nó só é executado para parcelamento
        if state.internal.get("fluxo_cota_unica", False):
            return state

        if "cotas_escolhidas" in state.data:
            return state

        # Processa payload se presente
        if "cotas_escolhidas" in state.payload:
            validated_data = EscolhaCotasParceladasPayload.model_validate(state.payload)
            state.data["cotas_escolhidas"] = validated_data.cotas_escolhidas
            state.agent_response = None
            return state

        # Obtém dados reais das cotas do state
        dados_cotas_dict = state.data.get("dados_cotas", {})
        cotas = dados_cotas_dict.get("cotas", [])

        if not cotas:
            # Fallback para caso não haja cotas carregadas
            response_text = """⚠️ **Erro ao carregar cotas**
            
Não foi possível carregar as informações das cotas para esta guia.
Por favor, tente novamente ou entre em contato com o suporte."""

            state.agent_response = AgentResponse(
                description=response_text,
                error_message="Dados de cotas não encontrados no state",
            )
            return state

        # Monta lista de cotas disponíveis usando dados reais
        cotas_texto = (
            "📋 **Escolher Cotas a Pagar**\n\nSelecione quais cotas deseja pagar:\n\n"
        )

        cotas_em_aberto = []
        valor_total = 0.0

        for cota in cotas:
            numero_cota = cota.get("numero_cota", "")
            valor_cota = cota.get("valor_cota", "0,00")
            data_vencimento = cota.get("data_vencimento", "")
            situacao = cota.get("situacao", {})
            esta_paga = cota.get("esta_paga", False)
            valor_numerico = cota.get("valor_numerico", 0.0)

            if not esta_paga:
                cotas_em_aberto.append(numero_cota)
                valor_total += valor_numerico

                # Formata status da cota
                status_icon = "🟡" if situacao.get("codigo") == "03" else "🟢"
                status_text = (
                    "VENCIDA" if situacao.get("codigo") == "03" else "EM ABERTO"
                )

                cotas_texto += f"• **{numero_cota}ª Cota** - Vencimento: {data_vencimento} - R$ {valor_cota} - {status_icon} {status_text}\n"

        if not cotas_em_aberto:
            # Todas as cotas já foram pagas
            response_text = """✅ **Todas as cotas já foram quitadas**
            
Todas as cotas desta guia já foram pagas. 
Por favor, selecione outra guia para pagamento."""

            state.agent_response = AgentResponse(
                description=response_text,
                payload_schema=EscolhaGuiasIPTUPayload.model_json_schema(),
            )
            # Limpa guia escolhida para permitir nova seleção
            state.data.pop("guia_escolhida", None)
            return state

        # Adiciona opção "Todas as cotas"
        cotas_texto += f"\n• **Todas as cotas** - Total: R$ {valor_total:.2f}\n"
        cotas_texto += "\n**Quais cotas você deseja pagar?**"

        response = AgentResponse(
            description=cotas_texto,
            payload_schema=EscolhaCotasParceladasPayload.model_json_schema(),
        )
        state.agent_response = response

        return state

    @handle_errors
    def _pagar_darm_separado(self, state: ServiceState) -> ServiceState:
        """Pergunta se deseja pagar as cotas em DARF separado (apenas informação interna)."""
        # Este nó só é executado para fluxo parcelado
        if state.internal.get("fluxo_cota_unica", False):
            return state

        # Se já foi respondido, pula
        if "pagar_darm_separado" in state.internal:
            return state

        # Processa payload se presente
        if "pagar_darm_separado" in state.payload:
            state.internal["pagar_darm_separado"] = bool(
                state.payload["pagar_darm_separado"]
            )
            state.agent_response = None
            return state

        # Pergunta sobre DARM separado (apenas SIM/NÃO - informação interna)
        description = """📋 **Deseja pagar as cotas em DARM separado?**

• **SIM** - Cada cota será gerada em um DARM separado
• **NÃO** - Guias serão geradas em código de barras

**Qual sua preferência?**"""

        # Schema simples para resposta SIM/NÃO
        schema = {
            "type": "object",
            "properties": {
                "pagar_darm_separado": {
                    "type": "boolean",
                    "description": "Se deseja pagar as cotas em DARM separado",
                }
            },
            "required": ["pagar_darm_separado"],
        }

        state.agent_response = AgentResponse(
            description=description,
            payload_schema=schema,
        )
        return state

    @handle_errors
    def _confirmacao_dados_pagamento(self, state: ServiceState) -> ServiceState:
        """Confirma os dados coletados para gerar o pagamento."""
        if state.internal.get("dados_confirmados", False):
            return state

        # Mostra resumo dos dados para confirmação
        inscricao = state.data["inscricao_imobiliaria"]
        guia_escolhida = state.data.get("guia_escolhida", "IPTU")
        cotas_escolhidas = state.data.get("cotas_escolhidas", [])
        fluxo_cota_unica = state.internal.get("fluxo_cota_unica", False)

        # Monta resumo dos dados para confirmação
        resumo_texto = f"""📋 **Confirmação dos Dados**

**Imóvel:** {inscricao}
**Guia:** {guia_escolhida}
**Tipo:** {"Cota única" if fluxo_cota_unica else "Cotas parceladas"}"""

        if not fluxo_cota_unica and cotas_escolhidas:
            cotas_str = (
                ", ".join(cotas_escolhidas)
                if len(cotas_escolhidas) > 1
                else cotas_escolhidas[0]
            )
            resumo_texto += f"\n**Cotas:** {cotas_str}"

        # Para parcelado, mostra informação sobre DARF separado se foi respondido
        if (
            not fluxo_cota_unica
            and "pagar_darm_separado" in state.internal
        ):
            formato_texto = (
                "DARM separado"
                if state.internal["pagar_darm_separado"]
                else "Código de barras"
            )
            resumo_texto += f"\n**Formato:** {formato_texto}"

        resumo_texto += "\n\n✅ **Os dados estão corretos?**"

        # Pergunta confirmação se ainda não foi confirmado
        if "confirmacao" not in state.payload:
            state.agent_response = AgentResponse(
                description=resumo_texto,
                payload_schema=ConfirmacaoDadosPayload.model_json_schema(),
            )
            return state

        # Processa confirmação
        validated_data = ConfirmacaoDadosPayload.model_validate(state.payload)
        if not validated_data.confirmacao:
            # Se não confirmou, volta ao início do fluxo
            state.agent_response = AgentResponse(
                description="❌ **Dados não confirmados**\n\nVoltando ao início do fluxo. Informe novamente a inscrição imobiliária:",
                payload_schema=InscricaoImobiliariaPayload.model_json_schema(),
            )
            # Limpa dados para começar novamente
            campos_limpar = ["guia_escolhida", "cotas_escolhidas"]
            for campo in campos_limpar:
                state.data.pop(campo, None)
            return state

        # Confirmação aceita - marca dados como confirmados
        state.internal["dados_confirmados"] = True

        # NÃO definir agent_response aqui para permitir que o fluxo continue automaticamente para gerar_darm
        state.agent_response = None
        return state

    @handle_errors
    def _gerar_darm(self, state: ServiceState) -> ServiceState:
        """Gera DARM após confirmação dos dados."""
        # Se já foi gerado, retorna
        if "guias_geradas" in state.data:
            return state

        # Obtém dados confirmados
        inscricao = state.data["inscricao_imobiliaria"]
        guia_escolhida = state.data.get("guia_escolhida", "IPTU")
        cotas_escolhidas = state.data.get("cotas_escolhidas", [])
        exercicio = state.data.get("ano_exercicio", 2024)

        # Usar API real para gerar DARM sempre
        api_service = IPTUAPIService()

        try:
            # Sempre gera DARM via API - independente das variáveis de fluxo
            dados_darm = asyncio.run(
                api_service.consultar_darm(
                    inscricao_imobiliaria=inscricao,
                    exercicio=exercicio,
                    numero_guia=guia_escolhida,
                    cotas_selecionadas=(
                        cotas_escolhidas if cotas_escolhidas else ["00"]
                    ),
                )
            )

            if dados_darm and dados_darm.darm:
                # Tenta fazer download do PDF
                pdf_base64 = asyncio.run(
                    api_service.download_pdf_darm(
                        inscricao_imobiliaria=inscricao,
                        exercicio=exercicio,
                        numero_guia=guia_escolhida,
                        cotas_selecionadas=(
                            cotas_escolhidas if cotas_escolhidas else ["00"]
                        ),
                    )
                )

                # Salva dados do DARM gerado (converte para dict para serialização JSON)
                state.data["dados_darm"] = dados_darm.model_dump() if dados_darm else None
                state.data["guias_geradas"] = [
                    {
                        "tipo": "darm",
                        "numero_guia": guia_escolhida,
                        "valor": dados_darm.darm.valor_numerico,
                        "vencimento": dados_darm.darm.data_vencimento,
                        "codigo_barras": dados_darm.darm.codigo_barras,
                        "linha_digitavel": dados_darm.darm.sequencia_numerica,
                        "pdf_base64": pdf_base64,
                    }
                ]

                response_text = f"""✅ **DARM Gerado com Sucesso!**

🆔 **Inscrição:** {inscricao}
📋 **Guia:** {guia_escolhida}
💳 **Cotas:** {', '.join(cotas_escolhidas) if cotas_escolhidas else 'Cota única'}
💰 **Valor:** R$ {dados_darm.darm.valor_numerico:.2f}
📅 **Vencimento:** {dados_darm.darm.data_vencimento}
📊 **Código de Barras:** {dados_darm.darm.codigo_barras}

{"📄 **PDF baixado com sucesso!**" if pdf_base64 else "⚠️ PDF não disponível no momento"}"""

            else:
                # Falha na geração do DARM
                response_text = """❌ **Erro na Geração do DARM**

Não foi possível gerar o DARM no momento. 
Por favor, tente novamente."""

        except Exception as e:
            # Em caso de erro na API, gera resposta de erro
            response_text = f"""❌ **Erro na Geração das Guias**

Ocorreu um erro ao gerar as guias de pagamento: {str(e)}
Por favor, tente novamente."""

        state.agent_response = AgentResponse(description=response_text)
        return state

    @handle_errors
    def _pergunta_mesma_guia(self, state: ServiceState) -> ServiceState:
        """Pergunta se quer gerar guia para o mesmo imóvel novamente."""
        # Se já foi respondido, não pergunta novamente
        if "quer_mesma_guia" in state.internal:
            return state

        # Monta descrição com informações do DARM gerado
        description_text = "✅ **DARM Gerado com Sucesso!**\n\n"
        
        # Verifica se há dados do DARM para mostrar
        if "dados_darm" in state.data and state.data["dados_darm"]:
            dados_darm = state.data["dados_darm"]
            inscricao = dados_darm.get("inscricao_imobiliaria", "N/A")
            numero_guia = dados_darm.get("numero_guia", "N/A")
            cotas = dados_darm.get("cotas_selecionadas", [])
            
            # Informações do DARM se disponível
            if "darm" in dados_darm and dados_darm["darm"]:
                darm_info = dados_darm["darm"]
                valor = darm_info.get("valor_numerico", 0)
                vencimento = darm_info.get("data_vencimento", "N/A")
                codigo_barras = darm_info.get("codigo_barras", "N/A")
                
                description_text += f"""🆔 **Inscrição:** {inscricao}
📋 **Guia:** {numero_guia}
💳 **Cotas:** {', '.join(cotas) if cotas else 'Cota única'}
💰 **Valor:** R$ {valor:.2f}
📅 **Vencimento:** {vencimento}
📊 **Código de Barras:** {codigo_barras}

"""
        
        # Verifica se há guias geradas para mostrar
        if "guias_geradas" in state.data and state.data["guias_geradas"]:
            guias = state.data["guias_geradas"]
            if len(guias) > 0:
                guia = guias[0]  # Primeira guia gerada
                description_text += f"""📄 **PDF:** {'Disponível' if guia.get('pdf_base64') else 'Não disponível'}

"""
        
        description_text += "🔄 **Deseja emitir mais guias para o mesmo imóvel?**"

        response = AgentResponse(
            description=description_text,
            payload_schema=EscolhaGuiaMesmoImovelPayload.model_json_schema(),
        )
        state.agent_response = response

        if "mesma_guia" in state.payload:
            validated_data = EscolhaGuiaMesmoImovelPayload.model_validate(state.payload)
            state.internal["quer_mesma_guia"] = validated_data.mesma_guia
            state.agent_response = None

        return state

    @handle_errors
    def _pergunta_outro_imovel(self, state: ServiceState) -> ServiceState:
        """Pergunta se quer gerar guia para outro imóvel."""
        # Se já foi respondido, não pergunta novamente
        if "quer_outro_imovel" in state.internal:
            return state

        response = AgentResponse(
            description="🏠 Deseja emitir guia para outro imóvel?",
            payload_schema=EscolhaOutroImovelPayload.model_json_schema(),
        )
        state.agent_response = response

        if "outro_imovel" in state.payload:
            validated_data = EscolhaOutroImovelPayload.model_validate(state.payload)
            state.internal["quer_outro_imovel"] = validated_data.outro_imovel
            state.agent_response = None

        return state

    @handle_errors
    def _reset_para_mesma_guia(self, state: ServiceState) -> ServiceState:
        """Reset dados para gerar nova guia do mesmo imóvel."""
        # Limpa apenas os dados de escolha, mantém a inscrição e dados do imóvel
        campos_limpar = [
            "guia_escolhida",
            "cotas_escolhidas",
            "formato_pagamento",
            "guias_geradas",
        ]
        for campo in campos_limpar:
            state.data.pop(campo, None)

        # Limpa flags internas relacionadas ao fluxo
        flags_limpar = ["dados_confirmados", "fluxo_cota_unica", "quer_mesma_guia"]
        for flag in flags_limpar:
            state.internal.pop(flag, None)

        return state

    @handle_errors
    def _reset_para_outro_imovel(self, state: ServiceState) -> ServiceState:
        """Reset completo para outro imóvel."""
        # Limpa todos os dados do imóvel anterior
        campos_limpar = [
            "inscricao_imobiliaria",
            "dados_guias",
            "guia_escolhida",
            "cotas_escolhidas",
            "formato_pagamento",
            "guias_geradas",
        ]
        for campo in campos_limpar:
            state.data.pop(campo, None)

        # Limpa flags internas
        flags_limpar = [
            "consulta_guias_realizada",
            "dados_confirmados",
            "fluxo_cota_unica",
            "quer_mesma_guia",
            "quer_outro_imovel",
            "inscricao_invalida",
        ]
        # Limpa também todas as flags de consulta de cotas específicas
        flags_cotas_para_limpar = [
            key
            for key in state.internal.keys()
            if key.startswith("consulta_cotas_realizada_")
        ]
        flags_limpar.extend(flags_cotas_para_limpar)
        for flag in flags_limpar:
            state.internal.pop(flag, None)

        return state

    @handle_errors
    def _finalizar_interacao(self, state: ServiceState) -> ServiceState:
        """Finaliza a interação e faz reset automático dos dados."""
        # Mensagem de finalização
        response = AgentResponse(
            description="✅ **Serviço finalizado com sucesso!**\n\n"
            "Obrigado por utilizar o serviço de consulta do IPTU da Prefeitura do Rio de Janeiro.\n\n"
            "Para uma nova consulta, informe uma nova inscrição imobiliária.",
        )
        state.agent_response = response

        # Reset automático no final da interação
        # Limpa todos os dados da interação atual
        campos_limpar = [
            "inscricao_imobiliaria",
            "dados_guias",
            "guia_escolhida",
            "cotas_escolhidas",
            "formato_pagamento",
            "guias_geradas",
        ]
        for campo in campos_limpar:
            state.data.pop(campo, None)

        # Limpa todas as flags internas
        flags_limpar = [
            "consulta_realizada",
            "dados_confirmados",
            "fluxo_cota_unica",
            "quer_mesma_guia",
            "quer_outro_imovel",
            "inscricao_invalida",
        ]
        for flag in flags_limpar:
            state.internal.pop(flag, None)

        # Marca como finalizado para futuras interações
        state.internal["interacao_finalizada"] = True

        return state

    # --- Roteadores Condicionais ---

    def _decide_after_data_collection(self, state: ServiceState):
        """Roteador genérico para nós de coleta de dados."""
        if state.agent_response is not None:
            return END
        return "continue"

    def _route_after_inscricao(self, state: ServiceState) -> str:
        """Roteamento após coleta da inscrição."""
        # Se tem inscrição, vai para seleção de ano
        if "inscricao_imobiliaria" in state.data:
            return "escolher_ano"
        # Se não tem inscrição, fica aguardando input
        return "informar_inscricao"

    def _route_consulta_guias(self, state: ServiceState) -> str:
        """Roteamento após consulta de guias."""
        # Se não tem dados de guias, significa que a consulta falhou
        if "dados_guias" not in state.data:
            return "informar_inscricao"
        return "usuario_escolhe_guias"

    def _route_after_verificacao_tipo_cotas(self, state: ServiceState) -> str:
        """Roteamento após verificação do tipo de cotas."""
        # Se a guia já foi paga, retorna para escolha de guias
        if state.internal.get("guia_paga", False):
            return "usuario_escolhe_guias"

        # Se é cota única em aberto, vai diretamente para confirmação de dados/pagamento
        if state.internal.get("fluxo_cota_unica", False):
            return "confirmacao_dados"

        # Se são múltiplas cotas, vai direto para seleção de cotas
        return "escolher_cotas"

    def _route_after_mesma_guia(self, state: ServiceState) -> str:
        """Roteamento após pergunta sobre mesma guia."""
        if state.internal.get("quer_mesma_guia", False):
            return "reset_mesma_guia"
        return "pergunta_outro_imovel"

    def _route_after_outro_imovel(self, state: ServiceState) -> str:
        """Roteamento após pergunta sobre outro imóvel."""
        if state.internal.get("quer_outro_imovel", False):
            return "reset_outro_imovel"
        return "finalizar_interacao"  # Finaliza com reset automático

    def _route_after_escolher_cotas(self, state: ServiceState) -> str:
        """Roteamento após escolha de cotas."""
        # Se é fluxo de cota única, vai direto para confirmação de dados
        if state.internal.get("fluxo_cota_unica", False):
            return "confirmacao_dados"

        # Se é fluxo parcelado, precisa perguntar sobre DARF separado primeiro
        return "pagar_darm_separado"

    # --- Construção do Grafo ---

    def build_graph(self) -> StateGraph[ServiceState]:
        """Constrói o grafo do workflow IPTU."""
        graph = StateGraph(ServiceState)

        # Adiciona todos os nós
        graph.add_node("informar_inscricao", self._informar_inscricao_imobiliaria)
        graph.add_node("escolher_ano", self._escolher_ano_exercicio)
        graph.add_node("consultar_guias", self._consultar_guias_disponiveis)
        graph.add_node("usuario_escolhe_guias", self._usuario_escolhe_guias_iptu)
        graph.add_node("verificar_tipo_cotas", self._verificar_tipo_cotas)
        graph.add_node("escolher_cotas", self._escolher_cotas_pagar)
        graph.add_node("pagar_darm_separado", self._pagar_darm_separado)
        graph.add_node("confirmacao_dados", self._confirmacao_dados_pagamento)
        graph.add_node("gerar_darm", self._gerar_darm)
        graph.add_node("pergunta_mesma_guia", self._pergunta_mesma_guia)
        graph.add_node("pergunta_outro_imovel", self._pergunta_outro_imovel)
        graph.add_node("reset_mesma_guia", self._reset_para_mesma_guia)
        graph.add_node("reset_outro_imovel", self._reset_para_outro_imovel)
        graph.add_node("finalizar_interacao", self._finalizar_interacao)

        # Nós de roteamento
        graph.add_node("route_inscricao", lambda state: state)
        graph.add_node("route_escolher_cotas", lambda state: state)
        graph.add_node("route_mesma_guia", lambda state: state)
        graph.add_node("route_outro_imovel", lambda state: state)

        # Define ponto de entrada
        graph.set_entry_point("informar_inscricao")

        # Fluxo principal
        graph.add_conditional_edges(
            "informar_inscricao",
            self._decide_after_data_collection,
            {"continue": "route_inscricao", END: END},
        )

        graph.add_conditional_edges(
            "route_inscricao",
            self._route_after_inscricao,
            {
                "informar_inscricao": "informar_inscricao",
                "escolher_ano": "escolher_ano",
            },
        )

        graph.add_conditional_edges(
            "escolher_ano",
            self._decide_after_data_collection,
            {"continue": "consultar_guias", END: END},
        )

        graph.add_conditional_edges(
            "consultar_guias",
            self._decide_after_data_collection,
            {"continue": "usuario_escolhe_guias", END: END},
        )

        graph.add_conditional_edges(
            "usuario_escolhe_guias",
            self._decide_after_data_collection,
            {"continue": "verificar_tipo_cotas", END: END},
        )

        graph.add_conditional_edges(
            "verificar_tipo_cotas",
            self._route_after_verificacao_tipo_cotas,
            {
                "usuario_escolhe_guias": "usuario_escolhe_guias",
                "escolher_cotas": "escolher_cotas",
                "confirmacao_dados": "confirmacao_dados",
            },
        )

        graph.add_conditional_edges(
            "escolher_cotas",
            self._decide_after_data_collection,
            {"continue": "route_escolher_cotas", END: END},
        )

        graph.add_conditional_edges(
            "route_escolher_cotas",
            self._route_after_escolher_cotas,
            {
                "pagar_darm_separado": "pagar_darm_separado",
                "confirmacao_dados": "confirmacao_dados",
            },
        )

        graph.add_conditional_edges(
            "pagar_darm_separado",
            self._decide_after_data_collection,
            {"continue": "confirmacao_dados", END: END},
        )

        graph.add_conditional_edges(
            "confirmacao_dados",
            self._decide_after_data_collection,
            {"continue": "gerar_darm", END: END},
        )

        graph.add_edge("gerar_darm", "pergunta_mesma_guia")

        graph.add_conditional_edges(
            "pergunta_mesma_guia",
            self._decide_after_data_collection,
            {"continue": "route_mesma_guia", END: END},
        )

        graph.add_conditional_edges(
            "route_mesma_guia",
            self._route_after_mesma_guia,
            {
                "reset_mesma_guia": "reset_mesma_guia",
                "pergunta_outro_imovel": "pergunta_outro_imovel",
            },
        )

        graph.add_edge("reset_mesma_guia", "usuario_escolhe_guias")

        graph.add_conditional_edges(
            "pergunta_outro_imovel",
            self._decide_after_data_collection,
            {"continue": "route_outro_imovel", END: END},
        )

        graph.add_conditional_edges(
            "route_outro_imovel",
            self._route_after_outro_imovel,
            {
                "reset_outro_imovel": "reset_outro_imovel",
                "finalizar_interacao": "finalizar_interacao",
            },
        )

        graph.add_edge("reset_outro_imovel", "informar_inscricao")
        graph.add_edge("finalizar_interacao", END)

        return graph
