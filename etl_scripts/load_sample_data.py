#!/usr/bin/env python3
"""Load a sample of the raw CSVs in data/raw/ into the MySQL `credit` schema.

Mappings (down-sampled by default):

  creditcard.csv (ULB fraud)                 -> card_transaction, fraud_case
  accepted_2007_to_2018Q4.csv (LendingClub)  -> loan_origination
  rejected_2007_to_2018Q4.csv (LendingClub)  -> loan_rejection
  Home Credit CSVs                            -> borrower, loan_application, bureau*, etc.

NOTE: credit_train.csv / credit_test.csv are a *different* "Bank Loan Status"-style
dataset and do NOT match the Home Credit-derived tables; this script skips them.

Usage:
  python etl_scripts/load_sample_data.py --db mysql://user:pass@localhost:3306/credit
  python etl_scripts/load_sample_data.py --only home-credit --n-borrowers 2000 --db mysql://...

Dependencies: pip install pandas pymysql
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
FRAUD_EPOCH = datetime(2023, 1, 1)

STATUS_MAP = {
    "Current": 1,
    "Fully Paid": 9,
    "Charged Off": 8,
    "Late (31-120 days)": 5,
    "Late (16-30 days)": 4,
    "In Grace Period": 3,
    "Default": 7,
    "Does not meet the credit policy. Status:Charged Off": 8,
    "Does not meet the credit policy. Status:Fully Paid": 9,
}


def _f(x):
    return None if pd.isna(x) else float(x)


def _i(x):
    return None if pd.isna(x) else int(float(x))


def _s(x):
    return None if pd.isna(x) else str(x)


def _pct(x, hi=1000.0):
    if pd.isna(x):
        return None
    s = str(x).strip().replace("%", "").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if v < 0 or v > hi:
        return None
    return v


def _mon_year(x):
    if pd.isna(x) or str(x).strip() == "":
        return None
    try:
        return pd.to_datetime(str(x).strip(), format="%b-%Y").date()
    except ValueError:
        return None


def _ymd(x):
    if pd.isna(x) or str(x).strip() == "":
        return None
    try:
        return pd.to_datetime(str(x).strip()).date()
    except ValueError:
        return None


def _to_bool(v):
    return False if pd.isna(v) else str(v).strip().upper() in ("Y", "1", "TRUE", "XNA")


def _to_date(days_birth):
    if pd.isna(days_birth):
        return None
    return (datetime(2023, 1, 1) + timedelta(days=int(days_birth))).date()


def _flag_docs(row):
    d = {
        c.replace("FLAG_DOCUMENT_", ""): int(row[c])
        for c in row.index
        if c.startswith("FLAG_DOCUMENT_") and pd.notna(row[c])
    }
    return json.dumps(d) if d else None


def load_fraud(conn, n_legit: int):
    df = pd.read_csv(os.path.join(RAW, "creditcard.csv"))
    fraud = df[df["Class"] == 1]
    legit = df[df["Class"] == 0]
    if n_legit and n_legit < len(legit):
        legit = legit.sample(n_legit, random_state=42)
    df = pd.concat([fraud, legit]).sample(frac=1, random_state=42)

    cur = conn.cursor()
    tx_cols = ["occurred_at", "amount"] + [f"v{i}" for i in range(1, 29)]
    tx_ph = ", ".join(["%s"] * len(tx_cols))
    n = 0
    # Row-by-row so we can capture each AUTO_INCREMENT id to link fraud_case.
    for _, r in df.iterrows():
        occurred = FRAUD_EPOCH + timedelta(seconds=int(r["Time"]))
        vals = (occurred, float(r["Amount"])) + tuple(float(r[f"V{i}"]) for i in range(1, 29))
        cur.execute(f"INSERT INTO credit.card_transaction ({', '.join(tx_cols)}) VALUES ({tx_ph})", vals)
        tid = cur.lastrowid
        cur.execute(
            "INSERT INTO credit.fraud_case (transaction_id, is_fraud, risk_score, rule_triggered, status) "
            "VALUES (%s, %s, %s, %s, %s)",
            (tid, bool(int(r["Class"])), None, None, "open"),
        )
        n += 1
    conn.commit()
    print(f"[fraud] {n} transactions ({len(fraud)} fraud, {n - len(fraud)} legit)")


def load_loans(conn, n: int):
    usecols = ["id", "loan_amnt", "funded_amnt", "term", "int_rate", "installment",
               "grade", "sub_grade", "purpose", "home_ownership", "annual_inc",
               "verification_status", "issue_d", "dti", "delinq_2yrs", "open_acc",
               "total_acc", "revol_bal", "revol_util", "earliest_cr_line", "loan_status"]
    path = os.path.join(RAW, "accepted_2007_to_2018q4.csv", "accepted_2007_to_2018Q4.csv")
    df = pd.read_csv(path, usecols=usecols, nrows=n, low_memory=False)

    rows = []
    for _, r in df.iterrows():
        term = None
        if pd.notna(r["term"]):
            term = int(str(r["term"]).strip().split()[0])
        rate = _pct(r["int_rate"], hi=100.0)
        rows.append((
            int(r["id"]), None, STATUS_MAP.get(str(r["loan_status"]).strip(), 1),
            _f(r["loan_amnt"]), _f(r["funded_amnt"]), term,
            (rate / 100.0) if rate is not None else None,
            _f(r["installment"]),
            (_s(r["grade"]) or "")[:1] or None,
            (_s(r["sub_grade"]) or "")[:2] or None,
            _s(r["purpose"]), _s(r["home_ownership"]), _f(r["annual_inc"]),
            _s(r["verification_status"]), _mon_year(r["issue_d"]), _f(r["dti"]),
            _i(r["delinq_2yrs"]), _i(r["open_acc"]), _i(r["total_acc"]),
            _f(r["revol_bal"]), _pct(r["revol_util"]), _mon_year(r["earliest_cr_line"]),
        ))

    cols = ["loan_id", "borrower_id", "loan_status_id", "loan_amount", "funded_amount",
            "term_months", "interest_rate", "installment", "grade", "sub_grade", "purpose",
            "home_ownership", "annual_income", "verification_status", "issue_date", "dti",
            "delinq_2yrs", "open_acc", "total_acc", "revol_balance", "revol_util", "earliest_cr_line"]
    cur = conn.cursor()
    db.bulk_insert(cur, "credit.loan_origination", cols, rows, ignore=True)
    conn.commit()
    print(f"[loans] {len(df)} accepted loans")


def load_rejections(conn, n: int):
    path = os.path.join(RAW, "rejected_2007_to_2018q4.csv", "rejected_2007_to_2018Q4.csv")
    df = pd.read_csv(path, nrows=n, low_memory=False)

    rows = []
    for _, r in df.iterrows():
        state = _s(r["State"])
        rows.append((
            _f(r["Amount Requested"]), _ymd(r["Application Date"]), _f(r["Risk_Score"]),
            _pct(r["Debt-To-Income Ratio"]), (state[:2] if state else None),
            _s(r["Employment Length"]), _i(r["Policy Code"]),
        ))

    cols = ["amount_requested", "application_date", "risk_score", "debt_to_income",
            "state", "employment_length", "policy_code"]
    cur = conn.cursor()
    db.bulk_insert(cur, "credit.loan_rejection", cols, rows)
    conn.commit()
    print(f"[rejections] {len(df)} rejected loans")


def _make_ref_getter(conn, table):
    id_col = table.replace("ref_", "") + "_id"
    cur = conn.cursor()
    cur.execute(f"SELECT name, {id_col} FROM credit.{table}")
    cache = {name: i for name, i in cur.fetchall()}

    def get(name):
        if pd.isna(name):
            name = "XNA"
        name = str(name)
        if name not in cache:
            cur.execute(
                f"INSERT INTO credit.{table} ({id_col}, name) "
                f"SELECT COALESCE(MAX({id_col}),0)+1, %s FROM credit.{table}",
                (name,),
            )
            cur.execute(f"SELECT MAX({id_col}) FROM credit.{table}")
            cache[name] = cur.fetchone()[0]
        return cache[name]

    return get


def load_home_credit(conn, n_borrowers):
    cur = conn.cursor()

    app_train = pd.read_csv(os.path.join(RAW, "application_train.csv"))
    app_test = pd.read_csv(os.path.join(RAW, "application_test.csv"))
    apps = pd.concat([app_train, app_test.assign(TARGET=None)], ignore_index=True)
    if n_borrowers and n_borrowers < len(apps):
        apps = apps.sample(n_borrowers, random_state=42)
    apps = apps.copy()  # defragment -> silences the "DataFrame is highly fragmented" warning
    kept = set(int(x) for x in apps["SK_ID_CURR"])

    fam = _make_ref_getter(conn, "ref_family_status")
    inc = _make_ref_getter(conn, "ref_income_type")
    edu = _make_ref_getter(conn, "ref_education_type")
    occ = _make_ref_getter(conn, "ref_occupation_type")
    org = _make_ref_getter(conn, "ref_organization_type")
    hou = _make_ref_getter(conn, "ref_housing_type")
    ct = _make_ref_getter(conn, "ref_contract_type")
    po = _make_ref_getter(conn, "ref_portfolio")
    ch = _make_ref_getter(conn, "ref_channel")
    pt = _make_ref_getter(conn, "ref_payment_type")
    cs = _make_ref_getter(conn, "ref_credit_status")

    # ---- borrowers ----
    rows = []
    for _, r in apps.iterrows():
        rows.append((
            int(r["SK_ID_CURR"]),
            (_s(r["CODE_GENDER"]) or "X")[:1],
            _to_date(r["DAYS_BIRTH"]),
            fam(r["NAME_FAMILY_STATUS"]),
            _i(r["CNT_CHILDREN"]) or 0,
            _f(r["CNT_FAM_MEMBERS"]),
            inc(r["NAME_INCOME_TYPE"]),
            edu(r["NAME_EDUCATION_TYPE"]),
            occ(r["OCCUPATION_TYPE"]),
            org(r["ORGANIZATION_TYPE"]),
            hou(r["NAME_HOUSING_TYPE"]),
            _to_bool(r["FLAG_OWN_CAR"]),
            _to_bool(r["FLAG_OWN_REALTY"]),
            _f(r["OWN_CAR_AGE"]),
            _i(r["DAYS_EMPLOYED"]),
            _f(r["AMT_INCOME_TOTAL"]),
            _f(r["REGION_POPULATION_RELATIVE"]),
            _i(r["REGION_RATING_CLIENT"]),
            _f(r["EXT_SOURCE_1"]),
            _f(r["EXT_SOURCE_2"]),
            _f(r["EXT_SOURCE_3"]),
            _i(r["OBS_30_CNT_SOCIAL_CIRCLE"]),
            _i(r["DEF_30_CNT_SOCIAL_CIRCLE"]),
            _to_bool(r["FLAG_WORK_PHONE"]),
            _to_bool(r["FLAG_PHONE"]),
            _to_bool(r["FLAG_EMAIL"]),
        ))
    cols = ["borrower_id", "gender", "birth_date", "family_status_id", "cnt_children",
            "cnt_fam_members", "income_type_id", "education_type_id", "occupation_type_id",
            "organization_type_id", "housing_type_id", "own_car", "own_realty", "own_car_age",
            "days_employed", "amt_income_total", "region_population_relative",
            "region_rating_client", "ext_source_1", "ext_source_2", "ext_source_3",
            "cnt_obs_30_social_circle", "cnt_def_30_social_circle", "flag_work_phone",
            "flag_phone", "flag_email"]
    db.bulk_insert(cur, "credit.borrower", cols, rows, ignore=True)
    conn.commit()
    print(f"[home-credit] borrowers: {len(rows)}")

    # ---- loan applications ----
    rows = []
    for _, r in apps.iterrows():
        rows.append((
            int(r["SK_ID_CURR"]), int(r["SK_ID_CURR"]), ct(r["NAME_CONTRACT_TYPE"]),
            _f(r["AMT_CREDIT"]), _f(r["AMT_ANNUITY"]), _f(r["AMT_GOODS_PRICE"]),
            _i(r["TARGET"]), _s(r["WEEKDAY_APPR_PROCESS_START"]), _i(r["HOUR_APPR_PROCESS_START"]),
            _i(r["DAYS_BIRTH"]), _i(r["DAYS_LAST_PHONE_CHANGE"]),
            _f(r["AMT_REQ_CREDIT_BUREAU_YEAR"]), _f(r["AMT_REQ_CREDIT_BUREAU_QRT"]),
            _f(r["AMT_REQ_CREDIT_BUREAU_MON"]), _f(r["AMT_REQ_CREDIT_BUREAU_WEEK"]),
            _f(r["AMT_REQ_CREDIT_BUREAU_DAY"]), _f(r["AMT_REQ_CREDIT_BUREAU_HOUR"]),
            _flag_docs(r),
        ))
    cols = ["application_id", "borrower_id", "contract_type_id", "amt_credit", "amt_annuity",
            "amt_goods_price", "target", "week_appr_process_start", "hour_appr_process_start",
            "days_birth", "days_last_phone_change", "amt_req_credit_bureau_year",
            "amt_req_credit_bureau_quarter", "amt_req_credit_bureau_month",
            "amt_req_credit_bureau_week", "amt_req_credit_bureau_day",
            "amt_req_credit_bureau_hour", "flags_document"]
    db.bulk_insert(cur, "credit.loan_application", cols, rows, ignore=True)
    conn.commit()
    print(f"[home-credit] applications: {len(rows)}")

    # ---- previous applications ----
    prev = pd.read_csv(os.path.join(RAW, "previous_application.csv"))
    prev = prev[prev["SK_ID_CURR"].isin(kept)]
    rows = []
    for _, r in prev.iterrows():
        rows.append((
            int(r["SK_ID_PREV"]), int(r["SK_ID_CURR"]), ct(r["NAME_CONTRACT_TYPE"]),
            po(r["NAME_PORTFOLIO"]), ch(r["CHANNEL_TYPE"]), pt(r["NAME_PAYMENT_TYPE"]),
            _s(r["NAME_CONTRACT_STATUS"]), _i(r["DAYS_DECISION"]),
            _f(r["AMT_APPLICATION"]), _f(r["AMT_CREDIT"]), _f(r["AMT_ANNUITY"]),
            _f(r["AMT_GOODS_PRICE"]), _f(r["AMT_DOWN_PAYMENT"]),
            _s(r["NAME_CLIENT_TYPE"]), _s(r["NAME_PRODUCT_TYPE"]),
            _i(r["SELLERPLACE_AREA"]), _s(r["NAME_SELLER_INDUSTRY"]),
        ))
    cols = ["previous_application_id", "application_id", "contract_type_id", "portfolio_id",
            "channel_id", "payment_type_id", "contract_status", "days_decision",
            "amt_application", "amt_credit", "amt_annuity", "amt_goods_price",
            "amt_down_payment", "client_type", "product_type", "sellerplace_area",
            "seller_industry"]
    db.bulk_insert(cur, "credit.previous_application", cols, rows, ignore=True)
    kept_prev = set(int(x) for x in prev["SK_ID_PREV"])
    conn.commit()
    print(f"[home-credit] previous applications: {len(rows)}")

    # ---- bureau records ----
    bureau = pd.read_csv(os.path.join(RAW, "bureau.csv"))
    bureau = bureau[bureau["SK_ID_CURR"].isin(kept)]
    rows = []
    for _, r in bureau.iterrows():
        rows.append((
            int(r["SK_ID_BUREAU"]), int(r["SK_ID_CURR"]), cs(r["CREDIT_ACTIVE"]), ct(r["CREDIT_TYPE"]),
            _s(r["CREDIT_CURRENCY"]), _i(r["DAYS_CREDIT"]), _i(r["DAYS_CREDIT_ENDDATE"]),
            _i(r["CREDIT_DAY_OVERDUE"]), _f(r["AMT_CREDIT_MAX_OVERDUE"]), _i(r["CNT_CREDIT_PROLONG"]),
            _f(r["AMT_CREDIT_SUM"]), _f(r["AMT_CREDIT_SUM_DEBT"]), _f(r["AMT_CREDIT_SUM_LIMIT"]),
            _f(r["AMT_CREDIT_SUM_OVERDUE"]), _f(r["AMT_ANNUITY"]), _i(r["DAYS_ENDDATE_FACT"]),
        ))
    cols = ["bureau_record_id", "borrower_id", "credit_status_id", "contract_type_id",
            "credit_currency", "days_credit", "days_credit_enddate", "credit_day_overdue",
            "amt_credit_max_overdue", "cnt_credit_prolong", "amt_credit_sum",
            "amt_credit_sum_debt", "amt_credit_sum_limit", "amt_credit_sum_overdue",
            "amt_annuity", "days_enddate_fact"]
    db.bulk_insert(cur, "credit.bureau_record", cols, rows, ignore=True)
    kept_bureau = set(int(x) for x in bureau["SK_ID_BUREAU"])
    conn.commit()
    print(f"[home-credit] bureau records: {len(rows)}")

    # ---- bureau balance ----
    bb = pd.read_csv(os.path.join(RAW, "bureau_balance.csv"))
    bb = bb[bb["SK_ID_BUREAU"].isin(kept_bureau)]
    rows = [(int(r["SK_ID_BUREAU"]), int(r["MONTHS_BALANCE"]), str(r["STATUS"])[:1])
            for _, r in bb.iterrows()]
    db.bulk_insert(cur, "credit.bureau_balance", ["bureau_record_id", "months_balance", "status"], rows, ignore=True)
    conn.commit()
    print(f"[home-credit] bureau balance: {len(rows)}")

    # ---- credit card balance ----
    ccb = pd.read_csv(os.path.join(RAW, "credit_card_balance.csv"))
    ccb = ccb[ccb["SK_ID_CURR"].isin(kept) & ccb["SK_ID_PREV"].isin(kept_prev)]
    rows = []
    for _, r in ccb.iterrows():
        rows.append((
            int(r["SK_ID_CURR"]), int(r["SK_ID_PREV"]), int(r["MONTHS_BALANCE"]),
            _f(r["AMT_BALANCE"]), _f(r["AMT_CREDIT_LIMIT_ACTUAL"]),
            _f(r["AMT_DRAWINGS_ATM_CURRENT"]), _f(r["AMT_DRAWINGS_CURRENT"]),
            _f(r["AMT_DRAWINGS_OTHER_CURRENT"]), _f(r["AMT_DRAWINGS_POS_CURRENT"]),
            _f(r["CNT_DRAWINGS_ATM_CURRENT"]), _f(r["CNT_DRAWINGS_CURRENT"]),
            _f(r["CNT_DRAWINGS_OTHER_CURRENT"]), _f(r["CNT_DRAWINGS_POS_CURRENT"]),
            _f(r["AMT_INST_MIN_REGULARITY"]), _f(r["AMT_PAYMENT_TOTAL_CURRENT"]),
            _i(r["SK_DPD"]), _i(r["SK_DPD_DEF"]),
        ))
    cols = ["application_id", "previous_application_id", "months_balance", "amt_balance",
            "amt_credit_limit_actual", "amt_drawings_atm_current", "amt_drawings_current",
            "amt_drawings_other_current", "amt_drawings_pos_current", "cnt_drawings_atm_current",
            "cnt_drawings_current", "cnt_drawings_other_current", "cnt_drawings_pos_current",
            "amt_inst_min_regularity", "amt_payment_total_current", "sk_dpd", "sk_dpd_def"]
    db.bulk_insert(cur, "credit.credit_card_balance", cols, rows)
    conn.commit()
    print(f"[home-credit] credit card balance: {len(rows)}")

    # ---- installment payments ----
    inst = pd.read_csv(os.path.join(RAW, "installments_payments.csv"))
    inst = inst[inst["SK_ID_CURR"].isin(kept) & inst["SK_ID_PREV"].isin(kept_prev)]
    rows = [(int(r["SK_ID_CURR"]), int(r["SK_ID_PREV"]), int(r["NUM_INSTALMENT_VERSION"]),
             int(r["NUM_INSTALMENT_NUMBER"]), _i(r["DAYS_INSTALMENT"]), _i(r["DAYS_ENTRY_PAYMENT"]),
             _f(r["AMT_INSTALMENT"]), _f(r["AMT_PAYMENT"])) for _, r in inst.iterrows()]
    cols = ["application_id", "previous_application_id", "installment_version",
            "installment_number", "days_installment", "days_entry_payment",
            "amt_installment", "amt_payment"]
    db.bulk_insert(cur, "credit.installment_payment", cols, rows, ignore=True)
    conn.commit()
    print(f"[home-credit] installments: {len(rows)}")

    # ---- POS cash balance ----
    pos = pd.read_csv(os.path.join(RAW, "POS_CASH_balance.csv"))
    pos = pos[pos["SK_ID_CURR"].isin(kept) & pos["SK_ID_PREV"].isin(kept_prev)]
    rows = [(int(r["SK_ID_CURR"]), int(r["SK_ID_PREV"]), int(r["MONTHS_BALANCE"]),
             _i(r["CNT_INSTALMENT"]), _i(r["CNT_INSTALMENT_FUTURE"]),
             _s(r["NAME_CONTRACT_STATUS"]), _i(r["SK_DPD"]), _i(r["SK_DPD_DEF"]))
            for _, r in pos.iterrows()]
    cols = ["application_id", "previous_application_id", "months_balance", "cnt_installment",
            "cnt_installment_future", "contract_status", "sk_dpd", "sk_dpd_def"]
    db.bulk_insert(cur, "credit.pos_cash_balance", cols, rows)
    conn.commit()
    print(f"[home-credit] POS cash balance: {len(rows)}")


def refresh_monthly_summary(conn):
    """Refresh monthly_transaction_summary (replaces the PostgreSQL materialized view)."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO credit.monthly_transaction_summary (month, txn_count, total_amount, fraud_count) "
        "SELECT DATE_FORMAT(ct.occurred_at, '%Y-%m-01'), COUNT(*), SUM(ct.amount), "
        "SUM(CASE WHEN fc.is_fraud THEN 1 ELSE 0 END) "
        "FROM credit.card_transaction ct "
        "LEFT JOIN credit.fraud_case fc ON fc.transaction_id = ct.transaction_id "
        "GROUP BY DATE_FORMAT(ct.occurred_at, '%Y-%m-01') "
        "ON DUPLICATE KEY UPDATE "
        "txn_count = VALUES(txn_count), total_amount = VALUES(total_amount), fraud_count = VALUES(fraud_count)"
    )
    conn.commit()
    print("[summary] refreshed monthly_transaction_summary")


def main():
    p = argparse.ArgumentParser(description="Load sample data into the MySQL credit schema.")
    p.add_argument("--db", default=os.environ.get("DATABASE_URL", "mysql://root@localhost:3306/credit"))
    p.add_argument("--only", choices=["fraud", "loans", "rejections", "home-credit", "all"],
                   default="all", help="which dataset(s) to load")
    p.add_argument("--fraud-legit", type=int, default=10000, help="non-fraud rows to sample")
    p.add_argument("--loans", type=int, default=20000, help="accepted loans to sample")
    p.add_argument("--rejections", type=int, default=5000, help="rejected loans to sample")
    p.add_argument("--n-borrowers", type=int, default=2000, help="Home Credit borrowers to sample")
    args = p.parse_args()

    conn = db.connect(args.db)
    try:
        if args.only in ("fraud", "all"):
            load_fraud(conn, args.fraud_legit)
            refresh_monthly_summary(conn)
        if args.only in ("loans", "all"):
            load_loans(conn, args.loans)
        if args.only in ("rejections", "all"):
            load_rejections(conn, args.rejections)
        if args.only in ("home-credit", "all"):
            load_home_credit(conn, args.n_borrowers)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
