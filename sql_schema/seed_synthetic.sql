-- ============================================================================
-- Synthetic smoke-test seed for credit_risk_schema.sql
-- Small, clearly-synthetic rows so the schema can be exercised immediately
-- without downloading the (large) real source files. For real data, run
-- etl_scripts/ingest_credit_risk.py (see docs/data_provenance.md).
--
-- Run AFTER credit_risk_schema.sql in the same session:
--   psql -v ON_ERROR_STOP=1 -d <your_db> -f credit_risk_schema.sql -f seed_synthetic.sql
-- ============================================================================

SET search_path = credit, public;

-- Shared date dimension (2019-2023)
INSERT INTO dim_date
SELECT to_char(d, 'YYYYMMDD')::int          AS date_id,
       d::date                               AS full_date,
       extract(year    FROM d)::smallint     AS year,
       extract(quarter FROM d)::smallint     AS quarter,
       extract(month   FROM d)::smallint     AS month,
       extract(day     FROM d)::smallint     AS day,
       extract(isodow  FROM d)::smallint     AS day_of_week,
       extract(week    FROM d)::smallint     AS week_of_year,
       (extract(isodow FROM d) IN (6,7))     AS is_weekend
FROM generate_series('2019-01-01'::date, '2023-12-31'::date, '1 day') AS d;

-- Borrowers
INSERT INTO borrower
    (borrower_id, gender, birth_date, family_status_id, cnt_children, cnt_fam_members,
     income_type_id, education_type_id, occupation_type_id, organization_type_id,
     housing_type_id, own_car, own_realty, own_car_age, days_employed, amt_income_total,
     region_population_relative, region_rating_client, ext_source_1, ext_source_2, ext_source_3,
     cnt_obs_30_social_circle, cnt_def_30_social_circle, flag_work_phone, flag_phone, flag_email)
VALUES
    (100001, 'F', '1985-04-12', 1, 1, 3.0, 1, 2, 3, 1, 1, true,  true,  6,  -4000, 180000.00, 0.018, 2, 0.68, 0.72, 0.64, 2, 0, true,  true,  true),
    (100002, 'M', '1990-09-30', 2, 0, 1.0, 1, 1, 1, 2, 2, false, true,  NULL, -2500, 90000.00,  0.011, 3, 0.42, 0.38, 0.51, 4, 1, false, true,  true),
    (100003, 'F', '1978-01-05', 3, 2, 4.0, 4, 3, 5, 3, 3, true,  false, 10, -9000, 120000.00, 0.024, 2, 0.55, 0.60, 0.49, 1, 0, true,  false, false),
    (100004, 'M', '1995-12-20', 2, 0, 1.0, 5, 2, 18, 7, 4, false, false, NULL, -120, 30000.00,  0.009, 3, 0.21, 0.19, 0.30, 5, 2, false, true,  true),
    (100005, 'F', '1988-07-18', 1, 1, 3.0, 2, 2, 4, 8, 1, true,  true,  4,  -6000, 150000.00, 0.015, 2, 0.61, 0.58, 0.66, 3, 1, true,  true,  true);

-- Loan applications
INSERT INTO loan_application
    (application_id, borrower_id, contract_type_id, amt_credit, amt_annuity, amt_goods_price,
     target, week_appr_process_start, hour_appr_process_start, days_birth, days_last_phone_change,
     amt_req_credit_bureau_year, amt_req_credit_bureau_quarter, amt_req_credit_bureau_month,
     amt_req_credit_bureau_week, amt_req_credit_bureau_day, amt_req_credit_bureau_hour,
     flags_document, extra)
