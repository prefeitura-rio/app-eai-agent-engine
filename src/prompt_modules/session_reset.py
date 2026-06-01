"""
Prompt module — limpeza de estado de workflow ao encerrar o atendimento.

Complementa o módulo ``session_close`` (que faz a despedida conversacional) e o
reset comportamental de ``engine/session_boundary.py`` (que trunca o
``llm_input_messages`` na mensagem seguinte). Faltava a peça do **estado de
workflow multi-step no MCP**: o ``StateManager`` (luminária, poda, IPTU…) não era
limpo no encerramento, então um workflow incompleto sobrevivia ao "tchau" e era
retomado na próxima mensagem (loop relatado em teste de campo). Este módulo
instrui o LLM a chamar a tool MCP ``reset_session_state`` quando confirma o
encerramento, fechando esse gap ponta a ponta.

Por que um módulo SEPARADO do ``session_close`` (e não uma instrução embutida):
``session_close`` é **sempre ativo e deliberadamente sem-tool** ("não chama tool,
não há risco de instruir tool não-bound"). Instruir ``reset_session_state`` lá
quebraria esse invariante quando a tool estiver fora. Aqui o gating segue o MESMO
padrão de ``audio_response`` / ``media_response`` / ``interactive_response``: o
módulo só entra em ``ENABLED_MODULES`` quando ``reset_session_state`` NÃO está em
``MCP_EXCLUDED_TOOLS`` e o kill-switch ``ENABLE_SESSION_RESET`` não é ``false``.

Os dois sinais têm semânticas distintas (ver comentário em ``__init__.py``):
excluir a tool (``MCP_EXCLUDED_TOOLS``) a desbinda E remove o módulo; o
kill-switch sozinho remove só a INSTRUÇÃO do prompt (a tool, se bound, segue
chamável — "soft off"). Em nenhum caso o LLM é instruído a chamar tool ausente, e
a despedida (``session_close``) continua funcionando mesmo sem a instrução.

Segurança: o alvo do reset é SEMPRE o telefone autenticado do thread. O
``user_id`` que o LLM passa é sobrescrito pelo engine — ver
``_inject_thread_id_in_user_id_params`` em ``<repo-root>/engine/agent.py`` (path
relativo à RAIZ do repo, não a ``src/``; o hook é genérico para todas as tools e
os params ``user_id``/``user_number``). O modelo não controla o alvo — mesma
garantia já usada pelo ``multi_step_service``.

Idempotência/concorrência (Flow tardio, tool em voo, disparo duplo) é endereçada
na Fase 2 do redesenho (``session_epoch``). Este módulo é a Fase 1: fecha o
sintoma sem depender do epoch.
"""

MODULE_NAME = "session_reset"

MODULE_PROMPT = """\
## Limpeza de estado ao encerrar (reset_session_state)

Quando você **confirmar o encerramento do atendimento** (intenção clara de
finalizar reconhecida na seção "Encerramento de atendimento", e já resolvida a
decisão de concluir ou cancelar qualquer workflow ativo), chame a tool
`reset_session_state` para limpar o estado de workflow que tenha ficado em aberto
(formulário a meio, etapa aguardando campo). Sem isso, um workflow incompleto
sobrevive ao encerramento e é retomado por engano na próxima mensagem do cidadão.

- Passe `user_id` como nas demais tools — o sistema o substitui pelo telefone
  autenticado da conversa (você não escolhe o alvo do reset).
- Chame **uma única vez**, no momento do encerramento. Não chame em respostas
  comuns nem no meio de um atendimento em andamento.
- O resultado é **interno**: NÃO mencione "limpei seu estado" nem o status da
  tool ao cidadão. Apenas siga com a despedida calorosa da seção de encerramento.
- Se o cidadão pediu pra **concluir** o workflow ativo (não cancelar), NÃO chame
  esta tool ainda — retome o workflow normalmente; o reset só vale quando a
  conversa realmente termina.
"""
