"""
Serviço de API para consulta de IPTU - Integração Real

Este módulo implementa a integração com a API real da Prefeitura do Rio
para consulta de IPTU e geração de guias de pagamento.
"""

import re
from typing import List, Optional, Dict, Any
import httpx

from src.config import env
from src.services.workflows.iptu_pagamento.models import (
    DadosGuias,
    Guia,
    Cota,
    DadosCotas,
    Darm,
    DadosDarm,
)
from loguru import logger


class IPTUAPIService:
    """
    Serviço de API para consulta de IPTU da Prefeitura do Rio.

    Integra com a API real para:
    - Consultar guias disponíveis (ConsultarGuias)
    - Consultar cotas/parcelas (ConsultarCotas)
    - Gerar DARM para pagamento (ConsultarDARM)
    - Download PDF do DARM (DownloadPdfDARM)
    """

    def __init__(self):
        """Inicializa o serviço com configurações da API."""
        self.api_base_url = env.IPTU_API_URL
        self.api_token = env.IPTU_API_TOKEN
        self.proxy = "http://proxy.squirrel-regulus.ts.net:3128"

        logger.info(f"IPTUAPIService initialized with API URL: {self.api_base_url}")

    @staticmethod
    def _limpar_inscricao(inscricao: str) -> str:
        """
        Remove caracteres não numéricos da inscrição imobiliária.

        Args:
            inscricao: Inscrição imobiliária

        Returns:
            Inscrição apenas com números
        """
        return re.sub(r"[^0-9]", "", inscricao)

    async def _make_api_request(
        self, endpoint: str, params: Dict[str, Any], expect_json: bool = True
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
                        logger.info(
                            f"API response successful for {endpoint} (binary/text)"
                        )
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
                    logger.error(
                        f"API error {response.status_code} for {endpoint}: {response.text}"
                    )
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

    async def consultar_guias(
        self, inscricao_imobiliaria: str, exercicio: int
    ) -> Optional[DadosGuias]:
        """
        Consulta dados e guias disponíveis do IPTU por inscrição imobiliária.

        Args:
            inscricao_imobiliaria: Número da inscrição imobiliária
            exercicio: Ano do exercício fiscal (ex: 2025)

        Returns:
            DadosGuias com informações do IPTU e guias disponíveis ou None se não encontrado
        """
        # Limpa inscrição removendo caracteres não numéricos
        inscricao_clean = self._limpar_inscricao(inscricao_imobiliaria)

        # Consulta guias disponíveis
        guias_response = await self._make_api_request(
            endpoint="ConsultarGuias",
            params={"inscricao": inscricao_clean, "exercicio": str(exercicio)},
        )
        logger.debug(f"Guias response: {guias_response}")
        if not guias_response:
            logger.info(
                f"No guides found for inscricao {inscricao_clean}, exercicio {exercicio}"
            )
            return None

        if not isinstance(guias_response, list) or len(guias_response) == 0:
            logger.info(f"Empty guide list for inscricao {inscricao_clean}")
            return None

        # Converte response para objetos Guia usando Pydantic
        guias = []
        for guia_data in guias_response:
            try:
                guia = Guia(**guia_data)

                # Processa campos calculados
                guia.valor_numerico = self._parse_brazilian_currency(
                    guia.valor_iptu_original_guia
                )
                guia.valor_desconto_numerico = self._parse_brazilian_currency(
                    guia.valor_iptu_desconto_avista
                )
                guia.valor_parcelas_numerico = self._parse_brazilian_currency(
                    guia.valor_parcelas
                )
                guia.esta_quitada = guia.situacao.get("codigo") == "02"
                guia.esta_em_aberto = guia.situacao.get("codigo") == "01"

                guias.append(guia)
            except Exception as e:
                logger.warning(f"Failed to parse guia data: {guia_data}, error: {e}")
                continue

        # Filtra apenas as guias em aberto para retorno
        guias_em_aberto = [g for g in guias if g.esta_em_aberto]

        if not guias_em_aberto:
            logger.info(f"No open guides found for inscricao {inscricao_clean}")
            return None

        # Cria objeto de dados das guias usando a estrutura simplificada
        dados_guias = DadosGuias(
            inscricao_imobiliaria=inscricao_clean,
            exercicio=str(exercicio),
            guias=guias_em_aberto,
            total_guias=len(guias_em_aberto),
        )

        logger.info(
            f"IPTU data retrieved for inscricao with {len(guias)} guides available"
        )
        return dados_guias

    async def obter_cotas(
        self,
        inscricao_imobiliaria: str,
        exercicio: int,
        numero_guia: str,
        tipo_guia: Optional[str] = None,
    ) -> Optional[DadosCotas]:
        """
        Consulta cotas disponíveis para uma guia específica.

        Args:
            inscricao_imobiliaria: Número da inscrição imobiliária
            exercicio: Ano do exercício fiscal
            numero_guia: Número da guia (ex: "00")
            tipo_guia: Tipo da guia (opcional, para evitar consulta redundante)
                      No workflow, pode ser obtido dos dados das guias já carregadas:
                      guia_selecionada = next((g for g in state.data["dados_guias"].guias if g.numero_guia == numero_guia), None)
                      tipo_guia = guia_selecionada.tipo if guia_selecionada else None

        Returns:
            DadosCotas com informações das cotas disponíveis ou None se não encontrado
        """
        # Limpa inscrição removendo caracteres não numéricos
        inscricao_clean = self._limpar_inscricao(inscricao_imobiliaria)

        # Consulta cotas disponíveis para esta guia
        cotas_response = await self._make_api_request(
            endpoint="ConsultarCotas",
            params={
                "inscricao": inscricao_clean,
                "exercicio": str(exercicio),
                "guia": numero_guia,
            },
        )
        logger.debug(f"Cotas response: {cotas_response}")

        if not cotas_response or "Cotas" not in cotas_response:
            logger.warning(f"No cotas found for guia {numero_guia}")
            return None

        # Converte response para objetos Cota usando Pydantic
        cotas = []
        for cota_data in cotas_response["Cotas"]:
            try:
                cota = Cota(**cota_data)

                # Processa campos calculados
                cota.valor_numerico = self._parse_brazilian_currency(cota.valor_cota)
                cota.valor_pago_numerico = self._parse_brazilian_currency(
                    cota.valor_pago
                )
                cota.dias_atraso_numerico = (
                    int(cota.quantidade_dias_atraso)
                    if cota.quantidade_dias_atraso.isdigit()
                    else 0
                )
                cota.esta_paga = cota.situacao.get("codigo") == "01"
                cota.esta_vencida = cota.situacao.get("codigo") == "03"

                cotas.append(cota)
            except Exception as e:
                logger.warning(f"Failed to parse cota data: {cota_data}, error: {e}")
                continue

        # Calcula valor total
        valor_total = sum(c.valor_numerico for c in cotas)

        # Usa tipo da guia fornecido ou valor padrão se não informado
        if not tipo_guia:
            tipo_guia = "ORDINÁRIA"

        # Cria objeto de dados das cotas
        dados_cotas = DadosCotas(
            inscricao_imobiliaria=inscricao_clean,
            exercicio=str(exercicio),
            numero_guia=numero_guia,
            tipo_guia=tipo_guia,
            cotas=cotas,
            total_cotas=len(cotas),
            valor_total=valor_total,
        )

        logger.info(
            f"Cotas data retrieved for guia {numero_guia} with {len(cotas)} cotas"
        )
        return dados_cotas

    async def consultar_darm(
        self,
        inscricao_imobiliaria: str,
        exercicio: int,
        numero_guia: str,
        cotas_selecionadas: List[str],
    ) -> Optional[DadosDarm]:
        """
        Consulta DARM para cotas específicas de uma guia.

        Args:
            inscricao_imobiliaria: Inscrição imobiliária
            exercicio: Ano do exercício
            numero_guia: Número da guia
            cotas_selecionadas: Lista das cotas selecionadas (ex: ["01", "02"])

        Returns:
            DadosDarm com dados do DARM ou None se não encontrar
        """
        # Limpa inscrição removendo caracteres não numéricos
        inscricao_clean = self._limpar_inscricao(inscricao_imobiliaria)

        # Converte lista de cotas para string separada por vírgula
        cotas_str = ",".join(cotas_selecionadas)

        # Faz requisição para ConsultarDARM
        darm_response = await self._make_api_request(
            endpoint="ConsultarDARM",
            params={
                "inscricao": inscricao_clean,
                "exercicio": str(exercicio),
                "guia": numero_guia,
                "cotas": cotas_str,
            },
        )

        if not darm_response:
            logger.warning(f"No DARM found for guia {numero_guia} cotas {cotas_str}")
            return None

        try:
            # Cria objeto Darm usando Pydantic
            darm = Darm(**darm_response)

            # Processa valores numéricos
            darm.valor_numerico = self._parse_brazilian_currency(darm.valor_a_pagar)

            # Gera código de barras a partir da sequencia_numerica (linha digitável)
            if darm.sequencia_numerica:
                # Remove pontos e espaços para criar código de barras
                darm.codigo_barras = darm.sequencia_numerica.replace(".", "").replace(
                    " ", ""
                )

            # Cria DadosDarm
            dados_darm = DadosDarm(
                inscricao_imobiliaria=inscricao_clean,
                exercicio=str(exercicio),
                numero_guia=numero_guia,
                cotas_selecionadas=cotas_selecionadas,
                darm=darm,
            )

            logger.info(f"DARM data retrieved for guia {numero_guia} cotas {cotas_str}")
            return dados_darm

        except Exception as e:
            logger.error(
                f"Error processing DARM data: {str(e)} - Data: {darm_response}"
            )
            return None

    async def download_pdf_darm(
        self,
        inscricao_imobiliaria: str,
        exercicio: int,
        numero_guia: str,
        cotas_selecionadas: List[str],
    ) -> Optional[str]:
        """
        Faz download do PDF da DARM em formato base64.

        Args:
            inscricao_imobiliaria: Inscrição imobiliária
            exercicio: Ano do exercício
            numero_guia: Número da guia
            cotas_selecionadas: Lista das cotas selecionadas (ex: ["01", "02"])

        Returns:
            String base64 do PDF ou None se falhar
        """
        # Limpa inscrição removendo caracteres não numéricos
        inscricao_clean = self._limpar_inscricao(inscricao_imobiliaria)

        # Converte lista de cotas para string separada por vírgula
        cotas_str = ",".join(cotas_selecionadas)

        # Faz requisição esperando resposta de texto (base64)
        pdf_base64 = await self._make_api_request(
            endpoint="DownloadPdfDARM",
            params={
                "inscricao": inscricao_clean,
                "exercicio": str(exercicio),
                "guia": numero_guia,
                "cotas": cotas_str,
            },
            expect_json=False,  # Espera texto/base64, não JSON
        )

        if pdf_base64 and not pdf_base64.startswith("<!DOCTYPE"):
            # Retorna apenas se não for uma página de erro HTML
            logger.info(f"PDF downloaded successfully for inscricao {inscricao_clean}")
            return pdf_base64
        else:
            logger.warning(f"PDF download failed or returned HTML error page")
            return None
