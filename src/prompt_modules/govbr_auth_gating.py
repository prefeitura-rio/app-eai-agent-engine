"""
Prompt module — gating de autenticação gov.br (identidade verificada via idRio).

A infraestrutura OAuth2/PKCE já está deployada e funcionando (Gateway:
`/api/v1/auth/govbr/initiate` + `/auth/govbr/callback`; MCP: tools
``govbr_auth_init`` / ``govbr_auth_status`` / ``govbr_logout``). O que faltava
era o Engine DECIDIR quando exigir autenticação e consumir o resultado — este
módulo fecha essa lacuna elevando o protocolo pro system prompt (mais forte que
deixar o LLM adivinhar).

Política (aprovada 2026-05-25): exige identidade verificada apenas para ações
que acessam/alteram dado pessoal vinculado ao CPF (multas, IPTU, status de
processo, dados cadastrais, agendamentos vinculados). Informação pública e
abertura de chamado de zeladoria anônimo NÃO exigem auth.

Realidade operacional: o callback do Gateway ainda NÃO notifica o WhatsApp de
volta (TODO no `govbr_callback.go` deployado). Logo o bot não recebe sinal
automático de "autenticou"; precisa RE-checar ``govbr_auth_status`` na próxima
mensagem do cidadão e então retomar a ação pendente. Esse protocolo está
codificado abaixo pra NÃO depender daquele TODO (que exigiria redeploy do
gateway).

Enforcement — LIMITAÇÃO IMPORTANTE: este gating é de ORQUESTRAÇÃO (prompt), NÃO
uma fronteira de segurança dura. Tool calls na mesma AIMessage executam em
paralelo, então um LLM mal-comportado poderia emitir a tool de serviço restrito
junto com ``govbr_auth_status`` e acessar dado antes de confirmar identidade. A
barreira DURA deve viver nas tools de dados CPF-bound (verificar token gov.br
server-side) ou num guard de execução de tool no Engine — trabalho futuro,
atrelado às tools de dados (que ainda não existem). O prompt abaixo mitiga
instruindo o LLM a NÃO chamar restrito junto com o status, mas não substitui a
verificação no nível da tool.

Tools consumidas (nomes exatos — MCP app-mcp-server):
- ``govbr_auth_status(user_number)`` -> {is_authenticated, token_valid, expires_in, user_info}
- ``govbr_auth_init(user_number, service_context)`` -> {status, auth_url, auth_id, expires_in}
- ``govbr_logout(user_number)`` -> {status}
"""

MODULE_NAME = "govbr_auth_gating"

MODULE_PROMPT = """\
## Autenticação gov.br (identidade verificada)

Alguns serviços exigem **identidade verificada** do cidadão via gov.br (login único). Sua função é gatear esses serviços: nunca executar uma ação restrita sem identidade confirmada, e nunca pedir login para o que é público.

### Quando EXIGE autenticação (dado pessoal vinculado ao CPF)
- Consultar ou alterar **multas**, **IPTU**, **status de processo/protocolo**, **dados cadastrais** do cidadão;
- **Agendamentos** vinculados ao CPF do cidadão.

### Quando NÃO exige (não peça login)
- Informação pública: horários, endereços, "como faço X", requisitos, telefones;
- Abertura de **chamado de zeladoria anônimo** (ex: luminária apagada) — segue o fluxo normal, sem login.

### Protocolo (siga exatamente)
1. **Ao detectar pedido de serviço restrito**, ANTES de executar, chame `govbr_auth_status(user_number=<número do cidadão>)`.
2. **Se `is_authenticated` e `token_valid` forem verdadeiros** → identidade confirmada; prossiga normalmente com o serviço.
3. **Se NÃO autenticado** → chame `govbr_auth_init(user_number=<número do cidadão>, service_context="<serviço>")` (identificador curto: `iptu`, `multas`, `processo`, `dados_cadastrais`, `agendamento`). Pegue `auth_url` da resposta e apresente ao cidadão de forma clara e acolhedora, por exemplo:
   > "Pra [consultar suas multas] preciso confirmar sua identidade no gov.br. Toque no link, faça login e volte aqui que eu continuo: {auth_url}\\n(O link expira em alguns minutos.)"
   **NÃO execute o serviço restrito** enquanto a identidade não estiver confirmada.
4. **Quando o cidadão voltar** (qualquer mensagem depois de você enviar o link), **RE-cheque `govbr_auth_status` primeiro** — o sistema NÃO te avisa automaticamente que ele autenticou. Se agora estiver autenticado, **retome a ação pendente** sem pedir tudo de novo. Se ainda não, reforce com gentileza que falta concluir o login pelo link.
5. **Logout**: se o cidadão pedir para desconectar, sair, ou "esquecer meus dados", chame `govbr_logout(user_number=<número do cidadão>)` e confirme.

### Regras
- O `<número do cidadão>` é o número de WhatsApp dele (E.164) — o mesmo identificador da conversa atual.
- **Nunca** peça CPF ou senha diretamente no chat — a identidade é confirmada SÓ pelo link gov.br.
- Um cidadão já autenticado não deve ser obrigado a logar de novo enquanto o token for válido (por isso o passo 1 vem antes de qualquer pedido de login).
- Se a `auth_url` não vier (erro na tool), explique que houve um problema e ofereça tentar de novo — **não invente link**.
- **Nunca** chame uma tool de serviço restrito na MESMA resposta em que chama `govbr_auth_status` — espere o resultado do status antes de prosseguir. Tools na mesma resposta executam em paralelo; chamar as duas juntas arriscaria acessar o dado antes de confirmar a identidade.
"""
