#!/usr/bin/env python3
"""
Teste para verificar o comportamento de grafo do framework.
Verifica se o orchestrator continua executando quando há múltiplas branches disponíveis.
"""

import os
import json
from src.services.tool import multi_step_service

def clean_test_state():
    """Remove arquivo de estado do teste se existir."""
    state_file = "src/services/data/test_user_graph.json"
    if os.path.exists(state_file):
        os.remove(state_file)

def test_graph_continuation():
    """
    Testa se o framework continua executando quando uma branch é completada
    mas existem outras branches disponíveis no grafo.
    """
    print("🧪 TESTE: Comportamento de Grafo - Continuação entre Branches")
    print("=" * 60)
    
    # Limpar estado anterior
    clean_test_state()
    
    user_id = 'test_user_graph'
    service_name = 'bank_account_opening'
    
    # Passo 1: Fornecer informações do usuário
    print("\n📝 PASSO 1: Fornecendo user_info completo")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {
            'user_info.name': 'John Doe', 
            'user_info.email': 'test@example.com'
        }
    })
    
    print(f"   Status: {result['status']}")
    print(f"   Próximo step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    assert result['status'] == 'IN_PROGRESS', f"Esperado IN_PROGRESS, obtido {result['status']}"
    
    # Aguardar que check_account seja executado automaticamente e chegue no account_type
    expected_next = result['next_step_info']['step_name'] if result['next_step_info'] else 'None'
    print(f"   Próximo step detectado: {expected_next}")
    
    # Se ainda está em user_info, significa que precisa de mais dados
    if expected_next == 'user_info':
        print("   ⚠️ Ainda em user_info, continuando...")
        return False
    elif expected_next == 'account_type':
        print("   ✅ Avançou para account_type conforme esperado")
    else:
        print(f"   🔍 Step inesperado: {expected_next}, continuando com o teste...")
    
    # Passo 2: Escolher tipo de conta (apenas se chegou ao account_type)
    if expected_next == 'account_type' or expected_next not in ['user_info']:
        print("\n📝 PASSO 2: Escolhendo account_type")
        result = multi_step_service.invoke({
            "service_name": service_name,
            "user_id": user_id,
            "payload": {'account_type': 'savings'}
        })
        
        print(f"   Status: {result['status']}")
        print(f"   Próximo step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
        assert result['status'] == 'IN_PROGRESS', f"Esperado IN_PROGRESS, obtido {result['status']}"
        
        next_step = result['next_step_info']['step_name'] if result['next_step_info'] else 'None'
        if next_step != 'initial_deposit':
            print(f"   ⚠️ Esperado initial_deposit, obtido {next_step}")
    else:
        print("\n⏭️ PASSO 2: Pulando account_type (ainda em user_info)")
        return False
    
    # Passo 3: Depósito inicial
    print("\n📝 PASSO 3: Fornecendo initial_deposit")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {'initial_deposit': {'deposit_amount': 500}}
    })
    
    print(f"   Status: {result['status']}")
    print(f"   Próximo step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    # AQUI É O TESTE CRÍTICO - depois que account_created_success é atingido,
    # o framework deveria continuar e encontrar ask_next_action
    
    # Passo 4: Payload vazio para verificar se encontra ask_next_action
    print("\n🔍 PASSO 4: Verificando continuação do grafo (payload vazio)")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {}
    })
    
    print(f"   Status: {result['status']}")
    print(f"   Próximo step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    # Mostrar a árvore de execução
    print("\n🌳 ÁRVORE DE EXECUÇÃO:")
    if result.get('execution_summary'):
        print(result['execution_summary']['tree'])
    
    # Verificar se encontrou ask_next_action
    if result['next_step_info'] and result['next_step_info']['step_name'] == 'ask_next_action':
        print("\n✅ SUCESSO: Framework continuou executando e encontrou ask_next_action!")
        print("   O comportamento de grafo está funcionando corretamente.")
        return True
    else:
        print("\n❌ FALHA: Framework não encontrou ask_next_action.")
        print("   O comportamento de grafo ainda não está funcionando.")
        print(f"   Status final: {result['status']}")
        return False

def test_complete_second_branch():
    """
    Testa a execução completa da segunda branch (ask_next_action -> deposit).
    """
    print("\n🧪 TESTE: Execução da Segunda Branch")
    print("=" * 60)
    
    user_id = 'test_user_graph'
    service_name = 'bank_account_opening'
    
    # Passo 5: Escolher fazer depósito
    print("\n📝 PASSO 5: Escolhendo fazer depósito")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {'ask_next_action': 'deposit'}
    })
    
    print(f"   Status: {result['status']}")
    print(f"   Próximo step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    if result['next_step_info']:
        assert result['next_step_info']['step_name'] == 'deposit_transaction', f"Esperado deposit_transaction, obtido {result['next_step_info']['step_name']}"
    
    # Passo 6: Fazer depósito
    print("\n📝 PASSO 6: Fazendo depósito")
    result = multi_step_service.invoke({
        "service_name": service_name,
        "user_id": user_id,
        "payload": {'deposit_transaction': 100}
    })
    
    print(f"   Status: {result['status']}")
    print(f"   Próximo step: {result['next_step_info']['step_name'] if result['next_step_info'] else 'None'}")
    
    # Mostrar resultado final
    print("\n🏁 RESULTADO FINAL:")
    print(f"   Status: {result['status']}")
    if result.get('final_output'):
        balance = result['final_output'].get('balance', 'N/A')
        print(f"   Balance final: {balance}")
    
    return result['status'] == 'COMPLETED'

if __name__ == "__main__":
    try:
        # Teste principal
        success1 = test_graph_continuation()
        
        if success1:
            # Se o primeiro teste passou, executar o segundo
            success2 = test_complete_second_branch()
            
            if success1 and success2:
                print("\n🎉 TODOS OS TESTES PASSARAM!")
                print("   O framework agora funciona como um grafo verdadeiro.")
            else:
                print("\n⚠️ TESTE PARCIAL: Primeira parte passou, segunda falhou.")
        else:
            print("\n❌ TESTE FALHOU: Correção ainda não está funcionando.")
            
    except Exception as e:
        print(f"\n💥 ERRO NO TESTE: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpar estado do teste
        clean_test_state()