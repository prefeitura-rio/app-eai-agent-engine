#!/usr/bin/env python3
"""
Bateria atualizada de testes para a nova interface otimizada
"""

import json
import os
import shutil
from typing import Dict, Any
from src.tools import multi_step_service


def setup_test_environment():
    """Prepara ambiente limpo para testes"""
    shutil.rmtree("service_states", ignore_errors=True)
    os.makedirs("service_states", exist_ok=True)


def print_test_header(test_name: str):
    """Imprime cabeçalho de teste formatado"""
    print(f"\n{'='*60}")
    print(f"🧪 {test_name}")
    print(f"{'='*60}")


def print_test_result(description: str, result: Dict[str, Any], success: bool = True):
    """Imprime resultado de teste formatado"""
    status_icon = "✅" if success else "❌"
    print(f"\n{status_icon} {description}")
    print(f"   Status: {result.get('status', 'N/A')}")
    if result.get("completion_message"):
        print(f"   Completion: {result['completion_message']}")
    if result.get("next_step_info"):
        next_info = result["next_step_info"]
        print(f"   Next step: {next_info.get('name')}")
    if result.get("completed") is not None:
        print(f"   Completo: {'Sim' if result['completed'] else 'Não'}")


def test_bulk_first_behavior():
    """Testa comportamento bulk-first"""
    print_test_header("COMPORTAMENTO BULK-FIRST")

    setup_test_environment()

    # 1. Start sempre solicita bulk
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "agent",
        }
    )
    print_test_result("Start solicita dados bulk", result)
    assert result["status"] == "bulk_request"
    assert "schema" in result
    assert "steps_info" in result

    # 2. Bulk completo funciona perfeitamente
    bulk_data = {"cpf": "12345678901", "email": "bulk@example.com", "name": "Bulk User"}
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "bulk",
            "payload": json.dumps(bulk_data),
            "user_id": "agent",
        }
    )
    print_test_result("Bulk completo - eficiência máxima", result)
    assert result["status"] == "bulk_success"
    assert result["completed"] == True
    assert "completion_message" in result


def test_next_step_info():
    """Testa nova estrutura next_step_info"""
    print_test_header("ESTRUTURA NEXT_STEP_INFO")

    setup_test_environment()

    # 1. Iniciar serviço
    multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "agent",
        }
    )

    # 2. Step individual retorna next_step_info completo
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "cpf",
            "payload": "98765432100",
            "user_id": "agent",
        }
    )
    print_test_result("Step com next_step_info completo", result)
    assert result["status"] == "success"
    assert "next_step_info" in result

    next_info = result["next_step_info"]
    assert "name" in next_info
    assert "example" in next_info


def test_bulk_partial_with_next_step_info():
    """Testa bulk parcial com next_step_info"""
    print_test_header("BULK PARCIAL COM NEXT_STEP_INFO")

    setup_test_environment()

    # 1. Iniciar serviço
    multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "agent",
        }
    )

    # 2. Bulk parcial
    partial_data = {
        "cpf": "11111111111",
        "email": "partial@test.com",
        # name missing
    }
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "partial",
            "payload": json.dumps(partial_data),
            "user_id": "agent",
        }
    )
    print_test_result("Bulk parcial com informações completas do próximo step", result)
    assert result["status"] == "partial_success"
    assert "next_step_info" in result
    assert "field_errors" in result
    assert "valid_fields" in result

    # Deve indicar o próximo step necessário
    next_info = result["next_step_info"]
    assert next_info.get("name") in [
        "name",
        "cpf",
    ]  # Pode ser qualquer um que esteja faltando


def test_error_handling_with_next_step_info():
    """Testa tratamento de erros com next_step_info"""
    print_test_header("TRATAMENTO DE ERROS COM NEXT_STEP_INFO")

    setup_test_environment()

    # 1. Iniciar serviço
    multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "agent",
        }
    )

    # 2. CPF inválido deve retornar next_step_info do mesmo step
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "cpf",
            "payload": "123",
            "user_id": "agent",
        }
    )
    print_test_result("Erro com next_step_info para retentar", result, success=False)
    assert result["status"] == "error"
    assert "next_step_info" in result
    assert "schema" in result

    # Deve retornar info do mesmo step para retry
    next_info = result["next_step_info"]
    assert next_info.get("name") == "cpf"


def test_schema_in_start():
    """Testa schema incluído no start"""
    print_test_header("SCHEMA NO START")

    setup_test_environment()

    # Start sempre inclui schema
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "agent",
        }
    )
    print_test_result("Schema incluído no start", result)
    assert result["status"] == "bulk_request"
    assert "schema" in result

    schema = result["schema"]
    assert "properties" in schema
    assert "cpf" in schema["properties"]
    assert "email" in schema["properties"]
    assert "name" in schema["properties"]


