"""Separate SQLite store for per-request usage / audit events (not the auth DB)."""
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass

DATA_DIR = os.environ.get("HOUND_DATA_DIR", "/opt/hound-coder/data")
USAGE_DB_PATH = os.path.join(DATA_DIR, "usage.db")
# Default ~26 weeks, matching the old usage.log retention.
RETENTION_DAYS = int(os.environ.get("USAGE_RETENTION_DAYS", "182"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS request_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    email TEXT NOT NULL,
    iat INTEGER NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status INTEGER NOT NULL,
    request_body TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms REAL,
    ttft_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_request_events_email_created
    ON request_events (email, created_at);
CREATE INDEX IF NOT EXISTS idx_request_events_created
    ON request_events (created_at);
"""


@dataclass
class RequestEvent:
    id: int
    created_at: int
    email: str
    iat: int
    endpoint: str
    method: str
    path: str
    status: int
    request_body: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float | None
    ttft_ms: float | None


@dataclass
class UsageAggregate:
    email: str
    endpoint: str | None
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    avg_latency_ms: float | None
    avg_ttft_ms: float | None


def init_db() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    prune_old_events()


@contextmanager
def get_conn():
    conn = sqlite3.connect(USAGE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_event(
    *,
    email: str,
    iat: int,
    endpoint: str,
    method: str,
    path: str,
    status: int,
    request_body: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: float | None,
    ttft_ms: float | None,
    created_at: int | None = None,
) -> None:
    ts = created_at if created_at is not None else int(time.time())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO request_events (
                created_at, email, iat, endpoint, method, path, status,
                request_body, prompt_tokens, completion_tokens, latency_ms, ttft_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                email,
                iat,
                endpoint,
                method,
                path,
                status,
                request_body,
                prompt_tokens,
                completion_tokens,
                latency_ms,
                ttft_ms,
            ),
        )


def prune_old_events(now: int | None = None) -> int:
    if RETENTION_DAYS <= 0:
        return 0
    cutoff = (now if now is not None else int(time.time())) - RETENTION_DAYS * 86400
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM request_events WHERE created_at < ?", (cutoff,))
        return cur.rowcount


def _row_to_event(row: tuple) -> RequestEvent:
    return RequestEvent(*row)


def list_events(
    *,
    email: str | None = None,
    endpoint: str | None = None,
    since: int | None = None,
    until: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[RequestEvent]:
    clauses: list[str] = []
    params: list[object] = []
    if email is not None:
        clauses.append("email = ?")
        params.append(email)
    if endpoint is not None:
        clauses.append("endpoint = ?")
        params.append(endpoint)
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("created_at <= ?")
        params.append(until)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, created_at, email, iat, endpoint, method, path, status,
                   request_body, prompt_tokens, completion_tokens, latency_ms, ttft_ms
            FROM request_events
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return [_row_to_event(r) for r in rows]


def aggregate_usage(
    *,
    email: str | None = None,
    endpoint: str | None = None,
    since: int | None = None,
    until: int | None = None,
    group_by_endpoint: bool = False,
) -> list[UsageAggregate]:
    clauses: list[str] = []
    params: list[object] = []
    if email is not None:
        clauses.append("email = ?")
        params.append(email)
    if endpoint is not None:
        clauses.append("endpoint = ?")
        params.append(endpoint)
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("created_at <= ?")
        params.append(until)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    if group_by_endpoint:
        group_cols = "email, endpoint"
        select_endpoint = "endpoint"
    else:
        group_cols = "email"
        select_endpoint = "NULL AS endpoint"

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT email, {select_endpoint},
                   COUNT(*),
                   COALESCE(SUM(prompt_tokens), 0),
                   COALESCE(SUM(completion_tokens), 0),
                   AVG(latency_ms),
                   AVG(ttft_ms)
            FROM request_events
            {where}
            GROUP BY {group_cols}
            ORDER BY email, {select_endpoint if group_by_endpoint else "email"}
            """,
            params,
        ).fetchall()
    return [
        UsageAggregate(
            email=r[0],
            endpoint=r[1],
            request_count=r[2],
            prompt_tokens=int(r[3]),
            completion_tokens=int(r[4]),
            avg_latency_ms=r[5],
            avg_ttft_ms=r[6],
        )
        for r in rows
    ]
