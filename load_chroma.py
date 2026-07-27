"""
Load chunks_final.parquet + embeddings_final.npy into the `kb_store`
Chroma collection. This parquet is expected to be the FULL corpus across
all domains (including ml) -- so this does a clean delete + rebuild rather
than an incremental append.

Usage:
    pip install chromadb pandas numpy --break-system-packages
    python load_chroma.py
"""

import pandas as pd
import numpy as np
import chromadb

CHUNKS_PATH = "chunks_final.parquet"
EMB_PATH = "embeddings_final.npy"
PERSIST_DIR = "./chroma_db"
COLLECTION_NAME = "kb_store"
BATCH_SIZE = 1000

def main():
    df = pd.read_parquet(CHUNKS_PATH)
    embeddings = np.load(EMB_PATH)

    assert len(df) == len(embeddings), (
        f"Row count mismatch: {len(df)} chunks vs {len(embeddings)} embeddings"
    )
    assert "domain" in df.columns, (
        "No 'domain' column found in parquet -- are you using the V1 notebook output? "
        "Use books_embedding_v2.ipynb, which tags each chunk with its domain."
    )

    client = chromadb.PersistentClient(path=PERSIST_DIR)

    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing '{COLLECTION_NAME}' -- rebuilding from full corpus.")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    ids = df["chunk_id"].astype(str).tolist()
    documents = df["text"].tolist()
    metadatas = df[["domain", "source_book", "page"]].to_dict("records")
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
    print("\nChunks per domain:")
    print(df["domain"].value_counts())

    # sanity check: embed a query with the SAME model used at ingestion,
    # never use query_texts= here (see retrieval.py docstring for why)
    from sentence_transformers import SentenceTransformer
    query_model = SentenceTransformer("all-MiniLM-L6-v2")
    query_vec = query_model.encode(["bias variance tradeoff"], normalize_embeddings=True).tolist()

    test = collection.query(query_embeddings=query_vec, n_results=3, where={"domain": "ml"})
    print("\nSanity check retrieval for 'bias variance tradeoff' (domain=ml):")
    for doc, meta in zip(test["documents"][0], test["metadatas"][0]):
        print(f"  [{meta['domain']}/{meta['source_book']} p.{meta['page']}] {doc[:100]}...")

if __name__ == "__main__":
    main()