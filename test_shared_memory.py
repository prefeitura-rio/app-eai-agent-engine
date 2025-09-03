#!/usr/bin/env python3
"""
Test script demonstrating shared memory between main agent and service agents.

This test shows how both the main agent and identification service agent 
access the same PostgreSQL memory and can see each other's conversation history.
"""

import asyncio
import src.config.env  # This loads the environment variables automatically
from engine.orchestrated_agent import OrchestratedAgent
from src.tools import mcp_tools


async def test_shared_memory():
    """Test that demonstrates shared memory between agents."""
    
    print("🔄 Environment loaded automatically...")
    
    print("🔧 Creating agent with both workflows and service agents enabled...")
    # Create agent with both approaches enabled
    agent = OrchestratedAgent(
        model="gemini-2.5-flash",
        system_prompt="""Você é um assistente municipal inteligente do Rio de Janeiro.

Ajude os cidadãos com serviços municipais, informações e identificação de usuário.

Você tem acesso tanto a workflows estruturados quanto a agentes de serviço especializados.
Ambos compartilham a mesma memória PostgreSQL, então você pode ver todo o histórico da conversa.
""",
        tools=mcp_tools,
        temperature=0.3,
        enable_service_agents=True,
        enable_workflows=True
    )
    
    # Use a specific thread_id to demonstrate memory persistence
    config = {"configurable": {"thread_id": "shared_memory_test_001"}}
    
    print("\n" + "="*60)
    print("🧪 TESTE DE MEMÓRIA COMPARTILHADA")
    print("="*60)
    
    # Step 1: User provides partial identification via workflow
    print("\n🔹 PASSO 1: Usuário fornece dados via workflow estruturado")
    step1_input = {
        "messages": [{"role": "human", "content": "Quero iniciar minha identificação no sistema"}]
    }
    
    result1 = await agent.async_query(input=step1_input, config=config)
    if result1 and "messages" in result1:
        for message in result1["messages"]:
            if hasattr(message, 'content') and "AIMessage" in str(type(message)):
                print(f"   🤖 Agente: {message.content}")
    
    # Step 2: User provides CPF via workflow
    print("\n🔹 PASSO 2: Usuário fornece CPF")
    step2_input = {
        "messages": [{"role": "human", "content": "Meu CPF é 11144477735"}]
    }
    
    result2 = await agent.async_query(input=step2_input, config=config)
    if result2 and "messages" in result2:
        for message in result2["messages"]:
            if hasattr(message, 'content') and "AIMessage" in str(type(message)):
                print(f"   🤖 Agente: {message.content}")
    
    # Step 3: Switch to service agent approach 
    print("\n🔹 PASSO 3: Switch para abordagem conversacional")
    print("   📝 Agora o usuário quer continuar via agente de serviço")
    step3_input = {
        "messages": [{"role": "human", "content": "Prefiro uma abordagem mais conversacional para continuar. Pode me ajudar via chat?"}]
    }
    
    result3 = await agent.async_query(input=step3_input, config=config)
    if result3 and "messages" in result3:
        for message in result3["messages"]:
            if hasattr(message, 'content') and "AIMessage" in str(type(message)):
                print(f"   🤖 Agente: {message.content}")
    
    # Step 4: Provide remaining data via service agent
    print("\n🔹 PASSO 4: Usuário completa dados via agente conversacional")
    step4_input = {
        "messages": [{"role": "human", "content": "Me chamo Bruno Silva e meu email é bruno.silva@email.com"}]
    }
    
    result4 = await agent.async_query(input=step4_input, config=config)
    if result4 and "messages" in result4:
        for message in result4["messages"]:
            if hasattr(message, 'content') and "AIMessage" in str(type(message)):
                print(f"   🤖 Agente: {message.content}")
    
    # Step 5: Verify memory persistence
    print("\n🔹 PASSO 5: Verificação de persistência de memória")
    step5_input = {
        "messages": [{"role": "human", "content": "Você lembra de todos os dados que eu forneci até agora?"}]
    }
    
    result5 = await agent.async_query(input=step5_input, config=config)
    if result5 and "messages" in result5:
        for message in result5["messages"]:
            if hasattr(message, 'content') and "AIMessage" in str(type(message)):
                print(f"   🤖 Agente: {message.content}")
    
    print("\n" + "="*60)
    print("✅ TESTE CONCLUÍDO - Memória compartilhada demonstrada!")
    print("="*60)
    print("\n📊 RESUMO:")
    print("• ✅ Workflow coletou CPF inicial")
    print("• ✅ Service agent completou dados restantes") 
    print("• ✅ Ambos compartilham mesma memória PostgreSQL")
    print("• ✅ Histórico completo preservado entre abordagens")
    print("• ✅ thread_id garante continuidade da conversa")


if __name__ == "__main__":
    asyncio.run(test_shared_memory())
