"""
V4 schema migration: adds `user_id` and `model_answer` to `attempts`.

- user_id: placeholder single-user constant for now (see config.DEFAULT_USER_ID).
  Real multi-user auth later just changes what gets written here, not the schema.
- model_answer: added alongside user_id since V7 (AI's own model answer per
  grading) needs somewhere to persist it, and it's the same kind of small
  additive change -- no reason to run two migrations back to back.

Safe to re-run: checks current state first, skips what's already applied.
Takes a timestamped backup before touching anything.

Usage:
    python migrate_v4.py [path/to/trainer.db]
    (defaults to ./trainer.db)
"""

import shutil
import sqlite3
import sys
from datetime import datetime

DEFAULT_DB_PATH = "trainer.db"
DEFAULT_USER_ID = "single_user"  # matches config.DEFAULT_USER_ID


def backup_db(db_path: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{stamp}"
    shutil.copy2(db_path, backup_path)
    print(f"Backed up {db_path} -> {backup_path}")
    return backup_path


def get_columns(conn, table):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def add_column_if_missing(conn, table, column, coltype, backfill_value=None):
    cols = get_columns(conn, table)
    if column in cols:
        print(f"  [{table}] `{column}` already exists — skipping.")
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    if backfill_value is not None:
        conn.execute(f"UPDATE {table} SET {column} = ? WHERE {column} IS NULL", (backfill_value,))
    print(f"  [{table}] added `{column}`.")


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    backup_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        print("\nMigrating `attempts`...")
        add_column_if_missing(conn, "attempts", "user_id", "TEXT", backfill_value=DEFAULT_USER_ID)
        add_column_if_missing(conn, "attempts", "model_answer", "TEXT")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_attempts_user_question "
            "ON attempts(user_id, question_id)"
        )

        conn.commit()
        print("\nMigration complete.")
    except Exception:
        conn.rollback()
        print("\nMigration FAILED — rolled back. DB left unchanged (backup is safe).")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()