#!/usr/bin/env python3
"""
Análise Técnica Comparativa: Agent vs Workflow
==============================================

Este script executa testes detalhados para comparar as abordagens:
1. Service Agent (conversational) 
2. Workflow (structured)

Métricas analisadas:
- Número de chamadas LLM
- Latência total
- Latência por interação
- Tokens utilizados
- Complexidade de execução
- Robustez a erros
"""

import asyncio
import time
import json
from typing import Dict, List, Any
from datetime import datetime
import src.config.env
from engine.orchestrated_agent import OrchestratedAgent
from src.tools import mcp_tools


class MetricsCollector:
    """Coleta métricas detalhadas das execuções."""
    
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.start_time = None
        self.end_time = None
        self.interactions = []
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_used = 0
        
    def start_test(self):
        self.start_time = time.time()
        
    def end_test(self):
        self.end_time = time.time()
        
    def add_interaction(self, user_input: str, agent_response: str, interaction_time: float):
        self.interactions.append({
            "user_input": user_input,
            "agent_response": agent_response,
            "interaction_time": interaction_time,
            "timestamp": datetime.now().isoformat()
        })
        
    def get_summary(self) -> Dict[str, Any]:
        total_time = self.end_time - self.start_time if self.end_time and self.start_time else 0
        avg_interaction_time = sum(i["interaction_time"] for i in self.interactions) / len(self.interactions) if self.interactions else 0
        
        return {
            "test_name": self.test_name,
            "total_time": total_time,
            "total_interactions": len(self.interactions),
            "average_interaction_time": avg_interaction_time,
            "llm_calls_estimated": len(self.interactions),  # Estimativa baseada em interações
            "tool_calls_estimated": sum(1 for i in self.interactions if "✅" in i["agent_response"] or "erro" in i["agent_response"].lower()),
            "interactions": self.interactions
        }


async def test_scenario(agent: OrchestratedAgent, scenario_name: str, messages: List[str], thread_id: str) -> MetricsCollector:
    """
    Executa um cenário de teste completo e coleta métricas.
    """
    print(f"\n{'='*60}")
    print(f"🧪 CENÁRIO: {scenario_name}")
    print(f"{'='*60}")
    
    metrics = MetricsCollector(scenario_name)
    metrics.start_test()
    
    config = {"configurable": {"thread_id": thread_id}}
    
    for i, message in enumerate(messages):
        print(f"\n🔹 INTERAÇÃO {i+1}: {message}")
        
        interaction_start = time.time()
        
        input_data = {
            "messages": [{"role": "human", "content": message}]
        }
        
        try:
            result = await agent.async_query(input=input_data, config=config)
            interaction_end = time.time()
            interaction_time = interaction_end - interaction_start
            
            # Extrair resposta do agente
            agent_response = ""
            if result and "messages" in result:
                for msg in result["messages"]:
                    if hasattr(msg, 'content') and "AIMessage" in str(type(msg)):
                        agent_response = msg.content
                        break
            
            print(f"   🤖 Resposta ({interaction_time:.2f}s): {agent_response[:200]}...")
            
            metrics.add_interaction(message, agent_response, interaction_time)
            
            # Pequena pausa entre interações para simular comportamento real
            await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"   ❌ Erro: {str(e)}")
            metrics.add_interaction(message, f"ERRO: {str(e)}", 0)
    
    metrics.end_test()
    
    # Resumo do cenário
    summary = metrics.get_summary()
    print(f"\n📊 RESUMO DO CENÁRIO:")
    print(f"   • Tempo total: {summary['total_time']:.2f}s")
    print(f"   • Interações: {summary['total_interactions']}")
    print(f"   • Tempo médio por interação: {summary['average_interaction_time']:.2f}s")
    print(f"   • Chamadas LLM estimadas: {summary['llm_calls_estimated']}")
    
    return metrics


