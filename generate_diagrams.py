#!/usr/bin/env python3
"""
Gerador de diagramas arquiteturais para análise Service Agent vs Workflow
"""

def generate_architecture_diagrams():
    """Gera diagramas em ASCII para visualizar as arquiteturas"""
    
    service_agent_diagram = """
🤖 SERVICE AGENT ARCHITECTURE
=====================================

┌─────────────────┐
│   User Input    │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│  Main Agent     │ ──────┐
│     (LLM)       │       │ 1 LLM Call
└─────────┬───────┘       │
          │               │
          ▼               ▼
┌─────────────────┐  ┌──────────────┐
│ Route Detection │  │   Metrics    │
│ "identificar"?  │  │ Time: 7-15s  │
└─────────┬───────┘  │ Calls: 1     │
          │          └──────────────┘
          ▼
┌─────────────────┐
│route_to_ident   │
│_agent(message)  │ ──────┐
└─────────┬───────┘       │ Direct Processing
          │               │ (No additional LLM)
          ▼               ▼
┌─────────────────┐  ┌──────────────┐
│ Service Tool    │  │ Regex Parse  │
│ • Regex Parsing │  │ • CPF Extract│
│ • Validation    │  │ • Email      │
│ • State Mgmt    │  │ • Name       │
└─────────┬───────┘  └──────────────┘
          │
          ▼
┌─────────────────┐
│ Formatted       │
│ Response        │
└─────────────────┘

Pros:
✅ Single LLM call per interaction
✅ Direct data processing
✅ Low latency (7-15s)
✅ Flexible input handling
✅ Robust error recovery

Cons:
❌ Complex regex logic
❌ Custom validation code
❌ Harder to maintain
❌ State management complexity
"""

    workflow_diagram = """
⚙️ WORKFLOW ARCHITECTURE  
=====================================

┌─────────────────┐
│   User Input    │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│  Main Agent     │ ──────┐
│     (LLM)       │       │ 1 LLM Call
└─────────┬───────┘       │
          │               │
          ▼               ▼
┌─────────────────┐  ┌──────────────┐
│ Workflow Tool   │  │   Metrics    │
│ Detection       │  │ Time: 12-19s │
└─────────┬───────┘  │ Calls: 1-3   │
          │          └──────────────┘
          ▼
┌─────────────────┐
│start_user_ident │ ──────┐
│ification()     │       │ Workflow Engine
└─────────┬───────┘       │ Processing
          │               ▼
          ▼          ┌──────────────┐
┌─────────────────┐  │ State Engine │
│ Workflow Engine │  │ • Step Track │
│ • State Machine │  │ • Validation │
│ • Step-by-step  │  │ • Progress   │
│ • Validation    │  └──────────────┘
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│process_user_    │ ──────┐
│identification   │       │ Final Processing
│(cpf,email,name) │       │ (May need LLM)
└─────────┬───────┘       ▼
          │          ┌──────────────┐
          ▼          │ Additional   │
┌─────────────────┐  │ LLM Call?    │
│ Formatted       │  │ (Structured) │
│ Response        │  └──────────────┘
└─────────────────┘

Pros:
✅ Structured execution flow
✅ Built-in validation
✅ Easy to debug/maintain
✅ Consistent UX
✅ Standard patterns

Cons:
❌ Higher latency (12-19s)
❌ Multiple potential LLM calls
❌ Workflow engine overhead
❌ Less flexible input
❌ Rigid step progression
"""

    comparison_diagram = """
📊 PERFORMANCE COMPARISON
=====================================

TIME PER INTERACTION:
Service Agent    ████████▌ 10.3s avg
Workflow        ████████████▌ 14.2s avg
                                 ↑ 38% slower

TOTAL TIME (Complex Scenario):
Service Agent    ███████████ 55.0s
Workflow        ████████████████▌ 88.5s
                                 ↑ 61% slower

LATENCY BREAKDOWN:
┌─────────────────┐ ┌─────────────────┐
│ Service Agent   │ │    Workflow     │
├─────────────────┤ ├─────────────────┤
│ LLM Call: ~60%  │ │ LLM Call: ~50%  │
│ Regex: ~15%     │ │ Engine: ~30%    │
│ Validation: ~10%│ │ Validation: ~10%│
│ Response: ~15%  │ │ Response: ~10%  │
└─────────────────┘ └─────────────────┘

SCALABILITY:
Interactions →  2    4    7
Service Agent   15s  8s   7s  ← Gets faster
Workflow       19s  12s  12s  ← Stays same

ARCHITECTURE EFFICIENCY:
Service Agent: Direct → Tool → Response
Workflow:      Agent → Engine → Steps → Response
               ↑ More overhead
"""

    return service_agent_diagram, workflow_diagram, comparison_diagram


def save_diagrams():
    """Salva os diagramas em arquivo"""
    service, workflow, comparison = generate_architecture_diagrams()
    
    full_diagram = f"""
# 🏗️ ANÁLISE ARQUITETURAL VISUAL

{service}

{workflow}

{comparison}

## 🎯 CONCLUSÕES VISUAIS

### Fluxo de Execução:
**Service Agent**: Linear, direto, menos etapas
**Workflow**: Estruturado, mais etapas, maior overhead

### Performance Pattern:
**Service Agent**: Melhora com complexidade (usuário caótico)
**Workflow**: Performance constante independente da complexidade

### Trade-offs:
**Service Agent**: Velocidade ↔ Complexidade de código
**Workflow**: Estrutura ↔ Performance

### Recomendação Técnica:
**Para Performance**: Service Agent
**Para Manutenibilidade**: Workflow
**Para Flexibilidade**: Service Agent
**Para Consistência**: Workflow
"""
    
    with open("ARCHITECTURE_DIAGRAMS.md", "w", encoding="utf-8") as f:
        f.write(full_diagram)
    
    print("✅ Diagramas arquiteturais salvos em: ARCHITECTURE_DIAGRAMS.md")


if __name__ == "__main__":
    save_diagrams()