VALUES
    (100001, 100001, 1, 450000.00, 21000.00, 450000.00, 0, 'WEDNESDAY', 10, -13500, -90,
     2.0, 0.0, 0.0, 0.0, 0.0, 0.0, '{"2":1,"3":1,"8":1,"11":1,"16":1,"20":1}', NULL),
    (100002, 100002, 1, 250000.00, 12000.00, 250000.00, 0, 'MONDAY',    9, -10900, -200,
     1.0, 0.0, 0.0, 0.0, 0.0, 0.0, '{"2":1,"3":1,"8":1}', NULL),
    (100003, 100003, 2, 80000.00,  4000.00,  80000.00,  1, 'FRIDAY',   15, -17300, -30,
     3.0, 1.0, 0.0, 0.0, 0.0, 0.0, '{"2":1,"3":1,"8":1,"11":1}', NULL),
    (100004, 100004, 1, 120000.00, 6000.00,  120000.00, 1, 'TUESDAY',  14, -10200, -10,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, '{"2":1,"3":1}', NULL),
    (100005, 100005, 3, 300000.00, 15000.00, 300000.00, 0, 'THURSDAY', 11, -13000, -60,
     2.0, 1.0, 1.0, 0.0, 0.0, 0.0, '{"2":1,"3":1,"8":1,"11":1,"16":1}', NULL);

-- Previous applications
INSERT INTO previous_application
    (previous_application_id, application_id, contract_type_id, portfolio_id, channel_id,
     payment_type_id, contract_status, days_decision, amt_application, amt_credit, amt_annuity,
     amt_goods_price, amt_down_payment, client_type, product_type, sellerplace_area, seller_industry, extra)
VALUES
    (200001, 100001, 1, 3, 1, 1, 'Approved',      -600, 450000.00, 450000.00, 21000.00, 450000.00, 0.00, 'Repeater', 'x-sell', 520000, 'Consumer electronics', NULL),
    (200002, 100001, 5, 2, 2, 3, 'Refused',       -900, 20000.00,  20000.00,  1500.00,  0.00,      0.00, 'New',      'walk-in', 520000, 'Consumer electronics', NULL),
    (200003, 100002, 1, 3, 1, 1, 'Approved',      -400, 250000.00, 250000.00, 12000.00, 250000.00, 0.00, 'Repeater', 'x-sell', 330000, 'Clothing', NULL),
    (200004, 100003, 2, 2, 5, 3, 'Canceled',      -300, 80000.00,  80000.00,  4000.00,  80000.00,  0.00, 'New',      'x-sell', 220000, 'Furniture', NULL),
    (200005, 100004, 4, 1, 3, 1, 'Refused',       -150, 120000.00, 120000.00, 6000.00,  120000.00, 0.00, 'New',      'walk-in', 100000, 'Industry', NULL);

-- Bureau records
INSERT INTO bureau_record
    (bureau_record_id, borrower_id, credit_status_id, contract_type_id, credit_currency,
     days_credit, days_credit_enddate, credit_day_overdue, amt_credit_max_overdue, cnt_credit_prolong,
     amt_credit_sum, amt_credit_sum_debt, amt_credit_sum_limit, amt_credit_sum_overdue,
     amt_annuity, days_enddate_fact)
VALUES
    (300001, 100001, 1, 4, 'EUR', -1200, -500, 0, 0.00,   0, 120000.00, 60000.00, 100000.00, 0.00,      8000.00,  -500),
    (300002, 100001, 1, 5, 'EUR', -800,  -200, 15, 150.00, 1, 30000.00,  25000.00, 30000.00,  120.00,    2500.00,  -200),
    (300003, 100002, 2, 4, 'EUR', -1500, -100, 0, 0.00,   0, 90000.00,  0.00,     90000.00,  0.00,      6000.00,  -100),
    (300004, 100003, 4, 7, 'EUR', -1000, -800, 60, 500.00, 2, 180000.00, 150000.00, 180000.00, 4000.00, 12000.00, -800),
    (300005, 100004, 1, 8, 'EUR', -300,  -30,  0, 0.00,   0, 15000.00,  12000.00, 15000.00,  0.00,      1500.00,  -30);

-- Bureau balance history
INSERT INTO bureau_balance (bureau_record_id, months_balance, status) VALUES
    (300001, -1, '0'), (300001, -2, '0'), (300001, -3, '0'),
    (300002, -1, '2'), (300002, -2, '1'), (300002, -3, '0'),
    (300003, -1, '0'), (300003, -2, 'C'),
    (300004, -1, '5'), (300004, -2, '4'), (300004, -3, '3'),
    (300005, -1, '0'), (300005, -2, 'X');

