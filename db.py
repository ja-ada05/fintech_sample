"""Shared MySQL connection + bulk-insert helpers (main platform).

The openNPL compliance module (etl_scripts/npl_export.py, npl_report.py) is a
separate stack and still uses psycopg2/PostgreSQL directly. Everything else in the
main platform connects to MySQL through this module.

DSN format: mysql://user:password@host:port/database

Dependency: pip install pymysql
"""
from __future__ import annotations

from urllib.parse import urlparse

import pymysql


def connect(dsn: str):
    """Open a MySQL connection from a ``mysql://`` DSN."""
    u = urlparse(dsn)
    return pymysql.connect(
        host=u.hostname or "localhost",
        port=u.port or 3306,
        user=u.username or "root",
        password=u.password or "",
        database=(u.path or "").lstrip("/") or None,
        charset="utf8mb4",
        autocommit=False,
    )


def bulk_insert(cur, table: str, columns, rows, ignore: bool = False, batch: int = 1000) -> int:
    """Multi-row ``INSERT`` in batches (replaces psycopg2 ``execute_values``).

    ``ignore=True`` emits ``INSERT IGNORE`` (MySQL equivalent of
    ``ON CONFLICT DO NOTHING``) for dedupe on PK/unique keys.
    """
    rows = list(rows)
    if not rows:
        return 0
    cols = ", ".join(columns)
    ph = ", ".join(["%s"] * len(columns))
    ign = "IGNORE " if ignore else ""
    n = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        values = ", ".join(["(" + ph + ")"] * len(chunk))
        params = [v for row in chunk for v in row]
        cur.execute(f"INSERT {ign}INTO {table} ({cols}) VALUES {values}", params)
        n += len(chunk)
    return n
