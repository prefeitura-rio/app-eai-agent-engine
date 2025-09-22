#!/usr/bin/env python3
"""
Teste para simular usuário existente e verificar comportamento de grafo.
"""

import os
import json
from src.services.tool import multi_step_service

def clean_test_state():
    """Remove arquivo de estado do teste se existir."""
    state_file = "src/services/data/test_existing_user.json"
    if os.path.exists(state_file):
        os.remove(state_file)

def setup_existing_user():
    """
    Configura um usuário existente simulando dados de conta já existentes.
    """
    # Primeiro, cria uma conta para simular um usuário existente
    user_id = 'test_existing_user'
    service_name = 'bank_account_opening'
    
    # Simular dados de usuário existente no estado
    state_data = {
        service_name: {
            "data": {
                "account_details": {
                    "account_number": 123456789
                },
                "deposits": [250.0],
                "balance": 250.0
            },
            "_internal": {
                "completed_steps": {
                    "user_info": True,
                    "user_info.name": True,
                    "user_info.email": True,
                    "check_account": True,
                    "account_created_success": True
                },
                "outcomes": {
                    "check_account": "ACCOUNT_EXISTS"  # CHAVE: fazer parecer que a conta existe
                }
            }
        }
    }
    
    # Salvar estado manualmente
    os.makedirs("src/services/data", exist_ok=True)
    with open("src/services/data/test_existing_user.json", "w") as f:
        json.dump(state_data, f, indent=2)
    
    return user_id, service_name

def test_existing_user_graph():
    """
    Testa o comportamento de grafo com usuário existente.
    """
    print("🧪 TESTE: Comportamento de Grafo - Usuário Existente")
    print("=" * 60)
    
    clean_test_state()
    user_id, service_name = setup_existing_user()
    
    # Passo 1: Fornecer user_info para usuário existente
    print("\n📝 PASSO 1: Fornecendo user_info (usuário existente)")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {
            'user_info.name': 'Jane Doe', 
            'user_info.email': 'jane@example.com'
        }
    })
    
    print(f"   Status: {result['status']}")
    print(f"   Próximo step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    # Mostrar a árvore de execução
    print("\n🌳 ÁRVORE DE EXECUÇÃO:")
    if result.get('execution_summary'):
        print(result['execution_summary']['tree'])
    
    # Verificar se encontrou ask_next_action
    if result['next_step_info'] and result['next_step_info']['step_name'] == 'ask_next_action':
        print("\n✅ SUCESSO: Framework encontrou ask_next_action para usuário existente!")
        print("   O comportamento de grafo está funcionando corretamente.")
        return True
    else:
        print("\n❌ FALHA: Framework não encontrou ask_next_action mesmo para usuário existente.")
        print(f"   Status: {result['status']}")
        print(f"   Next step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
        return False

def test_ask_next_action_flow():
    """
    Testa o fluxo completo de ask_next_action.
    """
    print("\n🧪 TESTE: Fluxo ask_next_action")
    print("=" * 60)
    
    user_id = 'test_existing_user'
    service_name = 'bank_account_opening'
    
    # Escolher fazer consulta de saldo
    print("\n📝 PASSO 2: Escolhendo verificar saldo")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {'ask_next_action': {'next_action': 'balance'}}
    })
    
    print(f"   Status: {result['status']}")
    print(f"   Próximo step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    # Verificar se executou get_balance automaticamente
    if result['status'] == 'COMPLETED':
        balance = result.get('final_output', {}).get('balance', 'N/A')
        print(f"   ✅ Saldo obtido: {balance}")
        return True
    else:
        print("   ❌ Não conseguiu completar verificação de saldo")
        return False

if __name__ == "__main__":
    try:
        # Teste principal - usuário existente
        success1 = test_existing_user_graph()
        
        if success1:
            # Se o primeiro teste passou, executar o fluxo ask_next_action
            success2 = test_ask_next_action_flow()
            
            if success1 and success2:
                print("\n🎉 TODOS OS TESTES PASSARAM!")
                print("   O framework agora funciona como um grafo verdadeiro.")
                print("   ✅ Detecta múltiplas branches")
                print("   ✅ Continua execução após completar uma branch")
                print("   ✅ Executa branches condicionais corretamente")
            else:
                print("\n⚠️ TESTE PARCIAL: Detecção funcionou, mas execução falhou.")
        else:
            print("\n❌ TESTE FALHOU: Ainda não detecta branches paralelas.")
            
    except Exception as e:
        print(f"\n💥 ERRO NO TESTE: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpar estado do teste
        clean_test_state()