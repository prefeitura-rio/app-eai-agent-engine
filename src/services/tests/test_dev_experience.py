#!/usr/bin/env python3
"""
Teste para comparar a experiência de desenvolvimento entre as duas versões.
"""

import sys
import os
import json
from src.services.tool import multi_step_service
from src.services.repository.bank_account_service_v2 import BankAccountServiceV2

def clean_state(user_id):
    """Remove arquivo de estado do teste se existir."""
    state_file = f"src/services/data/{user_id}.json"
    if os.path.exists(state_file):
        os.remove(state_file)

def test_action_driven_flow():
    """Testa o novo fluxo action-driven (V2)."""
    print("🚀 TESTE: Nova Experiência Action-Driven (V2)")
    print("=" * 60)
    
    # Register the new service temporarily in the tool registry
    from src.services.tool import _services
    _services["bank_account_opening_v2"] = BankAccountServiceV2
    
    user_id = 'test_v2_new_user'
    service_name = 'bank_account_opening_v2'
    clean_state(user_id)
    
    print("📝 1. Coletando informações do usuário...")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {
            'user_info.name': 'João Silva', 
            'user_info.email': 'joao@example.com'
        }
    })
    print(f"   Status: {result['status']} -> Próximo: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    print("\n📝 2. Escolhendo tipo de conta...")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {'account_type': 'savings'}
    })
    print(f"   Status: {result['status']} -> Próximo: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    print("\n📝 3. Escolhendo fazer depósito...")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {'ask_action': {'action': 'deposit'}}
    })
    print(f"   Status: {result['status']} -> Próximo: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    print("\n📝 4. Informando valor do depósito...")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {'deposit_amount': 500.0}
    })
    print(f"   Status: {result['status']}")
    
    if result['status'] == 'COMPLETED':
        print(f"   ✅ Serviço completado!")
        completion_msg = result.get('current_data', {}).get('_internal', {}).get('completion_message', 'N/A')
        print(f"   💬 Mensagem: {completion_msg}")
        return True
    else:
        print(f"   ❌ Falha no serviço")
        return False

def test_existing_user_flow_v2():
    """Testa usuário existente no V2."""
    print("\n🚀 TESTE: Usuário Existente (V2)")
    print("=" * 60)
    
    user_id = 'test_v2_existing_user'
    service_name = 'bank_account_opening_v2'
    clean_state(user_id)
    
    print("📝 1. Usuário existente fazendo login...")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {
            'user_info.name': 'User Existente', 
            'user_info.email': 'existing@example.com'  # Email de usuário existente
        }
    })
    print(f"   Status: {result['status']} -> Próximo: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    print("\n📝 2. Escolhendo consultar saldo...")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {'ask_action': {'action': 'balance'}}
    })
    print(f"   Status: {result['status']}")
    
    if result['status'] == 'COMPLETED':
        print(f"   ✅ Serviço completado!")
        completion_msg = result.get('current_data', {}).get('_internal', {}).get('completion_message', 'N/A')
        print(f"   💬 Mensagem: {completion_msg}")
        
        # Verificar se o saldo está correto (250 + 100 = 350)
        if "350" in completion_msg:
            print("   ✅ Saldo calculado corretamente!")
            return True
        else:
            print("   ❌ Saldo incorreto")
            return False
    else:
        print(f"   ❌ Falha no serviço")
        return False

def compare_developer_experience():
    """Compara a experiência de desenvolvimento."""
    print("\n🔄 COMPARAÇÃO DE EXPERIÊNCIA DE DESENVOLVIMENTO")
    print("=" * 70)
    
    print("📊 ANTES (V1 - com conditions e is_end):")
    print("""
    StepInfo(
        name="ask_action",
        description="Would you like to make a deposit or check your balance?",
        payload_schema={...},
        depends_on=["check_account"],
        condition='_internal.outcomes.check_account == "ACCOUNT_EXISTS" or _internal.outcomes.create_account == "ACCOUNT_CREATED"',  # 😵 Complexo!
    ),
    
    StepInfo(
        name="deposit_success",
        description="Deposit successful...",
        is_end=True,  # 😵 Action não controla!
        depends_on=["make_deposit"],
    )
    """)
    
    print("\n📊 DEPOIS (V2 - action-driven):")
    print("""
    def _check_account_exists(self, state):
        if has_account:
            return ExecutionResult(
                success=True,
                next_steps=["ask_action"]  # 😍 Action decide!
            )
        else:
            return ExecutionResult(
                success=True, 
                next_steps=["account_type"]  # 😍 Action decide!
            )
    
    def _make_deposit(self, state):
        # ... lógica do depósito ...
        return ExecutionResult(
            success=True,
            is_complete=True,  # 😍 Action decide quando terminar!
            completion_message="Deposit successful!"
        )
    """)
    
    print("\n✅ VANTAGENS DA NOVA ABORDAGEM:")
    print("   • Actions controlam completamente o fluxo")
    print("   • Sem conditions complexas e verbosas")
    print("   • Sem is_end - actions decidem quando terminar")
    print("   • Lógica centralizada nas actions")
    print("   • Mais fácil de debugar")
    print("   • Menos configuração, mais código")

def main():
    """Executa todos os testes da nova experiência."""
    print("🎯 TESTANDO NOVA EXPERIÊNCIA DE DESENVOLVIMENTO")
    print("=" * 80)
    
    tests = [
        ("Action-Driven Flow (Novo Usuário)", test_action_driven_flow),
        ("Action-Driven Flow (Usuário Existente)", test_existing_user_flow_v2),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
            status = "✅ PASSOU" if success else "❌ FALHOU"
            print(f"\n>>> {test_name}: {status}")
        except Exception as e:
            print(f"\n>>> {test_name}: 💥 ERRO - {e}")
            results.append((test_name, False))
    
    # Mostrar comparação
    compare_developer_experience()
    
    # Resumo final
    print("\n" + "=" * 80)
    print("📊 RESUMO DOS TESTES V2:")
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASSOU" if success else "❌ FALHOU"
        print(f"   {test_name}: {status}")
    
    print(f"\n🎯 RESULTADO FINAL: {passed}/{total} testes passaram")
    
    if passed == total:
        print("🎉 NOVA EXPERIÊNCIA FUNCIONANDO PERFEITAMENTE!")
        print("   A experiência de desenvolvimento foi drasticamente melhorada!")
    else:
        print("⚠️ Alguns ajustes ainda são necessários.")

if __name__ == "__main__":
    main()