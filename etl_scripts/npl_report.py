#!/usr/bin/env python3
"""NPL compliance report: flag non-performing loans and emit a summary + flagged list.

Reads the npl schema (populated by npl_export.py) and produces:
  * npl_outputs/npl_flagged_loans.csv  — every non-performing loan with severity/DPD/exposure
  * npl_outputs/npl_summary.json       — aggregate KPIs (NPL count, ratio, exposure, by severity)

Usage:
  python etl_scripts/npl_report.py --db postgresql://user:pass@localhost:5432/db
"""
from __future__ import annotations

import argparse
import csv
import json
import os

import psycopg2

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "npl_outputs")

FLAGGED_SQL = """
SELECT l.loan_identifier,
       c.name_of_counterparty,
       l.loan_status,
       l.severity,
       l.nonperforming_reason,
       l.days_in_pastdue,
       l.principal_balance,
       l.current_interest_rate,
       l.date_of_origination,
       l.original_maturity_date,
       l.date_of_default,
       l.product_type,
       l.loan_currency,
       e.enforcement_description
FROM npl.loan l
JOIN npl.counterparty c ON c.counterparty_identifier = l.counterparty_identifier
LEFT JOIN npl.enforcement e ON e.counterparty_identifier = l.counterparty_identifier
WHERE l.loan_status = 'non_performing'
ORDER BY l.principal_balance DESC;
"""

KPI_SQL = """
SELECT count(*) AS total_loans,
       count(*) FILTER (WHERE loan_status = 'non_performing') AS npl_count,
       coalesce(sum(principal_balance), 0) AS total_exposure,
       coalesce(sum(principal_balance) FILTER (WHERE loan_status = 'non_performing'), 0) AS npl_exposure
FROM npl.loan;
"""

SEVERITY_SQL = """
SELECT coalesce(severity, 'performing') AS severity,
       count(*) AS count,
       coalesce(sum(principal_balance), 0) AS exposure
FROM npl.loan
GROUP BY 1
ORDER BY 1;
"""


def main():
    p = argparse.ArgumentParser(description="Flag NPL loans and emit the compliance report.")
    p.add_argument("--db", default=os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"))
    args = p.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    conn = psycopg2.connect(args.db)
    try:
        with conn.cursor() as cur:
            cur.execute(KPI_SQL)
            kpi = dict(zip([d.name for d in cur.description], cur.fetchone()))
            cur.execute(SEVERITY_SQL)
            severity = [{"severity": r[0], "count": int(r[1]), "exposure": float(r[2])} for r in cur.fetchall()]
            cur.execute(FLAGGED_SQL)
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()

        # ---- CSV ----
        csv_path = os.path.join(OUT_DIR, "npl_flagged_loans.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow(["" if v is None else v for v in r])

        # ---- JSON ----
        total = int(kpi["total_loans"])
        npl_count = int(kpi["npl_count"])
        summary = {
            "report": "NPL compliance report",
            "total_loans": total,
            "npl_count": npl_count,
            "npl_ratio_pct": round(100.0 * npl_count / total, 2) if total else 0.0,
            "total_exposure": float(kpi["total_exposure"]),
            "npl_exposure": float(kpi["npl_exposure"]),
            "by_severity": severity,
            "flagged_loans_file": "npl_flagged_loans.csv",
        }
        json_path = os.path.join(OUT_DIR, "npl_summary.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        # ---- console ----
        print("=== NPL compliance report ===")
        print(f"total loans:        {total}")
        print(f"NPL count:          {npl_count}  ({summary['npl_ratio_pct']}%)")
        print(f"NPL exposure:       {summary['npl_exposure']:,.2f}  /  total {summary['total_exposure']:,.2f}")
        print("by severity:")
        for s in severity:
            print(f"  {s['severity']:<12s} n={s['count']:<6d} exposure={s['exposure']:,.2f}")
        print(f"top NPL exposures:")
        for r in rows[:5]:
            print(f"  loan {r[0]:<10s}  {r[5]} DPD  ${r[6]:>12,.2f}  ({r[3]})")
        print(f"wrote {csv_path} ({len(rows)} rows)")
        print(f"wrote {json_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
