from src.utils.infisical import getenv_or_action
import os

# if file .env exists, load it
if os.path.exists("./src/config/.env"):
    import dotenv

    dotenv.load_dotenv(dotenv_path="src/config/.env")

MPC_SERVER_URL = getenv_or_action("MPC_SERVER_URL")
MPC_API_TOKEN = getenv_or_action("MPC_API_TOKEN")

GEMINI_API_KEY = getenv_or_action("GEMINI_API_KEY")
PROJECT_ID = getenv_or_action("PROJECT_ID")
PROJECT_NUMBER = getenv_or_action("PROJECT_NUMBER")
LOCATION = getenv_or_action("LOCATION")
INSTANCE = getenv_or_action("INSTANCE")
DATABASE = getenv_or_action("DATABASE")
DATABASE_USER = getenv_or_action("DATABASE_USER")
DATABASE_PASSWORD = getenv_or_action("DATABASE_PASSWORD")
GCS_BUCKET = getenv_or_action("GCS_BUCKET")

REASONING_ENGINE_ID = getenv_or_action("REASONING_ENGINE_ID")


EAI_AGENT_URL = getenv_or_action("EAI_AGENT_URL")
EAI_AGENT_TOKEN = getenv_or_action("EAI_AGENT_TOKEN")

MCP_EXCLUDED_TOOLS = (
    getenv_or_action("MCP_EXCLUDED_TOOLS").split(",")
    if getenv_or_action("MCP_EXCLUDED_TOOLS", default="")
    else []
)

OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = getenv_or_action(
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
)
OTEL_EXPORTER_OTLP_TRACES_HEADERS = getenv_or_action(
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS"
)

# IPTU API Configuration
IPTU_API_URL = getenv_or_action("IPTU_API_URL")
IPTU_API_TOKEN = getenv_or_action("IPTU_API_TOKEN")

SHORT_API_URL = getenv_or_action("SHORT_API_URL")
SHORT_API_TOKEN = getenv_or_action("SHORT_API_TOKEN")

WA_IPTU_URL = getenv_or_action("WA_IPTU_URL")
WA_IPTU_TOKEN = getenv_or_action("WA_IPTU_TOKEN")
WA_IPTU_PUBLIC_KEY = getenv_or_action("WA_IPTU_PUBLIC_KEY")

WORKFLOWS_GCP_SERVICE_ACCOUNT = getenv_or_action("WORKFLOWS_GCP_SERVICE_ACCOUNT")
WORKFLOWS_GCS_BUCKET = getenv_or_action("WORKFLOWS_GCS_BUCKET")


DIVIDA_ATIVA_API_URL = getenv_or_action("DIVIDA_ATIVA_API_URL")
DIVIDA_ATIVA_ACCESS_KEY = getenv_or_action("DIVIDA_ATIVA_ACCESS_KEY")
REDIS_URL = getenv_or_action("REDIS_URL")
REDIS_TTL_SECONDS = int(getenv_or_action("REDIS_TTL_SECONDS"))

PROXY_URL = getenv_or_action("PROXY_URL")
# Short-term memory limits

CHATBOT_INTEGRATIONS_URL = getenv_or_action("CHATBOT_INTEGRATIONS_URL")
CHATBOT_INTEGRATIONS_KEY = getenv_or_action("CHATBOT_INTEGRATIONS_KEY")
# SGRC Configuration
SGRC_URL = getenv_or_action("SGRC_URL")
SGRC_AUTHORIZATION_HEADER = getenv_or_action("SGRC_AUTHORIZATION_HEADER")
SGRC_BODY_TOKEN = getenv_or_action("SGRC_BODY_TOKEN")
GMAPS_API_TOKEN = getenv_or_action("GMAPS_API_TOKEN")
DATA_DIR = getenv_or_action("DATA_DIR")
# Short-term memory limits (kept as strings for deployment)
SHORT_MEMORY_TIME_LIMIT = getenv_or_action(
    "SHORT_MEMORY_TIME_LIMIT", default="30"
)  # in days
SHORT_MEMORY_TOKEN_LIMIT = getenv_or_action(
    "SHORT_MEMORY_TOKEN_LIMIT", default="50000"
)  # in tokens
