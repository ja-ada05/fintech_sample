"""FastAPI backend for FinSight Analytics.

Run from the repo root::

    uvicorn backend.main:app --reload

Then open http://localhost:8000/docs for the interactive OpenAPI UI.

Dependencies: ``pip install fastapi 'uvicorn[standard]' pymysql python-multipart``
(plus the ML deps in the repo-root ``requirements.txt``).
"""
from __future__ import annotations

import csv
import io
import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response

from . import auth, database, inference, schemas

# Views/tables that may be read verbatim through the generic viewer/export.
VIEW_WHITELIST = {
    "v_application_overview",
    "v_default_features",
    "v_loan_portfolio",
    "v_fraud_overview",
    "v_overdue_installments",
    "v_npl_export",
    "v_fraud_dashboard",
    "monthly_transaction_summary",
}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPL_SUMMARY = os.path.join(_ROOT, "npl_outputs", "npl_summary.json")
NPL_FLAGGED = os.path.join(_ROOT, "npl_outputs", "npl_flagged_loans.csv")


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth.ensure_users_table()
    auth.seed_default_admin()
    yield


app = FastAPI(title="FinSight Analytics API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
@app.post("/api/auth/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest):
    row = auth.authenticate(body.username, body.password)
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"access_token": auth.create_token(row["username"], row["role"]), "token_type": "bearer"}


@app.post("/api/auth/register")
def register(body: schemas.LoginRequest, user: dict = Depends(auth.get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins may register users")
    existing = database.query(
        "SELECT 1 FROM credit.users WHERE username = %s", (body.username,)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    database.execute(
        "INSERT INTO credit.users (username, password_hash, role) VALUES (%s, %s, %s)",
        (body.username, auth.hash_password(body.password), "analyst"),
    )
    return {"status": "created", "username": body.username}


@app.get("/api/me")
def me(user: dict = Depends(auth.get_current_user)):
    return {"username": user.get("sub"), "role": user.get("role")}


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------
@app.get("/api/dashboard/kpis")
def dashboard_kpis():
    loans = database.query(
        """
        SELECT COUNT(*) AS total_loans,
               COALESCE(SUM(loan_amount), 0) AS total_exposure,
               COALESCE(SUM(CASE WHEN loan_status_id IN (5, 6, 7, 8) THEN 1 ELSE 0 END), 0) AS npl_count,
               COALESCE(AVG(interest_rate), 0) AS avg_interest_rate
        FROM credit.loan_origination
        """
    )[0]
    fraud = database.query(
        "SELECT COUNT(*) AS total_transactions, COALESCE(SUM(is_fraud), 0) AS fraud_count "
        "FROM credit.fraud_case"
    )[0]

    total_loans = int(loans["total_loans"] or 0)
    total_exposure = float(loans["total_exposure"] or 0)
    npl_count = int(loans["npl_count"] or 0)
    total_tx = int(fraud["total_transactions"] or 0)
    fraud_count = int(fraud["fraud_count"] or 0)

    return {
        "total_loans": total_loans,
        "total_exposure": round(total_exposure, 2),
        "npl_count": npl_count,
        "npl_rate": round(npl_count / total_loans, 4) if total_loans else 0,
        "avg_interest_rate": round(float(loans["avg_interest_rate"] or 0), 4),
        "total_transactions": total_tx,
        "fraud_count": fraud_count,
        "fraud_rate": round(fraud_count / total_tx, 4) if total_tx else 0,
    }


@app.get("/api/dashboard/purpose-breakdown")
def purpose_breakdown():
    rows = database.query(
        """
        SELECT purpose, COUNT(*) AS loans, COALESCE(SUM(loan_amount), 0) AS principal
        FROM credit.loan_origination
        WHERE purpose IS NOT NULL
        GROUP BY purpose
        ORDER BY principal DESC
        """
    )
    return {"rows": rows}


@app.get("/api/dashboard/monthly-transactions")
def monthly_transactions():
    rows = database.query(
        "SELECT month, txn_count, total_amount, fraud_count "
        "FROM credit.monthly_transaction_summary ORDER BY month"
    )
    return {"rows": rows}


@app.get("/api/views/{name}")
def get_view(name: str, limit: int = 1000):
    if name not in VIEW_WHITELIST:
        raise HTTPException(status_code=404, detail=f"Unknown view: {name}")
    limit = min(max(int(limit), 1), 10000)
    rows = database.query(f"SELECT * FROM credit.{name} LIMIT {limit}")
    return {"view": name, "count": len(rows), "rows": rows}


# --------------------------------------------------------------------------
# export (CSV)
# --------------------------------------------------------------------------
def _csv_val(v):
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


@app.get("/api/export/{name}")
def export_view(name: str):
    if name not in VIEW_WHITELIST:
        raise HTTPException(status_code=404, detail=f"Unknown view: {name}")
    rows = database.query(f"SELECT * FROM credit.{name}")
    buf = io.StringIO()
    if rows:
        columns = list(rows[0].keys())
        writer = csv.DictWriter(buf, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_val(v) for k, v in row.items()})
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


# --------------------------------------------------------------------------
# predictions
# --------------------------------------------------------------------------
@app.post("/api/predict/fraud", response_model=schemas.FraudPrediction)
def predict_fraud(body: schemas.FraudInput):
    return inference.predict_fraud(body.model_dump())


@app.post("/api/predict/customer-profile", response_model=schemas.ProfilePrediction)
def predict_profile(body: schemas.CustomerProfileInput):
    return inference.predict_profile(body.model_dump())


@app.post("/api/predict/batch")
async def predict_batch(model: str = Form(...), file: UploadFile = File(...)):
    if model not in ("fraud", "customer-profile"):
        raise HTTPException(status_code=400, detail="model must be 'fraud' or 'customer-profile'")
    content = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    fn = inference.predict_fraud if model == "fraud" else inference.predict_profile
    results = [fn(row) for row in reader]
    return {"model": model, "count": len(results), "predictions": results}


# --------------------------------------------------------------------------
# compliance (openNPL, separate PostgreSQL stack)
# --------------------------------------------------------------------------
@app.get("/api/compliance/npl")
def compliance_npl():
    try:
        with open(NPL_SUMMARY, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="NPL summary not found; run `python etl_scripts/npl_report.py` first",
        ) from None


@app.get("/api/compliance/npl-flagged")
def compliance_flagged(limit: int = 100):
    try:
        with open(NPL_FLAGGED, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return {"rows": [row for _, row in zip(range(min(limit, 10000)), reader)]}
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="NPL flagged loans not found; run `python etl_scripts/npl_report.py` first",
        ) from None
