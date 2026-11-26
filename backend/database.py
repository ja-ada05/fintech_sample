"""MySQL connection + query helpers for the FastAPI backend.

Uses the same `mysql://user:pass@host:port/database` DSN convention as the repo
root `db.py`, but is self-contained so the backend package does not depend on
repo layout. Returns dict rows (JSON-friendly).
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import pymysql

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _load_dotenv() -> None:
    """Load backend/.env into os.environ if present (stdlib, no python-dotenv)."""
    if not os.path.exists(_ENV_FILE):
        return
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def dsn() -> str:
    _load_dotenv()
    return os.environ.get("DATABASE_URL", "mysql://root@localhost:3306/credit")


def get_conn(dsn_str: str | None = None):
    u = urlparse(dsn_str or dsn())
    return pymysql.connect(
        host=u.hostname or "localhost",
        port=u.port or 3306,
        user=u.username or "root",
        password=u.password or "",
        database=(u.path or "").lstrip("/") or "credit",
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def query(sql: str, params=None, dsn_str: str | None = None) -> list[dict]:
    """Run a SELECT and return rows as list[dict]."""
    conn = get_conn(dsn_str)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql: str, params=None, dsn_str: str | None = None) -> int:
    """Run a write statement and return affected row count."""
    conn = get_conn(dsn_str)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount
    finally:
        conn.close()
