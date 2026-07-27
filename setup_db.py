"""
Creates the V1 SQLite schema and loads ml_questions_seed.csv into `questions`.

Usage:
    python setup_db.py
"""

import sqlite3
import csv
import os

DB_PATH = "trainer.db"
CSV_PATH = "ml_questions_seed.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    subtopic TEXT,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    source_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    your_answer TEXT NOT NULL,
    score INTEGER,                      -- 1-5 rubric score from grading LLM
    feedback TEXT,                      -- what's missing + corrected explanation
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE TABLE IF NOT EXISTS topic_stats (
    topic TEXT PRIMARY KEY,
    correct_count INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT                      -- ISO timestamp of last attempt on this topic
);

-- speeds up /question/next's "least-recently-seen, weighted by accuracy" query
CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic);
CREATE INDEX IF NOT EXISTS idx_attempts_question_id ON attempts(question_id);
"""

def create_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()
    print("Schema created (or already existed).")

def load_questions(conn):
    if not os.path.exists(CSV_PATH):
        print(f"No {CSV_PATH} found next to this script — skipping question load.")
        return

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM questions")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"questions table already has {existing} rows — skipping load to avoid duplicates.")
        print("(Delete trainer.db and rerun if you want a clean reload.)")
        return

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [(r["topic"], r["subtopic"], r["difficulty"], r["source_text"]) for r in reader]

    cur.executemany(
        "INSERT INTO questions (topic, subtopic, difficulty, source_text) VALUES (?, ?, ?, ?)",
        rows
    )
    conn.commit()
    print(f"Loaded {len(rows)} questions into `questions`.")

def seed_topic_stats(conn):
    """Pre-populate topic_stats with every topic at 0/0 so /question/next
    doesn't need special-case handling for 'never seen this topic yet'."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT topic FROM questions")
    topics = [r[0] for r in cur.fetchall()]

    cur.executemany(
        "INSERT OR IGNORE INTO topic_stats (topic, correct_count, attempt_count, last_seen) VALUES (?, 0, 0, NULL)",
        [(t,) for t in topics]
    )
    conn.commit()
    print(f"topic_stats seeded for {len(topics)} topics.")

def main():
    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    load_questions(conn)
    seed_topic_stats(conn)

    # sanity check
    cur = conn.cursor()
    cur.execute("SELECT topic, COUNT(*) FROM questions GROUP BY topic ORDER BY topic")
    print("\nQuestions per topic:")
    for topic, count in cur.fetchall():
        print(f"  {topic}: {count}")

    conn.close()
    print(f"\nDB ready at: {DB_PATH}")

if __name__ == "__main__":
    main()