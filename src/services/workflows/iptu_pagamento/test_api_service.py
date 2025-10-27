"""
Testes unitários para os métodos da IPTUAPIService.

Foca em testar os error handlers e diferentes cenários de resposta HTTP.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.services.workflows.iptu_pagamento.api_service import IPTUAPIService
from src.services.workflows.iptu_pagamento.exceptions import (
    APIUnavailableError,
    AuthenticationError,
)
from src.services.workflows.iptu_pagamento.models import DadosDividaAtiva

# Configura pytest-asyncio para modo auto
pytest_plugins = ('pytest_asyncio',)


class TestGetDividaAtivaInfoErrorHandling:
    """Testes de error handling para get_divida_ativa_info."""

    @pytest.fixture
    def api_service(self):
        """Fixture que cria uma instância do IPTUAPIService."""
        return IPTUAPIService()

    @pytest.mark.asyncio
    async def test_divida_ativa_timeout_autenticacao(self, api_service):
        """Testa que timeout na autenticação levanta APIUnavailableError."""
        print("\n🧪 Teste: Timeout na autenticação da dívida ativa")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula timeout na autenticação
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "não respondeu no tempo esperado" in str(exc_info.value)
            print("✅ Timeout na autenticação tratado corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_401_autenticacao(self, api_service):
        """Testa que 401 na autenticação levanta AuthenticationError."""
        print("\n🧪 Teste: Erro 401 na autenticação da dívida ativa")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 401 na autenticação
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_client.post = AsyncMock(return_value=mock_response)

            with pytest.raises(AuthenticationError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "autenticação" in str(exc_info.value).lower()
            print("✅ Erro 401 na autenticação tratado corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_500_autenticacao(self, api_service):
        """Testa que 500 na autenticação levanta APIUnavailableError."""
        print("\n🧪 Teste: Erro 500 na autenticação da dívida ativa")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 500 na autenticação
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client.post = AsyncMock(return_value=mock_response)

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "temporariamente indisponível" in str(exc_info.value)
            assert "500" in str(exc_info.value)
            print("✅ Erro 500 na autenticação tratado corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_503_autenticacao(self, api_service):
        """Testa que 503 na autenticação levanta APIUnavailableError."""
        print("\n🧪 Teste: Erro 503 na autenticação da dívida ativa")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 503 na autenticação
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.text = "Service Unavailable"
            mock_client.post = AsyncMock(return_value=mock_response)

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "temporariamente indisponível" in str(exc_info.value)
            assert "503" in str(exc_info.value)
            print("✅ Erro 503 na autenticação tratado corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_missing_token(self, api_service):
        """Testa que falta de token na resposta levanta AuthenticationError."""
        print("\n🧪 Teste: Token ausente na resposta de autenticação")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 200 mas sem access_token
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"error": "invalid_grant"}
            mock_client.post = AsyncMock(return_value=mock_response)

            with pytest.raises(AuthenticationError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "token" in str(exc_info.value).lower()
            print("✅ Falta de token tratada corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_timeout_consulta(self, api_service):
        """Testa que timeout na consulta de dívidas levanta APIUnavailableError."""
        print("\n🧪 Teste: Timeout na consulta de dívidas")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Primeira chamada (autenticação) retorna token
            mock_auth_response = MagicMock()
            mock_auth_response.status_code = 200
            mock_auth_response.json.return_value = {"access_token": "fake_token"}

            # Configura post para retornar auth response primeiro, depois timeout
            call_count = 0
            def post_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # Primeira chamada: autenticação bem-sucedida
                    return mock_auth_response
                else:
                    # Segunda chamada: timeout na consulta
                    raise httpx.TimeoutException("Timeout")

            mock_client.post = AsyncMock(side_effect=post_side_effect)

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "não respondeu no tempo esperado" in str(exc_info.value)
            print("✅ Timeout na consulta tratado corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_404_retorna_none(self, api_service):
        """Testa que 404 na consulta retorna None (sem débitos)."""
        print("\n🧪 Teste: 404 retorna None (sem débitos)")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Primeira chamada: autenticação bem-sucedida
            mock_auth_response = MagicMock()
            mock_auth_response.status_code = 200
            mock_auth_response.json.return_value = {"access_token": "fake_token"}

            # Segunda chamada: 404 na consulta
            mock_consulta_response = MagicMock()
            mock_consulta_response.status_code = 404
            mock_consulta_response.text = "Not Found"

            mock_client.post = AsyncMock(side_effect=[mock_auth_response, mock_consulta_response])

            result = await api_service.get_divida_ativa_info("12345678")

            assert result is None
            print("✅ 404 retorna None corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_401_consulta(self, api_service):
        """Testa que 401 na consulta de dívidas levanta AuthenticationError."""
        print("\n🧪 Teste: Erro 401 na consulta de dívidas")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Primeira chamada: autenticação bem-sucedida
            mock_auth_response = MagicMock()
            mock_auth_response.status_code = 200
            mock_auth_response.json.return_value = {"access_token": "fake_token"}

            # Segunda chamada: 401 na consulta
            mock_consulta_response = MagicMock()
            mock_consulta_response.status_code = 401
            mock_consulta_response.text = "Unauthorized"

            mock_client.post = AsyncMock(side_effect=[mock_auth_response, mock_consulta_response])

            with pytest.raises(AuthenticationError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "autenticação" in str(exc_info.value).lower()
            print("✅ Erro 401 na consulta tratado corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_500_consulta(self, api_service):
        """Testa que 500 na consulta levanta APIUnavailableError."""
        print("\n🧪 Teste: Erro 500 na consulta de dívidas")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Primeira chamada: autenticação bem-sucedida
            mock_auth_response = MagicMock()
            mock_auth_response.status_code = 200
            mock_auth_response.json.return_value = {"access_token": "fake_token"}

            # Segunda chamada: 500 na consulta
            mock_consulta_response = MagicMock()
            mock_consulta_response.status_code = 500
            mock_consulta_response.text = "Internal Server Error"

            mock_client.post = AsyncMock(side_effect=[mock_auth_response, mock_consulta_response])

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "temporariamente indisponível" in str(exc_info.value)
            assert "500" in str(exc_info.value)
            print("✅ Erro 500 na consulta tratado corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_503_consulta(self, api_service):
        """Testa que 503 na consulta levanta APIUnavailableError."""
        print("\n🧪 Teste: Erro 503 na consulta de dívidas")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Primeira chamada: autenticação bem-sucedida
            mock_auth_response = MagicMock()
            mock_auth_response.status_code = 200
            mock_auth_response.json.return_value = {"access_token": "fake_token"}

            # Segunda chamada: 503 na consulta
            mock_consulta_response = MagicMock()
            mock_consulta_response.status_code = 503
            mock_consulta_response.text = "Service Unavailable"

            mock_client.post = AsyncMock(side_effect=[mock_auth_response, mock_consulta_response])

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_divida_ativa_info("12345678")

            assert "temporariamente indisponível" in str(exc_info.value)
            assert "503" in str(exc_info.value)
            print("✅ Erro 503 na consulta tratado corretamente")

    @pytest.mark.asyncio
    async def test_divida_ativa_sucesso_com_dados(self, api_service):
        """Testa que consulta bem-sucedida retorna DadosDividaAtiva corretamente."""
        print("\n🧪 Teste: Consulta bem-sucedida com dados")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Primeira chamada: autenticação bem-sucedida
            mock_auth_response = MagicMock()
            mock_auth_response.status_code = 200
            mock_auth_response.json.return_value = {"access_token": "fake_token"}

            # Segunda chamada: consulta bem-sucedida
            mock_consulta_response = MagicMock()
            mock_consulta_response.status_code = 200
            mock_consulta_response.json.return_value = {
                "success": True,
                "data": {
                    "dataVencimento": "25/11/2025",
                    "saldoTotalDivida": "R$5.000,00",
                    "enderecoImovel": "Rua Teste, 123",
                    "bairroImovel": "Centro",
                    "pdf": None,
                    "urlPdf": None,
                    "debitosNaoParceladosComSaldoTotal": {
                        "cdasNaoAjuizadasNaoParceladas": [
                            {
                                "cdaId": "2024/123456",
                                "numExercicio": "2024",
                                "valorSaldoTotal": "R$5.000,00",
                            }
                        ],
                        "efsNaoParceladas": [],
                        "saldoTotalNaoParcelado": "R$5.000,00",
                    },
                    "guiasParceladasComSaldoTotal": {
                        "guiasParceladas": [],
                        "saldoTotalParcelado": "R$0,00",
                    },
                },
            }

            mock_client.post = AsyncMock(side_effect=[mock_auth_response, mock_consulta_response])

            result = await api_service.get_divida_ativa_info("12345678")

            assert result is not None
            assert isinstance(result, DadosDividaAtiva)
            assert result.tem_divida_ativa is True
            assert len(result.cdas) == 1
            assert result.cdas[0].cda_id == "2024/123456"
            print("✅ Consulta bem-sucedida processada corretamente")


class TestGetImovelInfoErrorHandling:
    """Testes de error handling para get_imovel_info."""

    @pytest.fixture
    def api_service(self):
        """Fixture que cria uma instância do IPTUAPIService."""
        return IPTUAPIService()

    @pytest.mark.asyncio
    async def test_imovel_info_timeout(self, api_service):
        """Testa que timeout levanta APIUnavailableError."""
        print("\n🧪 Teste: Timeout na consulta de dados do imóvel")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula timeout
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_imovel_info("12345678")

            assert "não respondeu no tempo esperado" in str(exc_info.value)
            print("✅ Timeout tratado corretamente")

    @pytest.mark.asyncio
    async def test_imovel_info_401(self, api_service):
        """Testa que 401 levanta AuthenticationError."""
        print("\n🧪 Teste: Erro 401 na consulta de dados do imóvel")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 401
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_client.get = AsyncMock(return_value=mock_response)

            with pytest.raises(AuthenticationError) as exc_info:
                await api_service.get_imovel_info("12345678")

            assert "autenticação" in str(exc_info.value).lower()
            print("✅ Erro 401 tratado corretamente")

    @pytest.mark.asyncio
    async def test_imovel_info_500(self, api_service):
        """Testa que 500 levanta APIUnavailableError."""
        print("\n🧪 Teste: Erro 500 na consulta de dados do imóvel")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 500
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client.get = AsyncMock(return_value=mock_response)

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_imovel_info("12345678")

            assert "temporariamente indisponível" in str(exc_info.value)
            assert "500" in str(exc_info.value)
            print("✅ Erro 500 tratado corretamente")

    @pytest.mark.asyncio
    async def test_imovel_info_503(self, api_service):
        """Testa que 503 levanta APIUnavailableError."""
        print("\n🧪 Teste: Erro 503 na consulta de dados do imóvel")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 503
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.text = "Service Unavailable"
            mock_client.get = AsyncMock(return_value=mock_response)

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_imovel_info("12345678")

            assert "temporariamente indisponível" in str(exc_info.value)
            assert "503" in str(exc_info.value)
            print("✅ Erro 503 tratado corretamente")

    @pytest.mark.asyncio
    async def test_imovel_info_404_retorna_none(self, api_service):
        """Testa que 404 retorna None (imóvel não encontrado)."""
        print("\n🧪 Teste: 404 retorna None (imóvel não encontrado)")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 404
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await api_service.get_imovel_info("12345678")

            assert result is None
            print("✅ 404 retorna None corretamente")

    @pytest.mark.asyncio
    async def test_imovel_info_sucesso(self, api_service):
        """Testa que consulta bem-sucedida retorna dados corretamente."""
        print("\n🧪 Teste: Consulta bem-sucedida de dados do imóvel")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 200 com dados
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "tipoLogradouro": "RUA",
                "nomeLogradouro": "TESTE",
                "numPorta": "123",
                "complEndereco": "APT 101",
                "bairro": "CENTRO",
                "cep": "20000-000",
                "proprietarioPrincipal": "JOÃO DA SILVA"
            }
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await api_service.get_imovel_info("12345678")

            assert result is not None
            assert "endereco" in result
            assert "proprietario" in result
            assert result["proprietario"] == "JOÃO DA SILVA"
            assert "RUA TESTE" in result["endereco"]
            print("✅ Consulta bem-sucedida processada corretamente")

    @pytest.mark.asyncio
    async def test_imovel_info_outros_erros(self, api_service):
        """Testa que outros erros HTTP levantam APIUnavailableError."""
        print("\n🧪 Teste: Outros erros HTTP (ex: 400)")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simula resposta 400
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_client.get = AsyncMock(return_value=mock_response)

            with pytest.raises(APIUnavailableError) as exc_info:
                await api_service.get_imovel_info("12345678")

            assert "400" in str(exc_info.value)
            print("✅ Outros erros HTTP tratados corretamente")
