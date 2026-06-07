"""
Prompt module — wrapper versionável para o prompt dinâmico de luminária.

O conteúdo mora em `engine.luminaria_interactive_prompt` porque `engine/` é o
pacote deployado pelo Agent Engine. Este módulo mantém o contrato do composer e
dos testes (`MODULE_NAME` + `MODULE_PROMPT`) sem fazer `engine/` importar `src/`.
"""

from engine import luminaria_interactive_prompt as _luminaria_interactive_prompt


MODULE_NAME = "interactive_response"
MODULE_PROMPT = _luminaria_interactive_prompt.MODULE_PROMPT
