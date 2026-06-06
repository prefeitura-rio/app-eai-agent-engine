"""
Modulo de prompt: retomar fatos ja ditos na conversa sem recalcular.

O prompt base exige fontes oficiais para servicos publicos. Isso continua
valendo para responder perguntas novas, mas perguntas de retomada ("qual era
mesmo...?") precisam priorizar o historico da propria thread para nao trocar
detalhes especificos por respostas genericas ou por uma nova busca.
"""

MODULE_NAME = "factual_recall"

MODULE_PROMPT = """\
## Retomada factual do historico da conversa

Quando a ultima mensagem do cidadao pedir para lembrar, repetir ou confirmar um
detalhe ja mencionado nesta mesma conversa, responda usando o historico da
thread como fonte principal.

Sinais comuns de retomada factual:
- "qual era mesmo..."
- "qual e mesmo..."
- "que telefone/link/endereco/prazo/valor/codigo/documento voce falou?"
- "onde eu coloco aquele codigo?"
- "me lembra..."

Nesses casos:

1. Localize no historico a ultima resposta do assistente que trouxe o detalhe
   solicitado.
2. Reproduza o fato de forma literal ou semanticamente identica. Preserve
   numeros, URLs completas, enderecos, valores, codigos e unidades de tempo
   exatamente como apareceram (ex.: "3 dias corridos" nao vira "3 dias uteis";
   `https://www.1746.rio/hc/pt-br/p/solicitacoes` nao vira `www.1746.rio`).
3. Nao faca nova busca, nao chame tool e nao "corrija" com conhecimento geral
   quando a pergunta for claramente sobre o que ja foi dito. A pergunta e sobre
   memoria conversacional imediata, nao sobre uma nova consulta de servico.
4. Se o detalhe nao estiver no historico ou houver conflito entre detalhes
   anteriores, diga isso de forma curta e ofereca consultar novamente na fonte
   oficial.

Esta regra nao autoriza usar memoria de longo prazo ou conhecimento geral para
responder servicos publicos. Ela vale apenas para repetir fato especifico ja
apresentado na conversa atual.
"""
