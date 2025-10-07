"""
Serviço de API para consulta de IPTU (Placeholder)

Este módulo implementa placeholders para as chamadas de API
que serão conectadas à API real da Prefeitura do Rio posteriormente.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from src.services.workflows.iptu_ano_vigente.models import DadosIPTU, GuiaIPTU, DadosConsulta


class IPTUAPIService:
    """
    Serviço de API placeholder para consulta de IPTU.
    
    Esta classe simula as respostas da API real da Prefeitura do Rio
    para permitir desenvolvimento e testes do workflow.
    """
    
    def __init__(self):
        self.inscricoes_validas = [
            "01234567890123",
            "98765432109876", 
            "11223344556677",
            "55667788990011"
        ]
    
    def consultar_iptu(self, inscricao_imobiliaria: str) -> Optional[DadosConsulta]:
        """
        Consulta dados do IPTU por inscrição imobiliária.
        
        Args:
            inscricao_imobiliaria: Número da inscrição imobiliária
            
        Returns:
            DadosConsulta com informações do IPTU ou None se não encontrado
        """
        # Simula verificação se inscrição é válida
        if inscricao_imobiliaria not in self.inscricoes_validas:
            return None
        
        # Simula dados do IPTU
        dados_iptu = DadosIPTU(
            inscricao_imobiliaria=inscricao_imobiliaria,
            endereco=self._gerar_endereco_ficticio(),
            proprietario=self._gerar_nome_ficticio(),
            valor_iptu=random.uniform(500.0, 5000.0),
            valor_taxa_lixo=random.uniform(50.0, 200.0),
            ano_vigente=2024
        )
        
        # Simula guias disponíveis
        guias = self._gerar_guias_ficticias(dados_iptu.valor_iptu)
        
        return DadosConsulta(
            dados_iptu=dados_iptu,
            guias_disponiveis=guias
        )
    
    def obter_guias_pagamento(
        self, 
        inscricao: str, 
        tipo_cobranca: str,
        formato_pagamento: str,
        guia_escolhida: str = "IPTU",
        cotas_escolhidas: List[str] = None
    ) -> List[GuiaIPTU]:
        """
        Obtém guias de pagamento formatadas conforme solicitado.
        
        Args:
            inscricao: Inscrição imobiliária
            tipo_cobranca: "cota_unica" ou "cota_parcelada"
            formato_pagamento: "darf" ou "codigo_barras"
            guia_escolhida: Tipo de guia ("IPTU" ou "Taxa de Lixo")
            cotas_escolhidas: Lista de cotas para parcelamento
            
        Returns:
            Lista de guias formatadas
        """
        if cotas_escolhidas is None:
            cotas_escolhidas = []
        dados_consulta = self.consultar_iptu(inscricao)
        if not dados_consulta:
            return []
        
        guias = []
        
        # Determina valor base conforme guia escolhida
        if guia_escolhida == "Taxa de Lixo":
            valor_base = dados_consulta.dados_iptu.valor_taxa_lixo or 0
            descricao_base = "Taxa de Lixo"
        else:
            valor_base = dados_consulta.dados_iptu.valor_iptu
            descricao_base = "IPTU"
        
        if tipo_cobranca == "cota_unica":
            # Desconto de 7% para cota única
            valor_com_desconto = valor_base * 0.93
            guia = self._criar_guia(
                "001", 
                valor_com_desconto, 
                formato_pagamento,
                descricao=f"Cota Única {descricao_base} 2024"
            )
            guias.append(guia)
        else:
            # Parcelamento - considera cotas escolhidas ou todas se vazio
            num_parcelas = 10
            valor_parcela = valor_base / num_parcelas
            
            if not cotas_escolhidas or "Todas as cotas" in cotas_escolhidas:
                # Gera todas as parcelas
                cotas_gerar = range(1, num_parcelas + 1)
            else:
                # Gera apenas as cotas escolhidas
                cotas_gerar = []
                for cota in cotas_escolhidas:
                    if "Cota" in cota:
                        # Extrai número da cota (ex: "1ª Cota" -> 1)
                        num_cota = int(cota.split("ª")[0])
                        cotas_gerar.append(num_cota)
            
            for i in cotas_gerar:
                vencimento = datetime.now() + timedelta(days=30 * (i-1))
                guia = self._criar_guia(
                    f"{i:03d}",
                    valor_parcela,
                    formato_pagamento,
                    descricao=f"Parcela {i}/{num_parcelas} {descricao_base} 2024",
                    vencimento=vencimento.strftime("%d/%m/%Y")
                )
                guias.append(guia)
        
        return guias
    
    def _gerar_endereco_ficticio(self) -> str:
        """Gera endereço fictício para teste."""
        ruas = [
            "Rua das Laranjeiras",
            "Avenida Copacabana", 
            "Rua Voluntários da Pátria",
            "Avenida Presidente Vargas",
            "Rua Barata Ribeiro"
        ]
        numero = random.randint(1, 999)
        bairro = random.choice([
            "Copacabana", "Ipanema", "Leblon", 
            "Botafogo", "Flamengo", "Laranjeiras"
        ])
        return f"{random.choice(ruas)}, {numero} - {bairro}, Rio de Janeiro/RJ"
    
    def _gerar_nome_ficticio(self) -> str:
        """Gera nome fictício para teste."""
        nomes = [
            "João da Silva Santos",
            "Maria Oliveira Costa", 
            "Carlos Alberto Ferreira",
            "Ana Paula Rodrigues",
            "Pedro Henrique Lima"
        ]
        return random.choice(nomes)
    
    def _gerar_guias_ficticias(self, valor_base: float) -> List[GuiaIPTU]:
        """Gera guias fictícias para desenvolvimento."""
        # Por enquanto retorna lista vazia, as guias serão geradas 
        # quando o usuário escolher o tipo de cobrança
        return []
    
    def _criar_guia(
        self, 
        numero: str, 
        valor: float, 
        formato: str,
        descricao: str = "",
        vencimento: Optional[str] = None
    ) -> GuiaIPTU:
        """Cria uma guia de pagamento."""
        if not vencimento:
            vencimento = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
        
        guia = GuiaIPTU(
            numero_guia=numero,
            valor=valor,
            vencimento=vencimento
        )
        
        if formato == "codigo_barras":
            # Simula código de barras
            guia.codigo_barras = f"03399{random.randint(100000000000, 999999999999)}00000000{int(valor*100):010d}"
            guia.linha_digitavel = self._gerar_linha_digitavel(guia.codigo_barras)
        else:
            # Simula dados DARF
            guia.darf_data = {
                "codigo_receita": "0561",
                "competencia": "12/2024",
                "vencimento": vencimento,
                "valor": valor,
                "descricao": descricao
            }
        
        return guia
    
    def _gerar_linha_digitavel(self, codigo_barras: str) -> str:
        """Gera linha digitável a partir do código de barras."""
        # Simulação simples - na implementação real seria o algoritmo correto
        return f"{codigo_barras[:5]}.{codigo_barras[5:10]} {codigo_barras[10:15]}.{codigo_barras[15:21]} {codigo_barras[21:26]}.{codigo_barras[26:32]} {codigo_barras[32:33]} {codigo_barras[33:]}"