from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_conn
from retrieval import retrieve
from grading import grade_answer
from config import CORRECT_THRESHOLD, DOMAINS, validate_domain, DEFAULT_USER_ID
from auth import require_auth

app = FastAPI(title="Interview Trainer", dependencies=[Depends(require_auth)])

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
def next_question(
    domain: str = Query(..., description=f"One of: {DOMAINS}"),
    topic: str | None = Query(
        None, description="Lock to a specific topic (Practice Mode) instead of auto priority"
    ),
    exclude_id: int | None = Query(
        None, description="Question id to avoid re-serving (used by Skip)"
    ),
):
    validate_domain(domain)
    conn = get_conn()
    cur = conn.cursor()

    if topic is not None:
        # Practice Mode: topic is locked by the user, skip priority selection
        # entirely. Still verify it actually exists in this domain so a
        # stale/typo'd topic doesn't silently 404 later with a confusing message.
        cur.execute(
            "SELECT 1 FROM topic_stats WHERE domain = ? AND topic = ?", (domain, topic)
        )
        if cur.fetchone() is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Unknown topic '{topic}' for domain '{domain}'.")
    else:
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

    def pick_question(exclude):
        params = [domain, topic]
        exclude_clause = ""
        if exclude is not None:
            exclude_clause = "AND q.id != ?"
            params.append(exclude)
        cur.execute(f"""
            SELECT q.id, q.domain, q.topic, q.subtopic, q.difficulty, q.source_text,
                   COUNT(a.id) AS attempt_count, MAX(a.timestamp) AS last_attempt
            FROM questions q
            LEFT JOIN attempts a ON a.question_id = q.id
            WHERE q.domain = ? AND q.topic = ? {exclude_clause}
            GROUP BY q.id
            ORDER BY attempt_count ASC, last_attempt IS NOT NULL, last_attempt ASC
            LIMIT 1
        """, params)
        return cur.fetchone()

    q = pick_question(exclude_id)
    if q is None and exclude_id is not None:
        # The excluded question was the only one in this topic -- fall back to it
        # rather than 404ing on a valid skip.
        q = pick_question(None)

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
        "INSERT INTO attempts (question_id, domain, user_id, your_answer, score, feedback, model_answer) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (req.question_id, domain, DEFAULT_USER_ID, req.answer, result["score"],
         result["missing"] + "\n\n" + result["corrected_explanation"], result["model_answer"])
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
        "model_answer": result["model_answer"],
    }


@app.get("/topics")
def list_topics(domain: str = Query(..., description=f"One of: {DOMAINS}")):
    """Ordered list of topics in a domain, for Practice Mode's topic selector
    and Prev/Next stepping. Ordered alphabetically -- stable and predictable
    for manual stepping, unlike the priority order used by auto mode."""
    validate_domain(domain)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT topic FROM topic_stats WHERE domain = ? ORDER BY topic", (domain,)
    )
    topics = [row["topic"] for row in cur.fetchall()]
    conn.close()
    return {"domain": domain, "topics": topics}


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


@app.get("/questions/{question_id}/attempts")
def question_attempts(question_id: int):
    """V4: full attempt history for a single question (this user only).
    Ordered newest-first so 'your last attempt' is attempts[0]."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, your_answer, score, feedback, model_answer, timestamp
        FROM attempts
        WHERE question_id = ? AND user_id = ?
        ORDER BY timestamp DESC
    """, (question_id, DEFAULT_USER_ID))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"question_id": question_id, "attempts": rows}


class CustomQuestionRequest(BaseModel):
    domain: str
    topic: str
    subtopic: str | None = None
    difficulty: str = "medium"
    source_text: str


@app.post("/questions/custom")
def create_custom_question(req: CustomQuestionRequest):
    """V8: user-submitted question. Grading still works even with no
    matching reference chunks in Chroma -- retrieval.py returns an empty
    list in that case, and grading.py's prompt already handles
    '(no reference context retrieved)' by falling back to the model's own
    domain knowledge, so no special-case fallback logic is needed here."""
    validate_domain(req.domain)
    if req.difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="difficulty must be easy, medium, or hard.")
    if not req.source_text.strip():
        raise HTTPException(status_code=400, detail="source_text cannot be empty.")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO questions (domain, topic, subtopic, difficulty, source_text) VALUES (?, ?, ?, ?, ?)",
        (req.domain, req.topic, req.subtopic, req.difficulty, req.source_text)
    )
    new_id = cur.lastrowid

    # make sure topic_stats has a row for this (domain, topic) so /question/next
    # and /topics see it immediately, even if it's a brand new topic name
    cur.execute("""
        INSERT OR IGNORE INTO topic_stats (domain, topic, correct_count, attempt_count, last_seen)
        VALUES (?, ?, 0, 0, NULL)
    """, (req.domain, req.topic))

    conn.commit()
    conn.close()

    return {
        "id": new_id,
        "domain": req.domain,
        "topic": req.topic,
        "subtopic": req.subtopic,
        "difficulty": req.difficulty,
        "question": req.source_text,
    }


@app.get("/")
def root():
    return {"status": "ok", "domains": DOMAINS, "endpoints": [
        "/question/next?domain=...&topic=(optional, Practice Mode)&exclude_id=(optional)",
        "/answer/submit (POST)", "/stats?domain=(optional)", "/stats/summary?domain=...",
        "/topics?domain=...", "/questions/{id}/attempts", "/questions/custom (POST)"
    ]}