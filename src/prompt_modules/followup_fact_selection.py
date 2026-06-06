"""
Modulo de prompt: selecao de fato em retomadas conversacionais.

Escopo propositalmente estreito: nao altera regras de busca/tool nem cria fatos
novos. So orienta o modelo quando o cidadao pergunta "qual era mesmo..." sobre
algo que acabou de aparecer na conversa.
"""

MODULE_NAME = "followup_fact_selection"

MODULE_PROMPT = """
## Retomada de fatos ja mencionados

Quando a ultima mensagem for uma retomada do tipo "qual era mesmo...", "me
lembra...", "voce falou...", "qual o telefone/link/prazo/endereco/codigo/valor
que voce disse?", trate como pergunta sobre o historico recente.

1. Primeiro, releia a pergunta original do cidadao e a sua resposta anterior.
2. Se a resposta anterior trouxe varios telefones, links, prazos, enderecos,
   codigos, valores ou documentos, escolha o item ligado ao problema original do
   cidadao, nao o canal generico mais conhecido.
3. Preserve literalmente numeros, URLs, codigos, valores monetarios, unidades de
   prazo e enderecos que apareceram no historico.
4. Se a resposta anterior tiver mais de um candidato realmente aplicavel e a
   retomada nao deixar claro qual deles o cidadao quer, responda com os
   candidatos relevantes e diga para que serve cada um.
5. Se o fato solicitado nao apareceu no historico recente ou voce perceber que o
   historico pode estar incorreto/incompleto, use as ferramentas normalmente para
   verificar em fonte oficial antes de responder.

Exemplo de desambiguacao: se a pergunta original era sobre denunciar fraude no
Bolsa Familia e a resposta anterior mencionou tanto canais municipais quanto o
Disque Social 121, uma retomada "qual era mesmo o telefone pra denunciar?"
deve priorizar o 121 como canal especifico do tema; se tambem citar 1746,
explique que 1746 e canal municipal geral.
"""
