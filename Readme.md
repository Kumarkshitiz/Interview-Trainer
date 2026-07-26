# ML Interview Trainer

Adaptive practice app for machine learning interview prep. Ingests ML textbooks
into a vector store, serves conceptual questions, grades free-text answers with
an LLM against retrieved reference context, and tracks per-topic accuracy to
prioritize weak areas.

**V1 scope:** classical ML only (no deep learning), conceptual Q&A (no code
execution). The goal of V1 is to prove the core loop — question → answer →
grade → feedback → progress — works and is worth building on.

## Architecture

```
Books (PDF) --Colab GPU--> chunks + embeddings --> Chroma (ml_kb collection)
                                                          |
                                                          v
Question bank (CSV) --> SQLite (questions, attempts, topic_stats)
                                                          |
                                                          v
                                              FastAPI backend
                                    /question/next  /answer/submit  /stats
                                                          |
                                                          v
                                              Streamlit frontend
```

- **Embeddings:** `all-MiniLM-L6-v2` (sentence-transformers), 384-dim,
  normalized for cosine similarity. Same model is used at ingestion and at
  query time — never let Chroma use its own default embedding function here,
  the vectors won't match.
- **Vector store:** Chroma, persisted locally at `./chroma_db`, collection
  name `ml_kb`.
- **Relational store:** SQLite (`trainer.db`) — `questions`, `attempts`,
  `topic_stats`. Schema in `setup_db.py`.
- **Grading LLM:** Groq (`openai/gpt-oss-120b` by default — Groq deprecated
  the Llama 3.3/3.1 chat models in June 2026). Single rubric-based grading
  call per answer, no agents/orchestration in V1.
- **Prioritization (V1):** rule-based — least-accurate topic first (unseen
  topics count as 0% accuracy, so they surface automatically), tie-broken by
  staleness. A learned (PyTorch) prioritization model is planned for a later
  version, not V1.

## Setup

### 1. Environment

```bash
python -m venv .venv
source .venv/Scripts/activate   # Git Bash on Windows
pip install -r backend/requirements.txt
```

Create `.env` in the project root:

```dotenv
GROQ_API_KEY=your_key_here
```

### 2. Build the knowledge base (one-time, or whenever you add books)

1. Drop book PDFs somewhere accessible to Colab (uploaded directly, or a
   Drive folder).
2. Run `ml_books_embedding.ipynb` on a Colab T4 GPU runtime. It extracts
   text, chunks it, embeds with `all-MiniLM-L6-v2`, and checkpoints
   throughout so a disconnect doesn't lose progress.
3. Download the two output files: `chunks_final.parquet` and
   `embeddings_final.npy`.
4. Place both next to `load_chroma.py` and run:
   ```bash
   python load_chroma.py
   ```
   This builds the local `ml_kb` Chroma collection at `./chroma_db`.

### 3. Build the question bank

`ml_questions_seed.csv` has 100 classical ML questions across 10 topics.
Place it next to `setup_db.py` and run:

```bash
python setup_db.py
```

This creates `trainer.db`, loads the questions, and seeds `topic_stats`.

### 4. Run the backend

```bash
cd backend
uvicorn main:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs`. Endpoints:

- `GET /question/next` — next question to answer, chosen by the
  prioritization rule above.
- `POST /answer/submit` — `{ "question_id": int, "answer": str }`, returns
  `{ score, missing, corrected_explanation }`. Also logs the attempt and
  updates `topic_stats`.
- `GET /stats` — per-topic accuracy for the dashboard.

### 5. Run the frontend

*(Streamlit app — TBD.)*

## Project layout

```
.
├── ml_books_embedding.ipynb   # Colab notebook: PDF -> chunks -> embeddings
├── load_chroma.py             # loads embeddings into local Chroma
├── ml_questions_seed.csv      # 100-question seed bank
├── setup_db.py                # creates trainer.db, loads questions
├── backend/
│   ├── main.py                # FastAPI app
│   ├── config.py              # env / constants
│   ├── db.py                  # SQLite connection helper
│   ├── retrieval.py           # Chroma query (query-side embedding)
│   ├── grading.py             # Groq rubric grading
│   └── requirements.txt
└── .gitignore
```

## Notes / gotchas hit so far

- Chroma collection names need 3+ characters (`"ml"` fails, `"ml_kb"` works).
- Never use `query_texts=` against Chroma if you embedded with a specific
  model at ingestion — it silently falls back to Chroma's own default
  embedding function, which both requires an extra download and mismatches
  your stored vectors.
- If pip/HuggingFace downloads fail with an SSL `FileNotFoundError` on
  Windows + conda, check for a stale `SSL_CERT_FILE` env var — `conda
  deactivate` (stop stacking conda's base env under the project venv) fixed
  it here.