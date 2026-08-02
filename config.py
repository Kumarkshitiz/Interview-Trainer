import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not found — check your .env file is in this folder.")

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# V3: single-user auth. One shared secret gates both the Streamlit UI and
# the FastAPI backend (LAN-reachable, so this isn't optional even for a
# single user). V4 swaps this for a real `users` table + per-user check
# without touching how the frontend/backend talk to each other.
APP_SECRET = os.environ.get("APP_SECRET")
if not APP_SECRET:
    raise RuntimeError("APP_SECRET not found — add APP_SECRET=<your password> to .env.")

DB_PATH = os.environ.get("DB_PATH", "trainer.db")
CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION_NAME", "kb_store")  # 'kb' rejected: Chroma needs 3+ chars
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# score >= this is counted as "correct" for topic_stats accuracy tracking
CORRECT_THRESHOLD = 4  # rubric is 1-5

# V2: single source of truth for valid domain strings. Every module that
# takes a `domain` param should validate against this instead of trusting
# a raw string -- one place to add a domain in V3+, not scattered edits.
DOMAINS = ["ml", "dl", "genai", "bigdata", "dbms", "dsa", "python"]

# V4: attempts get a real user_id column even though auth is single-user
# for now (V3). "single_user" is a placeholder constant -- when real
# multi-user accounts arrive, this becomes the authenticated user's id
# instead, and nothing else about the attempts schema needs to change.
DEFAULT_USER_ID = "single_user"

# human-readable labels for prompt templating (grading.py uses these to tell
# Groq what kind of interview question it's grading)
DOMAIN_LABELS = {
    "ml": "Machine Learning",
    "dl": "Deep Learning",
    "genai": "Generative AI / LLMs",
    "bigdata": "Big Data / Data Engineering",
    "dbms": "Databases / SQL",
    "dsa": "Data Structures & Algorithms",
    "python": "Python",
}

def validate_domain(domain: str) -> str:
    if domain not in DOMAINS:
        raise ValueError(f"Unknown domain '{domain}'. Must be one of: {DOMAINS}")
    return domain

# V20: local Whisper for audio-to-text. "base" is a reasonable CPU speed/
# accuracy tradeoff -- "small" is more accurate but noticeably slower on CPU.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")