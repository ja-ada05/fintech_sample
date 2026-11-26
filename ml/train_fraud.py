#!/usr/bin/env python3
"""Fraud detection: train a tuned Random Forest on labeled card transactions (MySQL).

Ground truth: credit.fraud_case.is_fraud (the ULB creditcard.csv 'Class' label: 1=fraud, 0=legit).
Features: credit.card_transaction.amount + v1..v28 (29 cols -> ml.features.FRAUD_FEATURE_COLS).

Subcommands:
  extract   pull labeled transactions -> ml/data/fraud_features.csv
  train     RandomForest + RandomizedSearchCV (class_weight=balanced) -> model + metadata
  predict   score one transaction from a JSON file (parity check)
  score     batch: upsert fraud_case.risk_score (+ rule/status by threshold)

Usage:
  python ml/train_fraud.py extract --db mysql://user:pass@localhost:3306/credit
  python ml/train_fraud.py train
  python ml/train_fraud.py predict --json-file ml/data/sample_tx.json
  python ml/train_fraud.py score --db mysql://user:pass@localhost:3306/credit --threshold 0.5

Dependencies: pip install scikit-learn pymysql (plus pandas)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

try:
    from ml import features
except ImportError:  # pragma: no cover
    import features

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
MODELS_DIR = os.path.join(HERE, "models")
DATA_FILE = os.path.join(DATA_DIR, "fraud_features.csv")
MODEL_FILE = os.path.join(MODELS_DIR, "fraud_rf_v1.joblib")
META_FILE = os.path.join(MODELS_DIR, "fraud_rf_meta_v1.json")
DEFAULT_DSN = "mysql://root@localhost:3306/credit"


def _fraud_sql(labeled_only: bool = True) -> str:
    feat_cols = ", ".join(f"ct.{c}" for c in features.FRAUD_FEATURE_COLS)
    join = "JOIN" if labeled_only else "LEFT JOIN"
    return (
        f"SELECT ct.transaction_id, {feat_cols}, fc.is_fraud, "
        f"fc.transaction_id AS fc_txn "
        f"FROM credit.card_transaction ct "
        f"{join} credit.fraud_case fc ON fc.transaction_id = ct.transaction_id"
    )


def cmd_extract(args) -> int:
    import pandas as pd

    os.makedirs(DATA_DIR, exist_ok=True)
    conn = db.connect(args.db)
    try:
        df = pd.read_sql_query(_fraud_sql(labeled_only=True), conn)
    finally:
        conn.close()
    if df.empty:
        print("No labeled transactions found.", file=sys.stderr)
        return 1
    df.to_csv(DATA_FILE, index=False)
    print(f"[extract] {len(df)} labeled transactions ({int(df['is_fraud'].sum())} fraud) -> {DATA_FILE}")
    print(f"[extract] features: {features.FRAUD_FEATURE_COLS}")
    return 0


def cmd_train(args) -> int:
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        average_precision_score,
        confusion_matrix,
        f1_score,
        precision_recall_curve,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from sklearn.model_selection import RandomizedSearchCV, train_test_split

    df = pd.read_csv(DATA_FILE)
    X = df[features.FRAUD_FEATURE_COLS].fillna(0.0).to_numpy()
    y = df["is_fraud"].astype(int).to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    grid = {
        "n_estimators": [100, 200, 400],
        "max_depth": [None, 10, 20, 30],
        "min_samples_leaf": [1, 2, 4],
        "max_features": ["sqrt", "log2"],
        "class_weight": ["balanced", "balanced_subsample"],
    }
    search = RandomizedSearchCV(
        RandomForestClassifier(random_state=42),
        grid,
        n_iter=20,
        cv=3,
        scoring="average_precision",
        n_jobs=1,
        random_state=42,
    )
    search.fit(X_train, y_train)
    best = search.best_estimator_

    proba = best.predict_proba(X_test)[:, 1]
    y_pred = (proba >= 0.5).astype(int)

    prec, rec, thresh = precision_recall_curve(y_test, proba)
    f1s = 2 * prec * rec / (prec + rec + 1e-9)
    best_idx = int(np.argmax(f1s))
    best_thr = float(thresh[best_idx]) if best_idx < len(thresh) else 0.5

    importances = dict(
        sorted(zip(features.FRAUD_FEATURE_COLS, best.feature_importances_), key=lambda kv: -kv[1])
    )

    meta = {
        "model": "fraud_rf",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": int(len(df)),
        "n_fraud": int(y.sum()),
        "fraud_rate": float(y.mean()),
        "features": features.FRAUD_FEATURE_COLS,
        "best_params": search.best_params_,
        "threshold": 0.5,
        "best_f1_threshold": best_thr,
        "metrics": {
            "pr_auc": float(average_precision_score(y_test, proba)),
            "roc_auc": float(roc_auc_score(y_test, proba)),
            "precision_at_0.5": float(precision_score(y_test, y_pred, zero_division=0)),
            "recall_at_0.5": float(recall_score(y_test, y_pred)),
            "f1_at_0.5": float(f1_score(y_test, y_pred)),
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        },
        "feature_importances": {k: float(v) for k, v in importances.items()},
        "random_state": 42,
    }

    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(best, MODEL_FILE)
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    m = meta["metrics"]
    print(f"[train] PR-AUC={m['pr_auc']:.3f}  ROC-AUC={m['roc_auc']:.3f}  F1@0.5={m['f1_at_0.5']:.3f}")
    print(f"[train] precision@0.5={m['precision_at_0.5']:.3f}  recall@0.5={m['recall_at_0.5']:.3f}")
    print(f"[train] confusion matrix (rows=true): {m['confusion_matrix']}")
    print(f"[train] best params: {search.best_params_}")
    print(f"[train] suggested threshold (max F1): {best_thr:.3f}")
    print("[train] top feature importances:")
    for feat, imp in list(importances.items())[:5]:
        print(f"        {feat:<8s} {imp:.3f}")
    print(f"[train] saved {MODEL_FILE}")
    print(f"[train] saved {META_FILE}")
    return 0


def cmd_predict(args) -> int:
    import joblib

    if not os.path.exists(MODEL_FILE):
        print("Run 'train' first.", file=sys.stderr)
        return 1
    model = joblib.load(MODEL_FILE)
    with open(META_FILE, encoding="utf-8") as f:
        meta = json.load(f)
    with open(args.json_file, encoding="utf-8") as f:
        data = json.load(f)

    vec = features.build_vector(data, features.FRAUD_FEATURE_COLS)
    proba = float(model.predict_proba([vec])[0][1])
    verdict = "fraud" if proba >= meta.get("threshold", 0.5) else "not fraud"
    print(f"fraud_probability={proba:.4f}  verdict={verdict}")
    return 0


def cmd_score(args) -> int:
    import joblib
    import pandas as pd

    if not os.path.exists(MODEL_FILE):
        print("Run 'train' first.", file=sys.stderr)
        return 1
    model = joblib.load(MODEL_FILE)
    with open(META_FILE, encoding="utf-8") as f:
        meta = json.load(f)
    threshold = args.threshold if args.threshold is not None else meta.get("threshold", 0.5)

    conn = db.connect(args.db)
    try:
        df = pd.read_sql_query(_fraud_sql(labeled_only=False), conn)
        if df.empty:
            print("No transactions to score.", file=sys.stderr)
            return 1
        X = df[features.FRAUD_FEATURE_COLS].fillna(0.0).to_numpy()
        proba = model.predict_proba(X)[:, 1]

        new_cases, updates = [], []
        for (_, r), p in zip(df.iterrows(), proba):
            p = float(p)
            rule = "ml_rf_score" if p >= threshold else None
            status = "open" if p >= threshold else "dismissed"
            tid = int(r["transaction_id"])
            if pd.isna(r["fc_txn"]):
                new_cases.append((tid, False, p, rule, status))
            else:
                updates.append((p, rule, status, tid))

        with conn.cursor() as cur:
            if new_cases:
                db.bulk_insert(cur, "credit.fraud_case",
                               ["transaction_id", "is_fraud", "risk_score", "rule_triggered", "status"],
                               new_cases)
            if updates:
                cur.executemany(
                    "UPDATE credit.fraud_case SET risk_score=%s, rule_triggered=%s, status=%s "
                    "WHERE transaction_id=%s",
                    updates,
                )
        conn.commit()
        n_high = int((proba >= threshold).sum())
        print(f"[score] scored {len(df)} transactions; {n_high} flagged at threshold={threshold:.3f}; "
              f"{len(new_cases)} new cases, {len(updates)} updated")
    finally:
        conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=os.environ.get("DATABASE_URL", DEFAULT_DSN))

    p = argparse.ArgumentParser(
        description="Fraud detection via tuned Random Forest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract", help="labeled transactions -> CSV", parents=[common])
    sub.add_parser("train", help="RF + tuning -> model + metadata", parents=[common])
    pp = sub.add_parser("predict", help="score one transaction (parity check)", parents=[common])
    pp.add_argument("--json-file", required=True, help="path to a JSON file of feature values")
    sp = sub.add_parser("score", help="batch score -> fraud_case.risk_score", parents=[common])
    sp.add_argument("--threshold", type=float, default=None, help="override the stored threshold")

    args = p.parse_args(argv)
    return {
        "extract": cmd_extract,
        "train": cmd_train,
        "predict": cmd_predict,
        "score": cmd_score,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
