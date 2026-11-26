"""Shared feature definitions for the fraud and loan-default models.

This module is the single source of truth for feature columns and vector
construction. It is imported by BOTH:

  * ``train_models.py`` (training + batch scoring), and
  * the FastAPI real-time endpoint (``/predict/*``),

so that training and serving use identical, canonically-ordered features
(i.e. no train/serve skew).
"""
from __future__ import annotations

from typing import Mapping, Sequence

# ---------------------------------------------------------------------------
# Fraud model: one row per card transaction.
# Features = transaction amount + the 28 anonymised PCA components (v1..v28)
# stored on credit.card_transaction.
# ---------------------------------------------------------------------------
FRAUD_FEATURE_COLS: list[str] = ["amount"] + [f"v{i}" for i in range(1, 29)]
assert len(FRAUD_FEATURE_COLS) == 29

# ---------------------------------------------------------------------------
# Default model: mirrors the columns of the `v_default_features` view, minus
# the application_id / target columns.
# ---------------------------------------------------------------------------
DEFAULT_FEATURE_COLS: list[str] = [
    "amt_credit",
    "amt_annuity",
    "amt_goods_price",
    "amt_income_total",
    "days_employed",
    "days_birth",
    "cnt_children",
    "cnt_fam_members",
    "ext_source_1",
    "ext_source_2",
    "ext_source_3",
    "region_rating_client",
    "contract_type_id",
    "income_type_id",
    "education_type_id",
    "family_status_id",
    "housing_type_id",
    "occupation_type_id",
]


def build_vector(
    values: Mapping[str, float],
    cols: Sequence[str],
    fill: float = 0.0,
) -> list[float]:
    """Return a feature row in canonical column order.

    ``values`` maps column name -> value (from sliders or a DB row). Missing or
    ``None`` values are replaced by ``fill`` so the returned vector always has
    exactly ``len(cols)`` elements in ``cols`` order.
    """
    out: list[float] = []
    for col in cols:
        v = values.get(col)
        out.append(fill if v is None else float(v))
    return out


def fraud_vector(amount: float, pca: Sequence[float]) -> list[float]:
    """Build a fraud feature vector from ``amount`` and the 28 PCA values (v1..v28)."""
    if len(pca) != 28:
        raise ValueError(f"expected 28 PCA values, got {len(pca)}")
    values: dict[str, float] = {"amount": amount}
    values.update({f"v{i}": pca[i - 1] for i in range(1, 29)})
    return build_vector(values, FRAUD_FEATURE_COLS)


def default_vector(**features: float) -> list[float]:
    """Build a default-risk feature vector from keyword arguments."""
    return build_vector(features, DEFAULT_FEATURE_COLS)
