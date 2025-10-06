"""
Workflow IPTU Ano Vigente - Prefeitura do Rio de Janeiro

Implementa o fluxo completo de consulta e emissão de guias de IPTU
seguindo o fluxograma oficial da Prefeitura do Rio.
"""

from typing import Optional
from langgraph.graph import StateGraph, END

from src.services.core.base_workflow import BaseWorkflow, handle_errors
from src.services.core.models import ServiceState, AgentResponse

from src.services.workflows.iptu_ano_vigente.models import (
    InscricaoImobiliariaPayload,
    ColetarGuiasPayload,
    EscolhaCobrancaPayload,
    EscolhaFormatoPagamentoPayload,
    ConfirmacaoDadosPayload,
    EscolhaGuiaMesmoImovelPayload,
    EscolhaOutroImovelPayload,
)
from src.services.workflows.iptu_ano_vigente.api_service import IPTUAPIService


class IPTUAnoVigenteWorkflow(BaseWorkflow):
    """
    Workflow para consulta de IPTU do ano vigente da Prefeitura do Rio.
    
    Fluxo principal:
    1. Coleta inscrição imobiliária
    2. Consulta guias disponíveis
    3. Usuário informa qual cota quer pagar
    4. Verifica se é cota única
    5. Escolhe cotas a pagar
    6. Confirma dados para pagamento
    7. Pergunta se quer guia do mesmo imóvel ou outro
    """
    
    service_name = "iptu_ano_vigente"
    description = "Consulta e emissão de guias de IPTU do ano vigente - Prefeitura do Rio de Janeiro"
    
    def __init__(self):
        super().__init__()
        self.api_service = IPTUAPIService()
    
    # --- Nós do Grafo ---
    
    @handle_errors
    def _informar_inscricao_imobiliaria(self, state: ServiceState) -> ServiceState:
        """Coleta a inscrição imobiliária do usuário."""
        if "inscricao_imobiliaria" in state.data:
            return state
        
        response = AgentResponse(
            description="📋 Para consultar o IPTU, informe a inscrição imobiliária do seu imóvel (14 a 16 dígitos).",
            payload_schema=InscricaoImobiliariaPayload.model_json_schema(),
        )
        state.agent_response = response
        
        if "inscricao_imobiliaria" in state.payload:
            try:
                validated_data = InscricaoImobiliariaPayload.model_validate(state.payload)
                state.data["inscricao_imobiliaria"] = validated_data.inscricao_imobiliaria
                state.agent_response = None
            except Exception as e:
                response.error_message = f"Inscrição imobiliária inválida: {str(e)}"
        
        return state
    
    @handle_errors 
    def _consultar_guias_disponiveis(self, state: ServiceState) -> ServiceState:
        """Consulta as guias disponíveis para pagamento."""
        inscricao = state.data.get("inscricao_imobiliaria")
        
        if not inscricao:
            state.agent_response = AgentResponse(
                description="❌ Erro interno: inscrição imobiliária não encontrada.",
                error_message="Inscrição imobiliária não foi coletada corretamente"
            )
            return state
        
        # Consulta dados via API (placeholder)
        dados_consulta = self.api_service.consultar_iptu(inscricao)
        
        if not dados_consulta:
            # Inscrição não encontrada - volta para informar inscrição
            state.internal["inscricao_invalida"] = True
            state.agent_response = AgentResponse(
                description="❌ Inscrição imobiliária não encontrada. Verifique o número e tente novamente.",
                payload_schema=InscricaoImobiliariaPayload.model_json_schema(),
            )
            # Remove inscrição inválida para permitir nova entrada
            state.data.pop("inscricao_imobiliaria", None)
            return state
        
        # Salva dados da consulta
        state.data["dados_iptu"] = dados_consulta.dados_iptu.model_dump()
        state.internal["consulta_realizada"] = True
        
        # Não para o fluxo aqui - apenas salva os dados e continua automaticamente
        # O próximo nó (_usuario_informa_cota_pagar) vai mostrar as opções
        state.agent_response = None
        
        return state
    
    @handle_errors
    def _usuario_informa_cota_pagar(self, state: ServiceState) -> ServiceState:
        """Usuário informa qual cota quer pagar."""
        if "tipo_cobranca" in state.data:
            return state
        
        # Mostra informações do imóvel se acabou de ser consultado
        dados_iptu = state.data.get("dados_iptu", {})
        if dados_iptu:
            response_text = f"""🏠 **Dados do Imóvel Encontrado:**

📍 **Endereço:** {dados_iptu['endereco']}
👤 **Proprietário:** {dados_iptu['proprietario']}
💰 **Valor IPTU {dados_iptu['ano_vigente']}:** R$ {dados_iptu['valor_iptu']:.2f}
🗑️ **Taxa de Lixo:** R$ {dados_iptu['valor_taxa_lixo']:.2f}

💳 **Qual forma de pagamento você prefere?**

• **Cota Única** - Pagamento à vista com 7% de desconto
• **Cota Parcelada** - Parcelamento em até 10x sem juros"""
        else:
            response_text = """💳 Qual forma de pagamento você prefere?

• **Cota Única** - Pagamento à vista com 7% de desconto
• **Cota Parcelada** - Parcelamento em até 10x sem juros"""
        
        response = AgentResponse(
            description=response_text,
            payload_schema=EscolhaCobrancaPayload.model_json_schema(),
        )
        state.agent_response = response
        
        if "tipo_cobranca" in state.payload:
            validated_data = EscolhaCobrancaPayload.model_validate(state.payload)
            state.data["tipo_cobranca"] = validated_data.tipo_cobranca
            state.agent_response = None
        
        return state
    
    @handle_errors
    def _verificar_cota_unica(self, state: ServiceState) -> ServiceState:
        """Verifica se é cota única e processa adequadamente."""
        tipo_cobranca = state.data.get("tipo_cobranca")
        
        if tipo_cobranca == "cota_unica":
            state.internal["fluxo_cota_unica"] = True
        else:
            state.internal["fluxo_cota_unica"] = False
        
        # Não para o fluxo aqui - vai direto para o próximo step
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
            validated_data = EscolhaFormatoPagamentoPayload.model_validate(state.payload)
            state.data["formato_pagamento"] = validated_data.formato_pagamento
            state.agent_response = None
        
        return state
    
    @handle_errors
    def _escolher_cotas_pagar(self, state: ServiceState) -> ServiceState:
        """Para fluxo parcelado, permite escolher formato de pagamento."""
        # Este nó só é executado para parcelamento
        if state.internal.get("fluxo_cota_unica", False):
            return state
        
        if "formato_pagamento" in state.data:
            return state
        
        response_text = """📋 **Parcelamento Selecionado**

Você optou pelo parcelamento em até 10x. As parcelas estarão disponíveis com vencimentos mensais.

Escolha como deseja receber as guias de pagamento:"""
        
        response = AgentResponse(
            description=response_text,
            payload_schema=EscolhaFormatoPagamentoPayload.model_json_schema(),
        )
        state.agent_response = response
        
        if "formato_pagamento" in state.payload:
            validated_data = EscolhaFormatoPagamentoPayload.model_validate(state.payload)
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
                validated_data = EscolhaFormatoPagamentoPayload.model_validate(state.payload)
                state.data["formato_pagamento"] = validated_data.formato_pagamento
            else:
                state.agent_response = AgentResponse(
                    description="📋 Escolha como deseja receber as guias de pagamento:",
                    payload_schema=EscolhaFormatoPagamentoPayload.model_json_schema(),
                )
                return state
        
        # Gera as guias de pagamento
        inscricao = state.data["inscricao_imobiliaria"]
        tipo_cobranca = state.data["tipo_cobranca"]
        formato_pagamento = state.data["formato_pagamento"]
        
        guias = self.api_service.obter_guias_pagamento(
            inscricao, tipo_cobranca, formato_pagamento
        )
        
        # Salva as guias geradas
        state.data["guias_geradas"] = [guia.model_dump() for guia in guias]
        
        # Monta texto de confirmação
        dados_iptu = state.data["dados_iptu"]
        response_text = f"""
✅ **Guias de Pagamento Geradas!**

🏠 **Imóvel:** {dados_iptu['endereco']}
💳 **Tipo:** {'Cota Única (7% desconto)' if tipo_cobranca == 'cota_unica' else 'Parcelamento'}
📄 **Formato:** {'DARF Separado' if formato_pagamento == 'darf' else 'Código de Barras'}

📋 **Guias Geradas:** {len(guias)} guia(s)
        """
        
        if formato_pagamento == "codigo_barras":
            for i, guia in enumerate(guias[:3], 1):  # Mostra só as 3 primeiras
                response_text += f"\n\n**Guia {i}:**\n"
                response_text += f"💰 Valor: R$ {guia.valor:.2f}\n"
                response_text += f"📅 Vencimento: {guia.vencimento}\n"
                response_text += f"📊 Código: {guia.linha_digitavel}"
            
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
        campos_limpar = ["tipo_cobranca", "formato_pagamento", "guias_geradas"]
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
            "inscricao_imobiliaria", "dados_iptu", "tipo_cobranca", 
            "formato_pagamento", "guias_geradas"
        ]
        for campo in campos_limpar:
            state.data.pop(campo, None)
        
        # Limpa flags internas
        flags_limpar = [
            "consulta_realizada", "dados_confirmados", "fluxo_cota_unica",
            "quer_mesma_guia", "quer_outro_imovel", "inscricao_invalida"
        ]
        for flag in flags_limpar:
            state.internal.pop(flag, None)
        
        return state
    
    # --- Roteadores Condicionais ---
    
    def _decide_after_data_collection(self, state: ServiceState):
        """Roteador genérico para nós de coleta de dados."""
        if state.agent_response is not None:
            return END
        return "continue"
    
    def _route_after_inscricao(self, state: ServiceState) -> str:
        """Roteamento após coleta da inscrição."""
        if state.internal.get("inscricao_invalida", False):
            # Se inscrição inválida, volta para coleta
            return "informar_inscricao"
        return "consultar_guias"
    
    def _route_consulta_guias(self, state: ServiceState) -> str:
        """Roteamento após consulta de guias."""
        if state.internal.get("inscricao_invalida", False):
            return "informar_inscricao"
        return "usuario_informa_cota"
    
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
        return END  # Finaliza o workflow
    
    # --- Construção do Grafo ---
    
    def build_graph(self) -> StateGraph[ServiceState]:
        """Constrói o grafo do workflow IPTU."""
        graph = StateGraph(ServiceState)
        
        # Adiciona todos os nós
        graph.add_node("informar_inscricao", self._informar_inscricao_imobiliaria)
        graph.add_node("consultar_guias", self._consultar_guias_disponiveis)
        graph.add_node("usuario_informa_cota", self._usuario_informa_cota_pagar)
        graph.add_node("verificar_cota_unica", self._verificar_cota_unica)
        graph.add_node("escolher_formato_cota_unica", self._escolher_formato_cota_unica)
        graph.add_node("escolher_cotas", self._escolher_cotas_pagar)
        graph.add_node("confirmacao_dados", self._confirmacao_dados_pagamento)
        graph.add_node("pergunta_mesma_guia", self._pergunta_mesma_guia)
        graph.add_node("pergunta_outro_imovel", self._pergunta_outro_imovel)
        graph.add_node("reset_mesma_guia", self._reset_para_mesma_guia)
        graph.add_node("reset_outro_imovel", self._reset_para_outro_imovel)
        
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
            {"continue": "route_inscricao", END: END}
        )
        
        graph.add_conditional_edges(
            "route_inscricao",
            self._route_after_inscricao,
            {
                "informar_inscricao": "informar_inscricao",
                "consultar_guias": "consultar_guias"
            }
        )
        
        graph.add_conditional_edges(
            "consultar_guias",
            self._route_consulta_guias,
            {
                "informar_inscricao": "informar_inscricao",
                "usuario_informa_cota": "usuario_informa_cota"
            }
        )
        
        graph.add_conditional_edges(
            "usuario_informa_cota",
            self._decide_after_data_collection,
            {"continue": "verificar_cota_unica", END: END}
        )
        
        graph.add_conditional_edges(
            "verificar_cota_unica",
            self._decide_after_data_collection,
            {"continue": "route_cota", END: END}
        )
        
        graph.add_conditional_edges(
            "route_cota",
            self._route_after_verificacao_cota,
            {
                "escolher_formato_cota_unica": "escolher_formato_cota_unica",
                "escolher_cotas": "escolher_cotas"
            }
        )
        
        graph.add_conditional_edges(
            "escolher_formato_cota_unica",
            self._decide_after_data_collection,
            {"continue": "confirmacao_dados", END: END}
        )
        
        graph.add_conditional_edges(
            "escolher_cotas",
            self._decide_after_data_collection,
            {"continue": "confirmacao_dados", END: END}
        )
        
        graph.add_edge("confirmacao_dados", "pergunta_mesma_guia")
        
        graph.add_conditional_edges(
            "pergunta_mesma_guia",
            self._decide_after_data_collection,
            {"continue": "route_mesma_guia", END: END}
        )
        
        graph.add_conditional_edges(
            "route_mesma_guia",
            self._route_after_mesma_guia,
            {
                "reset_mesma_guia": "reset_mesma_guia",
                "pergunta_outro_imovel": "pergunta_outro_imovel"
            }
        )
        
        graph.add_edge("reset_mesma_guia", "usuario_informa_cota")
        
        graph.add_conditional_edges(
            "pergunta_outro_imovel",
            self._decide_after_data_collection,
            {"continue": "route_outro_imovel", END: END}
        )
        
        graph.add_conditional_edges(
            "route_outro_imovel",
            self._route_after_outro_imovel,
            {
                "reset_outro_imovel": "reset_outro_imovel",
                END: END
            }
        )
        
        graph.add_edge("reset_outro_imovel", "informar_inscricao")
        
        return graph