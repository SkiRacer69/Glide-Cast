from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "glidecast.db"

BASIC_VENUES = (
    "Sugarloaf",
    "Sunday River",
    "Gore Mountain",
    "Mount Snow",
    "Killington",
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                email TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                plan_tier TEXT NOT NULL DEFAULT 'basic',
                trial_ends_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                inputs_json TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_user(username: str, email: str, password_hash: str) -> dict:
    now = datetime.now(timezone.utc)
    trial_ends = now + timedelta(days=7)
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, email, password_hash, plan_tier, trial_ends_at, created_at)
            VALUES (?, ?, ?, 'basic', ?, ?)
            """,
            (
                username.strip(),
                (email or "").strip(),
                password_hash,
                trial_ends.isoformat(),
                now.isoformat(),
            ),
        )
        user_id = cur.lastrowid
    return get_user_by_id(user_id)


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_username(username: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
    return dict(row) if row else None


def user_has_access(user: dict) -> bool:
    if user.get("plan_tier") == "pro":
        return True
    trial_ends = datetime.fromisoformat(user["trial_ends_at"])
    if trial_ends.tzinfo is None:
        trial_ends = trial_ends.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) <= trial_ends


def venues_for_user(user: dict, engine_keys: list[str]) -> list[str]:
    key_set = set(engine_keys)
    if user.get("plan_tier") == "pro":
        return [v for v in engine_keys if v in key_set]
    return [v for v in BASIC_VENUES if v in key_set]


def save_calculation(user_id: int, inputs_json: str, results_json: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO calculations (user_id, inputs_json, results_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, inputs_json, results_json, now),
        )
