"""SQLite user store.

One table; connections are opened per call (sqlite3 objects are not
thread-safe and FastAPI serves from a thread pool). The database lives
under ``webapp/data/`` which the repo .gitignore already excludes.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    plan          TEXT NOT NULL DEFAULT 'free',
    created_at    TEXT NOT NULL,
    upgraded_at   TEXT
);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def create_user(email: str, password_hash: str,
                db_path: Path | None = None) -> int | None:
    """Insert a user; return the new id, or None if the email is taken."""
    with _connect(db_path) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, password_hash, datetime.now(timezone.utc).isoformat()),
            )
        except sqlite3.IntegrityError:
            return None
        return cur.lastrowid


def get_user_by_email(email: str, db_path: Path | None = None) -> sqlite3.Row | None:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()


def get_user(user_id: int, db_path: Path | None = None) -> sqlite3.Row | None:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def set_plan(user_id: int, plan: str, db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET plan = ?, upgraded_at = ? WHERE id = ?",
            (plan, datetime.now(timezone.utc).isoformat(), user_id),
        )