async def run_comparative_analysis():
    """
    Executa análise comparativa completa entre Agent e Workflow.
    """
    
    print("🔧 Criando agentes para teste...")
    
    # Agent com Service Agents habilitados (conversational)
    agent_service = OrchestratedAgent(
        model="gemini-2.5-flash",
        system_prompt="""Você é um assistente municipal que usa APENAS abordagem conversacional.
        
Para identificação de usuários, sempre use o route_to_identification_agent.
Seja eficiente e colete dados de forma natural.""",
        tools=mcp_tools,
        temperature=0.3,
        enable_service_agents=True,
        enable_workflows=False  # Força uso de service agents
    )
    
    # Agent com Workflows habilitados (structured)
    agent_workflow = OrchestratedAgent(
        model="gemini-2.5-flash",
        system_prompt="""Você é um assistente municipal que usa APENAS workflows estruturados.

Para identificação de usuários, sempre use as ferramentas de workflow.
Seja metódico e siga o processo passo a passo.""",
        tools=mcp_tools,
        temperature=0.3,
        enable_service_agents=False,  # Força uso de workflows
        enable_workflows=True
    )
    
    # Definir cenários de teste
    scenarios = {
        "cenario_1_perfeito": {
            "name": "CENÁRIO 1: Usuário Perfeito (3 dados de uma vez)",
            "messages": [
                "Quero me identificar no sistema",
                "Meu CPF é 11144477735, me chamo Bruno Silva e meu email é bruno.silva@email.com"
            ]
        },
        "cenario_2_sequencial": {
            "name": "CENÁRIO 2: Usuário Sequencial (1 dado por vez)",
            "messages": [
                "Preciso me identificar",
                "Meu CPF é 11144477735",
                "Meu email é bruno.silva@email.com", 
                "Me chamo Bruno Silva"
            ]
        },
        "cenario_3_caotico": {
            "name": "CENÁRIO 3: Usuário Caótico (dados incorretos + correções)",
            "messages": [
                "Oi, quero me identificar",
                "Meu CPF é 123456 e me chamo João",  # CPF inválido
                "Ops, meu CPF correto é 11144477735",
                "Na verdade meu nome é Bruno Silva, não João",
                "Meu email é bruno@email",  # Email inválido
                "Desculpa, meu email correto é bruno.silva@email.com",
                "Está tudo correto agora?"
            ]
        }
    }
    
    # Executar testes para Service Agent
    print("\n" + "🤖 TESTANDO SERVICE AGENT (Conversational)".center(80, "="))
    service_results = {}
    
    for scenario_key, scenario_data in scenarios.items():
        thread_id = f"service_{scenario_key}_{int(time.time())}"
        metrics = await test_scenario(
            agent_service, 
            f"SERVICE: {scenario_data['name']}", 
            scenario_data["messages"], 
            thread_id
        )
        service_results[scenario_key] = metrics.get_summary()
    
    # Executar testes para Workflow
    print("\n" + "⚙️ TESTANDO WORKFLOW (Structured)".center(80, "="))
    workflow_results = {}
    
    for scenario_key, scenario_data in scenarios.items():
        thread_id = f"workflow_{scenario_key}_{int(time.time())}"
        metrics = await test_scenario(
            agent_workflow, 
            f"WORKFLOW: {scenario_data['name']}", 
            scenario_data["messages"], 
            thread_id
        )
        workflow_results[scenario_key] = metrics.get_summary()
    
    # Análise comparativa
    print("\n" + "📊 ANÁLISE COMPARATIVA FINAL".center(80, "="))
    
    comparison_table = []
    
    for scenario_key in scenarios.keys():
        service_data = service_results[scenario_key]
        workflow_data = workflow_results[scenario_key]
        
        comparison = {
            "scenario": scenarios[scenario_key]["name"],
            "service_agent": {
                "total_time": service_data["total_time"],
                "interactions": service_data["total_interactions"], 
                "avg_time": service_data["average_interaction_time"],
                "llm_calls": service_data["llm_calls_estimated"]
            },
            "workflow": {
                "total_time": workflow_data["total_time"],
                "interactions": workflow_data["total_interactions"],
                "avg_time": workflow_data["average_interaction_time"], 
                "llm_calls": workflow_data["llm_calls_estimated"]
            }
        }
        
        comparison_table.append(comparison)
    
    # Imprimir tabela comparativa
    print(f"\n{'CENÁRIO':<40} {'SERVICE AGENT':<25} {'WORKFLOW':<25}")
    print(f"{'':<40} {'Time|Int|LLM':<25} {'Time|Int|LLM':<25}")
    print("-" * 90)
    
    for comp in comparison_table:
        scenario_name = comp["scenario"][:35] + "..." if len(comp["scenario"]) > 35 else comp["scenario"]
        
        service_stats = f"{comp['service_agent']['total_time']:.1f}s|{comp['service_agent']['interactions']}|{comp['service_agent']['llm_calls']}"
        workflow_stats = f"{comp['workflow']['total_time']:.1f}s|{comp['workflow']['interactions']}|{comp['workflow']['llm_calls']}"
        
        print(f"{scenario_name:<40} {service_stats:<25} {workflow_stats:<25}")
    
    # Salvar resultados detalhados
    detailed_results = {
        "timestamp": datetime.now().isoformat(),
        "service_agent_results": service_results,
        "workflow_results": workflow_results,
        "comparison_table": comparison_table
    }
    
    with open("comparative_analysis_results.json", "w", encoding="utf-8") as f:
        json.dump(detailed_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Análise completa! Resultados detalhados salvos em: comparative_analysis_results.json")
    
    # Conclusões técnicas
    print("\n" + "🎯 CONCLUSÕES TÉCNICAS".center(80, "="))
    
    # Calcular médias
    service_avg_time = sum(r["total_time"] for r in service_results.values()) / len(service_results)
    workflow_avg_time = sum(r["total_time"] for r in workflow_results.values()) / len(workflow_results)
    
    service_avg_interactions = sum(r["total_interactions"] for r in service_results.values()) / len(service_results)
    workflow_avg_interactions = sum(r["total_interactions"] for r in workflow_results.values()) / len(workflow_results)
    
    print(f"\n📈 PERFORMANCE MÉDIA:")
    print(f"   SERVICE AGENT: {service_avg_time:.2f}s total, {service_avg_interactions:.1f} interações")
    print(f"   WORKFLOW:      {workflow_avg_time:.2f}s total, {workflow_avg_interactions:.1f} interações")
    
    if service_avg_time < workflow_avg_time:
        print(f"   🏆 SERVICE AGENT é {((workflow_avg_time/service_avg_time-1)*100):.1f}% mais rápido")
    else:
        print(f"   🏆 WORKFLOW é {((service_avg_time/workflow_avg_time-1)*100):.1f}% mais rápido")


if __name__ == "__main__":
    asyncio.run(run_comparative_analysis())
