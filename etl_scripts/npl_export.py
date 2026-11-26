#!/usr/bin/env python3
"""ETL: map credit.loan_origination into the npl (openNPL EBA mirror) schema.

Creates the npl schema (from sql_schema/npl_schema.sql) and loads:
  * counterparty         (one synthetic counterparty per loan — source is anonymised)
  * loan                 (all loans, with NPL status + severity + days-past-due)
  * enforcement          (default / charged-off loans)
  * historical_repayment / forbearance  (left empty — no payment/forbearance data)

Usage:
  python etl_scripts/npl_export.py --db postgresql://user:pass@localhost:5432/db
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_FILE = os.path.join(os.path.dirname(HERE), "sql_schema", "npl_schema.sql")

COUNTERPARTY_SQL = """
INSERT INTO npl.counterparty
    (counterparty_identifier, name_of_counterparty, legal_type_of_counterparty)
SELECT DISTINCT 'CP-' || lo.loan_id, 'Borrower ' || lo.loan_id, 'Private Individual'
FROM credit.loan_origination lo;
"""

LOAN_SQL = """
INSERT INTO npl.loan
    (loan_identifier, counterparty_identifier, date_of_origination, loan_currency,
     principal_balance, origination_amount, current_interest_rate, original_maturity_date,
     days_in_pastdue, date_of_default, loan_status, nonperforming_reason, severity,
     product_type, asset_class, total_pastdue_amount, forbearance_measure)
SELECT
    lo.loan_id::text,
    'CP-' || lo.loan_id,
    lo.issue_date,
    'USD',
    lo.loan_amount,
    lo.loan_amount,
    lo.interest_rate,
    (lo.issue_date + make_interval(months => lo.term_months))::date,
    CASE ls.name
        WHEN 'late_16_30' THEN 23
        WHEN 'late_31_120' THEN 75
        WHEN 'delinquent' THEN 60
        WHEN 'default' THEN 120
        WHEN 'charged_off' THEN 180
        ELSE 0
    END,
    CASE WHEN ls.name IN ('default', 'charged_off')
         THEN (lo.issue_date + make_interval(months => 12))::date END,
    CASE WHEN ls.is_npl THEN 'non_performing' ELSE 'performing' END,
    CASE ls.name
        WHEN 'late_16_30' THEN 'days past due (16-30)'
        WHEN 'late_31_120' THEN 'days past due (31-120)'
        WHEN 'delinquent' THEN 'days past due'
        WHEN 'default' THEN 'defaulted (CRR Art.178)'
        WHEN 'charged_off' THEN 'charged off'
    END,
    CASE ls.name
        WHEN 'late_16_30' THEN 'watch'
        WHEN 'late_31_120' THEN 'substandard'
        WHEN 'delinquent' THEN 'substandard'
        WHEN 'default' THEN 'doubtful'
        WHEN 'charged_off' THEN 'loss'
    END,
    lo.purpose,
    'Consumer',
    NULL,
    false
FROM credit.loan_origination lo
JOIN credit.ref_loan_status ls ON ls.loan_status_id = lo.loan_status_id;
"""

ENFORCEMENT_SQL = """
INSERT INTO npl.enforcement
    (enforcement_identifier, counterparty_identifier, indicator_of_enforcement, enforcement_description)
SELECT
    'ENF-' || lo.loan_id,
    'CP-' || lo.loan_id,
    true,
    'Enforcement eligible — loan status: ' || ls.name
FROM credit.loan_origination lo
JOIN credit.ref_loan_status ls ON ls.loan_status_id = lo.loan_status_id
WHERE ls.name IN ('default', 'charged_off');
"""


def create_schema(conn):
    sql = open(SCHEMA_FILE, encoding="utf-8").read()
    for stmt in sql.split(";"):
        # strip comment lines and skip fragments that are nothing but comments/whitespace
        lines = [ln for ln in stmt.splitlines() if ln.strip() and not ln.lstrip().startswith("--")]
        body = "\n".join(lines).strip()
        if body:
            with conn.cursor() as cur:
                cur.execute(body)
    conn.commit()


def main():
    p = argparse.ArgumentParser(description="Load credit.loan_origination into the npl schema.")
    p.add_argument("--db", default=os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"))
    args = p.parse_args()

    conn = psycopg2.connect(args.db)
    try:
        create_schema(conn)
        with conn.cursor() as cur:
            cur.execute(COUNTERPARTY_SQL)
            print(f"[counterparty] {cur.rowcount} rows")
            cur.execute(LOAN_SQL)
            print(f"[loan] {cur.rowcount} rows")
            cur.execute(ENFORCEMENT_SQL)
            print(f"[enforcement] {cur.rowcount} rows")
        conn.commit()
        print("npl schema loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