-- Credit card balance history
INSERT INTO credit_card_balance
    (application_id, previous_application_id, months_balance, amt_balance, amt_credit_limit_actual,
     amt_drawings_atm_current, amt_drawings_current, amt_drawings_other_current, amt_drawings_pos_current,
     cnt_drawings_atm_current, cnt_drawings_current, cnt_drawings_other_current, cnt_drawings_pos_current,
     amt_inst_min_regularity, amt_payment_total_current, sk_dpd, sk_dpd_def)
VALUES
    (100001, 200002, -1, 8000.00, 20000.00, 500.00,  2000.00, 100.00,  3000.00, 2, 5, 1, 8, 300.00, 3500.00, 0, 0),
    (100001, 200002, -2, 7500.00, 20000.00, 0.00,    1500.00, 0.00,    2800.00, 0, 4, 0, 7, 300.00, 3200.00, 0, 0),
    (100003, 200004, -1, 12000.00, 15000.00, 800.00, 5000.00, 200.00,  4000.00, 3, 9, 1, 12, 600.00, 6000.00, 5, 0),
    (100004, 200005, -1, 4000.00,  5000.00,  0.00,    800.00,  0.00,    1200.00, 0, 3, 0, 4, 200.00, 1000.00, 12, 1);

-- Installment payments
INSERT INTO installment_payment
    (application_id, previous_application_id, installment_version, installment_number,
     days_installment, days_entry_payment, amt_installment, amt_payment)
VALUES
    (100001, 200001, 0, 1, -600, -600, 21000.00, 21000.00),
    (100001, 200001, 0, 2, -570, -570, 21000.00, 21000.00),
    (100001, 200001, 0, 3, -540, -530, 21000.00, 21000.00),
    (100002, 200003, 0, 1, -400, -400, 12000.00, 12000.00),
    (100002, 200003, 0, 2, -370, NULL, 12000.00, 0.00),
    (100004, 200005, 0, 1, -150, -140, 6000.00,  6000.00),
    (100004, 200005, 0, 2, -120, NULL, 6000.00,  2000.00);

-- POS cash balance history
INSERT INTO pos_cash_balance
    (application_id, previous_application_id, months_balance, cnt_installment, cnt_installment_future, contract_status, sk_dpd, sk_dpd_def)
VALUES
    (100001, 200001, -1, 12, 11, 'Active',    0, 0),
    (100001, 200001, -2, 12, 11, 'Active',    0, 0),
    (100003, 200004, -1, 24, 22, 'Active',    3, 0),
    (100004, 200005, -1, 12, 10, 'Active',    10, 1),
    (100005, 200005, -1, 18, 17, 'Completed', 0, 0);

-- Card transactions (synthetic; PCA features V1..V28 are synthetic magnitudes)
INSERT INTO card_transaction
    (occurred_at, amount, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10,
     v11, v12, v13, v14, v15, v16, v17, v18, v19, v20, v21, v22, v23, v24, v25, v26, v27, v28)
VALUES
    ('2023-01-15 10:00:00+00', 45.00, -1.2, 0.4, -0.5, 1.1, -0.2, 0.0, 0.8, -0.1, 0.3, -0.4,
      0.5, -0.6, 0.2, -0.3, 0.1, -0.2, 0.4, -0.5, 0.6, -0.7, 0.8, -0.9, 0.1, -0.2, 0.3, -0.4, 0.5, -0.6),
    ('2023-02-20 14:30:00+00', 180.00, 1.8, -0.6, 1.2, -0.8, 0.5, 1.4, -0.9, 0.7, -1.1, 0.6,
      -0.5, 0.9, -0.7, 0.8, -0.6, 1.0, -0.8, 0.5, -1.2, 0.4, -0.3, 0.6, -0.5, 0.7, -0.8, 0.9, -0.6, 0.4),
    ('2023-03-05 09:15:00+00', 12.00, -0.8, 0.1, -0.3, 0.5, -0.1, 0.2, 0.3, -0.2, 0.1, -0.1,
      0.2, -0.3, 0.1, -0.1, 0.0, -0.1, 0.2, -0.2, 0.3, -0.3, 0.4, -0.4, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3),
    ('2023-04-10 21:45:00+00', 2300.00, -4.5, 3.2, -2.8, 4.1, -3.5, 2.9, -4.0, 3.3, -2.6, 3.8,
      -3.1, 2.7, -3.6, 2.5, -2.9, 3.4, -3.0, 2.8, -3.3, 2.6, -2.7, 3.1, -2.9, 2.4, -3.2, 2.9, -2.8, 3.0),
    ('2023-05-25 13:00:00+00', 95.00, -0.5, 0.3, -0.2, 0.4, -0.3, 0.1, 0.5, -0.4, 0.2, -0.2,
      0.3, -0.4, 0.2, -0.3, 0.1, -0.2, 0.3, -0.3, 0.4, -0.4, 0.5, -0.5, 0.1, -0.2, 0.2, -0.3, 0.3, -0.4);

