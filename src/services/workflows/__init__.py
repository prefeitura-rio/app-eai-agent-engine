"""
Workflows V5 - LangGraph based multi-step services

Este módulo centraliza todos os workflows disponíveis.
Para adicionar um novo workflow:
1. Crie o arquivo do workflow em workflows/
2. Importe e adicione na lista 'workflows' abaixo
3. Cada workflow deve ter um atributo 'service_name'
"""

# Import workflows aqui
from src.services.workflows.bank_account import BankAccountWorkflow
from src.services.workflows.iptu_ano_vigente import IPTUAnoVigenteWorkflow

# Lista central de workflows (classes)
workflows = [
    BankAccountWorkflow,
    IPTUAnoVigenteWorkflow,
]

# Lista de workflows disponíveis para import fácil
__all__ = ["workflows"]
