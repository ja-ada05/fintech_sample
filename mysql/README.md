# MySQL schema — main platform

The main BI platform runs on **MySQL 8**. The **openNPL compliance module** is a separate
stack and stays on **PostgreSQL** (see `sql_schema/` and `etl_scripts/npl_*.py`). The two share
the same logical 26-table `credit` schema, in different dialects.

## Files

| File | Purpose |
|---|---|
| `credit_risk_schema.sql` | 26 tables + indexes + views + `monthly_transaction_summary` + reference data |
| `seed_synthetic.sql` | small synthetic smoke seed |
| `fraud_dashboard_view.sql` | fraud dashboard aggregate view |

## Load (in order)

```bash
mysql -u <user> -p < mysql/credit_risk_schema.sql
mysql -u <user> -p credit < mysql/seed_synthetic.sql
mysql -u <user> -p credit < mysql/fraud_dashboard_view.sql
```

## Requirements

- **MySQL 8.0.16+** — otherwise `CHECK` constraints are parsed but not enforced.
- **MySQL 8.0.19+** — required for the recursive CTE that fills `dim_date` in the seed.

## Load real data (after the schema is up)

```bash
pip install pymysql pandas scikit-learn
python etl_scripts/load_sample_data.py --db mysql://user:pass@localhost:3306/credit
python etl_scripts/load_sample_data.py --only home-credit --n-borrowers 2000 --db mysql://user:pass@localhost:3306/credit
```

The Python scripts connect via the shared `db.py` (pymysql), DSN format `mysql://user:pass@host:port/database`.

## Differences vs the PostgreSQL twin (`sql_schema/`)

| PostgreSQL | MySQL |
|---|---|
| `GENERATED ALWAYS AS IDENTITY` | `AUTO_INCREMENT` |
| `boolean` | `TINYINT(1)` |
| `jsonb` | `JSON` |
| `timestamptz` | `DATETIME` / `TIMESTAMP` |
| `numeric(p,s)` | `DECIMAL(p,s)` |
| materialized view `mv_monthly_transaction_summary` | regular table `monthly_transaction_summary` (ETL-refreshed) |
| `FILTER (WHERE …)` | `SUM(CASE WHEN … THEN 1 ELSE 0 END)` |
| `date_trunc('month', …)` | `DATE_FORMAT(…, '%Y-%m-01')` |
| `ON CONFLICT … DO NOTHING` | `INSERT IGNORE` (or `ON DUPLICATE KEY UPDATE`) |
| column-level `REFERENCES` | table-level `FOREIGN KEY` (MySQL ignores inline `REFERENCES`) |
