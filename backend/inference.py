"""Load the trained models once (cached) and expose prediction helpers."""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache

import joblib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml import customer_features  # noqa: E402
from ml import features  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "ml", "models")
DATA_DIR = os.path.join(ROOT, "ml", "data")

FRAUD_MODEL = os.path.join(MODELS_DIR, "fraud_rf_v1.joblib")
FRAUD_META = os.path.join(MODELS_DIR, "fraud_rf_meta_v1.json")
PROFILE_MODEL = os.path.join(MODELS_DIR, "customer_profile_rf_v1.joblib")
PROFILE_META = os.path.join(MODELS_DIR, "customer_profile_meta_v1.json")
CLUSTER_LABELS = os.path.join(DATA_DIR, "cluster_labels.json")


@lru_cache(maxsize=1)
def _fraud_model():
    if not os.path.exists(FRAUD_MODEL):
        raise RuntimeError(
            f"Fraud model not found ({FRAUD_MODEL}). Run `python ml/train_fraud.py train` first."
        )
    return joblib.load(FRAUD_MODEL)


@lru_cache(maxsize=1)
def _profile_model():
    if not os.path.exists(PROFILE_MODEL):
        raise RuntimeError(
            f"Profile model not found ({PROFILE_MODEL}). Run `python ml/train_customer_profiles.py train` first."
        )
    return joblib.load(PROFILE_MODEL)


def load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _cluster_name(cluster: int) -> str:
    labels = load_json(CLUSTER_LABELS)
    if isinstance(labels, dict):
        name = labels.get(str(cluster), labels.get(cluster))
        if name:
            return str(name)
    return f"cluster_{cluster}"


def predict_fraud(data: dict, threshold: float | None = None) -> dict:
    meta = load_json(FRAUD_META)
    thr = threshold if threshold is not None else float(meta.get("threshold", 0.5))
    vec = features.build_vector(data, features.FRAUD_FEATURE_COLS)
    p = float(_fraud_model().predict_proba([vec])[0][1])
    return {
        "fraud_probability": round(p, 4),
        "threshold": round(thr, 4),
        "verdict": "fraud" if p >= thr else "not_fraud",
    }


def predict_profile(data: dict) -> dict:
    vec = customer_features.build_vector(data, customer_features.CUSTOMER_FEATURE_COLS)
    model = _profile_model()
    cluster = int(model.predict([vec])[0])
    confidence = float(model.predict_proba([vec])[0].max())
    return {
        "cluster_id": cluster,
        "cluster_name": _cluster_name(cluster),
        "confidence": round(confidence, 4),
    }
