"""
Prompt module — interpretação de emojis na ENTRADA do cidadão.

Emojis enviados pelo cidadão (dentro de um texto ou sozinhos) chegam crus ao
modelo — não há strip/normalização no caminho gateway→engine. O Gemini em geral
entende emoji, mas o comportamento não era especificado: faltava instrução pra
tratar emojis comuns como SINAIS de entrada (confirmação, negação, intenção de
localização, escolha de opção) de forma consistente.

Escopo: SÓ interpretação de emoji na entrada. O uso de emoji na SAÍDA do bot é
regido pelo prompt base / outros módulos (ex: ``audio_response`` evita emoji em
TTS) — não é tocado aqui.

Conservador por design: interpreta no CONTEXTO do último turno do bot, não trata
emoji decorativo como comando, e manda perguntar quando o sentido é ambíguo — pra
não sobre-interpretar num canal oficial da Prefeitura.

Reações de emoji do WhatsApp (long-press → reagir a uma mensagem) são um caso
SEPARADO: hoje a reação não chega ao engine (o gateway rejeita o
``message_type=reaction``). Cobrir isso exige mudança em Mule + gateway, fora
deste módulo de prompt.

Sempre ativo (sem flag): não instrui a chamar nenhuma tool, então não há risco de
tool não-bound — mesmo critério de ``workflow_continuation`` / ``session_close``.
"""

MODULE_NAME = "emoji_input"

MODULE_PROMPT = """\
## Interpretação de emojis enviados pelo cidadão (entrada)

O cidadão pode responder com emojis — sozinhos ou dentro de uma frase. **Um emoji
é uma mensagem real, não ruído: interprete-o no contexto do seu último turno**,
como faria com texto.

### Sinais comuns (sempre lendo pelo contexto)
- 👍 👌 ✅ 🆗 🙏 — **confirmação / "sim"**, quando vêm como resposta a uma
  pergunta de sim/não ou a um pedido de confirmação (ex: você perguntou "confirma
  o endereço?" e o cidadão responde "👍" → trate como "sim" e siga o fluxo).
- 👎 ❌ 🚫 — **negação / "não"**, no mesmo contexto.
- 📍 🗺️ — sinal de **localização**, mas **só** quando o seu último turno pediu ou
  ofereceu endereço/localização (ex: você perguntou "qual o endereço?"). Fora desse
  contexto, trate como decorativo — não ofereça "me manda sua localização" por
  causa de um emoji solto.
- 1️⃣ 2️⃣ 3️⃣ (números em emoji) — **escolha da opção** correspondente, quando você
  ofereceu uma lista numerada.
- 💡 🔦 — pista de **iluminação pública / luminária** (trate como um relato desse
  tema e siga o fluxo normal de luminária).

### Regras
- **Não ignore** um emoji isolado — ele responde ao seu último turno; aja sobre
  ele em vez de pedir "manda em texto".
- **Emoji decorativo dentro de uma frase NÃO é comando.** "Resolvido, obrigado 😊"
  é um agradecimento; "minha rua tá escura 😩" é um relato, não um comando de
  localização. Use o texto como sinal principal e o emoji como reforço de tom.
- **Quando o sentido for genuinamente ambíguo** (ex: um emoji solto que não
  responde claramente a nada), **faça uma pergunta curta** em vez de adivinhar
  ("Desculpa, não entendi bem — você quer confirmar ou prefere mudar algo?").
- Isto vale pra **entrada**; não muda como você usa (ou evita) emoji nas suas
  próprias respostas.
"""
