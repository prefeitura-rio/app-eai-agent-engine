"""
Templates de mensagens para o workflow IPTU.

Este módulo centraliza todos os textos e mensagens exibidas ao agente
durante o fluxo de consulta e pagamento de IPTU.
"""

from typing import List, Dict, Any


class IPTUMessageTemplates:
    """Templates de mensagens para cada etapa do workflow IPTU."""

    # --- Coleta de Dados Iniciais ---

    @staticmethod
    def solicitar_inscricao() -> str:
        """Mensagem solicitando inscrição imobiliária."""
        return "📋 Para consultar o IPTU, informe a inscrição imobiliária do seu imóvel (8 a 15 dígitos)."

    @staticmethod
    def escolher_ano() -> str:
        """Mensagem para escolha do ano de exercício."""
        return "📅 Escolha o ano de exercício para consulta do IPTU:"

    # --- Erros de Consulta ---

    @staticmethod
    def inscricao_nao_encontrada() -> str:
        """Mensagem quando inscrição não é encontrada."""
        return "❌ Inscrição imobiliária não encontrada. Verifique o número e tente novamente."

    @staticmethod
    def inscricao_nao_encontrada_apos_tentativas() -> str:
        """Mensagem quando inscrição não é encontrada após múltiplas tentativas."""
        return "❌ Inscrição imobiliária não encontrada após múltiplas tentativas. Verifique o número e tente novamente."

    @staticmethod
    def nenhuma_guia_encontrada(inscricao: str, exercicio: int) -> str:
        """Mensagem quando nenhuma guia é encontrada para o ano selecionado."""
        return f"❌ Nenhuma guia de IPTU foi encontrada para o ano {exercicio} da inscrição {inscricao}.\n\n📅 Por favor, escolha outro ano de exercício:"

    @staticmethod
    def nenhuma_cota_encontrada(guia_escolhida: str) -> str:
        """Mensagem quando nenhuma cota é encontrada para a guia."""
        return f"❌ Nenhuma cota foi encontrada para a guia {guia_escolhida}.\n\n🎯 Por favor, selecione outra guia disponível:"

    @staticmethod
    def cotas_quitadas(guia_escolhida: str) -> str:
        """Mensagem quando todas as cotas da guia já foram quitadas."""
        return f"✅ Todas as cotas da guia {guia_escolhida} já foram quitadas.\n\n🎯 Por favor, selecione outra guia disponível:"

    # --- Exibição de Dados ---

    @staticmethod
    def dados_imovel(
        inscricao: str,
        proprietario: str,
        endereco: str,
        exercicio: str,
        guias: List[Dict[str, Any]],
    ) -> str:
        """Formata dados do imóvel e guias disponíveis."""
        texto = f"""🏠 **Dados do Imóvel Encontrado:**
🆔 **Inscrição:** {inscricao}
💼 **Proprietário:** {proprietario}
📍 **Endereço:** {endereco}

📋 **Guias Disponíveis para IPTU {exercicio}:**

"""
        for guia in guias:
            numero_guia = guia.get("numero_guia", "N/A")
            tipo_guia = guia.get("tipo", "IPTU").upper()
            valor_original = guia.get("valor_original", 0.0)
            situacao = guia.get("situacao", "EM ABERTO")

            texto += f"""💳 **Guia {numero_guia}** - {tipo_guia}
• Valor: R$ {valor_original:.2f}
• Situação: {situacao}

"""

        # Lista os números das guias disponíveis
        numeros_disponiveis = [guia.get("numero_guia", "N/A") for guia in guias]
        exemplos_reais = ", ".join([f'"{num}"' for num in numeros_disponiveis])

        texto += f"""🎯 **Para continuar, selecione a guia desejada:**
Informe o número da guia ({exemplos_reais})"""

        return texto


    @staticmethod
    def selecionar_cotas(cotas: List[Dict[str, Any]], valor_total: float) -> str:
        """Formata lista de cotas disponíveis para seleção."""
        texto = "📋 **Selecione as cotas que deseja pagar:**\n\n"

        for cota in cotas:
            numero_cota = cota.get("numero_cota", "?")
            data_vencimento = cota.get("data_vencimento", "N/A")
            valor_cota = cota.get("valor_cota", "0,00")
            esta_vencida = cota.get("esta_vencida", False)

            status_icon = "🟡" if esta_vencida else "🟢"
            status_text = "VENCIDA" if esta_vencida else "EM ABERTO"

            texto += f"• **{numero_cota}ª Cota** - Venc: {data_vencimento} - R$ {valor_cota} - {status_icon} {status_text}\n"

        texto += f"\n• **Todas as cotas** - Total: R$ {valor_total:.2f}\n"
        texto += "\n**Quais cotas você deseja pagar?**"

        return texto

    # --- Formato de Pagamento ---

    @staticmethod
    def escolher_formato_darm() -> str:
        """Mensagem para escolha do formato de boleto."""
        return """📋 **Como deseja gerar os boletos?**

• **Boleto único** para todas as cotas selecionadas.
• **Um boleto para cada cota** selecionada.
"""

    # --- Confirmação ---

    @staticmethod
    def confirmacao_dados(
        inscricao: str,
        endereco: str,
        proprietario: str,
        guia_escolhida: str,
        cotas_escolhidas: List[str],
        num_boletos: int,
    ) -> str:
        """Formata confirmação dos dados antes da geração."""
        return f"""📋 **Confirmação dos Dados**

**Imóvel:** {inscricao}
**Endereço:** {endereco}
**Proprietário:** {proprietario}
**Guia:** {guia_escolhida}
**Cotas:** {', '.join(cotas_escolhidas)}
**Boletos a serem gerados:** {num_boletos}

✅ **Os dados estão corretos?**"""

    @staticmethod
    def dados_nao_confirmados() -> str:
        """Mensagem quando usuário não confirma os dados."""
        return "❌ **Dados não confirmados**. Voltando ao início."

    # --- Geração de Boletos ---

    @staticmethod
    def boletos_gerados(
        guias_geradas: List[Dict[str, Any]], inscricao: str
    ) -> str:
        """Formata informações dos boletos gerados."""
        if not guias_geradas:
            return "❌ Nenhum boleto foi gerado."

        texto = "✅ **Boletos Gerados com Sucesso!**\n\n"

        for boleto_num, guia in enumerate(guias_geradas, 1):
            texto += f"**Boleto {boleto_num}:**\n"
            texto += f"**Inscrição:** {inscricao}\n"
            texto += f"**Guia:** {guia['numero_guia']}\n"
            texto += f"**Cotas:** {guia['cotas']}\n"
            texto += f"**Valor:** R$ {guia['valor']:.2f}\n"
            texto += f"**Vencimento:** {guia['vencimento']}\n"
            texto += f"**Código de Barras:** {guia['codigo_barras']}\n"
            texto += f"**Linha Digitável:** {guia['linha_digitavel']}\n"
            texto += f"**PDF:** {guia.get('pdf', 'Não disponível')}\n\n"

        return texto

    @staticmethod
    def erro_gerar_darm(cotas: List[str]) -> str:
        """Mensagem de erro ao gerar DARM."""
        return f"❌ Não foi possível gerar o DARM para as cotas {', '.join(cotas)}.\n\n🎯 Por favor, selecione novamente as cotas para pagamento:"

    @staticmethod
    def erro_processar_pagamento(cotas: List[str], erro: str) -> str:
        """Mensagem de erro ao processar pagamento."""
        return f"❌ Erro ao processar o pagamento das cotas {', '.join(cotas)}: {erro}\n\n🎯 Por favor, selecione novamente as cotas para pagamento:"

    @staticmethod
    def nenhum_boleto_gerado() -> str:
        """Mensagem quando nenhum boleto foi gerado com sucesso."""
        return "❌ Não foi possível gerar nenhum boleto de pagamento.\n\n🎯 Por favor, selecione novamente as cotas para pagamento:"

    # --- Perguntas de Continuidade ---

    @staticmethod
    def perguntar_mais_cotas(boletos_gerados: str) -> str:
        """Pergunta se quer pagar mais cotas da mesma guia."""
        return boletos_gerados + "\n🔄 **Deseja pagar mais cotas da mesma guia?**"

    @staticmethod
    def perguntar_outras_guias(boletos_gerados: str) -> str:
        """Pergunta se quer pagar outras guias do mesmo imóvel."""
        return boletos_gerados + "\n🔄 **Deseja pagar outras guias do mesmo imóvel?**"

    @staticmethod
    def perguntar_outro_imovel() -> str:
        """Pergunta se quer emitir guia para outro imóvel."""
        return "🏠 Deseja emitir guia para outro imóvel?"

    # --- Finalização ---

    @staticmethod
    def finalizacao() -> str:
        """Mensagem de finalização do serviço."""
        return """✅ **Serviço finalizado com sucesso!**

Obrigado por utilizar o serviço de consulta do IPTU da Prefeitura do Rio de Janeiro.

Para uma nova consulta, informe uma nova inscrição imobiliária."""

    # --- Erros Internos ---

    @staticmethod
    def erro_interno(detalhe: str) -> str:
        """Mensagem genérica de erro interno."""
        return f"❌ Erro interno: {detalhe}"

    @staticmethod
    def erro_dados_guias_invalidos() -> str:
        """Mensagem quando dados das guias estão incompletos ou inválidos."""
        return "❌ Não foi possível carregar as informações das guias. Por favor, tente novamente mais tarde ou verifique a inscrição imobiliária."

    @staticmethod
    def erro_dados_cotas_invalidos() -> str:
        """Mensagem quando dados das cotas estão incompletos ou inválidos."""
        return "❌ Não foi possível carregar as informações das cotas. Por favor, tente novamente."
