from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_conn
from retrieval import retrieve
from grading import grade_answer
from config import CORRECT_THRESHOLD, DOMAINS, validate_domain

app = FastAPI(title="Interview Trainer")

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
def next_question(domain: str = Query(..., description=f"One of: {DOMAINS}")):
    validate_domain(domain)
    conn = get_conn()
    cur = conn.cursor()

    # Rule-based prioritization (V1/V2): worst accuracy first within this
    # domain (unseen topics = 0 accuracy, prioritized automatically),
    # tie-broken by staleness.
    cur.execute("""
        SELECT topic FROM topic_stats
        WHERE domain = ?
        ORDER BY
            CASE WHEN attempt_count = 0 THEN 0.0
                 ELSE CAST(correct_count AS FLOAT) / attempt_count END ASC,
            last_seen IS NOT NULL,
            last_seen ASC
        LIMIT 1
    """, (domain,))
    topic_row = cur.fetchone()
    if topic_row is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"No topics found for domain '{domain}'.")
    topic = topic_row["topic"]

    cur.execute("""
        SELECT q.id, q.domain, q.topic, q.subtopic, q.difficulty, q.source_text,
               COUNT(a.id) AS attempt_count, MAX(a.timestamp) AS last_attempt
        FROM questions q
        LEFT JOIN attempts a ON a.question_id = q.id
        WHERE q.domain = ? AND q.topic = ?
        GROUP BY q.id
        ORDER BY attempt_count ASC, last_attempt IS NOT NULL, last_attempt ASC
        LIMIT 1
    """, (domain, topic))
    q = cur.fetchone()
    conn.close()

    if q is None:
        raise HTTPException(status_code=404, detail=f"No questions found for {domain}/{topic}.")

    return {
        "id": q["id"],
        "domain": q["domain"],
        "topic": q["topic"],
        "subtopic": q["subtopic"],
        "difficulty": q["difficulty"],
        "question": q["source_text"],
    }


@app.post("/answer/submit")
def submit_answer(req: SubmitAnswerRequest):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, domain, topic, source_text FROM questions WHERE id = ?", (req.question_id,))
    question = cur.fetchone()
    if question is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Question not found.")

    domain = question["domain"]

    # domain filter ensures a DSA question never gets graded against
    # ML-retrieved context, etc.
    context_chunks = retrieve(question["source_text"], domain=domain, n_results=3)
    result = grade_answer(question["source_text"], req.answer, context_chunks, domain=domain)

    cur.execute(
        "INSERT INTO attempts (question_id, domain, your_answer, score, feedback) VALUES (?, ?, ?, ?, ?)",
        (req.question_id, domain, req.answer, result["score"],
         result["missing"] + "\n\n" + result["corrected_explanation"])
    )

    is_correct = 1 if result["score"] >= CORRECT_THRESHOLD else 0
    cur.execute("""
        INSERT INTO topic_stats (domain, topic, correct_count, attempt_count, last_seen)
        VALUES (?, ?, ?, 1, datetime('now'))
        ON CONFLICT(domain, topic) DO UPDATE SET
            correct_count = correct_count + ?,
            attempt_count = attempt_count + 1,
            last_seen = datetime('now')
    """, (domain, question["topic"], is_correct, is_correct))

    conn.commit()
    conn.close()

    return {
        "domain": domain,
        "score": result["score"],
        "missing": result["missing"],
        "corrected_explanation": result["corrected_explanation"],
    }


@app.get("/stats")
def stats(domain: str | None = Query(None, description=f"Optional filter, one of: {DOMAINS}")):
    if domain is not None:
        validate_domain(domain)

    conn = get_conn()
    cur = conn.cursor()

    if domain:
        cur.execute("""
            SELECT domain, topic, correct_count, attempt_count,
                   CASE WHEN attempt_count = 0 THEN 0.0
                        ELSE ROUND(CAST(correct_count AS FLOAT) / attempt_count, 3) END AS accuracy,
                   last_seen
            FROM topic_stats
            WHERE domain = ?
            ORDER BY topic
        """, (domain,))
    else:
        cur.execute("""
            SELECT domain, topic, correct_count, attempt_count,
                   CASE WHEN attempt_count = 0 THEN 0.0
                        ELSE ROUND(CAST(correct_count AS FLOAT) / attempt_count, 3) END AS accuracy,
                   last_seen
            FROM topic_stats
            ORDER BY domain, topic
        """)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"topics": rows}


@app.get("/stats/summary")
def stats_summary(domain: str = Query(..., description=f"One of: {DOMAINS}")):
    """Overall progress for a domain: how many of its questions have been
    attempted at least once (out of the total bank), and the average raw
    score (1-5) across all attempts -- not the same as topic_stats'
    correct/attempt accuracy, which only tracks pass/fail at the threshold."""
    validate_domain(domain)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS total FROM questions WHERE domain = ?", (domain,))
    total_questions = cur.fetchone()["total"]

    cur.execute("""
        SELECT COUNT(DISTINCT question_id) AS attempted
        FROM attempts WHERE domain = ?
    """, (domain,))
    attempted_questions = cur.fetchone()["attempted"]

    cur.execute("""
        SELECT COUNT(*) AS total_attempts, AVG(score) AS avg_score
        FROM attempts WHERE domain = ? AND score > 0
    """, (domain,))  # score=0 means the grading response failed to parse, exclude from the average
    row = cur.fetchone()
    total_attempts = row["total_attempts"] or 0
    avg_score = round(row["avg_score"], 2) if row["avg_score"] is not None else None

    conn.close()

    return {
        "domain": domain,
        "total_questions": total_questions,
        "attempted_questions": attempted_questions,
        "remaining_questions": total_questions - attempted_questions,
        "total_attempts": total_attempts,
        "average_score": avg_score,
    }


@app.get("/")
def root():
    return {"status": "ok", "domains": DOMAINS, "endpoints": [
        "/question/next?domain=...", "/answer/submit (POST)", "/stats?domain=(optional)"
    ]}