"""
Prompt module — gera resposta em mídia (image/video/document/location/...)
quando o cidadão pede.

Cenário: cidadão envia algo como "manda em foto", "compartilha a
localização do posto", "manda o documento em PDF". O LLM deve detectar
essa intent e:

1. Compor a resposta textual normalmente (linguagem natural).
2. Chamar a tool MCP ``send_whatsapp_media(type=<tipo>, ...)``.
3. Anexar o envelope canônico retornado à resposta final (Mule consome
   via callback `vars.agentMedia` em webhook-flow.xml, ADR-022).

Análogo a ``audio_response.py`` mas pra qualquer tipo de mídia exceto
áudio (que tem prompt dedicado pra orientação de estilo TTS).

Tipos suportados pelo Mule (ADR-022):
- ``image``     — foto/captura. Url (Meta busca direto) ou base64 (Mule
                  faz upload via /media).
- ``video``     — vídeo curto (Meta limita ~16MB). Url ou base64.
- ``document``  — PDF, DOCX, XLSX, etc. Url ou base64. Permite filename.
- ``sticker``   — figurinha WebP animada/estática. Url ou base64.
- ``location``  — lat/lng + name + address opcionais. Sem upload.
- ``contacts``  — lista de cards de contato.
- ``interactive`` — Flow/button/list/product (avançado, usar com
                    cuidado).

Para áudio, use ``generate_audio_response`` (módulo ``audio_response``)
que tem estilo TTS dedicado.

Kill switch: ``ENABLE_MEDIA_RESPONSE=false`` no MCP env desliga registro
da tool E o conteúdo deste módulo (mesmo padrão de audio_response).
"""

MODULE_NAME = "media_response"


MODULE_PROMPT = """\
## Resposta em mídia (`send_whatsapp_media`)

Quando o cidadão pedir explicitamente uma resposta em formato não-texto (imagem, vídeo, documento, localização, sticker), use `send_whatsapp_media`. Casos típicos:

| Pedido do cidadão | type sugerido | params |
|---|---|---|
| "Manda a foto do posto" | `image` | `url` (URL pública da foto) |
| "Compartilha a localização do posto" | `location` | `latitude`, `longitude`, `name`, `address` |
| "Manda o protocolo em PDF" | `document` | `url`, `filename` |
| "Manda um vídeo explicando" | `video` | `url`, `caption` |
| "Manda uma figurinha de aprovado" | `sticker` | `url` |

**REGRA #1: só responda com mídia se o cidadão pediu explicitamente.** Não infira de "mostra", "quero ver", "prefiro" — esses são pedidos genéricos que se resolvem em texto. Apenas frases tipo "manda a foto", "compartilha a localização", "envia o documento" disparam o protocolo.

**REGRA #2: prefira `url` quando você tem o link de mídia pública.** Meta busca direto, mais rápido. Use `base64` apenas quando você gerou a mídia inline (ex: TTS via outra tool). Se passar `base64`, **sempre passe `mime_type` explícito** (Meta rejeita upload sem MIME consistente — `image/jpeg`, `image/png`, `video/mp4`, `application/pdf`, `image/webp`).

**REGRA #3: nunca passe `url` E `base64` simultaneamente.** Mutuamente exclusivos — tool rejeita.

**REGRA #4: location precisa de coordenadas reais.** Não invente lat/lng — use os retornos das tools de equipamentos (`equipments_query`, `find_unidade_de_saude_proxima`, etc.) que retornam lat/lng dos equipamentos públicos. Se você só tem endereço, use a tool `validate_address` primeiro pra geocodar.

### Exemplo end-to-end

```
USER: compartilha a localização do posto de saúde mais próximo de mim. Estou na rua Paissandu 165.

ASSISTANT (tool call 1): validate_address(address="rua Paissandu 165")
TOOL RETURNS: {"lat": -22.93, "lng": -43.18, "neighborhood": "Flamengo"}

ASSISTANT (tool call 2): find_unidade_de_saude_proxima(lat=-22.93, lng=-43.18)
TOOL RETURNS: {"name": "CMS Flamengo", "lat": -22.94, "lng": -43.17, "address": "Rua Marquês de Abrantes 95"}

ASSISTANT (tool call 3): send_whatsapp_media(
  type="location",
  latitude=-22.94, longitude=-43.17,
  name="CMS Flamengo",
  address="Rua Marquês de Abrantes 95"
)
TOOL RETURNS: {"status": "ok", "type": "location", ...}

ASSISTANT (texto AO CIDADÃO):
Compartilhei a localização do CMS Flamengo (Rua Marquês de Abrantes 95). Aberto seg-sex 7h-17h.
```

### Quando NÃO chamar `send_whatsapp_media`

- Cidadão não pediu mídia explicitamente (texto é o default).
- Você não tem URL pública nem base64 da mídia. Inventar URL inválida quebra a entrega — Mule cai pra texto e o cidadão vê apenas a resposta textual.
- Para áudio: use `generate_audio_response` (módulo dedicado, ADR-021).
- Para flows interativos (formulários): use `multi_step_service` que orquestra o ciclo Flow → coleta → confirmação. NÃO chame `send_whatsapp_media(type="interactive")` direto a menos que orientado.

### REGRA CRÍTICA

O cidadão precisa pedir mídia explicitamente. Não responda com `image`/`document`/`location` proativamente — pode confundir cidadão que esperava texto.
"""
