import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not found — check your .env file is in this folder.")

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

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

def validate_domain(domain: str) -> str:
    if domain not in DOMAINS:
        raise ValueError(f"Unknown domain '{domain}'. Must be one of: {DOMAINS}")
    return domain