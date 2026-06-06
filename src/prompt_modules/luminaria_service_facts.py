"""
Modulo de prompt: fatos oficiais do servico de reparo de luminaria.

Escopo propositalmente estreito: ancora somente prazos de iluminacao publica
usados em retomadas e perguntas informacionais durante o fluxo de luminaria.
"""

MODULE_NAME = "luminaria_service_facts"

MODULE_PROMPT = """
## Fatos oficiais — reparo de luminaria

Use estes fatos quando o contexto recente for reparo de luminaria/iluminacao
publica, inclusive durante o WhatsApp Flow ou antes do cidadao enviar endereco.
Eles tambem valem para retomadas como "qual e o prazo mesmo?", "qual o prazo de
atendimento?" ou "quanto tempo leva?".

1. Reparo de luminaria comum — luminaria apagada, piscando, acesa de dia,
   pendurada, danificada, fraca, com ruido ou grupo de luminarias com esses
   defeitos: o prazo oficial e **ate 3 dias corridos**.
2. Reparo de cabo/fios de iluminacao publica — fios caidos, pendurados,
   desnivelados, frouxos, expostos, faiscando, queimando ou furto/roubo de fios:
   a retirada de risco e imediata quando houver risco, e o reparo/atendimento
   tem prazo oficial de **ate 4 dias corridos**.
3. Nunca troque esses prazos por "dias uteis". Se precisar mencionar a unidade,
   diga sempre "dias corridos".
4. Para perguntas diretas de prazo dentro desse contexto, responda com o prazo
   acima diretamente; nao chame google_search apenas para confirmar esse fato.
5. Se a mensagem indicar falta de energia em casas/predios ou semaforo apagado,
   explique que nao e reparo de luminaria da RIOLUZ e oriente a Light pelo
   0800 0210196, mantendo o fluxo de luminaria apenas se o problema for de
   iluminacao publica.
"""
