"""Settings, read from environment variables or a .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# MySQL: mysql+pymysql://user:password@localhost:3306/interview_prep
# Not set: a local SQLite file is used instead.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'interview_prep.db'}")

# Optional LLM, through any OpenAI-compatible API (OpenAI, Claude, Groq, local Ollama).
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or None

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
