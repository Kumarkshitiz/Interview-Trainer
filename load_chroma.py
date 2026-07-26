"""
Load chunks_final.parquet + embeddings_final.npy into a local persistent
Chroma collection called `ml`.

Usage:
    pip install chromadb pandas numpy --break-system-packages
    python load_chroma.py
"""

import pandas as pd
import numpy as np
import chromadb

CHUNKS_PATH = "chunks_final.parquet"      # <- put next to this script, or edit path
EMB_PATH = "embeddings_final.npy"          # <- put next to this script, or edit path
PERSIST_DIR = "./chroma_db"                # local on-disk store, reused across runs
COLLECTION_NAME = "ml_kb"
BATCH_SIZE = 1000                          # chroma add() batches for large corpora

def main():
    df = pd.read_parquet(CHUNKS_PATH)
    embeddings = np.load(EMB_PATH)

    assert len(df) == len(embeddings), (
        f"Row count mismatch: {len(df)} chunks vs {len(embeddings)} embeddings"
    )

    client = chromadb.PersistentClient(path=PERSIST_DIR)

    # Fresh start if collection already exists (re-running is idempotent)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}  # embeddings were normalized, cosine is correct
    )

    ids = df["chunk_id"].astype(str).tolist()
    documents = df["text"].tolist()
    metadatas = df[["source_book", "page"]].to_dict("records")
    vectors = embeddings.tolist()

    for start in range(0, len(ids), BATCH_SIZE):
        end = start + BATCH_SIZE
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
            embeddings=vectors[start:end],
        )
        print(f"added {min(end, len(ids))}/{len(ids)}")

    print(f"\nDone. Collection '{COLLECTION_NAME}' has {collection.count()} chunks.")
    print(f"Persisted at: {PERSIST_DIR}")

    # sanity check: quick retrieval test
    # NOTE: must embed the query with the SAME model used to build the stored
    # vectors (all-MiniLM-L6-v2). Using query_texts here would let Chroma fall
    # back to its own default embedding function (a different model), which
    # both requires an extra download and would silently degrade retrieval quality.
    from sentence_transformers import SentenceTransformer
    query_model = SentenceTransformer("all-MiniLM-L6-v2")
    query_vec = query_model.encode(["bias variance tradeoff"], normalize_embeddings=True).tolist()

    test = collection.query(query_embeddings=query_vec, n_results=3)
    print("\nSanity check retrieval for 'bias variance tradeoff':")
    for doc, meta in zip(test["documents"][0], test["metadatas"][0]):
        print(f"  [{meta['source_book']} p.{meta['page']}] {doc[:100]}...")

if __name__ == "__main__":
    main()