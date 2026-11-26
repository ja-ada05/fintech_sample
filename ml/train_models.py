#!/usr/bin/env python3
"""Train and batch-score the fraud (LogReg baseline) and loan-default models (MySQL).

Three subcommands:

  train    Fit both models on the current `credit` schema and save joblib artifacts.
  score    Batch scoring: fraud -> upsert fraud_case.risk_score; default -> credit.prediction.
  predict  Single-row scoring (mirrors the real-time endpoint).

The tuned RandomForest fraud model lives in ml/train_fraud.py; this script keeps the
LogisticRegression fraud baseline plus the loan-default model.

Usage:
  python ml/train_models.py train   --db mysql://user:pass@localhost:3306/credit
  python ml/train_models.py score   --db mysql://user:pass@localhost:3306/credit [--threshold 0.5]
  python ml/train_models.py predict fraud --json '{"amount":120,"v1":-1.2, ...}'

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

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
DEFAULT_DSN = "mysql://root@localhost:3306/credit"

PREDICTION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS credit.prediction (
    prediction_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    entity_type   VARCHAR(20) NOT NULL,
    entity_id     BIGINT      NOT NULL,
    model         VARCHAR(40) NOT NULL,
    score         DECIMAL(5,4) NOT NULL,
    features      JSON,
    scored_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _sklearn():
    try:
        import joblib
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        return joblib, LogisticRegression, make_pipeline, StandardScaler
    except ImportError as exc:  # pragma: no cover
        sys.exit(f"Missing ML packages ({exc}). Install with:  pip install scikit-learn")


def _fraud_sql(labeled: bool) -> str:
    vcols = ", ".join(f"ct.{c}" for c in features.FRAUD_FEATURE_COLS)
    join = "JOIN" if labeled else "LEFT JOIN"
    return (
        f"SELECT ct.transaction_id, {vcols}, fc.is_fraud, "
        f"fc.transaction_id AS fc_txn "
        f"FROM credit.card_transaction ct "
        f"{join} credit.fraud_case fc ON fc.transaction_id = ct.transaction_id"
    )


def _fraud_df(conn, labeled: bool):
    import pandas as pd
    return pd.read_sql_query(_fraud_sql(labeled), conn)


def _default_df(conn):
    import pandas as pd
    return pd.read_sql_query("SELECT * FROM credit.v_default_features", conn)


def _train_model(name: str, X, y, version: int) -> bool:
    joblib, LogisticRegression, make_pipeline, StandardScaler = _sklearn()

    y = y.astype(int)
    counts = y.value_counts().to_dict()
    if len(counts) < 2 or min(counts.values()) < 2:
        print(f"[skip] {name}: need >= 2 samples of >= 2 classes (got {counts})")
        return False

    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
    model.fit(X, y)

    os.makedirs(MODELS_DIR, exist_ok=True)
    path = os.path.join(MODELS_DIR, f"{name}_v{version}.joblib")
    joblib.dump(model, path)
    print(f"[saved] {path}  (n={len(y)}, classes={counts})")
    return True


def cmd_train(args) -> int:
    conn = db.connect(args.db)
    try:
        df = _fraud_df(conn, labeled=True)
        if df.empty:
            print("[train fraud] no labeled transactions (JOIN fraud_case)")
        else:
            _train_model("fraud", df[features.FRAUD_FEATURE_COLS].fillna(0.0), df["is_fraud"], args.version)

        ddf = _default_df(conn)
        labeled = ddf[ddf["target"].notna()]
        if labeled.empty:
            print("[train default] no labeled applications (target is NULL)")
        else:
            _train_model("default", labeled[features.DEFAULT_FEATURE_COLS].fillna(0.0), labeled["target"], args.version)
    finally:
        conn.close()
    return 0


def _load_model(model: str, version: int):
    joblib, _, _, _ = _sklearn()
    path = os.path.join(MODELS_DIR, f"{model}_v{version}.joblib")
    if not os.path.exists(path):
        sys.exit(f"No model at {path}; run `train` first.")
    return joblib.load(path)


def cmd_score(args) -> int:
    import pandas as pd

    conn = db.connect(args.db)
    try:
        # ---- fraud: upsert fraud_case.risk_score --------------------------
        model = _load_model("fraud", args.version)
        df = _fraud_df(conn, labeled=False)
        if not df.empty:
            X = df[features.FRAUD_FEATURE_COLS].fillna(0.0)
            proba = model.predict_proba(X)[:, 1]
            new_cases, updates = [], []
            for (_, r), p in zip(df.iterrows(), proba):
                p = float(p)
                rule = "ml_score_high" if p >= args.threshold else None
                status = "open" if p >= args.threshold else "dismissed"
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
            print(f"[score fraud] scored {len(df)} transactions, {len(new_cases)} new cases")

        # ---- default: insert into credit.prediction ------------------------
        model = _load_model("default", args.version)
        ddf = _default_df(conn)
        if not ddf.empty:
            X = ddf[features.DEFAULT_FEATURE_COLS].fillna(0.0)
            proba = model.predict_proba(X)[:, 1]
            rows = [
                ("default", int(r["application_id"]), f"default_v{args.version}", float(p), None)
                for (_, r), p in zip(ddf.iterrows(), proba)
            ]
            with conn.cursor() as cur:
                cur.execute(PREDICTION_TABLE_SQL)
                db.bulk_insert(cur, "credit.prediction",
                               ["entity_type", "entity_id", "model", "score", "features"], rows)
            print(f"[score default] scored {len(ddf)} applications")

        conn.commit()
    finally:
        conn.close()
    return 0


def cmd_predict(args) -> int:
    model = _load_model(args.model, args.version)
    data = json.loads(args.json)
    cols = features.FRAUD_FEATURE_COLS if args.model == "fraud" else features.DEFAULT_FEATURE_COLS
    vec = features.build_vector(data, cols)
    p = model.predict_proba([vec])[0]
    band = "HIGH" if p[1] >= 0.7 else ("MEDIUM" if p[1] >= 0.3 else "LOW")
    print(f"score={p[1]:.4f}  band={band}")
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=os.environ.get("DATABASE_URL", DEFAULT_DSN))

    parser = argparse.ArgumentParser(description="Train and batch-score the fraud/default models.",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, parents=[common])
    parser.add_argument("--version", type=int, default=1, help="model version (default 1)")

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("train", help="fit both models and save artifacts", parents=[common])
    sp = sub.add_parser("score", help="batch-score the current data", parents=[common])
    sp.add_argument("--threshold", type=float, default=0.5, help="fraud alert threshold")
    pp = sub.add_parser("predict", help="single-row score (parity check)", parents=[common])
    pp.add_argument("model", choices=["fraud", "default"])
    pp.add_argument("--json", required=True, help="feature values as a JSON object")

    args = parser.parse_args(argv)
    return {"train": cmd_train, "score": cmd_score, "predict": cmd_predict}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
