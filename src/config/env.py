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
GCS_BUCKET_STAGING = getenv_or_action("GCS_BUCKET_STAGING")

REASONING_ENGINE_ID = getenv_or_action("REASONING_ENGINE_ID")

PG_URI = getenv_or_action("PG_URI", action="ignore")
