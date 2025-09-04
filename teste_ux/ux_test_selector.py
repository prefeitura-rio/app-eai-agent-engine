#!/usr/bin/env python3
"""
🎯 SELETOR DE TESTES UX
========================

Escolha qual abordagem testar: Service Agent ou Workflow.
"""

import subprocess
import sys
import os


class UXTestSelector:
    def print_welcome(self):
        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     🎯 TESTES UX - SELETOR DE ABORDAGENS                    ║
║                                                                              ║
║           Escolha qual abordagem você quer testar interativamente           ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    
    def print_options(self):
        print("""
🚀 OPÇÕES DISPONÍVEIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣  🤖 SERVICE AGENT
    ✨ Abordagem conversacional com agentes especializados
    ✨ Roteamento inteligente para diferentes serviços
    ✨ Ideal para conversas naturais e flexíveis

2️⃣  📋 WORKFLOW 
    ✨ Abordagem estruturada com fluxos organizados
    ✨ Processos step-by-step mais previsíveis
    ✨ Ideal para procedimentos estruturados

3️⃣  � GUIA DE TESTE
    ✨ Instruções completas para avaliação UX
    ✨ Critérios de comparação
    ✨ Cenários de teste recomendados

0️⃣  🚪 SAIR

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    
    def show_test_guide(self):
        print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        📚 GUIA DE TESTE UX                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

🎯 DIFERENÇAS PRINCIPAIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 SERVICE AGENT:
   ✅ Conversação mais natural e fluida
   ✅ Roteamento automático para especialistas
   ✅ Melhor para usuários que preferem chat livre
   ⚠️  Pode ser menos previsível

📋 WORKFLOW:
   ✅ Fluxo mais estruturado e organizado
   ✅ Etapas claras e previsíveis
   ✅ Melhor performance (4.4% mais rápido)
   ⚠️  Pode parecer mais "robótico"

🧪 CENÁRIOS DE TESTE ESSENCIAIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🟢 BÁSICOS:
   • "Oi, quero me identificar. Meu CPF é 111.444.777-35"
   • "Onde fica a prefeitura?"
   • "Preciso de ajuda com IPTU"

� VALIDAÇÕES:
   • "Meu CPF é 111.444.777-99" (inválido)
   • "Meu email é usuario@dominio" (formato inválido)

🔴 COMPLEXOS:
   • "Tem um buraco na rua, como reporto?"
   • "Quero marcar consulta médica"

� CRITÉRIOS DE AVALIAÇÃO:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

□ Tempo de resposta < 15s
□ Conversação fluida e natural
□ Validações funcionam corretamente
□ Mensagens de erro são claras
□ Usuário consegue completar tarefas
□ Interface é intuitiva

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
        input("\n📖 Pressione ENTER para voltar ao menu...")
    
    def run_service_agent_test(self):
        print("\n🚀 Iniciando teste do SERVICE AGENT...")
        try:
            subprocess.run([sys.executable, "test_service_agent_ux.py"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"❌ Erro ao executar teste: {e}")
    
    def run_workflow_test(self):
        print("\n🚀 Iniciando teste do WORKFLOW...")
        try:
            subprocess.run([sys.executable, "test_workflow_ux.py"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"❌ Erro ao executar teste: {e}")
    
    def run(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls')
            self.print_welcome()
            self.print_options()
            
            try:
                choice = input("🎯 Escolha uma opção (0-3): ").strip()
                
                if choice == "0":
                    print("\n👋 Obrigado por usar os testes UX!")
                    break
                elif choice == "1":
                    self.run_service_agent_test()
                    input("\n📖 Pressione ENTER para voltar ao menu...")
                elif choice == "2":
                    self.run_workflow_test()
                    input("\n📖 Pressione ENTER para voltar ao menu...")
                elif choice == "3":
                    self.show_test_guide()
                else:
                    print("❌ Opção inválida. Escolha entre 0-3.")
                    input("\n📖 Pressione ENTER para continuar...")
                    
            except KeyboardInterrupt:
                print("\n\n⏸️  Teste interrompido pelo usuário.")
                break


if __name__ == "__main__":
    UXTestSelector().run()