-- Fraud cases (is_fraud mirrors the source Class label; risk_score is ML output)
INSERT INTO fraud_case (transaction_id, is_fraud, risk_score, rule_triggered, status) VALUES
    (1, false, 0.03, NULL,               'dismissed'),
    (2, false, 0.11, NULL,               'dismissed'),
    (3, false, 0.02, NULL,               'dismissed'),
    (4, true,  0.97, 'large_amount_pca', 'confirmed'),
    (5, false, 0.06, NULL,               'dismissed');

-- Secondary loan book (LendingClub-shaped)
INSERT INTO loan_origination
    (loan_id, borrower_id, loan_status_id, loan_amount, funded_amount, term_months, interest_rate,
     installment, grade, sub_grade, purpose, home_ownership, annual_income, verification_status,
     issue_date, dti, delinq_2yrs, open_acc, total_acc, revol_balance, revol_util, earliest_cr_line)
VALUES
    (500001, 100001, 9, 15000.00, 15000.00, 36, 0.104200, 488.70, 'B', 'B3', 'credit_card',     'MORTGAGE', 85000.00, 'Verified',    '2022-03-01', 22.10, 0, 8,  12, 12000.00, 35.0, '2008-05-01'),
    (500002, 100002, 1, 20000.00, 20000.00, 60, 0.152000, 476.40, 'C', 'C1', 'debt_consolidation','RENT',    45000.00, 'Not Verified','2021-11-15', 28.50, 1, 5,  8,  8000.00,  45.0, '2010-02-01'),
    (500003, 100003, 7, 30000.00, 30000.00, 36, 0.189900, 1100.30, 'D', 'D2', 'small_business',  'OWN',      60000.00, 'Source Verified','2020-06-01', 31.20, 2, 3, 5, 15000.00, 60.0, '2005-01-01'),
    (500004, 100004, 8, 5000.00,  5000.00,  36, 0.235000, 190.20, 'E', 'E1', 'credit_card',     'RENT',     25000.00, 'Not Verified','2022-08-10', 35.00, 3, 2, 3,  5000.00,  70.0, '2012-07-01'),
    (500005, 100005, 9, 25000.00, 25000.00, 60, 0.128000, 567.80, 'A', 'A5', 'home_improvement','MORTGAGE', 95000.00, 'Verified',    '2021-04-20', 18.00, 0, 10, 15, 20000.00, 28.0, '2006-09-01');

INSERT INTO loan_payment (loan_id, installment_no, due_date, payment_date, amount_due, amount_paid) VALUES
    (500001, 1, '2022-04-01', '2022-04-01', 488.70, 488.70),
    (500001, 2, '2022-05-01', '2022-05-02', 488.70, 488.70),
    (500002, 1, '2021-12-15', '2021-12-15', 476.40, 476.40),
    (500002, 2, '2022-01-15', NULL,        476.40, 0.00),
    (500003, 1, '2020-07-01', '2020-07-01', 1100.30, 1100.30),
    (500003, 2, '2020-08-01', NULL,        1100.30, 0.00),
    (500004, 1, '2022-09-10', NULL,        190.20,  0.00),
    (500005, 1, '2021-05-20', '2021-05-20', 567.80, 567.80);

INSERT INTO loan_rejection
    (amount_requested, application_date, risk_score, debt_to_income, state, employment_length, policy_code)
VALUES
    (25000.00, '2022-02-10', 545.00, 38.50, 'CA', '10+ years',  1),
    (12000.00, '2022-06-01', 412.00, 29.00, 'NY', '3 years',    1),
    (40000.00, '2023-01-15', 620.00, 42.00, 'TX', '< 1 year',   1);
