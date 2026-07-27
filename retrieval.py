"""
Loads the embedding model once at import time (expensive), and exposes a
retrieve() function used to ground grading feedback in the actual book text.

IMPORTANT: queries must be embedded with the SAME model used when the
`ml_kb` collection was built (all-MiniLM-L6-v2). Never use Chroma's
query_texts= here — that falls back to a different default embedding model.
"""

import chromadb
from sentence_transformers import SentenceTransformer
from config import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME, EMBEDDING_MODEL_NAME

_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
_collection = _client.get_collection(CHROMA_COLLECTION_NAME)


def retrieve(query: str, n_results: int = 3):
    """Returns a list of {text, source_book, page} dicts most relevant to query."""
    query_vec = _model.encode([query], normalize_embeddings=True).tolist()
    results = _collection.query(query_embeddings=query_vec, n_results=n_results)

    hits = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    for doc, meta in zip(docs, metas):
        hits.append({
            "text": doc,
            "source_book": meta.get("source_book"),
            "page": meta.get("page"),
        })
    return hits