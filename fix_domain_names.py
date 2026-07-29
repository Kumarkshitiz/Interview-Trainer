"""
Fixes domain metadata values in the existing `kb_store` collection to match
the canonical names in config.DOMAINS, without re-embedding anything.

Your folder names became domain values literally (e.g. 'ml_pdfs',
'big_data_pdfs'), which don't match what retrieval.py/config.py expect
('ml', 'bigdata'). This remaps them in place.

Fetches and updates in paginated batches -- a single get() across all
~38k chunks hits SQLite's bound-variable limit under the hood.

Usage:
    python fix_domain_names.py
"""

import chromadb

PERSIST_DIR = "./chroma_db"
COLLECTION_NAME = "kb_store"
PAGE_SIZE = 500  # small enough to stay under SQLite's variable limit

# old (as currently stored) -> new (canonical, matches config.DOMAINS)
DOMAIN_MAP = {
    "ml_pdfs": "ml",
    "dl_pdfs": "dl",
    "genai_pdfs": "genai",
    "big_data_pdfs": "bigdata",
    "dbms_pdfs": "dbms",
    "dsa_pdfs": "dsa",
    "python_pdfs": "python",
}


def main():
    client = chromadb.PersistentClient(path=PERSIST_DIR)
    collection = client.get_collection(COLLECTION_NAME)

    total = collection.count()
    print(f"'{COLLECTION_NAME}' has {total} chunks. Remapping in pages of {PAGE_SIZE}...")

    changed = 0
    offset = 0
    while offset < total:
        page = collection.get(include=["metadatas"], limit=PAGE_SIZE, offset=offset)
        ids = page["ids"]
        metadatas = page["metadatas"]

        page_changed_ids = []
        page_changed_metas = []
        for i, m in zip(ids, metadatas):
            old_domain = m.get("domain")
            if old_domain in DOMAIN_MAP:
                m["domain"] = DOMAIN_MAP[old_domain]
                page_changed_ids.append(i)
                page_changed_metas.append(m)

        if page_changed_ids:
            collection.update(ids=page_changed_ids, metadatas=page_changed_metas)
            changed += len(page_changed_ids)

        offset += PAGE_SIZE
        print(f"processed {min(offset, total)}/{total} (remapped so far: {changed})")

    print(f"\nDone. Remapped {changed} chunks.")

    # verify -- counts per canonical domain, paginated (a single unbounded
    # get() on a large domain like dbms's ~15k chunks can hit the same limit)
    print("\nVerifying — counts per canonical domain:")
    for domain in sorted(set(DOMAIN_MAP.values())):
        domain_count = 0
        d_offset = 0
        while True:
            res = collection.get(where={"domain": domain}, include=[], limit=PAGE_SIZE, offset=d_offset)
            n = len(res["ids"])
            domain_count += n
            if n < PAGE_SIZE:
                break
            d_offset += PAGE_SIZE
        print(f"  {domain}: {domain_count} chunks")


if __name__ == "__main__":
    main()