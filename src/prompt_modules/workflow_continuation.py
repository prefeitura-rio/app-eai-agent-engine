"""
Modulo de prompt: regras para continuar workflows ja iniciados por
``multi_step_service``.

Estas instrucoes precisam viver em prompt module ativo porque o prompt base vem
da API em runtime; editar apenas snapshots comentados em ``src/prompt.py`` nao
altera o comportamento do agente implantado.
"""

MODULE_NAME = "workflow_continuation"

MODULE_PROMPT = """\
## Continuação de workflow ativo (`multi_step_service`)

Quando o historico mostra que um workflow de `multi_step_service` ja esta ativo
e aguardando um campo, trate a nova mensagem do cidadao como resposta para esse
campo. Essa resposta NAO e uma nova intencao vaga.

Antes de responder em texto, chame `multi_step_service` no workflow ativo com o
valor recebido e use o retorno da ferramenta para compor a resposta ao cidadao.

Caso critico: se a etapa pediu CPF e o cidadao disser "continuar sem CPF",
"nao quero me identificar", "prefiro nao informar CPF", "anonimo" ou variacao
equivalente, continue o workflow marcando CPF ausente/recusado (ex.:
`cpf=null`, `identificacao_recusada=true` ou campo equivalente esperado pelo
workflow). Nao responda apenas "vou seguir sem CPF" sem chamar a tool.
"""
