"""Customer-profiling feature definitions.

Single source of truth for the customer-level credit-card features used by the
clustering -> random-forest pipeline. One row per customer (``application_id`` =
``SK_ID_CURR``), aggregated from ``credit.credit_card_balance``.

Used by ``train_customer_profiles.py`` (training + batch) and the FastAPI
real-time endpoint, so train and serve use identical, canonically-ordered features.
"""
from __future__ import annotations

from typing import Mapping, Sequence

# Canonical ordered feature list (must match EXTRACT_SQL's SELECT order).
CUSTOMER_FEATURE_COLS: list[str] = [
    "credit_limit_max",
    "credit_limit_mean",
    "balance_mean",
    "balance_max",
    "utilization_mean",
    "spend_total",
    "spend_pos_total",
    "spend_other_total",
    "cash_advance_total",
    "cash_advance_mean",
    "n_drawings_total",
    "n_atm_drawings_total",
    "n_pos_drawings_total",
    "payment_mean",
    "install_regularity_mean",
    "dpd_max",
    "ever_delinquent",
    "n_months",
]

# Aggregate credit_card_balance into one row per customer.
EXTRACT_SQL = """
SELECT application_id,
       MAX(amt_credit_limit_actual)  AS credit_limit_max,
       AVG(amt_credit_limit_actual)  AS credit_limit_mean,
       AVG(amt_balance)              AS balance_mean,
       MAX(amt_balance)              AS balance_max,
       AVG(CASE WHEN amt_credit_limit_actual > 0
                THEN amt_balance / amt_credit_limit_actual ELSE 0 END) AS utilization_mean,
       COALESCE(SUM(amt_drawings_current), 0)       AS spend_total,
       COALESCE(SUM(amt_drawings_pos_current), 0)   AS spend_pos_total,
       COALESCE(SUM(amt_drawings_other_current), 0) AS spend_other_total,
       COALESCE(SUM(amt_drawings_atm_current), 0)   AS cash_advance_total,
       AVG(amt_drawings_atm_current)       AS cash_advance_mean,
       COALESCE(SUM(cnt_drawings_current), 0)       AS n_drawings_total,
       COALESCE(SUM(cnt_drawings_atm_current), 0)   AS n_atm_drawings_total,
       COALESCE(SUM(cnt_drawings_pos_current), 0)   AS n_pos_drawings_total,
       AVG(amt_payment_total_current)      AS payment_mean,
       AVG(amt_inst_min_regularity)        AS install_regularity_mean,
       MAX(sk_dpd)                         AS dpd_max,
       MAX(CASE WHEN sk_dpd > 0 THEN 1 ELSE 0 END) AS ever_delinquent,
       COUNT(months_balance)               AS n_months
FROM credit.credit_card_balance
GROUP BY application_id
"""


def build_vector(
    values: Mapping[str, float],
    cols: Sequence[str] = CUSTOMER_FEATURE_COLS,
    fill: float = 0.0,
) -> list[float]:
    """Return a customer feature vector in canonical column order."""
    out: list[float] = []
    for col in cols:
        v = values.get(col)
        out.append(fill if v is None else float(v))
    return out


def extract(conn):
    """Aggregate credit_card_balance into a per-customer DataFrame."""
    import pandas as pd

    return pd.read_sql_query(EXTRACT_SQL, conn)
