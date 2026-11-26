# FinSight Analytics — Loan Portfolio Risk & BI Platform

Backend + ML + schemas + ETL for the FinSight BI platform.
The frontend lives in a separate repository (`lonyle17/finsightanalytics`).

## Stack

- **Database:** MySQL 8 (`credit` schema) — main platform
- **Backend:** FastAPI (`backend/`)
- **ML:** scikit-learn (`ml/` — fraud RF, customer-profile RF, loan-default)
- **Compliance:** openNPL module (separate PostgreSQL stack — `sql_schema/npl_schema.sql`, `etl_scripts/npl_*.py`)
- **Frontend:** Vite + React (separate repo)

---

## How to run (after cloning / forking on a new machine)

### Prerequisites

- **Python 3.10+** (verified on 3.15)
- **Node.js 18+** (for the frontend)
- **MySQL 8.0.19+** (8.0.16+ for `CHECK` enforcement, 8.0.19+ for the `dim_date` recursive CTE in the seed)

### 1. Clone both repositories

```bash
git clone https://github.com/ja-ada05/fintech_sample.git
git clone https://github.com/lonyle17/finsightanalytics.git finsight-ui
```

### 2. Install Python dependencies

```bash
cd fintech_sample
pip install -r requirements.txt -r backend/requirements.txt
```

### 3. Create the database schema + seed

Run in MySQL Workbench or the `mysql` CLI (in this order):

```bash
mysql -u <user> -p < mysql/credit_risk_schema.sql
mysql -u <user> -p credit < mysql/seed_synthetic.sql
mysql -u <user> -p credit < mysql/fraud_dashboard_view.sql
```

### 4. Configure the backend database connection

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and set:

```
DATABASE_URL=mysql://USER:PASSWORD@HOST:PORT/credit
```

> Important: write the password **raw** (no quotes, no `%xx`-encoding) after `USER:`.

### 5. (Optional) Load the real data

The raw CSVs are **not** in this repo (they're large). Download them into `data/raw/`
(see the docstring in `etl_scripts/load_sample_data.py` for the exact file list), then:

```bash
python etl_scripts/load_sample_data.py --db "mysql://USER:PASSWORD@HOST:PORT/credit"
python etl_scripts/load_sample_data.py --only home-credit --n-borrowers 2000 --db "mysql://USER:PASSWORD@HOST:PORT/credit"
```

If you skip this step, the committed seed has 5 synthetic rows and the committed
models still work for prediction.

### 6. Run the backend

```bash
python -m uvicorn backend.main:app --reload
# -> http://localhost:8000/docs  (interactive API docs)
```

### 7. Run the frontend (separate terminal)

```bash
cd finsight-ui
npm install
npm run dev
# -> http://localhost:5173
```

The frontend talks to the backend at `http://localhost:8000` by default.
Override with a Vite env var if needed: `VITE_API_URL=http://your-host:8000`.

### 8. Test

- **Dashboard** tab → live KPIs + charts from MySQL.
- **ML Sandbox** tab → customer-profile form (18 fields) + fraud CSV upload
  (use `test_inputs/fraud_5rows.csv`).
- **openNPL** tab → compliance summary + severity + flagged loans.

---

## Notes

- **Trained models** are committed in `ml/models/*.joblib`, so prediction works
  without retraining.
- **To retrain**, you first need data in MySQL, then:
  ```bash
  python ml/train_fraud.py extract && python ml/train_fraud.py train
  python ml/train_customer_profiles.py extract --db "mysql://…" && python ml/train_customer_profiles.py cluster && python ml/train_customer_profiles.py train
  ```
- **NPL compliance** is a separate PostgreSQL stack. `npl_outputs/npl_summary.json`
  is committed (so `/api/compliance/npl` works), but `npl_outputs/npl_flagged_loans.csv`
  is not (CSV files are git-ignored). Regenerate it with
  `python etl_scripts/npl_report.py` once the openNPL Postgres schema is up.
- **CSV files** are git-ignored except `test_inputs/*.csv`.
