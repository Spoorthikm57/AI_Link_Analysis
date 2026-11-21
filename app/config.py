import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_TIMEOUT_SECONDS = 45.0
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
TAVILY_TIMEOUT_SECONDS = 15.0

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing. Set it in the .env file or environment.")

if not GROQ_MODEL:
    GROQ_MODEL = "openai/gpt-oss-120b"