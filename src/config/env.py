import os

from src.utils.infisical import getenv_or_action

# if file .env exists, load it
if os.path.exists("src/config/.env"):
    import dotenv

    dotenv.load_dotenv(dotenv_path="src/config/.env")

MCP_SERVER_URL = getenv_or_action("MCP_SERVER_URL")
MCP_SERVER_PUBLIC_URL = getenv_or_action("MCP_SERVER_PUBLIC_URL")
MCP_API_TOKEN = getenv_or_action("MCP_API_TOKEN")

GEMINI_API_KEY = getenv_or_action("GEMINI_API_KEY")
PROJECT_ID = getenv_or_action("PROJECT_ID")
PROJECT_NUMBER = getenv_or_action("PROJECT_NUMBER")
LOCATION = getenv_or_action("LOCATION")
INSTANCE = getenv_or_action("INSTANCE")
DATABASE_HOST = getenv_or_action("DATABASE_HOST", default="localhost")
DATABASE_PORT = getenv_or_action("DATABASE_PORT", default="5432")
DATABASE = getenv_or_action("DATABASE")
DATABASE_USER = getenv_or_action("DATABASE_USER")
DATABASE_PASSWORD = getenv_or_action("DATABASE_PASSWORD")
GCS_BUCKET = getenv_or_action("GCS_BUCKET")

REASONING_ENGINE_ID = getenv_or_action("REASONING_ENGINE_ID")


EAI_AGENT_URL = getenv_or_action("EAI_AGENT_URL")
EAI_AGENT_TOKEN = getenv_or_action("EAI_AGENT_TOKEN")

EAI_GATEWAY_API_URL = getenv_or_action("EAI_GATEWAY_API_URL", default="")
EAI_GATEWAY_API_TOKEN = getenv_or_action("EAI_GATEWAY_API_TOKEN", default="")

MCP_EXCLUDED_TOOLS = (
    getenv_or_action("MCP_EXCLUDED_TOOLS").split(",")
    if getenv_or_action("MCP_EXCLUDED_TOOLS", default="")
    else []
)

# Kill switch coarse pro TTS — desliga prompt module `audio_response` no
# engine + tool `generate_audio_response` no MCP server. Default-on:
# valor vazio/ausente OU qualquer != "false" ⇒ habilitado. Tem que
# espelhar o que o MCP server lê.
ENABLE_TTS_ADDENDUM = getenv_or_action("ENABLE_TTS_ADDENDUM", default="true")
# Kill switch pro media response generico (ADR-022) — desliga prompt
# module `media_response` no engine + tool `send_whatsapp_media` no MCP
# server. Mesma semantica do ENABLE_TTS_ADDENDUM.
ENABLE_MEDIA_RESPONSE = getenv_or_action("ENABLE_MEDIA_RESPONSE", default="true")
# Kill switch pro interactive response (ADR-024 + ADR-022) — desliga
# prompt module `interactive_response` + tools send_whatsapp_flow/
# _buttons/_list no MCP server.
ENABLE_INTERACTIVE_RESPONSE = getenv_or_action(
    "ENABLE_INTERACTIVE_RESPONSE", default="true"
)

# === LLM tuning (latency vs quality trade-offs) ===
# THINKING_BUDGET: tokens maximos que o Gemini 2.5 Flash pode gastar em
# chain-of-thought antes de responder. Default CAPADO em 1024 (era -1/unbounded):
# o prompt deste bot e' fortemente escaffoldado (regras explicitas, Flow-first
# deterministico), entao 1024 tokens de raciocinio sao amplos pras decisoes de
# roteamento/tool e cortam ~5-15s/turn de latencia (e custo). E' so um teto — o
# modelo usa MENOS quando nao precisa. Tunavel via env THINKING_BUDGET, mas
# EFETIVO SO NO PROXIMO DEPLOY: o valor e' resolvido aqui em deploy-time e baked
# no agent via cloudpickle (agent.py le do atributo, NAO do env em runtime —
# mesma pegadinha do OTEL_SDK_DISABLED). O deploy loga o valor efetivo; medir p95
# e qualidade no Signoz pos-deploy. Se query complexa/ambigua regredir, suba pra
# 2048-4096 e re-deploye. 0 desliga, -1 volta ao unbounded.
THINKING_BUDGET = int(getenv_or_action("THINKING_BUDGET", default="1024") or "1024")
# INCLUDE_THOUGHTS: se o LLM retorna o texto de chain-of-thought no
# response (alem da resposta final). Default true mantem traces visiveis
# em logs/OTel pra debug. Setar false reduz payload de saida mas nao
# afeta latencia de inferencia significativamente.
INCLUDE_THOUGHTS = (
    (getenv_or_action("INCLUDE_THOUGHTS", default="true") or "true").lower() != "false"
)
# LLM_TEMPERATURE: criatividade do LLM. Default 0.7 (atual). Valores
# menores (e.g. 0.3) sao mais deterministicos + ligeiramente mais rapidos.
LLM_TEMPERATURE = float(
    getenv_or_action("LLM_TEMPERATURE", default="0.7") or "0.7"
)

# OTEL opcional (default ""): o export de traces fica DESLIGADO sem endpoint
# (ver agent._set_up_opentelemetry). Não obrigar a var presente no deploy — o
# Vertex engine roda com OTEL off de propósito (coletor inalcançável daqui).
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = getenv_or_action(
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", default=""
)
OTEL_EXPORTER_OTLP_TRACES_HEADERS = getenv_or_action(
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS", default=""
)

# Short-term memory limits (kept as strings for deployment)
SHORT_MEMORY_TIME_LIMIT = getenv_or_action(
    "SHORT_MEMORY_TIME_LIMIT", default="30"
)  # in days
SHORT_MEMORY_TOKEN_LIMIT = getenv_or_action(
    "SHORT_MEMORY_TOKEN_LIMIT", default="50000"
)  # in tokens

# VPC Network attachment for accessing MCP server in private network
NETWORK_ATTACHMENT = getenv_or_action("NETWORK_ATTACHMENT", default="")

# Error Interceptor configuration (optional)
ERROR_INTERCEPTOR_URL = getenv_or_action("ERROR_INTERCEPTOR_URL", default="")
ERROR_INTERCEPTOR_TOKEN = getenv_or_action("ERROR_INTERCEPTOR_TOKEN", default="")

# Namespace configuration for checkpoints
NS_MAX_BYTES = (getenv_or_action("_NS_MAX_BYTES", default="2500"))
NS_HASH_PREFIX = getenv_or_action("_NS_HASH_PREFIX", default="hash:")
NS_VERSION_MAX_BYTES = getenv_or_action("_NS_VERSION_MAX_BYTES", default="2000")
