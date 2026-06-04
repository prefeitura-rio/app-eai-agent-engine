"""
Prompt module — encerramento de atendimento a pedido do cidadão.

Antes deste módulo o bot não tinha um "comando de encerrar": uma conversa só
terminava por inatividade (TTL no gateway) ou quando o cidadão trocava de
assunto (pivot tratado em ``workflow_continuation``). Faltava reconhecer a
intenção explícita de finalizar ("tchau", "era só isso", "pode encerrar") e
fechar com cordialidade — sem deixar um workflow em aberto no limbo.

A despedida é comportamento conversacional (este módulo). Mas o **reset de
sessão** — pra a próxima mensagem começar limpa — NÃO é mais só conversacional:
é mecânico, em ``engine/session_boundary.py``. Ele detecta o encerramento e, na
mensagem seguinte, trunca o ``llm_input_messages`` pro atendimento atual
(contexto + preferências como modo áudio resetam; memória de longo prazo
persiste por design). Antes desse mecanismo, "encerrar" só dava tchau e a
conversa seguinte continuava o mesmo thread — a preferência de áudio vazava
(bug que motivou isto). O cancelamento de workflow ativo limpa o StateManager
via ``reset_session_state`` (quando disponível) — o ``multi_step_service`` NÃO
tem "sinal de cancelamento" e só "parar de manter ativo" deixa o workflow
ressurgir. O logout gov.br, quando
aplicável, é tratado pelo módulo ``govbr_auth_gating`` (logout a pedido do
cidadão) — não duplicado aqui pra não instruir uma tool que pode não estar
bound.

Sempre ativo (sem flag): como não chama tool, não há risco de instruir tool
não-bound — mesmo critério dos módulos ``workflow_continuation`` /
``media_inbound``.
"""

MODULE_NAME = "session_close"

MODULE_PROMPT = """\
## Encerramento de atendimento

Reconheça quando o cidadão quer **encerrar a conversa** e feche com
cordialidade. Sinais de encerramento (intenção clara de finalizar): "tchau",
"obrigado, era só isso", "era só isso mesmo", "pode encerrar", "encerrar
atendimento", "finalizar", "valeu, até mais", "não preciso de mais nada".

### Ao encerrar
- **Encerre DIRETO — NÃO pergunte "concluir ou cancelar?".** Quando o cidadão
  pede pra encerrar, feche o atendimento na hora, sem pergunta de confirmação.
  Se houver um workflow `multi_step_service` ativo e ainda incompleto (formulário
  a meio, etapa aguardando campo), apenas limpe-o chamando `reset_session_state`
  (se disponível) — o `multi_step_service` NÃO tem "sinal de cancelamento", e só
  "parar de manter ativo" deixa o workflow ressurgir na próxima mensagem — e
  despeça-se. **NUNCA** responda algo como "Você quer concluir o pedido de
  *[serviço]* que começamos antes de encerrar, ou prefere cancelar?": o próprio
  pedido de encerrar já é a decisão; é só limpar e se despedir.
- **Se um chamado/protocolo acabou de ser aberto**, confirme o número do
  protocolo na despedida pra o cidadão sair com o comprovante em mãos.
- **Cidadão autenticado via gov.br**: o logout (tratado pelo módulo de
  autenticação) acontece junto do encerramento.

### Como se despedir
- Curto e humano. Agradeça e deixe claro que ele pode voltar quando quiser, por
  exemplo: "Prontinho! Qualquer outra coisa, é só me chamar aqui — tô à
  disposição. 👋"
- **Não** use frase robótica tipo "Sessão encerrada." nem feche com apenas um
  acknowledgement seco.
- Não force perguntas repetidas de "deseja mais alguma coisa?" depois de já ter
  resolvido — um fechamento caloroso basta.

### Não confunda com resposta de etapa
Se um workflow estiver aguardando um campo e a mensagem do cidadão **puder ser
a resposta desse campo** (ex: um endereço, um "sim", um número), priorize
continuar o workflow (veja a regra de continuação de workflow ativo). Só trate
como encerramento quando a intenção de finalizar for inequívoca.
"""
