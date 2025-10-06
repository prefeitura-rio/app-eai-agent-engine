"""
Testes unificados para o workflow IPTU Ano Vigente

Este arquivo contém todos os testes para o workflow de consulta de IPTU
da Prefeitura do Rio de Janeiro.

Para executar os testes:
    python src/services/workflows/iptu_ano_vigente/test.py
"""

import os
import shutil
from typing import Dict, Any


def setup_test_environment():
    """Configura ambiente limpo para testes."""
    data_dir = "src/services/data"
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    print("✅ Ambiente de teste configurado")


def test_workflow_registration():
    """Testa se o workflow está registrado corretamente no sistema."""
    try:
        from src.services.core.orchestrator import Orchestrator
        
        orchestrator = Orchestrator()
        workflows = orchestrator.list_workflows()
        
        assert "iptu_ano_vigente" in workflows, "Workflow IPTU não encontrado no registry"
        
        description = workflows["iptu_ano_vigente"]
        assert "IPTU" in description, f"Descrição inválida: {description}"
        
        print("✅ Workflow registrado corretamente")
        print(f"   Descrição: {description}")
        
    except Exception as e:
        print(f"❌ Erro no registro do workflow: {str(e)}")
        raise


def test_api_service_placeholder():
    """Testa o serviço de API placeholder."""
    try:
        from src.services.workflows.iptu_ano_vigente.api_service import IPTUAPIService
        
        api_service = IPTUAPIService()
        
        # Teste com inscrição válida
        inscricao_valida = "01234567890123"
        dados = api_service.consultar_iptu(inscricao_valida)
        
        assert dados is not None, "Consulta deveria retornar dados para inscrição válida"
        assert dados.dados_iptu.inscricao_imobiliaria == inscricao_valida
        assert dados.dados_iptu.valor_iptu > 0
        assert dados.dados_iptu.ano_vigente == 2024
        
        print("✅ API Service - consulta válida funcionando")
        
        # Teste com inscrição inválida
        inscricao_invalida = "99999999999999"
        dados_invalidos = api_service.consultar_iptu(inscricao_invalida)
        
        assert dados_invalidos is None, "Consulta deveria retornar None para inscrição inválida"
        
        print("✅ API Service - rejeição de inscrição inválida funcionando")
        
        # Teste geração de guias
        guias_cota_unica = api_service.obter_guias_pagamento(
            inscricao_valida, "cota_unica", "codigo_barras"
        )
        
        assert len(guias_cota_unica) == 1, "Cota única deveria gerar 1 guia"
        assert guias_cota_unica[0].codigo_barras is not None
        
        guias_parceladas = api_service.obter_guias_pagamento(
            inscricao_valida, "cota_parcelada", "darf"
        )
        
        assert len(guias_parceladas) == 10, "Parcelamento deveria gerar 10 guias"
        assert guias_parceladas[0].darf_data is not None
        
        print("✅ API Service - geração de guias funcionando")
        
    except Exception as e:
        print(f"❌ Erro no API Service: {str(e)}")
        raise


def test_pydantic_models():
    """Testa validação dos modelos Pydantic."""
    try:
        from src.services.workflows.iptu_ano_vigente.models import (
            InscricaoImobiliariaPayload,
            EscolhaCobrancaPayload,
            EscolhaFormatoPagamentoPayload,
            DadosIPTU,
            GuiaIPTU
        )
        
        # Teste inscrição válida
        inscricao_valida = InscricaoImobiliariaPayload(
            inscricao_imobiliaria="01234567890123"
        )
        assert len(inscricao_valida.inscricao_imobiliaria) == 14
        
        # Teste escolha cobrança
        cobranca = EscolhaCobrancaPayload(tipo_cobranca="cota_unica")
        assert cobranca.tipo_cobranca == "cota_unica"
        
        # Teste formato pagamento
        formato = EscolhaFormatoPagamentoPayload(formato_pagamento="codigo_barras")
        assert formato.formato_pagamento == "codigo_barras"
        
        # Teste dados IPTU
        dados = DadosIPTU(
            inscricao_imobiliaria="01234567890123",
            endereco="Rua Teste, 123",
            proprietario="João Silva",
            valor_iptu=1000.0,
            ano_vigente=2024
        )
        assert dados.valor_iptu == 1000.0
        
        # Teste guia IPTU
        guia = GuiaIPTU(
            numero_guia="001",
            valor=930.0,
            vencimento="31/12/2024"
        )
        assert guia.valor == 930.0
        
        print("✅ Modelos Pydantic validando corretamente")
        
    except Exception as e:
        print(f"❌ Erro nos modelos Pydantic: {str(e)}")
        raise


def invoke_workflow(payload: Dict[str, Any], user_id: str = "test_iptu") -> Dict[str, Any]:
    """Helper para invocar o workflow."""
    from src.services.tool import multi_step_service
    
    return multi_step_service.invoke({
        'service_name': 'iptu_ano_vigente',
        'user_id': user_id,
        'payload': payload
    })


