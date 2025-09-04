#!/usr/bin/env python3
"""
Test interativo para Workflow - Foco UX
=======================================

Este script permite testar o Workflow de forma interativa,
focado na experiência do usuário final.
"""

import time
import sys
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Carregar variáveis de ambiente
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src', 'config', '.env')
load_dotenv(env_path)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.orchestrated_agent import OrchestratedAgent


class WorkflowTester:
    def __init__(self):
        print("\n⚡ Iniciando Workflow...")
        self.agent = OrchestratedAgent(
            enable_service_agents=False,
            enable_workflows=True
        )
        print("✅ Workflow inicializado com sucesso!")
        
    def run_interactive_test(self):
        """Executa teste interativo do Workflow"""
        print(f"\n{'='*50}")
        print("🟡 TESTE INTERATIVO - WORKFLOW")
        print(f"{'='*50}")
        print("\nℹ️  Para sair, digite 'sair' ou pressione Ctrl+C")
        print("\n💡 Exemplos de teste:")
        print("   • 'Meu CPF é 12345678901'")
        print("   • 'Quero validar meu email usuario@exemplo.com'")
        print("   • 'Preciso registrar um novo usuário'")
        
        while True:
            try:
                user_input = input("\n🗣️  Você: ").strip()
                
                if user_input.lower() in ['sair', 'exit', 'quit']:
                    print("\n👋 Encerrando teste do Workflow...")
                    break
                    
                if not user_input:
                    continue
                
                print("\n⚡ Workflow processando...")
                start_time = time.time()
                
                # OrchestratedAgent usa query com input e config
                response = self.agent.query(
                    input={"messages": [HumanMessage(content=user_input)]},
                    config={"configurable": {"thread_id": "ux_test_session"}}
                )
                
                end_time = time.time()
                print(f"\n✅ Resposta (⏱️ {end_time - start_time:.2f}s):")
                
                # Extrair mensagem de resposta do resultado
                if isinstance(response, dict) and "messages" in response:
                    messages = response["messages"]
                    if messages:
                        last_message = messages[-1]
                        if hasattr(last_message, 'content'):
                            print(f"💬 {last_message.content}")
                        else:
                            print(f"💬 {last_message}")
                    else:
                        print(f"💬 {response}")
                else:
                    print(f"💬 {response}")
                
            except KeyboardInterrupt:
                print("\n\n👋 Teste interrompido pelo usuário.")
                break
            except Exception as e:
                print(f"\n❌ Erro: {e}")


def main():
    """Função principal"""
    try:
        tester = WorkflowTester()
        tester.run_interactive_test()
    except Exception as e:
        print(f"❌ Erro ao inicializar: {e}")


if __name__ == "__main__":
    main()
