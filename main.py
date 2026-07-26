from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_conn
from retrieval import retrieve
from grading import grade_answer
from config import CORRECT_THRESHOLD

app = FastAPI(title="ML Interview Trainer")

# Streamlit runs on a different port — allow it during local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SubmitAnswerRequest(BaseModel):
    question_id: int
    answer: str


@app.get("/question/next")
def next_question():
    conn = get_conn()
    cur = conn.cursor()

    # Rule-based prioritization (V1): worst accuracy first (unseen topics = 0
    # accuracy, so they're naturally prioritized), tie-broken by staleness.
    cur.execute("""
        SELECT topic FROM topic_stats
        ORDER BY
            CASE WHEN attempt_count = 0 THEN 0.0
                 ELSE CAST(correct_count AS FLOAT) / attempt_count END ASC,
            last_seen IS NOT NULL,
            last_seen ASC
        LIMIT 1
    """)
    topic_row = cur.fetchone()
    if topic_row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="No topics found — did you run setup_db.py?")
    topic = topic_row["topic"]

    # Within that topic, pick the least-attempted question, tie-broken by
    # the one attempted longest ago (or never).
    cur.execute("""
        SELECT q.id, q.topic, q.subtopic, q.difficulty, q.source_text,
               COUNT(a.id) AS attempt_count, MAX(a.timestamp) AS last_attempt
        FROM questions q
        LEFT JOIN attempts a ON a.question_id = q.id
        WHERE q.topic = ?
        GROUP BY q.id
        ORDER BY attempt_count ASC, last_attempt IS NOT NULL, last_attempt ASC
        LIMIT 1
    """, (topic,))
    q = cur.fetchone()
    conn.close()

    if q is None:
        raise HTTPException(status_code=404, detail=f"No questions found for topic '{topic}'.")

    return {
        "id": q["id"],
        "topic": q["topic"],
        "subtopic": q["subtopic"],
        "difficulty": q["difficulty"],
        "question": q["source_text"],
    }


@app.post("/answer/submit")
def submit_answer(req: SubmitAnswerRequest):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, topic, source_text FROM questions WHERE id = ?", (req.question_id,))
    question = cur.fetchone()
    if question is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Question not found.")

    context_chunks = retrieve(question["source_text"], n_results=3)
    result = grade_answer(question["source_text"], req.answer, context_chunks)

    cur.execute(
        "INSERT INTO attempts (question_id, your_answer, score, feedback) VALUES (?, ?, ?, ?)",
        (req.question_id, req.answer, result["score"], result["missing"] + "\n\n" + result["corrected_explanation"])
    )

    is_correct = 1 if result["score"] >= CORRECT_THRESHOLD else 0
    cur.execute("""
        INSERT INTO topic_stats (topic, correct_count, attempt_count, last_seen)
        VALUES (?, ?, 1, datetime('now'))
        ON CONFLICT(topic) DO UPDATE SET
            correct_count = correct_count + ?,
            attempt_count = attempt_count + 1,
            last_seen = datetime('now')
    """, (question["topic"], is_correct, is_correct))

    conn.commit()
    conn.close()

    return {
        "score": result["score"],
        "missing": result["missing"],
        "corrected_explanation": result["corrected_explanation"],
    }


@app.get("/stats")
def stats():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT topic, correct_count, attempt_count,
               CASE WHEN attempt_count = 0 THEN 0.0
                    ELSE ROUND(CAST(correct_count AS FLOAT) / attempt_count, 3) END AS accuracy,
               last_seen
        FROM topic_stats
        ORDER BY topic
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"topics": rows}


@app.get("/")
def root():
    return {"status": "ok", "endpoints": ["/question/next", "/answer/submit (POST)", "/stats"]}