"""
Teste simples para verificar se o contador de tentativas funciona
quando uma inscrição não retorna dados.
"""

from src.services.workflows.iptu_pagamento.iptu_workflow import IPTUWorkflow
from src.services.core.models import ServiceState


def test_simple_recursion():
    """
    Teste simples e direto do contador de tentativas.
    """
    print("=== TESTE SIMPLES DO CONTADOR DE TENTATIVAS ===\n")
    
    # Cria workflow com API fake
    workflow = IPTUWorkflow(use_fake_api=True)
    
    # Estado com inscrição e ano já definidos
    state = ServiceState(
        user_id="test_simple",
        service_name="iptu_pagamento",
        data={
            "inscricao_imobiliaria": "99999999999999",  # Inscrição inexistente na API fake
            "ano_exercicio": 2024
        },
        internal={}
    )
    
    print("1. TENTATIVA 1: Chamada direta de _consultar_guias_disponiveis")
    try:
        result_state = workflow._consultar_guias_disponiveis(state)
        print(f"   Tentativas após 1ª chamada: {result_state.internal.get('tentativas_falhas_99999999999999', 0)}")
        print(f"   Resposta: {result_state.agent_response.description[:60] if result_state.agent_response else 'None'}...")
        state = result_state
    except Exception as e:
        print(f"   ❌ Erro: {str(e)}")
        return
    
    print()
    print("2. TENTATIVA 2: Segunda chamada com ano diferente")
    state.data["ano_exercicio"] = 2023
    try:
        result_state = workflow._consultar_guias_disponiveis(state)
        print(f"   Tentativas após 2ª chamada: {result_state.internal.get('tentativas_falhas_99999999999999', 0)}")
        print(f"   Resposta: {result_state.agent_response.description[:60] if result_state.agent_response else 'None'}...")
        state = result_state
    except Exception as e:
        print(f"   ❌ Erro: {str(e)}")
        return
    
    print()
    print("3. TENTATIVA 3: Terceira chamada com ano diferente (deve desistir)")
    state.data["ano_exercicio"] = 2022
    try:
        result_state = workflow._consultar_guias_disponiveis(state)
        print(f"   Tentativas após 3ª chamada: {result_state.internal.get('tentativas_falhas_99999999999999', 0)}")
        if result_state.agent_response:
            print(f"   Resposta: {result_state.agent_response.description[:100]}...")
            
            # Verifica se desistiu
            if "múltiplas tentativas" in result_state.agent_response.description:
                print("   ✅ SUCESSO: Detectou inscrição inexistente após 3 tentativas!")
            else:
                print("   ⚠️  Ainda não desistiu")
        state = result_state
    except Exception as e:
        print(f"   ❌ Erro: {str(e)}")
        return
    
    print()
    print("=== TESTE COM INSCRIÇÃO VÁLIDA ===")
    
    # Teste com inscrição válida para comparação
    state_valido = ServiceState(
        user_id="test_valid",
        service_name="iptu_pagamento",
        data={
            "inscricao_imobiliaria": "01234567890123",  # Inscrição válida na API fake
            "ano_exercicio": 2024
        },
        internal={}
    )
    
    try:
        result_state = workflow._consultar_guias_disponiveis(state_valido)
        print(f"   Inscrição válida - dados carregados: {'dados_guias' in result_state.data}")
        print(f"   Resposta: {result_state.agent_response.description[:60] if result_state.agent_response else 'None'}...")
    except Exception as e:
        print(f"   ❌ Erro: {str(e)}")
    
    print()
    print("=== RESULTADO ===")
    print("✅ Teste completo do contador de tentativas")


if __name__ == "__main__":
    test_simple_recursion()