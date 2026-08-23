"""SQLite storage for allowed users and their issued tokens."""
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

DATA_DIR = os.environ.get("AUTH_DATA_DIR", "/opt/hound-coder/auth")
DB_PATH = os.path.join(DATA_DIR, "hound_coder_auth.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
    email TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    issue_date INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (email, issue_date)
);
"""


@dataclass
class User:
    email: str
    is_admin: bool
    created_at: int


@dataclass
class Token:
    email: str
    issue_date: int
    revoked: bool


def init_db() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_user(email: str) -> User | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT email, is_admin, created_at FROM users WHERE email = ?", (email,)
        ).fetchone()
    return User(row[0], bool(row[1]), row[2]) if row else None


def list_users() -> list[User]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT email, is_admin, created_at FROM users ORDER BY email"
        ).fetchall()
    return [User(r[0], bool(r[1]), r[2]) for r in rows]


def create_user(email: str, is_admin: bool, created_at: int) -> User:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (email, is_admin, created_at) VALUES (?, ?, ?)",
            (email, int(is_admin), created_at),
        )
    return User(email, is_admin, created_at)


def set_admin(email: str, is_admin: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_admin = ? WHERE email = ?", (int(is_admin), email))


def delete_user(email: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))


def create_token(email: str, issue_date: int) -> Token:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tokens (email, issue_date, revoked) VALUES (?, ?, 0)",
            (email, issue_date),
        )
    return Token(email, issue_date, False)


def get_token(email: str, issue_date: int) -> Token | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT email, issue_date, revoked FROM tokens WHERE email = ? AND issue_date = ?",
            (email, issue_date),
        ).fetchone()
    return Token(row[0], row[1], bool(row[2])) if row else None


def list_tokens(email: str) -> list[Token]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT email, issue_date, revoked FROM tokens WHERE email = ? ORDER BY issue_date",
            (email,),
        ).fetchall()
    return [Token(r[0], r[1], bool(r[2])) for r in rows]


def revoke_token(email: str, issue_date: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE tokens SET revoked = 1 WHERE email = ? AND issue_date = ?",
            (email, issue_date),
        )
