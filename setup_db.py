"""
Creates the V2 SQLite schema (domain-aware) and loads all domain question CSVs.

Expects one CSV per domain next to this script, named `<domain>_questions_seed.csv`
(e.g. ml_questions_seed.csv, dl_questions_seed.csv, ...) with columns:
    topic, subtopic, difficulty, source_text

For a fresh install only. If you already have a V1 trainer.db, use
migrate_v2_schema.py instead — this script's CREATE TABLE IF NOT EXISTS
won't retrofit an existing V1 table.

Usage:
    python setup_db.py
"""

import sqlite3
import csv
import os

from config import DB_PATH, DOMAINS

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    topic TEXT NOT NULL,
    subtopic TEXT,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    source_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    your_answer TEXT NOT NULL,
    score INTEGER,                      -- 1-5 rubric score from grading LLM
    feedback TEXT,                      -- what's missing + corrected explanation
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE TABLE IF NOT EXISTS topic_stats (
    domain TEXT NOT NULL,
    topic TEXT NOT NULL,
    correct_count INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT,                     -- ISO timestamp of last attempt on this topic
    PRIMARY KEY (domain, topic)
);

-- speeds up /question/next's "least-recently-seen, weighted by accuracy" query,
-- now scoped per domain
CREATE INDEX IF NOT EXISTS idx_questions_domain_topic ON questions(domain, topic);
CREATE INDEX IF NOT EXISTS idx_attempts_question_id ON attempts(question_id);
"""


def create_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()
    print("Schema created (or already existed).")


def load_questions_for_domain(conn, domain):
    csv_path = f"{domain}_questions_seed.csv"
    if not os.path.exists(csv_path):
        print(f"  [{domain}] no {csv_path} found — skipping.")
        return 0

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM questions WHERE domain = ?", (domain,))
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"  [{domain}] already has {existing} rows — skipping load to avoid duplicates.")
        return 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            (domain, r["topic"], r["subtopic"], r["difficulty"], r["source_text"])
            for r in reader
        ]

    cur.executemany(
        "INSERT INTO questions (domain, topic, subtopic, difficulty, source_text) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    print(f"  [{domain}] loaded {len(rows)} questions.")
    return len(rows)


def seed_topic_stats(conn):
    """Pre-populate topic_stats with every (domain, topic) pair at 0/0 so
    /question/next doesn't need special-case handling for 'never seen yet'."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT domain, topic FROM questions")
    pairs = cur.fetchall()

    cur.executemany(
        "INSERT OR IGNORE INTO topic_stats (domain, topic, correct_count, attempt_count, last_seen) "
        "VALUES (?, ?, 0, 0, NULL)",
        pairs,
    )
    conn.commit()
    print(f"topic_stats seeded for {len(pairs)} (domain, topic) pairs.")


def main():
    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)

    print("\nLoading question banks:")
    total = 0
    for domain in DOMAINS:
        total += load_questions_for_domain(conn, domain)
    print(f"\nTotal new questions loaded: {total}")

    seed_topic_stats(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT domain, topic, COUNT(*) FROM questions GROUP BY domain, topic ORDER BY domain, topic"
    )
    print("\nQuestions per (domain, topic):")
    for domain, topic, count in cur.fetchall():
        print(f"  [{domain}] {topic}: {count}")

    conn.close()
    print(f"\nDB ready at: {DB_PATH}")


if __name__ == "__main__":
    main()