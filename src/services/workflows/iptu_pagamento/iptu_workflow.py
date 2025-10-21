"""
Workflow IPTU Ano Vigente - Prefeitura do Rio de Janeiro

Implementa o fluxo completo de consulta e emissão de guias de IPTU
seguindo o fluxograma oficial da Prefeitura do Rio.
"""

import asyncio
from typing import Optional, Dict, List
from langgraph.graph import StateGraph, END

from src.services.core.base_workflow import BaseWorkflow, handle_errors
from src.services.core.models import ServiceState, AgentResponse

from src.services.workflows.iptu_pagamento.models import (
    InscricaoImobiliariaPayload,
    EscolhaAnoPayload,
    EscolhaGuiasIPTUPayload,
    EscolhaCotasParceladasPayload,
    EscolhaMaisCotasPayload,
    EscolhaOutrasGuiasPayload,
    EscolhaOutroImovelPayload,
    ConfirmacaoDadosPayload,
    DadosGuias,
    DadosCotas,
)
from src.services.workflows.iptu_pagamento.api_service import IPTUAPIService


class IPTUWorkflow(BaseWorkflow):
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

    service_name = "iptu_pagamento"
    description = "Consulta e emissão de guias de IPTU - Prefeitura do Rio de Janeiro"

    def __init__(self):
        super().__init__()
        self.api_service = IPTUAPIService()

    # --- Métodos auxiliares ---

    def _reset_completo(
        self,
        state: ServiceState,
        manter_inscricao: bool = False,
        fields: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """
        Faz reset completo ou seletivo dos dados e flags internas.

        Args:
            state: Estado do serviço
            manter_inscricao: Se True, mantém a inscrição imobiliária atual
            fields: Dict com 'data' e 'internal' contendo listas de campos para resetar.
                   Se None, faz reset completo. Se especificado, reseta apenas os campos listados.
        """
        if fields is None:
            # Reset completo (comportamento original)
            inscricao_atual = (
                state.data.get("inscricao_imobiliaria") if manter_inscricao else None
            )

            # Reset completo do data
            state.data.clear()

            # Reset completo do internal
            state.internal.clear()

            # Restaura inscrição se necessário
            if inscricao_atual:
                state.data["inscricao_imobiliaria"] = inscricao_atual
        else:
            # Reset seletivo
            inscricao_atual = (
                state.data.get("inscricao_imobiliaria") if manter_inscricao else None
            )

            # Reset seletivo do data
            if "data" in fields:
                for field in fields["data"]:
                    state.data.pop(field, None)

            # Reset seletivo do internal
            if "internal" in fields:
                for field in fields["internal"]:
                    state.internal.pop(field, None)

            # Restaura inscrição se necessário e não foi removida no reset
            if inscricao_atual and "inscricao_imobiliaria" not in fields.get(
                "data", []
            ):
                state.data["inscricao_imobiliaria"] = inscricao_atual

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
                    self._reset_completo(state)

                # Salva a nova inscrição
                state.data["inscricao_imobiliaria"] = nova_inscricao
                state.agent_response = None
                return state

            except Exception as e:
                response = AgentResponse(
                    description="📋 Para consultar o IPTU, informe a inscrição imobiliária do seu imóvel (8 a 15 dígitos).",
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
            description="📋 Para consultar o IPTU, informe a inscrição imobiliária do seu imóvel (8 a 15 dígitos).",
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
                # Reset completo para permitir nova entrada
                self._reset_completo(state)
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
    def _consultar_cotas(self, state: ServiceState) -> ServiceState:
        """Consulta as cotas disponíveis para a guia selecionada via API."""
        # Se já temos dados de cotas, pula a consulta
        if "dados_cotas" in state.data:
            return state

        # Valida dados necessários para consulta
        inscricao = state.data.get("inscricao_imobiliaria")
        exercicio = state.data.get("ano_exercicio")
        guia_escolhida = state.data.get("guia_escolhida")

        if not all([inscricao, exercicio, guia_escolhida]):
            state.agent_response = AgentResponse(
                description="❌ Erro interno: dados para consulta de cotas ausentes.",
                error_message="Inscrição, exercício ou guia não encontrados.",
            )
            return state

        # Faz consulta via API
        dados_cotas = asyncio.run(
            self.api_service.obter_cotas(
                str(inscricao), int(exercicio or 2025), str(guia_escolhida)
            )
        )

        if not dados_cotas or not dados_cotas.cotas:
            state.agent_response = AgentResponse(
                description="⚠️ Nenhuma cota encontrada para esta guia. Por favor, selecione outra guia.",
                payload_schema=EscolhaGuiasIPTUPayload.model_json_schema(),
            )
            state.data.pop("guia_escolhida", None)
            return state

        # Salva dados das cotas
        state.data["dados_cotas"] = dados_cotas.model_dump()
        cotas_em_aberto = [c for c in dados_cotas.cotas if not c.esta_paga]

        if not cotas_em_aberto:
            state.agent_response = AgentResponse(
                description="✅ Todas as cotas desta guia já foram quitadas. Selecione outra guia.",
                payload_schema=EscolhaGuiasIPTUPayload.model_json_schema(),
            )
            state.data.pop("guia_escolhida", None)
            return state

        # Se há apenas uma cota, seleciona automaticamente
        if len(cotas_em_aberto) == 1:
            state.data["cotas_escolhidas"] = [cotas_em_aberto[0].numero_cota]
            state.internal["fluxo_cota_unica"] = True
            state.agent_response = None
            return state

        # Consulta realizada com sucesso, próximo nó irá apresentar escolhas
        state.agent_response = None
        return state

    @handle_errors
    def _usuario_escolhe_cotas_iptu(self, state: ServiceState) -> ServiceState:
        """Permite ao usuário escolher as cotas a pagar."""
        # Se já temos cotas escolhidas, não precisa escolher novamente
        if "cotas_escolhidas" in state.data:
            return state

        # Processa payload se presente
        if "cotas_escolhidas" in state.payload:
            validated_data = EscolhaCotasParceladasPayload.model_validate(state.payload)
            state.data["cotas_escolhidas"] = validated_data.cotas_escolhidas
            state.agent_response = None
            return state

        # Carrega dados das cotas do state
        dados_cotas_dict = state.data.get("dados_cotas")
        if not dados_cotas_dict:
            state.agent_response = AgentResponse(
                description="❌ Erro interno: dados de cotas não encontrados.",
                error_message="Dados de cotas não carregados.",
            )
            return state

        # Reconstrói objeto DadosCotas
        dados_cotas = DadosCotas(**dados_cotas_dict)
        cotas_em_aberto = [c for c in dados_cotas.cotas if not c.esta_paga]

        # Apresenta opções de cotas para escolha
        cotas_texto = "📋 **Selecione as cotas que deseja pagar:**\n\n"
        valor_total = 0.0
        for cota in cotas_em_aberto:
            valor_total += 0.0 if cota.valor_numerico is None else cota.valor_numerico
            status_icon = "🟡" if cota.esta_vencida else "🟢"
            status_text = "VENCIDA" if cota.esta_vencida else "EM ABERTO"
            cotas_texto += f"• **{cota.numero_cota}ª Cota** - Venc: {cota.data_vencimento} - R$ {cota.valor_cota} - {status_icon} {status_text}\n"

        cotas_texto += f"\n• **Todas as cotas** - Total: R$ {valor_total:.2f}\n"
        cotas_texto += "\n**Quais cotas você deseja pagar?**"

        state.agent_response = AgentResponse(
            description=cotas_texto,
            payload_schema=EscolhaCotasParceladasPayload.model_json_schema(),
        )
        return state

    @handle_errors
    def _perguntar_formato_darm(self, state: ServiceState) -> ServiceState:
        """Pergunta se o usuário quer um boleto único ou separado para as cotas selecionadas."""
        if "darm_separado" in state.internal:
            return state

        cotas_escolhidas = state.data.get("cotas_escolhidas", [])
        if len(cotas_escolhidas) <= 1:
            state.internal["darm_separado"] = False  # Padrão para cota única
            return state

        if "darm_separado" in state.payload:
            state.internal["darm_separado"] = bool(state.payload["darm_separado"])
            state.agent_response = None
            return state

        description = """📋 **Como deseja gerar os boletos?**

• **Boleto único** para todas as cotas selecionadas.
• **Um boleto para cada cota** selecionada.
"""
        schema = {
            "type": "object",
            "properties": {
                "darm_separado": {
                    "type": "boolean",
                    "description": "True para boletos separados, False para boleto único.",
                }
            },
            "required": ["darm_separado"],
        }
        state.agent_response = AgentResponse(
            description=description, payload_schema=schema
        )
        return state

    @handle_errors
    def _confirmacao_dados_pagamento(self, state: ServiceState) -> ServiceState:
        """Confirma os dados coletados para gerar o pagamento."""
        if state.internal.get("dados_confirmados", False):
            return state

        inscricao = state.data["inscricao_imobiliaria"]
        guia_escolhida = state.data.get("guia_escolhida", "N/A")
        cotas_escolhidas = state.data.get("cotas_escolhidas", [])
        darm_separado = state.internal.get("darm_separado", False)

        resumo_texto = f"""📋 **Confirmação dos Dados**

**Imóvel:** {inscricao}
**Guia:** {guia_escolhida}
**Cotas:** {', '.join(cotas_escolhidas)}
**Boletos a serem gerados:** {len(cotas_escolhidas) if darm_separado else 1}

✅ **Os dados estão corretos?**"""

        if "confirmacao" not in state.payload:
            state.agent_response = AgentResponse(
                description=resumo_texto,
                payload_schema=ConfirmacaoDadosPayload.model_json_schema(),
            )
            return state

        validated_data = ConfirmacaoDadosPayload.model_validate(state.payload)
        if not validated_data.confirmacao:
            state.agent_response = AgentResponse(
                description="❌ **Dados não confirmados**. Voltando ao início.",
                payload_schema=InscricaoImobiliariaPayload.model_json_schema(),
            )
            # Reset completo para recomeçar, mantendo a inscrição
            self._reset_completo(state, manter_inscricao=True)
            return state

        state.internal["dados_confirmados"] = True
        state.agent_response = None
        return state

    @handle_errors
    def _gerar_darm(self, state: ServiceState) -> ServiceState:
        """Gera DARM(s) após confirmação dos dados."""
        if "guias_geradas" in state.data:
            return state

        inscricao = state.data["inscricao_imobiliaria"]
        guia_escolhida = state.data["guia_escolhida"]
        cotas_escolhidas = state.data["cotas_escolhidas"]
        exercicio = state.data["ano_exercicio"]
        darm_separado = state.internal.get("darm_separado", False)

        guias_geradas = []

        cotas_a_processar = []
        if darm_separado:
            cotas_a_processar = [[c] for c in cotas_escolhidas]
        else:
            cotas_a_processar = [cotas_escolhidas]

        for cotas_para_darm in cotas_a_processar:
            try:
                dados_darm = asyncio.run(
                    self.api_service.consultar_darm(
                        inscricao_imobiliaria=inscricao,
                        exercicio=exercicio,
                        numero_guia=guia_escolhida,
                        cotas_selecionadas=cotas_para_darm,
                    )
                )

                if dados_darm and dados_darm.darm:
                    pdf_base64 = asyncio.run(
                        self.api_service.download_pdf_darm(
                            inscricao_imobiliaria=inscricao,
                            exercicio=exercicio,
                            numero_guia=guia_escolhida,
                            cotas_selecionadas=cotas_para_darm,
                        )
                    )
                    guias_geradas.append(
                        {
                            "tipo": "darm",
                            "numero_guia": guia_escolhida,
                            "cotas": ", ".join(cotas_para_darm),
                            "valor": dados_darm.darm.valor_numerico,
                            "vencimento": dados_darm.darm.data_vencimento,
                            "codigo_barras": dados_darm.darm.codigo_barras,
                            "linha_digitavel": dados_darm.darm.sequencia_numerica,
                            # "pdf_base64": pdf_base64,
                        }
                    )
            except Exception as e:
                state.agent_response = AgentResponse(
                    description=f"❌ Erro ao gerar DARM para as cotas {', '.join(cotas_para_darm)}: {e}"
                )
                return state

        state.data["guias_geradas"] = guias_geradas

        # Não define agent_response aqui, pois o workflow deve continuar para pergunta_mesma_guia
        # A resposta será definida no método _pergunta_mesma_guia
        return state

    def _tem_mais_cotas_disponiveis(self, state: ServiceState) -> bool:
        """Verifica se há mais cotas disponíveis da guia atual para pagar."""
        dados_cotas_dict = state.data.get("dados_cotas")
        cotas_escolhidas = state.data.get("cotas_escolhidas", [])

        if not dados_cotas_dict or not cotas_escolhidas:
            return False

        cotas_disponiveis = dados_cotas_dict.get("cotas", [])
        total_cotas = len(cotas_disponiveis)
        cotas_selecionadas = len(cotas_escolhidas)

        return cotas_selecionadas < total_cotas

    def _tem_outras_guias_disponiveis(self, state: ServiceState) -> bool:
        """Verifica se há outras guias disponíveis no imóvel."""
        dados_guias_dict = state.data.get("dados_guias")
        guia_atual = state.data.get("guia_escolhida")

        if not dados_guias_dict:
            return False

        guias_disponiveis = dados_guias_dict.get("guias", [])
        total_guias = len(guias_disponiveis)

        # Se há mais de uma guia disponível, significa que há outras além da atual
        return total_guias > 1

    @handle_errors
    def _pergunta_mesma_guia(self, state: ServiceState) -> ServiceState:
        """
        Roteador condicional inteligente pós-geração de boletos:
        1. Se há mais cotas disponíveis da mesma guia → redireciona para pergunta_mais_cotas
        2. Se há outras guias disponíveis no imóvel → redireciona para pergunta_outras_guias
        3. Caso contrário → redireciona para pergunta_outro_imovel
        """
        # Analisa contexto para determinar próxima pergunta
        tem_mais_cotas = self._tem_mais_cotas_disponiveis(state)
        tem_outras_guias = self._tem_outras_guias_disponiveis(state)

        # Define o tipo de pergunta baseado no contexto
        if tem_mais_cotas:
            state.internal["tipo_pergunta_seguinte"] = "mais_cotas"
        elif tem_outras_guias:
            state.internal["tipo_pergunta_seguinte"] = "outras_guias"
        else:
            state.internal["tipo_pergunta_seguinte"] = "outro_imovel"

        # Não define agent_response, deixa o roteamento decidir o próximo nó
        return state

    @handle_errors
    def _pergunta_mais_cotas(self, state: ServiceState) -> ServiceState:
        """Pergunta se quer pagar mais cotas da mesma guia."""
        # Se já foi respondido, não pergunta novamente
        if "quer_mais_cotas" in state.internal:
            return state

        # Se tem payload com resposta, processa
        if "mais_cotas" in state.payload:
            validated_data = EscolhaMaisCotasPayload.model_validate(state.payload)
            state.internal["quer_mais_cotas"] = validated_data.mais_cotas
            state.agent_response = None
            return state

        # Monta descrição com os boletos gerados + pergunta específica
        description_text = self._gerar_descricao_boletos_gerados(state)
        description_text += "\n🔄 **Deseja pagar mais cotas da mesma guia?**"

        response = AgentResponse(
            description=description_text,
            payload_schema=EscolhaMaisCotasPayload.model_json_schema(),
        )
        state.agent_response = response
        return state

    @handle_errors
    def _pergunta_outras_guias(self, state: ServiceState) -> ServiceState:
        """Pergunta se quer pagar outras guias do mesmo imóvel."""
        # Se já foi respondido, não pergunta novamente
        if "quer_outras_guias" in state.internal:
            return state

        # Se tem payload com resposta, processa
        if "outras_guias" in state.payload:
            validated_data = EscolhaOutrasGuiasPayload.model_validate(state.payload)
            state.internal["quer_outras_guias"] = validated_data.outras_guias
            state.agent_response = None
            return state

        # Monta descrição com os boletos gerados + pergunta específica
        description_text = self._gerar_descricao_boletos_gerados(state)
        description_text += "\n🔄 **Deseja pagar outras guias do mesmo imóvel?**"

        response = AgentResponse(
            description=description_text,
            payload_schema=EscolhaOutrasGuiasPayload.model_json_schema(),
        )
        state.agent_response = response
        return state

    def _gerar_descricao_boletos_gerados(self, state: ServiceState) -> str:
        """Gera a descrição padrão dos boletos gerados."""
        description_text = "✅ **Boletos Gerados com Sucesso!**\n\n"
        guias_geradas = state.data.get("guias_geradas", [])
        inscricao = state.data.get("inscricao_imobiliaria", "N/A")

        if not guias_geradas:
            description_text = "Nenhum boleto foi gerado."
        else:
            for boleto_num, guia in enumerate(guias_geradas, 1):
                description_text += f"**Boleto {boleto_num}:**\n"
                description_text += f"**Inscrição:** {inscricao}\n"
                description_text += f"**Guia:** {guia['numero_guia']}\n"
                description_text += f"**Cotas:** {guia['cotas']}\n"
                description_text += f"**Valor:** R$ {guia['valor']:.2f}\n"
                description_text += f"**Vencimento:** {guia['vencimento']}\n"
                description_text += f"**Código de Barras:** {guia['codigo_barras']}\n"
                description_text += f"**Linha Digitável:** {guia['linha_digitavel']}\n"
                description_text += f"**PDF:** {'Disponível' if guia.get('pdf_base64') else 'Não disponível'}\n\n"

        return description_text

    @handle_errors
    def _pergunta_outro_imovel(self, state: ServiceState) -> ServiceState:
        """Pergunta se quer gerar guia para outro imóvel."""
        # Se já foi respondido, não pergunta novamente
        if "quer_outro_imovel" in state.internal:
            return state

        # Se tem payload com resposta, processa
        if "outro_imovel" in state.payload:
            validated_data = EscolhaOutroImovelPayload.model_validate(state.payload)
            state.internal["quer_outro_imovel"] = validated_data.outro_imovel
            state.agent_response = None
            return state

        response = AgentResponse(
            description="🏠 Deseja emitir guia para outro imóvel?",
            payload_schema=EscolhaOutroImovelPayload.model_json_schema(),
        )
        state.agent_response = response

        return state

    @handle_errors
    def _reset_para_mais_cotas(self, state: ServiceState) -> ServiceState:
        """Reset seletivo para pagar mais cotas da mesma guia."""
        # Reset apenas dos campos relacionados à seleção de cotas e posteriores
        fields_to_reset = {
            "data": ["cotas_escolhidas", "dados_darm", "guias_geradas"],
            "internal": ["quer_mais_cotas", "quer_outras_guias", "quer_outro_imovel"],
        }

        self._reset_completo(state, manter_inscricao=True, fields=fields_to_reset)
        return state

    @handle_errors
    def _reset_para_outras_guias(self, state: ServiceState) -> ServiceState:
        """Reset seletivo para pagar outras guias do mesmo imóvel."""
        # Reset dos campos relacionados à seleção de guia e posteriores
        fields_to_reset = {
            "data": [
                "guia_escolhida",
                "dados_cotas",
                "cotas_escolhidas",
                "dados_darm",
                "guias_geradas",
            ],
            "internal": ["quer_mais_cotas", "quer_outras_guias", "quer_outro_imovel"],
        }

        self._reset_completo(state, manter_inscricao=True, fields=fields_to_reset)
        return state

    @handle_errors
    def _reset_para_mesma_guia(self, state: ServiceState) -> ServiceState:
        """Reset dados para gerar nova guia do mesmo imóvel."""
        # Reset completo mantendo inscrição e dados das guias consultadas
        inscricao = state.data.get("inscricao_imobiliaria")
        dados_guias = state.data.get("dados_guias")

        self._reset_completo(state)

        # Restaura apenas inscrição e dados das guias
        if inscricao:
            state.data["inscricao_imobiliaria"] = inscricao
        if dados_guias:
            state.data["dados_guias"] = dados_guias
            state.internal["consulta_guias_realizada"] = True

        return state

    @handle_errors
    def _reset_para_outro_imovel(self, state: ServiceState) -> ServiceState:
        """Reset completo para outro imóvel."""
        # Reset completo de tudo
        self._reset_completo(state)
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

        # Reset automático completo no final da interação
        self._reset_completo(state)

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

    def _route_after_mesma_guia(self, state: ServiceState) -> str:
        """Roteamento após pergunta sobre mesma guia - agora é um roteador condicional."""
        # Se já determinou o tipo de pergunta, roteia adequadamente
        tipo_pergunta = state.internal.get("tipo_pergunta_seguinte")

        if tipo_pergunta == "mais_cotas":
            return "pergunta_mais_cotas"
        elif tipo_pergunta == "outras_guias":
            return "pergunta_outras_guias"
        elif tipo_pergunta == "outro_imovel":
            return "pergunta_outro_imovel"

        # Se não determinou ainda, fica no END (não deveria acontecer)
        return END

    def _route_after_outro_imovel(self, state: ServiceState) -> str:
        """Roteamento após pergunta sobre outro imóvel."""
        # Se ainda não respondeu, fica no nó atual para aguardar resposta
        if "quer_outro_imovel" not in state.internal:
            return END

        if state.internal.get("quer_outro_imovel", False):
            return "reset_outro_imovel"
        return "finalizar_interacao"  # Finaliza com reset automático

    def _route_after_mais_cotas(self, state: ServiceState) -> str:
        """Roteamento após pergunta sobre mais cotas."""
        # Se ainda não respondeu, fica no nó atual para aguardar resposta
        if "quer_mais_cotas" not in state.internal:
            return END

        if state.internal.get("quer_mais_cotas", False):
            return "reset_mais_cotas"

        # Se não quer mais cotas, verifica se tem outras guias
        if self._tem_outras_guias_disponiveis(state):
            return "pergunta_outras_guias"

        # Se não tem outras guias, vai direto para pergunta sobre outro imóvel
        return "pergunta_outro_imovel"

    def _route_after_outras_guias(self, state: ServiceState) -> str:
        """Roteamento após pergunta sobre outras guias."""
        # Se ainda não respondeu, fica no nó atual para aguardar resposta
        if "quer_outras_guias" not in state.internal:
            return END

        if state.internal.get("quer_outras_guias", False):
            return "reset_outras_guias"

        # Se não quer outras guias, vai para pergunta sobre outro imóvel
        return "pergunta_outro_imovel"

    # --- Construção do Grafo ---

    def build_graph(self) -> StateGraph[ServiceState]:
        """Constrói o grafo do workflow IPTU."""
        graph = StateGraph(ServiceState)

        # Adiciona todos os nós
        graph.add_node("informar_inscricao", self._informar_inscricao_imobiliaria)
        graph.add_node("escolher_ano", self._escolher_ano_exercicio)
        graph.add_node("consultar_guias", self._consultar_guias_disponiveis)
        graph.add_node("usuario_escolhe_guias", self._usuario_escolhe_guias_iptu)
        graph.add_node("consultar_cotas", self._consultar_cotas)
        graph.add_node("usuario_escolhe_cotas", self._usuario_escolhe_cotas_iptu)
        graph.add_node("perguntar_formato_darm", self._perguntar_formato_darm)
        graph.add_node("confirmacao_dados", self._confirmacao_dados_pagamento)
        graph.add_node("gerar_darm", self._gerar_darm)
        graph.add_node("pergunta_mesma_guia", self._pergunta_mesma_guia)
        graph.add_node("pergunta_mais_cotas", self._pergunta_mais_cotas)
        graph.add_node("pergunta_outras_guias", self._pergunta_outras_guias)
        graph.add_node("pergunta_outro_imovel", self._pergunta_outro_imovel)
        graph.add_node("reset_mesma_guia", self._reset_para_mesma_guia)
        graph.add_node("reset_mais_cotas", self._reset_para_mais_cotas)
        graph.add_node("reset_outras_guias", self._reset_para_outras_guias)
        graph.add_node("reset_outro_imovel", self._reset_para_outro_imovel)
        graph.add_node("finalizar_interacao", self._finalizar_interacao)

        # Define ponto de entrada
        graph.set_entry_point("informar_inscricao")

        # Fluxo principal
        graph.add_conditional_edges(
            "informar_inscricao",
            self._decide_after_data_collection,
            {"continue": "escolher_ano", END: END},
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
            {"continue": "consultar_cotas", END: END},
        )
        graph.add_conditional_edges(
            "consultar_cotas",
            self._decide_after_data_collection,
            {"continue": "usuario_escolhe_cotas", END: END},
        )
        graph.add_conditional_edges(
            "usuario_escolhe_cotas",
            self._decide_after_data_collection,
            {"continue": "perguntar_formato_darm", END: END},
        )
        graph.add_conditional_edges(
            "perguntar_formato_darm",
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
            self._route_after_mesma_guia,
            {
                "pergunta_mais_cotas": "pergunta_mais_cotas",
                "pergunta_outras_guias": "pergunta_outras_guias",
                "pergunta_outro_imovel": "pergunta_outro_imovel",
                END: END,
            },
        )

        graph.add_conditional_edges(
            "pergunta_mais_cotas",
            self._route_after_mais_cotas,
            {
                "reset_mais_cotas": "reset_mais_cotas",
                "pergunta_outras_guias": "pergunta_outras_guias",
                "pergunta_outro_imovel": "pergunta_outro_imovel",
                END: END,
            },
        )
        graph.add_edge("reset_mais_cotas", "usuario_escolhe_cotas")

        graph.add_conditional_edges(
            "pergunta_outras_guias",
            self._route_after_outras_guias,
            {
                "reset_outras_guias": "reset_outras_guias",
                "pergunta_outro_imovel": "pergunta_outro_imovel",
                END: END,
            },
        )
        graph.add_edge("reset_outras_guias", "usuario_escolhe_guias")

        graph.add_conditional_edges(
            "pergunta_outro_imovel",
            self._route_after_outro_imovel,
            {
                "reset_outro_imovel": "reset_outro_imovel",
                "finalizar_interacao": "finalizar_interacao",
                END: END,
            },
        )
        graph.add_edge("reset_outro_imovel", "informar_inscricao")
        graph.add_edge("finalizar_interacao", END)

        return graph