def test_hybrid_completion():
    """Testa conclusão híbrida bulk + step"""
    print_test_header("CONCLUSÃO HÍBRIDA")

    setup_test_environment()

    # 1. Iniciar
    multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "agent",
        }
    )

    # 2. Bulk parcial
    partial_data = {"cpf": "12345678901", "email": "hybrid@test.com"}  # CPF válido
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "hybrid",
            "payload": json.dumps(partial_data),
            "user_id": "agent",
        }
    )

    # 3. Completar via step
    if "next_step_info" in result:
        next_info = result["next_step_info"]
        missing_step = next_info["name"]

        if missing_step == "name":
            payload = "Híbrido Silva"
        else:
            payload = "33333333333"

        result = multi_step_service.invoke(
            {
                "service_name": "data_collection",
                "step": missing_step,
                "payload": payload,
                "user_id": "agent",
            }
        )

        # Continue até completar
        while not result.get("completed") and "next_step_info" in result:
            next_info = result["next_step_info"]
            step_name = next_info["name"]

            if step_name == "name":
                payload = "Híbrido Silva"
            elif step_name == "email":
                payload = "final@test.com"
            else:
                payload = "44444444444"

            result = multi_step_service.invoke(
                {
                    "service_name": "data_collection",
                    "step": step_name,
                    "payload": payload,
                    "user_id": "agent",
                }
            )

    print_test_result("Híbrido completado", result)
    assert result["status"] == "completed"
    assert result["completed"] == True


def test_user_id_system():
    """Testa sistema baseado puramente em user_id"""
    print_test_header("SISTEMA BASEADO EM USER_ID")

    setup_test_environment()

    # 1. User A inicia
    result_a = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "user_a",
        }
    )
    print_test_result("User A - inicio sem session_id", result_a)
    assert result_a["status"] == "bulk_request"
    assert "session_id" not in result_a

    # 2. User B inicia separadamente
    result_b = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "user_b",
        }
    )
    print_test_result("User B - sessão independente", result_b)
    assert result_b["status"] == "bulk_request"

    # 3. User B faz bulk
    bulk_data = {"cpf": "12345678901", "email": "userb@test.com", "name": "User B"}
    result_b2 = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "bulk",
            "payload": json.dumps(bulk_data),
            "user_id": "user_b",
        }
    )
    print_test_result("User B - bulk completo", result_b2)
    assert result_b2["status"] == "bulk_success"

    # 4. Verificar arquivos baseados em user_id
    files = os.listdir("service_states")
    expected = ["user_a__data_collection.json", "user_b__data_collection.json"]
    for exp in expected:
        assert exp in files, f"Arquivo {exp} não encontrado"

    print(f"✅ Arquivos de estado baseados em user_id: {len(expected)} encontrados")


def test_final_optimizations():
    """Teste das otimizações finais do sistema"""
    print_test_header("OTIMIZAÇÕES FINAIS")

    setup_test_environment()

    # 1. Interface limpa sem session_id
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "start",
            "payload": "",
            "user_id": "final_test",
        }
    )

    optimizations = {
        "Session_id removido": "session_id" not in result,
        "Comportamento bulk-first": result["status"] == "bulk_request",
        "Schema incluído": "schema" in result,
        "Steps info incluído": "steps_info" in result,
    }

    for opt_name, opt_status in optimizations.items():
        status_icon = "✅" if opt_status else "❌"
        print(f"   {status_icon} {opt_name}")
        assert opt_status, f"Otimização falhou: {opt_name}"

    # 2. Bulk eficiente
    bulk_data = {"cpf": "98765432100", "email": "final@test.com", "name": "Final Test"}
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "bulk",
            "payload": json.dumps(bulk_data),
            "user_id": "final_test",
        }
    )

    print_test_result("Sistema otimizado - bulk eficiente", result)
    assert result["status"] == "bulk_success"
    assert result["completed"] == True
    assert "completion_message" in result


def run_complete_tests():
    """Executa bateria completa de testes centralizados"""
    print("🚀 BATERIA COMPLETA DE TESTES CENTRALIZADOS")
    print("Sistema Multi-Step Otimizado - Interface Final\n")

    tests = [
        test_bulk_first_behavior,
        test_next_step_info,
        test_bulk_partial_with_next_step_info,
        test_error_handling_with_next_step_info,
        test_schema_in_start,
        test_hybrid_completion,
        test_user_id_system,
        test_final_optimizations,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ FALHA: {test_func.__name__} - {e}")
            failed += 1
        except Exception as e:
            print(f"💥 ERRO: {test_func.__name__} - {e}")
            failed += 1

    # Resumo final
    print(f"\n{'='*60}")
    print(f"📊 RESUMO FINAL DOS TESTES")
    print(f"{'='*60}")
    print(f"✅ Testes Aprovados: {passed}")
    print(f"❌ Testes Falharam: {failed}")
    print(f"📈 Taxa de Sucesso: {(passed/(passed+failed)*100):.1f}%")

    if failed == 0:
        print(f"\n🎉 SISTEMA COMPLETAMENTE OTIMIZADO!")
        print(f"- ❌ Session_id removido")
        print(f"- ✅ User_id como identificador")
        print(f"- ✅ Next_step_info implementado")
        print(f"- ✅ Comportamento bulk-first")
        print(f"- ✅ Detecção automática")
        print(f"- ✅ Interface natural")
    else:
        print(f"\n⚠️  {failed} teste(s) falharam.")


if __name__ == "__main__":
    run_complete_tests()
