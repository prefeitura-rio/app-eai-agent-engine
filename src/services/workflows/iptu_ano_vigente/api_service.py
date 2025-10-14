"""
Serviço de API para consulta de IPTU - Integração Real

Este módulo implementa a integração com a API real da Prefeitura do Rio
para consulta de IPTU e geração de guias de pagamento.
"""

import logging
import re
import string
from datetime import datetime
from typing import List, Optional, Dict, Any
import httpx

from src.config import env
from src.services.workflows.iptu_ano_vigente.models import DadosIPTU, GuiaIPTU, DadosConsulta

logger = logging.getLogger(__name__)


class IPTUAPIService:
    """
    Serviço de API para consulta de IPTU da Prefeitura do Rio.
    
    Integra com a API real para:
    - Consultar guias disponíveis (ConsultarGuias)
    - Consultar cotas/parcelas (ConsultarCotas)
    - Gerar DARM para pagamento (ConsultarDARM)
    """
    
    def __init__(self):
        """Inicializa o serviço com configurações da API."""
        self.api_base_url = env.IPTU_API_URL
        self.api_token = env.IPTU_API_TOKEN
        self.proxy = "http://proxy.squirrel-regulus.ts.net:3128"
        
        # Ano vigente padrão - pode ser sobrescrito
        self.ano_vigente = datetime.now().year
        
        logger.info(f"IPTUAPIService initialized with API URL: {self.api_base_url}")
    
    @staticmethod
    def _validar_inscricao(inscricao: str) -> Optional[str]:
        """
        Valida e limpa a inscrição imobiliária.
        
        Remove pontuação e valida o formato.
        
        Args:
            inscricao: Inscrição imobiliária a validar
            
        Returns:
            Inscrição limpa ou None se inválida
        """
        if not inscricao:
            return None
        
        # Remove pontuação e espaços
        inscricao_clean = inscricao.translate(str.maketrans('', '', string.punctuation + ' '))
        
        # Valida se é numérico
        if not inscricao_clean.isdigit():
            logger.warning(f"Inscricao contains non-numeric characters: {inscricao}")
            return None
        
        # Valida tamanho ANTES de remover zeros (API aceita inscrições curtas)
        # Máximo de 15 dígitos para evitar erro 500
        if len(inscricao_clean) > 15:
            logger.warning(f"Inscricao too long: {inscricao_clean} ({len(inscricao_clean)} chars)")
            return None
        
        # Remove zeros à esquerda
        inscricao_clean = str(int(inscricao_clean))
        
        return inscricao_clean
    
    async def _make_api_request(
        self, 
        endpoint: str, 
        params: Dict[str, Any],
        expect_json: bool = True
    ) -> Optional[Any]:
        """
        Faz requisição à API com tratamento de erros.
        
        Args:
            endpoint: Nome do endpoint (ex: "ConsultarGuias")
            params: Parâmetros da requisição
            expect_json: Se True, espera resposta JSON. Se False, retorna texto bruto (para PDFs)
            
        Returns:
            Resposta JSON da API, texto bruto, ou None em caso de erro
        """
        # Adiciona token aos parâmetros
        params["token"] = self.api_token
        
        url = f"{self.api_base_url}/{endpoint}"
        
        try:
            async with httpx.AsyncClient(proxy=self.proxy, timeout=30.0) as client:
                logger.info(f"Calling API: {endpoint} with params: {params}")
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    if expect_json:
                        data = response.json()
                        logger.info(f"API response successful for {endpoint}")
                        return data
                    else:
                        # Para downloads de PDF (base64)
                        logger.info(f"API response successful for {endpoint} (binary/text)")
                        return response.text
                elif response.status_code == 404:
                    logger.warning(f"API endpoint not found: {endpoint}")
                    return None
                elif response.status_code == 401:
                    logger.error(f"API authentication failed for {endpoint}")
                    return None
                elif response.status_code == 500:
                    logger.error(f"API internal error for {endpoint}: {response.text}")
                    return None
                else:
                    logger.error(f"API error {response.status_code} for {endpoint}: {response.text}")
                    return None
                    
        except httpx.TimeoutException:
            logger.error(f"Timeout calling API endpoint {endpoint}")
            return None
        except Exception as e:
            logger.error(f"Error calling API endpoint {endpoint}: {str(e)}")
            return None
    
    @staticmethod
    def _parse_brazilian_currency(value_str: str) -> float:
        """
        Converte string de valor brasileiro para float.
        
        Formato brasileiro: "4.123,92" -> 4123.92
        
        Args:
            value_str: String com valor no formato brasileiro
            
        Returns:
            Valor convertido para float
        """
        if not value_str or value_str == "0,00":
            return 0.0
        
        try:
            # Remove pontos (separador de milhar) e substitui vírgula por ponto
            clean_value = value_str.replace(".", "").replace(",", ".")
            return float(clean_value)
        except (ValueError, AttributeError):
            logger.warning(f"Failed to parse currency value: {value_str}")
            return 0.0
    
    async def consultar_iptu(
        self, 
        inscricao_imobiliaria: str,
        exercicio: Optional[int] = None
    ) -> Optional[DadosConsulta]:
        """
        Consulta dados do IPTU por inscrição imobiliária.
        
        Args:
            inscricao_imobiliaria: Número da inscrição imobiliária
            exercicio: Ano do exercício fiscal (ex: 2025). Se None, usa ano atual.
            
        Returns:
            DadosConsulta com informações do IPTU ou None se não encontrado
        """
        if exercicio is None:
            exercicio = self.ano_vigente
        
        # Valida e limpa inscrição
        inscricao_clean = self._validar_inscricao(inscricao_imobiliaria)
        if not inscricao_clean:
            logger.warning(f"Invalid inscricao format: {inscricao_imobiliaria}")
            return None
        
        # Consulta guias disponíveis
        guias_response = await self._make_api_request(
            "ConsultarGuias",
            {
                "inscricao": inscricao_clean,
                "exercicio": str(exercicio)
            }
        )
        
        if not guias_response:
            logger.info(f"No guides found for inscricao {inscricao_clean}, exercicio {exercicio}")
            return None
        
        if not isinstance(guias_response, list) or len(guias_response) == 0:
            logger.info(f"Empty guide list for inscricao {inscricao_clean}")
            return None
        
        # Filtra apenas guias em aberto (Situacao.codigo == "01")
        guias_em_aberto = [
            g for g in guias_response 
            if g.get("Situacao", {}).get("codigo") == "01"
        ]
        
        if not guias_em_aberto:
            logger.info(f"No open guides found for inscricao {inscricao_clean}")
            return None
        
        # Pega primeira guia em aberto para obter dados básicos
        primeira_guia = guias_em_aberto[0]
        
        # Extrai informações do imóvel
        inscricao_formatada = primeira_guia.get("Inscricao", inscricao_clean)
        valor_iptu = self._parse_brazilian_currency(
            primeira_guia.get("ValorIPTUOriginalGuia", "0,00")
        )
        
        # Cria objeto de dados IPTU
        # Nota: API não retorna endereço/proprietário neste endpoint
        # Esses dados podem vir de outro endpoint ou serem buscados posteriormente
        dados_iptu = DadosIPTU(
            inscricao_imobiliaria=inscricao_formatada,
            endereco=primeira_guia.get("Endereco") or "Endereço não disponível",
            proprietario=primeira_guia.get("Nome") or "Proprietário não disponível",
            valor_iptu=valor_iptu,
            valor_taxa_lixo=0.0,  # API não fornece separado neste endpoint
            ano_vigente=exercicio
        )
        
        return DadosConsulta(
            dados_iptu=dados_iptu,
            guias_disponiveis=[]  # Guias serão geradas sob demanda
        )
    
    async def obter_guias_pagamento(
        self, 
        inscricao: str, 
        tipo_cobranca: str,
        formato_pagamento: str,
        guia_escolhida: str = "IPTU",
        cotas_escolhidas: Optional[List[str]] = None,
        exercicio: Optional[int] = None
    ) -> List[GuiaIPTU]:
        """
        Obtém guias de pagamento formatadas conforme solicitado.
        
        Args:
            inscricao: Inscrição imobiliária
            tipo_cobranca: "cota_unica" ou "cota_parcelada"
            formato_pagamento: "darf" ou "codigo_barras"
            guia_escolhida: Tipo de guia ("IPTU" ou "Taxa de Lixo")
            cotas_escolhidas: Lista de cotas para parcelamento
            exercicio: Ano do exercício fiscal
            
        Returns:
            Lista de guias formatadas com código de barras ou dados DARF
        """
        if cotas_escolhidas is None:
            cotas_escolhidas = []
        
        if exercicio is None:
            exercicio = self.ano_vigente
        
        # Valida e limpa inscrição
        inscricao_clean = self._validar_inscricao(inscricao)
        if not inscricao_clean:
            logger.warning(f"Invalid inscricao format: {inscricao}")
            return []
        
        # Primeiro, consulta guias disponíveis
        guias_response = await self._make_api_request(
            "ConsultarGuias",
            {
                "inscricao": inscricao_clean,
                "exercicio": str(exercicio)
            }
        )
        
        if not guias_response or len(guias_response) == 0:
            logger.warning(f"No guides found for inscricao {inscricao_clean}")
            return []
        
        # Filtra guias em aberto
        guias_em_aberto = [
            g for g in guias_response 
            if g.get("Situacao", {}).get("codigo") == "01"
        ]
        
        if not guias_em_aberto:
            logger.warning(f"No open guides found for inscricao {inscricao_clean}")
            return []
        
        # Pega primeira guia em aberto (normalmente guia "00")
        guia_data = guias_em_aberto[0]
        numero_guia = guia_data.get("NGuia", "00")
        
        # Consulta cotas disponíveis para esta guia
        cotas_response = await self._make_api_request(
            "ConsultarCotas",
            {
                "inscricao": inscricao_clean,
                "exercicio": str(exercicio),
                "guia": numero_guia
            }
        )
        
        if not cotas_response or "Cotas" not in cotas_response:
            logger.warning(f"No cotas found for guia {numero_guia}")
            return []
        
        # Filtra cotas não pagas (Situacao.codigo != "01" significa não está em aberto, já foi paga)
        # Queremos as que ainda não foram pagas
        cotas_disponiveis = [
            c for c in cotas_response["Cotas"]
            if c.get("Situacao", {}).get("codigo") != "01"  # != "01" = não está em aberto (vencida, a vencer, etc)
        ]
        
        if not cotas_disponiveis:
            logger.warning(f"No unpaid cotas found for guia {numero_guia}")
            return []
        
        guias_result = []
        
        if tipo_cobranca == "cota_unica":
            # Para cota única, usa "00" conforme implementação original
            cotas_str = "00"
            
            darm_response = await self._make_api_request(
                "ConsultarDARM",
                {
                    "inscricao": inscricao_clean,
                    "exercicio": str(exercicio),
                    "guia": numero_guia,
                    "cotas": cotas_str
                }
            )
            
            if darm_response:
                # Valida se cota única ainda está válida (não vencida)
                data_vencimento_str = darm_response.get("DataVencimento", "")
                if data_vencimento_str:
                    try:
                        data_vencimento = datetime.strptime(data_vencimento_str, "%d/%m/%Y").date()
                        if data_vencimento < datetime.now().date():
                            logger.warning(f"Cota única expired: {data_vencimento_str}")
                            # Ainda retorna a guia mas pode adicionar flag
                    except ValueError:
                        logger.warning(f"Invalid date format: {data_vencimento_str}")
                
                guia = self._criar_guia_from_darm(darm_response, formato_pagamento)
                if guia:
                    guias_result.append(guia)
        
        else:
            # Parcelamento - determina quais cotas gerar
            if not cotas_escolhidas or "Todas as cotas" in cotas_escolhidas:
                # Gera DARM para todas as cotas disponíveis
                cotas_para_gerar = cotas_disponiveis
            else:
                # Filtra apenas cotas escolhidas
                cotas_nums_escolhidas = []
                for cota_str in cotas_escolhidas:
                    # Extrai número da cota (ex: "1ª Cota" -> "01")
                    if "ª Cota" in cota_str:
                        num = cota_str.split("ª")[0]
                        cotas_nums_escolhidas.append(f"{int(num):02d}")
                
                # Filtra cotas disponíveis
                cotas_para_gerar = [
                    c for c in cotas_disponiveis 
                    if c["NCota"] in cotas_nums_escolhidas
                ]
            
            # Gera DARM para cotas selecionadas (agrupado)
            if len(cotas_para_gerar) > 0:
                cotas_nums = [c["NCota"] for c in cotas_para_gerar]
                cotas_str = ",".join(cotas_nums)
                
                darm_response = await self._make_api_request(
                    "ConsultarDARM",
                    {
                        "inscricao": inscricao_clean,
                        "exercicio": str(exercicio),
                        "guia": numero_guia,
                        "cotas": cotas_str
                    }
                )
                
                if darm_response:
                    guia = self._criar_guia_from_darm(darm_response, formato_pagamento)
                    if guia:
                        guias_result.append(guia)
        
        return guias_result
    
    def _criar_guia_from_darm(
        self, 
        darm_data: Dict[str, Any], 
        formato: str
    ) -> Optional[GuiaIPTU]:
        """
        Cria uma GuiaIPTU a partir da resposta do ConsultarDARM.
        
        Args:
            darm_data: Dados retornados pela API ConsultarDARM
            formato: "darf" ou "codigo_barras"
            
        Returns:
            GuiaIPTU ou None se dados inválidos
        """
        try:
            valor = self._parse_brazilian_currency(
                darm_data.get("ValorAPagar", "0,00")
            )
            vencimento = darm_data.get("DataVencimento", "")
            numero_guia = darm_data.get("NGuia", "00")
            
            guia = GuiaIPTU(
                numero_guia=numero_guia,
                valor=valor,
                vencimento=vencimento
            )
            
            if formato == "codigo_barras":
                # API retorna SequenciaNumerica que é a linha digitável
                sequencia = darm_data.get("SequenciaNumerica", "")
                if sequencia:
                    guia.linha_digitavel = sequencia
                    # Código de barras seria uma conversão da linha digitável
                    # Por enquanto usa a mesma sequência
                    guia.codigo_barras = sequencia.replace(".", "").replace(" ", "")
            else:
                # Formato DARF
                guia.darf_data = {
                    "codigo_receita": darm_data.get("CodReceita", ""),
                    "descricao_receita": darm_data.get("DesReceita", ""),
                    "competencia": f"{darm_data.get('Exercicio', '')}/{darm_data.get('NGuia', '')}",
                    "vencimento": vencimento,
                    "valor": valor,
                    "descricao": darm_data.get("DescricaoDARM", ""),
                    "inscricao": darm_data.get("Inscricao", ""),
                    "tipo": darm_data.get("Tipo", ""),
                    "cotas": darm_data.get("Cotas", [])
                }
            
            return guia
            
        except Exception as e:
            logger.error(f"Error creating guia from DARM data: {str(e)}")
            return None
    
    async def download_pdf_darm(
        self,
        inscricao: str,
        exercicio: int,
        guia: str,
        cotas: str
    ) -> Optional[str]:
        """
        Faz download do PDF da DARM em formato base64.
        
        Args:
            inscricao: Inscrição imobiliária
            exercicio: Ano do exercício
            guia: Número da guia
            cotas: Cotas separadas por vírgula (ex: "01,02")
            
        Returns:
            String base64 do PDF ou None se falhar
        """
        # Valida e limpa inscrição
        inscricao_clean = self._validar_inscricao(inscricao)
        if not inscricao_clean:
            logger.warning(f"Invalid inscricao format: {inscricao}")
            return None
        
        # Faz requisição esperando resposta de texto (base64)
        pdf_base64 = await self._make_api_request(
            "DownloadPdfDARM",
            {
                "inscricao": inscricao_clean,
                "exercicio": str(exercicio),
                "guia": guia,
                "cotas": cotas
            },
            expect_json=False  # Espera texto/base64, não JSON
        )
        
        if pdf_base64 and not pdf_base64.startswith("<!DOCTYPE"):
            # Retorna apenas se não for uma página de erro HTML
            logger.info(f"PDF downloaded successfully for inscricao {inscricao_clean}")
            return pdf_base64
        else:
            logger.warning(f"PDF download failed or returned HTML error page")
            return None