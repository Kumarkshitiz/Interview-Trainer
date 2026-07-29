"""
V2 schema migration for trainer.db.

Changes:
  - questions:   add `domain` column (backfilled to 'ml' for all existing rows,
                 since V1 was ML-only)
  - attempts:    add `domain` column, backfilled via join against questions.domain
  - topic_stats: rebuild with composite PRIMARY KEY (domain, topic) instead of
                 (topic) alone, since two domains could otherwise share a topic
                 name and collide

Safe to re-run: every step checks current state first and skips if already
applied. Takes a timestamped backup of trainer.db before touching anything.

Usage:
    python migrate_v2_schema.py [path/to/trainer.db]
    (defaults to ./trainer.db)
"""

import shutil
import sqlite3
import sys
from datetime import datetime

DEFAULT_DB_PATH = "trainer.db"
V1_DEFAULT_DOMAIN = "ml"  # everything pre-migration was ML-only


def backup_db(db_path: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{stamp}"
    shutil.copy2(db_path, backup_path)
    print(f"Backed up {db_path} -> {backup_path}")
    return backup_path


def get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def add_domain_column(conn: sqlite3.Connection, table: str, backfill_sql: str | None):
    cols = get_columns(conn, table)
    if "domain" in cols:
        print(f"  [{table}] already has `domain` column — skipping add.")
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN domain TEXT")
    if backfill_sql:
        conn.execute(backfill_sql)
    else:
        conn.execute(f"UPDATE {table} SET domain = ?", (V1_DEFAULT_DOMAIN,))
    print(f"  [{table}] added `domain` column and backfilled.")


def is_composite_pk(conn: sqlite3.Connection, table: str, pk_cols: set[str]) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    actual_pk = {row[1] for row in cur.fetchall() if row[5] > 0}  # pk flag is col index 5
    return actual_pk == pk_cols


def rebuild_topic_stats(conn: sqlite3.Connection):
    if not table_exists(conn, "topic_stats"):
        print("  [topic_stats] table not found — skipping (nothing to migrate).")
        return

    if is_composite_pk(conn, "topic_stats", {"domain", "topic"}):
        print("  [topic_stats] already has composite (domain, topic) PK — skipping rebuild.")
        return

    old_cols = get_columns(conn, "topic_stats")
    if "topic" not in old_cols:
        raise RuntimeError("topic_stats has no `topic` column — unexpected schema, aborting.")

    # every column except `topic` (and `domain`, if it somehow already exists)
    # carries over unchanged into the rebuilt table
    other_cols = [c for c in old_cols if c not in ("topic", "domain")]
    other_cols_def = ", ".join(f"{c} TEXT" if c == "" else f"{c}" for c in other_cols)
    # pull actual types from the old table instead of assuming TEXT
    cur = conn.execute("PRAGMA table_info(topic_stats)")
    type_map = {row[1]: row[2] or "TEXT" for row in cur.fetchall()}

    new_cols_sql = ["domain TEXT NOT NULL", "topic TEXT NOT NULL"]
    for c in other_cols:
        new_cols_sql.append(f"{c} {type_map.get(c, 'TEXT')}")
    new_cols_sql.append("PRIMARY KEY (domain, topic)")

    conn.execute("DROP TABLE IF EXISTS topic_stats_new")
    conn.execute(f"CREATE TABLE topic_stats_new ({', '.join(new_cols_sql)})")

    select_cols = ["?", "topic"] + other_cols
    insert_cols = ["domain", "topic"] + other_cols
    conn.execute(
        f"INSERT INTO topic_stats_new ({', '.join(insert_cols)}) "
        f"SELECT {', '.join(select_cols)} FROM topic_stats",
        (V1_DEFAULT_DOMAIN,),
    )

    conn.execute("DROP TABLE topic_stats")
    conn.execute("ALTER TABLE topic_stats_new RENAME TO topic_stats")
    print(f"  [topic_stats] rebuilt with composite PK (domain, topic); "
          f"carried over columns: {other_cols}")


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    backup_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")  # rebuilding topic_stats mid-transaction
    try:
        print("\nMigrating `questions`...")
        add_domain_column(conn, "questions", backfill_sql=None)

        print("\nMigrating `attempts`...")
        # backfill from the question it belongs to, in case that's ever not 'ml'
        backfill = """
            UPDATE attempts
            SET domain = (
                SELECT questions.domain FROM questions
                WHERE questions.id = attempts.question_id
            )
        """
        add_domain_column(conn, "attempts", backfill_sql=backfill)
        # anything that didn't join (orphaned attempt rows) falls back to 'ml'
        conn.execute(
            "UPDATE attempts SET domain = ? WHERE domain IS NULL", (V1_DEFAULT_DOMAIN,)
        )

        print("\nMigrating `topic_stats`...")
        rebuild_topic_stats(conn)

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