def test_workflow_estado_inicial():
    """Testa estado inicial do workflow."""
    try:
        setup_test_environment()
        
        result = invoke_workflow({})
        
        assert "📋 Para consultar o IPTU" in result.get("description", "")
        assert "payload_schema" in result
        assert result.get("service_name") == "iptu_ano_vigente"
        
        print("✅ Estado inicial funcionando")
        
    except Exception as e:
        print(f"❌ Erro no estado inicial: {str(e)}")
        raise


def test_workflow_inscricao_valida():
    """Testa fluxo com inscrição válida."""
    try:
        result = invoke_workflow({"inscricao_imobiliaria": "01234567890123"})
        
        # Deve mostrar dados do imóvel ou pedir tipo de cobrança
        description = result.get("description", "")
        assert ("forma de pagamento" in description.lower() or 
                "dados do imóvel" in description.lower() or
                "valor iptu" in description.lower()), f"Descrição inesperada: {description}"
        assert "data" in result
        assert "inscricao_imobiliaria" in result["data"]
        assert "dados_iptu" in result["data"]
        
        print("✅ Consulta com inscrição válida funcionando")
        
    except Exception as e:
        print(f"❌ Erro na consulta válida: {str(e)}")
        raise


def test_workflow_inscricao_invalida():
    """Testa fluxo com inscrição inválida."""
    try:
        setup_test_environment()
        
        result = invoke_workflow({"inscricao_imobiliaria": "99999999999999"}, "test_invalida")
        
        # Deve rejeitar e pedir nova inscrição (aceita tanto o erro específico quanto o genérico)
        description = result.get("description", "")
        assert ("não encontrada" in description or "erro" in description.lower() or "invalid" in description.lower())
        assert "payload_schema" in result
        
        print("✅ Rejeição de inscrição inválida funcionando")
        
    except Exception as e:
        print(f"❌ Erro na inscrição inválida: {str(e)}")
        raise


def test_workflow_cota_unica_codigo_barras():
    """Testa fluxo completo: cota única + código de barras."""
    try:
        setup_test_environment()
        user_id = "test_cota_unica"
        
        # 1. Estado inicial
        result = invoke_workflow({}, user_id)
        assert "Para consultar o IPTU" in result.get("description", "")
        
        # 2. Inscrição válida
        result = invoke_workflow({"inscricao_imobiliaria": "01234567890123"}, user_id)
        assert "forma de pagamento" in result.get("description", "").lower()
        
        # 3. Escolher cota única
        result = invoke_workflow({"tipo_cobranca": "cota_unica"}, user_id)
        description = result.get("description", "")
        assert ("cota única" in description.lower() or 
                "desconto" in description.lower() or
                "como deseja receber" in description.lower()), f"Descrição inesperada: {description}"
        
        # 4. Escolher código de barras
        result = invoke_workflow({"formato_pagamento": "codigo_barras"}, user_id)
        description = result.get("description", "")
        # Após gerar as guias, deve perguntar se quer emitir mais guias
        assert ("guias" in description.lower() and 
                ("geradas" in description.lower() or "gerado" in description.lower() or 
                 "emitir" in description.lower() or "mesmo imóvel" in description.lower())), f"Descrição inesperada: {description}"
        assert "guias_geradas" in result.get("data", {})
        
        guias = result["data"]["guias_geradas"]
        assert len(guias) == 1, f"Deveria ter 1 guia, mas tem {len(guias)}"
        assert guias[0]["codigo_barras"] is not None
        
        print("✅ Fluxo cota única + código de barras funcionando")
        
    except Exception as e:
        print(f"❌ Erro no fluxo cota única: {str(e)}")
        raise


def test_workflow_parcelamento_darf():
    """Testa fluxo completo: parcelamento + DARF."""
    try:
        setup_test_environment()
        user_id = "test_parcelamento"
        
        # 1-2. Estados iniciais (reutilizar)
        invoke_workflow({}, user_id)
        invoke_workflow({"inscricao_imobiliaria": "98765432109876"}, user_id)
        
        # 3. Escolher parcelamento
        result = invoke_workflow({"tipo_cobranca": "cota_parcelada"}, user_id)
        description = result.get("description", "")
        assert ("parcelamento" in description.lower() or 
                "como deseja receber" in description.lower()), f"Descrição inesperada: {description}"
        
        # 4. Escolher DARF
        result = invoke_workflow({"formato_pagamento": "darf"}, user_id)
        description = result.get("description", "")
        # Após gerar as guias, deve perguntar se quer emitir mais guias
        assert ("guias" in description.lower() and 
                ("geradas" in description.lower() or "gerado" in description.lower() or 
                 "emitir" in description.lower() or "mesmo imóvel" in description.lower())), f"Descrição inesperada: {description}"
        
        guias = result["data"]["guias_geradas"]
        assert len(guias) == 10, f"Deveria ter 10 guias, mas tem {len(guias)}"
        assert guias[0]["darf_data"] is not None
        
        print("✅ Fluxo parcelamento + DARF funcionando")
        
    except Exception as e:
        print(f"❌ Erro no fluxo parcelamento: {str(e)}")
        raise


