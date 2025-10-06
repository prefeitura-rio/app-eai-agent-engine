"""
Workflow IPTU Ano Vigente - Prefeitura do Rio de Janeiro

Este workflow implementa o processo de consulta de IPTU do ano vigente
seguindo o fluxograma oficial da Prefeitura do Rio.
"""

from src.services.workflows.iptu_ano_vigente.iptu_workflow import IPTUAnoVigenteWorkflow

__all__ = ["IPTUAnoVigenteWorkflow"]