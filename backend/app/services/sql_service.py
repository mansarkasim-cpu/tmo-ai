import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import os

# Default to a file-based SQLite DB in the backend folder so tables persist
default_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tmo_ai.db"))
DB_PATH = os.environ.get("TMO_AI_DB_PATH", default_db_path)

# lazy import for postgres driver
_have_psycopg2 = False
try:
    import psycopg2
    _have_psycopg2 = True
except Exception:
    psycopg2 = None


def _is_postgres_url(dsn: str) -> bool:
    if not dsn:
        return False
    s = dsn.strip().lower()
    return s.startswith("postgres://") or s.startswith("postgresql://")

_USE_POSTGRES = _is_postgres_url(DB_PATH)


def _is_readonly_query(sql: str) -> bool:
    s = sql.strip().lower()
    # allow SELECT and PRAGMA only for readonly by default
    return s.startswith("select") or s.startswith("pragma")


def execute_query(query: str, params: Optional[List[Any]] = None, max_rows: int = 100, readonly: bool = True) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Execute a SQL query against the configured SQLite database.

    Safety:
    - If `readonly` is True, only `SELECT` and `PRAGMA` are allowed.
    - Only a single statement is allowed; multiple statements separated by `;` are rejected.
    - Results are limited to `max_rows`.
    """
    if readonly and not _is_readonly_query(query):
        raise ValueError("Only readonly queries are allowed when readonly=True")

    # basic check to prevent multiple statements
    if ";" in query.strip().rstrip(';'):
        # if semicolon present inside SQL (common), reject to be safe
        raise ValueError("Multiple statements are not allowed")

    if _USE_POSTGRES:
        if not _have_psycopg2:
            raise RuntimeError("psycopg2 is required for Postgres DB support. Install psycopg2-binary.")
        conn = psycopg2.connect(DB_PATH)
        try:
            cur = conn.cursor()
            # convert sqlite-style ? placeholders to psycopg2 %s
            if params:
                q = query.replace("?", "%s")
                cur.execute(q, params)
            else:
                cur.execute(query)
            cols = [c.name for c in cur.description] if cur.description else []
            rows = []
            for r in cur.fetchmany(max_rows):
                # r is a tuple
                rows.append({cols[i]: r[i] for i in range(len(cols))})
            return rows, cols
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)

            cols = [c[0] for c in cur.description] if cur.description else []
            rows = []
            for r in cur.fetchmany(max_rows):
                rows.append({k: r[k] for k in cols})

            return rows, cols
        finally:
            conn.close()


def execute_write(query: str, params: Optional[List[Any]] = None) -> int:
    """Execute a write (INSERT/UPDATE/DELETE) against the configured SQLite database.

    Returns the last inserted row id when available (0 otherwise).
    """
    # basic check to prevent multiple statements
    if ";" in query.strip().rstrip(";"):
        raise ValueError("Multiple statements are not allowed")

    if _USE_POSTGRES:
        if not _have_psycopg2:
            raise RuntimeError("psycopg2 is required for Postgres DB support. Install psycopg2-binary.")
        conn = psycopg2.connect(DB_PATH)
        try:
            cur = conn.cursor()
            if params:
                q = query.replace("?", "%s")
                cur.execute(q, params)
            else:
                cur.execute(query)
            conn.commit()
            # psycopg2's lastrowid isn't always set; try to fetch via RETURNING if needed
            try:
                return cur.lastrowid if hasattr(cur, "lastrowid") and cur.lastrowid is not None else 0
            except Exception:
                return 0
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            cur = conn.cursor()
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            conn.commit()
            return cur.lastrowid if cur.lastrowid is not None else 0
        finally:
            conn.close()


def init_db() -> None:
    """Create required tables if they do not exist."""
    if _USE_POSTGRES:
        if not _have_psycopg2:
            raise RuntimeError("psycopg2 is required for Postgres DB support. Install psycopg2-binary.")
        conn = psycopg2.connect(DB_PATH)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id SERIAL PRIMARY KEY,
                    message TEXT NOT NULL,
                    response TEXT NOT NULL,
                    document_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    response TEXT NOT NULL,
                    document_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    # create memories table as well
    if _USE_POSTGRES:
        conn = psycopg2.connect(DB_PATH)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id SERIAL PRIMARY KEY,
                    key TEXT,
                    value TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def save_chat(message: str, response: str, document_id: Optional[str] = None) -> int:
    """Insert a chat record and return the inserted id."""
    from datetime import datetime

    created_at = datetime.utcnow().isoformat() + "Z"
    q = "INSERT INTO chats (message, response, document_id, created_at) VALUES (?, ?, ?, ?)"
    # execute_write will convert placeholders for Postgres automatically
    return execute_write(q, [message, response, document_id, created_at])


def save_memory(key: Optional[str], value: str) -> int:
    """Save a memory key/value and return inserted id."""
    from datetime import datetime

    created_at = datetime.utcnow().isoformat() + "Z"
    q = "INSERT INTO memories (key, value, created_at) VALUES (?, ?, ?)"
    return execute_write(q, [key, value, created_at])


def get_memories(search: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieve memories, optionally filtered by search term in key or value."""
    if search:
        pattern = f"%{search}%"
        rows, cols = execute_query(
            "SELECT id, key, value, created_at FROM memories WHERE key LIKE ? OR value LIKE ? ORDER BY created_at DESC LIMIT ?",
            params=[pattern, pattern, limit],
            readonly=True,
        )
    else:
        rows, cols = execute_query(
            "SELECT id, key, value, created_at FROM memories ORDER BY created_at DESC LIMIT ?",
            params=[limit],
            readonly=True,
        )
    return rows
