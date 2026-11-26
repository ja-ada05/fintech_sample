#!/usr/bin/env python3
"""Customer profiling: clustering -> human labels -> Random Forest classifier.

Pipeline subcommands:
  extract   Aggregate credit_card_balance into one row per customer -> ml/data/customer_features.csv
  cluster   Standardize + KMeans; append cluster labels; save scaler/clusterer; show elbow/silhouette
  report    Per-cluster interpretable stats + draft cluster_labels.json (for you to name the clusters)
  train     Train a tuned RandomForest on the labeled data -> deployable model + metadata
  predict   Classify one customer from a feature vector (mirrors the real-time endpoint)

Usage:
  python ml/train_customer_profiles.py extract --db postgresql://user:pass@localhost:5432/db
  python ml/train_customer_profiles.py cluster --k 5
  python ml/train_customer_profiles.py report
  python ml/train_customer_profiles.py train
  python ml/train_customer_profiles.py predict --json '{"credit_limit_max":15000, ...}'

Dependencies:  pip install scikit-learn pymysql   (plus pandas)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Support both `python ml/train_customer_profiles.py` and `python -m ml.train_customer_profiles`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

try:
    from ml import customer_features
except ImportError:  # pragma: no cover
    import customer_features

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
MODELS_DIR = os.path.join(HERE, "models")

DATA_FILE = os.path.join(DATA_DIR, "customer_features.csv")
CLUSTER_PROFILES_FILE = os.path.join(DATA_DIR, "cluster_profiles.csv")
CLUSTER_LABELS_FILE = os.path.join(DATA_DIR, "cluster_labels.json")
MODEL_FILE = os.path.join(MODELS_DIR, "customer_profile_rf_v1.joblib")
META_FILE = os.path.join(MODELS_DIR, "customer_profile_meta_v1.json")
CLUSTERER_FILE = os.path.join(MODELS_DIR, "customer_profile_cluster_v1.joblib")

DEFAULT_DSN = "mysql://root@localhost:3306/credit"


def _load_data(path: str = DATA_FILE):
    import pandas as pd

    return pd.read_csv(path)


def cmd_extract(args) -> int:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = db.connect(args.db)
    try:
        df = customer_features.extract(conn)
    finally:
        conn.close()
    if df.empty:
        print("No credit_card_balance rows found.", file=sys.stderr)
        return 1
    df.to_csv(DATA_FILE, index=False)
    print(f"[extract] {len(df)} customers -> {DATA_FILE}")
    print(f"[extract] features: {customer_features.CUSTOMER_FEATURE_COLS}")
    return 0


def _sweep(X_scaled):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    print("k  inertia  silhouette")
    for k in range(2, 11):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        sil = silhouette_score(X_scaled, labels)
        print(f"{k:2d} {km.inertia_:>12.1f} {sil:>10.3f}")


def cmd_cluster(args) -> int:
    import joblib
    import pandas as pd
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    df = _load_data()
    X = df[customer_features.CUSTOMER_FEATURE_COLS].fillna(0.0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    _sweep(X_scaled)

    km = KMeans(n_clusters=args.k, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)
    sil = silhouette_score(X_scaled, labels)
    print(f"[cluster] k={args.k} inertia={km.inertia_:.1f} silhouette={sil:.3f}")

    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump({"scaler": scaler, "kmeans": km, "k": args.k, "silhouette": sil}, CLUSTERER_FILE)
    print(f"[cluster] saved {CLUSTERER_FILE}")

    df["cluster"] = labels.astype(int)
    df.to_csv(DATA_FILE, index=False)
    print(f"[cluster] updated {DATA_FILE} with 'cluster' column")
    return 0


def cmd_report(args) -> int:
    import pandas as pd

    df = _load_data()
    if "cluster" not in df.columns:
        print("Run 'cluster' first.", file=sys.stderr)
        return 1

    feat_cols = [c for c in customer_features.CUSTOMER_FEATURE_COLS if c in df.columns]
    overall_mean = df[feat_cols].mean()
    overall_std = df[feat_cols].std().replace(0, 1.0)

    rows = []
    labels_draft = {}
    for cl in sorted(df["cluster"].unique()):
        sub = df[df["cluster"] == cl]
        means = sub[feat_cols].mean()
        z = (means - overall_mean) / overall_std
        top = z.abs().sort_values(ascending=False).head(3).index.tolist()
        row = {"cluster": int(cl), "size": int(len(sub))}
        for c in feat_cols:
            row[c] = round(float(means[c]), 2)
        row["top_features"] = ", ".join(top)
        rows.append(row)
        labels_draft[str(int(cl))] = {"name": f"Cluster {int(cl)}", "description": ""}
        print(f"cluster {int(cl):2d}  n={len(sub):5d}  top: {', '.join(top)}")

    os.makedirs(DATA_DIR, exist_ok=True)
    pd.DataFrame(rows).to_csv(CLUSTER_PROFILES_FILE, index=False)
    with open(CLUSTER_LABELS_FILE, "w", encoding="utf-8") as f:
        json.dump(labels_draft, f, indent=2)
    print(f"[report] wrote {CLUSTER_PROFILES_FILE}")
    print(f"[report] wrote {CLUSTER_LABELS_FILE}  <- edit name/description per cluster, then run 'train'")
    return 0


def _load_labels() -> dict:
    if os.path.exists(CLUSTER_LABELS_FILE):
        with open(CLUSTER_LABELS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def cmd_train(args) -> int:
    import joblib
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
    from sklearn.model_selection import RandomizedSearchCV, train_test_split

    df = _load_data()
    if "cluster" not in df.columns:
        print("Run 'cluster' first.", file=sys.stderr)
        return 1

    # Fit on numpy arrays (no feature names) so the deployed predict path
    # (build_vector -> list) matches without a sklearn feature-name warning.
    X = df[customer_features.CUSTOMER_FEATURE_COLS].fillna(0.0).to_numpy()
    y = df["cluster"].astype(int).to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    grid = {
        "n_estimators": [100, 200, 400],
        "max_depth": [None, 10, 20, 30],
        "min_samples_leaf": [1, 2, 4],
        "max_features": ["sqrt", "log2"],
        "class_weight": ["balanced", None],
    }
    search = RandomizedSearchCV(
        RandomForestClassifier(random_state=42),
        grid,
        n_iter=20,
        cv=3,
        scoring="f1_macro",
        n_jobs=1,  # single-process: sandbox/CI environments block joblib's multiprocessing pipes
        random_state=42,
    )
    search.fit(X_train, y_train)
    best = search.best_estimator_

    y_pred = best.predict(X_test)
    importances = dict(
        sorted(
            zip(customer_features.CUSTOMER_FEATURE_COLS, best.feature_importances_),
            key=lambda kv: -kv[1],
        )
    )

    labels = _load_labels()
    classes = {
        str(c): labels.get(str(c), {}).get("name", f"Cluster {c}")
        for c in sorted({int(x) for x in y})
    }

    meta = {
        "model": "customer_profile_rf",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": int(len(df)),
        "features": customer_features.CUSTOMER_FEATURE_COLS,
        "best_params": search.best_params_,
        "metrics": {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "macro_f1": float(f1_score(y_test, y_pred, average="macro")),
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
            "classification_report": classification_report(y_test, y_pred, output_dict=True),
        },
        "feature_importances": {k: float(v) for k, v in importances.items()},
        "classes": classes,
        "random_state": 42,
    }

    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(best, MODEL_FILE)
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"[train] accuracy={meta['metrics']['accuracy']:.3f} "
          f"macro_f1={meta['metrics']['macro_f1']:.3f}")
    print(f"[train] best params: {search.best_params_}")
    print("[train] top feature importances:")
    for feat, imp in list(importances.items())[:5]:
        print(f"        {feat:<26s} {imp:.3f}")
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

    data = json.loads(args.json)
    vec = customer_features.build_vector(data)
    cls = int(model.predict([vec])[0])
    proba = model.predict_proba([vec])[0]
    name = meta.get("classes", {}).get(str(cls), f"Cluster {cls}")
    print(f"profile={name}  (cluster={cls}, probability={proba[cls]:.3f})")
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=os.environ.get("DATABASE_URL", DEFAULT_DSN))

    p = argparse.ArgumentParser(
        description="Customer profiling via clustering -> Random Forest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("extract", help="aggregate credit_card_balance per customer -> CSV", parents=[common])
    cp = sub.add_parser("cluster", help="StandardScaler + KMeans, append cluster labels", parents=[common])
    cp.add_argument("--k", type=int, default=5)
    sub.add_parser("report", help="per-cluster stats + draft cluster_labels.json", parents=[common])
    sub.add_parser("train", help="tuned RandomForest on labeled data -> model + metadata", parents=[common])
    pp = sub.add_parser("predict", help="classify one customer (parity check)", parents=[common])
    pp.add_argument("--json", required=True, help="feature values as a JSON object")

    args = p.parse_args(argv)
    return {
        "extract": cmd_extract,
        "cluster": cmd_cluster,
        "report": cmd_report,
        "train": cmd_train,
        "predict": cmd_predict,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
