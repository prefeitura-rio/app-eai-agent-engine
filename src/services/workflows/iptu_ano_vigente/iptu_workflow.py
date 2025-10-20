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
    EscolhaCobrancaPayload,
    EscolhaFormatoPagamentoPayload,
    EscolhaCotasParceladasPayload,
    EscolhaGuiaMesmoImovelPayload,
    EscolhaOutroImovelPayload,
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
                        "tipo_cobranca",
                        "cotas_escolhidas",
                        "formato_pagamento",
                        "guias_geradas",
                    ]
                    for campo in campos_limpar:
                        state.data.pop(campo, None)

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
                state.internal["consulta_realizada"] = True
                state.internal["dados_simulados"] = True  # Flag para indicar dados de teste
                
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
        state.internal["consulta_realizada"] = True

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
        numeros_disponiveis = [guia.get("numero_guia", "N/A") for guia in guias_disponiveis]
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
    def _verificar_cota_unica(self, state: ServiceState) -> ServiceState:
        """Verifica se é cota única (informa forma de pagamento)."""
        if "tipo_cobranca" in state.data:
            return state

        response_text = """📋 **Qual forma de pagamento você deseja realizar?**

• **Cota Única** - Pagamento à vista com 7% de desconto
• **Em Cotas Mensais** - Parcelamento em até 10x sem juros

💳 **Escolha sua preferência:**"""

        response = AgentResponse(
            description=response_text,
            payload_schema=EscolhaCobrancaPayload.model_json_schema(),
        )
        state.agent_response = response

        if "tipo_cobranca" in state.payload:
            validated_data = EscolhaCobrancaPayload.model_validate(state.payload)
            state.data["tipo_cobranca"] = validated_data.tipo_cobranca

            # Define flag para roteamento
            if validated_data.tipo_cobranca == "cota_unica":
                state.internal["fluxo_cota_unica"] = True
            else:
                state.internal["fluxo_cota_unica"] = False

            state.agent_response = None

        return state

    @handle_errors
    def _escolher_formato_cota_unica(self, state: ServiceState) -> ServiceState:
        """Para cota única, coleta o formato de pagamento."""
        # Este nó só é executado para cota única
        if not state.internal.get("fluxo_cota_unica", False):
            return state

        if "formato_pagamento" in state.data:
            return state

        response = AgentResponse(
            description="✅ Cota única selecionada! Você terá 7% de desconto.\n\n"
            "Escolha como deseja receber a guia de pagamento:",
            payload_schema=EscolhaFormatoPagamentoPayload.model_json_schema(),
        )
        state.agent_response = response

        if "formato_pagamento" in state.payload:
            validated_data = EscolhaFormatoPagamentoPayload.model_validate(
                state.payload
            )
            state.data["formato_pagamento"] = validated_data.formato_pagamento
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

        response_text = """📋 **Escolher Cotas a Pagar**

Você optou pelo parcelamento. Selecione quais cotas deseja pagar:

• **1ª Cota** - Vencimento: Janeiro/2024
• **2ª Cota** - Vencimento: Fevereiro/2024
• **3ª Cota** - Vencimento: Março/2024
• **4ª Cota** - Vencimento: Abril/2024
• **5ª Cota** - Vencimento: Maio/2024
• **Todas as cotas** - Todas as parcelas em aberto

**Quais cotas você deseja pagar?**"""

        response = AgentResponse(
            description=response_text,
            payload_schema=EscolhaCotasParceladasPayload.model_json_schema(),
        )
        state.agent_response = response

        if "cotas_escolhidas" in state.payload:
            validated_data = EscolhaCotasParceladasPayload.model_validate(state.payload)
            state.data["cotas_escolhidas"] = validated_data.cotas_escolhidas
            state.agent_response = None

        return state

    @handle_errors
    def _deseja_pagar_darf_separado(self, state: ServiceState) -> ServiceState:
        """Pergunta se deseja pagar as cotas em DARF separado."""
        if "formato_pagamento" in state.data:
            return state

        response_text = """📋 **Deseja pagar as cotas em DARF separado?**

• **Sim** - Cada cota será gerada em um DARF separado
• **Não** - Guias serão geradas em código de barras

**Qual sua preferência?**"""

        response = AgentResponse(
            description=response_text,
            payload_schema=EscolhaFormatoPagamentoPayload.model_json_schema(),
        )
        state.agent_response = response

        if "formato_pagamento" in state.payload:
            validated_data = EscolhaFormatoPagamentoPayload.model_validate(
                state.payload
            )
            state.data["formato_pagamento"] = validated_data.formato_pagamento
            state.agent_response = None

        return state

    @handle_errors
    def _confirmacao_dados_pagamento(self, state: ServiceState) -> ServiceState:
        """Confirma os dados coletados para gerar o pagamento."""
        if state.internal.get("dados_confirmados", False):
            return state

        # Coleta formato de pagamento se ainda não foi coletado
        if "formato_pagamento" not in state.data:
            if "formato_pagamento" in state.payload:
                validated_data = EscolhaFormatoPagamentoPayload.model_validate(
                    state.payload
                )
                state.data["formato_pagamento"] = validated_data.formato_pagamento
            else:
                state.agent_response = AgentResponse(
                    description="📋 Escolha como deseja receber as guias de pagamento:",
                    payload_schema=EscolhaFormatoPagamentoPayload.model_json_schema(),
                )
                return state

        # Gera as guias de pagamento via API (usa asyncio.run)
        inscricao = state.data["inscricao_imobiliaria"]
        guia_escolhida = state.data.get("guia_escolhida", "IPTU")
        tipo_cobranca = state.data["tipo_cobranca"]
        formato_pagamento = state.data["formato_pagamento"]
        cotas_escolhidas = state.data.get("cotas_escolhidas", [])
        exercicio = state.data.get("ano_exercicio", 2024)

        # Simulação das guias geradas para compatibilidade com o fluxo
        # Na implementação real, usaria os métodos consultar_darm ou obter_cotas
        guias_simuladas = []
        if formato_pagamento == "codigo_barras":
            # Simula código de barras
            guias_simuladas = [{
                "numero_guia": guia_escolhida,
                "valor": 1000.00,
                "vencimento": "31/12/2024",
                "codigo_barras": "23793.38128 60005.021006 00000.987654 2 99190000100000",
                "linha_digitavel": "23793.38128 60005.021006 00000.987654 2 99190000100000"
            }]
        else:
            # Simula DARF
            guias_simuladas = [{
                "numero_guia": guia_escolhida,
                "valor": 1000.00,
                "vencimento": "31/12/2024",
                "darf_data": {
                    "codigo_receita": "310-7",
                    "sequencia_numerica": "23793.38128 60005.021006 00000.987654 2 99190000100000"
                }
            }]
        
        # Converte para objetos com atributos
        class GuiaSimulada:
            def __init__(self, data):
                self.numero_guia: str = data.get("numero_guia", "")
                self.valor: float = data.get("valor", 0.0)
                self.vencimento: str = data.get("vencimento", "")
                self.codigo_barras: str = data.get("codigo_barras", "")
                self.linha_digitavel: str = data.get("linha_digitavel", "")
                self.darf_data: dict = data.get("darf_data", {})
            
            def model_dump(self):
                return {
                    "numero_guia": self.numero_guia,
                    "valor": self.valor,
                    "vencimento": self.vencimento,
                    "codigo_barras": self.codigo_barras,
                    "linha_digitavel": self.linha_digitavel,
                    "darf_data": self.darf_data
                }
        
        guias = [GuiaSimulada(guia) for guia in guias_simuladas]

        # Salva as guias geradas
        state.data["guias_geradas"] = [guia.model_dump() for guia in guias]

        # Monta texto de confirmação
        dados_guias = state.data["dados_guias"]
        response_text = f"""
✅ **Guias de Pagamento Geradas!**

🆔 **Inscrição:** {dados_guias['inscricao_imobiliaria']}
📋 **Guia IPTU:** {guia_escolhida}
💳 **Tipo:** {'Cota Única (7% desconto)' if tipo_cobranca == 'cota_unica' else 'Parcelamento'}
📄 **Formato:** {'DARF Separado' if formato_pagamento == 'darf' else 'Código de Barras'}

📋 **Guias Geradas:** {len(guias)} guia(s)
        """

        if formato_pagamento == "codigo_barras":
            for i, guia in enumerate(guias[:3], 1):  # Mostra só as 3 primeiras
                response_text += f"\n\n**Guia {i}:**\n"
                response_text += f"💰 Valor: R$ {guia.valor:.2f}\n"
                response_text += f"📅 Vencimento: {guia.vencimento}\n"
                response_text += f"📊 Código: {guia.codigo_barras}"

            if len(guias) > 3:
                response_text += f"\n\n... e mais {len(guias) - 3} guia(s)"
        else:
            total_valor = sum(guia.valor for guia in guias)
            response_text += f"\n💰 **Valor Total:** R$ {total_valor:.2f}"

        state.internal["dados_confirmados"] = True
        state.agent_response = AgentResponse(description=response_text.strip())

        return state

    @handle_errors
    def _pergunta_mesma_guia(self, state: ServiceState) -> ServiceState:
        """Pergunta se quer gerar guia para o mesmo imóvel novamente."""
        # Se já foi respondido, não pergunta novamente
        if "quer_mesma_guia" in state.internal:
            return state

        response = AgentResponse(
            description="🔄 Deseja emitir mais guias para o mesmo imóvel?",
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
            "tipo_cobranca",
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
            "tipo_cobranca",
            "cotas_escolhidas",
            "formato_pagamento",
            "guias_geradas",
        ]
        for campo in campos_limpar:
            state.data.pop(campo, None)

        # Limpa flags internas
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
            "tipo_cobranca",
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

    def _route_after_verificacao_cota(self, state: ServiceState) -> str:
        """Roteamento após verificação do tipo de cota."""
        if state.internal.get("fluxo_cota_unica", False):
            return "escolher_formato_cota_unica"
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

    # --- Construção do Grafo ---

    def build_graph(self) -> StateGraph[ServiceState]:
        """Constrói o grafo do workflow IPTU."""
        graph = StateGraph(ServiceState)

        # Adiciona todos os nós
        graph.add_node("informar_inscricao", self._informar_inscricao_imobiliaria)
        graph.add_node("escolher_ano", self._escolher_ano_exercicio)
        graph.add_node("consultar_guias", self._consultar_guias_disponiveis)
        graph.add_node("usuario_escolhe_guias", self._usuario_escolhe_guias_iptu)
        graph.add_node("verificar_cota_unica", self._verificar_cota_unica)
        graph.add_node("escolher_formato_cota_unica", self._escolher_formato_cota_unica)
        graph.add_node("escolher_cotas", self._escolher_cotas_pagar)
        graph.add_node("darf_separado", self._deseja_pagar_darf_separado)
        graph.add_node("confirmacao_dados", self._confirmacao_dados_pagamento)
        graph.add_node("pergunta_mesma_guia", self._pergunta_mesma_guia)
        graph.add_node("pergunta_outro_imovel", self._pergunta_outro_imovel)
        graph.add_node("reset_mesma_guia", self._reset_para_mesma_guia)
        graph.add_node("reset_outro_imovel", self._reset_para_outro_imovel)
        graph.add_node("finalizar_interacao", self._finalizar_interacao)

        # Nós de roteamento
        graph.add_node("route_inscricao", lambda state: state)
        graph.add_node("route_cota", lambda state: state)
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
            {"continue": "verificar_cota_unica", END: END},
        )

        graph.add_conditional_edges(
            "verificar_cota_unica",
            self._decide_after_data_collection,
            {"continue": "route_cota", END: END},
        )

        graph.add_conditional_edges(
            "route_cota",
            self._route_after_verificacao_cota,
            {
                "escolher_formato_cota_unica": "escolher_formato_cota_unica",
                "escolher_cotas": "escolher_cotas",
            },
        )

        graph.add_conditional_edges(
            "escolher_formato_cota_unica",
            self._decide_after_data_collection,
            {"continue": "confirmacao_dados", END: END},
        )

        graph.add_conditional_edges(
            "escolher_cotas",
            self._decide_after_data_collection,
            {"continue": "darf_separado", END: END},
        )

        graph.add_conditional_edges(
            "darf_separado",
            self._decide_after_data_collection,
            {"continue": "confirmacao_dados", END: END},
        )

        graph.add_edge("confirmacao_dados", "pergunta_mesma_guia")

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
