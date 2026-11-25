#!/usr/bin/env python3
"""Export every VIEW in the MySQL `credit` database to a CSV file.

Writes one CSV per view into the output directory (default: the folder this
script lives in, i.e. sql_schema/).

MySQL has no materialized views, so the monthly_transaction_summary is a regular
TABLE and is not exported here; query it directly if needed.

Requirements:
    pip install pymysql

Usage:
    python etl_scripts/export_views.py --db mysql://user:pass@localhost:3306/credit
    python etl_scripts/export_views.py --outdir ./exports
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

DEFAULT_DSN = "mysql://root@localhost:3306/credit"


def get_views(cur, database: str) -> list[str]:
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'VIEW' ORDER BY table_name",
        (database,),
    )
    return [row[0] for row in cur.fetchall()]


def export_view(cur, view: str, outdir: str) -> int:
    cur.execute(f"SELECT * FROM {view}")
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()

    path = os.path.join(outdir, f"{view}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export each MySQL view to CSV.")
    parser.add_argument("--db", default=os.environ.get("DATABASE_URL", DEFAULT_DSN))
    parser.add_argument("--database", default="credit", help="database name (default: credit)")
    parser.add_argument("--outdir", default=os.path.dirname(os.path.abspath(__file__)))
    args = parser.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    conn = db.connect(args.db)
    try:
        with conn.cursor() as cur:
            views = get_views(cur, args.database)
            if not views:
                print(f"No views found in database {args.database!r}.", file=sys.stderr)
                return 1
            total = 0
            print(f"Exporting {len(views)} view(s) from {args.database!r} to {args.outdir}")
            for view in views:
                n = export_view(cur, view, args.outdir)
                total += n
                print(f"  {view:<32} -> {view}.csv  ({n} rows)")
            print(f"Done: {total} rows across {len(views)} file(s).")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