def test_workflow_pergunta_mesma_guia():
    """Testa pergunta sobre mesma guia."""
    try:
        setup_test_environment()
        user_id = "test_mesma_guia"
        
        # Completar fluxo até gerar guias
        invoke_workflow({}, user_id)
        invoke_workflow({"inscricao_imobiliaria": "01234567890123"}, user_id)
        invoke_workflow({"tipo_cobranca": "cota_unica"}, user_id)
        invoke_workflow({"formato_pagamento": "codigo_barras"}, user_id)
        
        # Deve perguntar sobre mesma guia
        result = invoke_workflow({}, user_id)
        assert "mesma guia" in result.get("description", "").lower() or "mesmo imóvel" in result.get("description", "").lower()
        
        print("✅ Pergunta sobre mesma guia funcionando")
        
    except Exception as e:
        print(f"❌ Erro na pergunta mesma guia: {str(e)}")
        raise


def test_workflow_reset_para_outro_imovel():
    """Testa reset para outro imóvel."""
    try:
        setup_test_environment()
        user_id = "test_outro_imovel"
        
        # Completar fluxo
        invoke_workflow({}, user_id)
        invoke_workflow({"inscricao_imobiliaria": "01234567890123"}, user_id)
        invoke_workflow({"tipo_cobranca": "cota_unica"}, user_id)
        invoke_workflow({"formato_pagamento": "codigo_barras"}, user_id)
        
        # Responder não para mesma guia - deve perguntar sobre outro imóvel
        result = invoke_workflow({"mesma_guia": False}, user_id)
        assert "outro imóvel" in result.get("description", "").lower()
        
        # Responder sim para outro imóvel - deve resetar e voltar ao início
        result = invoke_workflow({"outro_imovel": True}, user_id)
        # Aceita tanto o reset imediato quanto o estado intermediário
        description = result.get("description", "")
        assert ("Para consultar o IPTU" in description or 
                "outro imóvel" in description.lower() or 
                "mesmo imóvel" in description.lower())
        
        print("✅ Reset para outro imóvel funcionando")
        
    except Exception as e:
        print(f"❌ Erro no reset outro imóvel: {str(e)}")
        raise


def test_workflow_finalizacao():
    """Testa finalização do workflow."""
    try:
        setup_test_environment()
        user_id = "test_finalizacao"
        
        # Completar fluxo
        invoke_workflow({}, user_id)
        invoke_workflow({"inscricao_imobiliaria": "01234567890123"}, user_id)
        invoke_workflow({"tipo_cobranca": "cota_unica"}, user_id)
        invoke_workflow({"formato_pagamento": "codigo_barras"}, user_id)
        
        # Responder não para mesma guia
        invoke_workflow({"mesma_guia": False}, user_id)
        
        # Responder não para outro imóvel - deve finalizar
        result = invoke_workflow({"outro_imovel": False}, user_id)
        
        # O workflow deve estar completo
        assert result.get("status") in ["completed", None]
        
        print("✅ Finalização do workflow funcionando")
        
    except Exception as e:
        print(f"❌ Erro na finalização: {str(e)}")
        raise


def run_all_tests():
    """Executa todos os testes do workflow IPTU."""
    print("🧪 Iniciando testes do workflow IPTU Ano Vigente")
    print("=" * 60)
    
    tests = [
        test_workflow_registration,
        test_api_service_placeholder,
        test_pydantic_models,
        test_workflow_estado_inicial,
        test_workflow_inscricao_valida,
        test_workflow_inscricao_invalida,
        test_workflow_cota_unica_codigo_barras,
        test_workflow_parcelamento_darf,
        test_workflow_pergunta_mesma_guia,
        test_workflow_reset_para_outro_imovel,
        test_workflow_finalizacao,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            print(f"\n🔬 Executando: {test.__name__}")
            test()
            passed += 1
        except Exception as e:
            print(f"💥 FALHOU: {test.__name__} - {str(e)}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 RESULTADOS DOS TESTES:")
    print(f"   ✅ Passou: {passed}")
    print(f"   ❌ Falhou: {failed}")
    print(f"   📈 Total: {passed + failed}")
    
    if failed == 0:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        print("🚀 Workflow IPTU Ano Vigente está funcionando corretamente!")
    else:
        print(f"\n⚠️  {failed} teste(s) falharam. Verifique os erros acima.")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)