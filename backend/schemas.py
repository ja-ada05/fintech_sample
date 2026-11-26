"""Pydantic request/response models.

The prediction request models are generated dynamically from the canonical
feature lists in ``ml/features.py`` and ``ml/customer_features.py``, so the API
contract always matches what the models were trained on (single source of truth
and real input validation).
"""
from __future__ import annotations

import os
import sys

from pydantic import BaseModel, create_model

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml import customer_features  # noqa: E402
from ml import features  # noqa: E402

CustomerProfileInput = create_model(
    "CustomerProfileInput",
    **{name: (float, ...) for name in customer_features.CUSTOMER_FEATURE_COLS},
)

FraudInput = create_model(
    "FraudInput",
    **{name: (float, ...) for name in features.FRAUD_FEATURE_COLS},
)


class FraudPrediction(BaseModel):
    fraud_probability: float
    threshold: float
    verdict: str


class ProfilePrediction(BaseModel):
    cluster_id: int
    cluster_name: str
    confidence: float


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
