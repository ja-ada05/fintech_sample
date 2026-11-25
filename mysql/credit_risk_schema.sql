-- ============================================================================
-- Consolidated Credit Risk & Fraud Analytics schema for MySQL 8+
--
-- MySQL version. The PostgreSQL original remains in
-- sql_schema/credit_risk_schema.sql (retained as the openNPL compliance
-- module's Postgres source). These two are the SAME logical 26-table schema
-- in different dialects.
--
-- Data sources (see docs/data_provenance.md):
--   1. Home Credit Default Risk   -> credit & bureau area
--   2. Credit Card Fraud (ULB)    -> card fraud area
--   3. LendingClub                -> secondary loan book
--
-- Run:  mysql -u <user> -p < credit_risk_schema.sql
-- ============================================================================

DROP DATABASE IF EXISTS credit;
CREATE DATABASE credit CHARACTER SET utf8mb4;
USE credit;

-- ============================================================================
-- Reference dimensions (tables 1-12)
-- ============================================================================

CREATE TABLE ref_contract_type (
    contract_type_id SMALLINT PRIMARY KEY,
    name VARCHAR(60) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_income_type (
    income_type_id SMALLINT PRIMARY KEY,
    name VARCHAR(40) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_education_type (
    education_type_id SMALLINT PRIMARY KEY,
    name VARCHAR(40) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_family_status (
    family_status_id SMALLINT PRIMARY KEY,
    name VARCHAR(30) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_housing_type (
    housing_type_id SMALLINT PRIMARY KEY,
    name VARCHAR(40) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_occupation_type (
    occupation_type_id SMALLINT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_organization_type (
    organization_type_id SMALLINT PRIMARY KEY,
    name VARCHAR(60) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_credit_status (
    credit_status_id SMALLINT PRIMARY KEY,
    name VARCHAR(20) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_loan_status (
    loan_status_id SMALLINT PRIMARY KEY,
    name VARCHAR(30) NOT NULL UNIQUE,
    is_npl TINYINT(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE ref_portfolio (
    portfolio_id SMALLINT PRIMARY KEY,
    name VARCHAR(20) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_channel (
    channel_id SMALLINT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE ref_payment_type (
    payment_type_id SMALLINT PRIMARY KEY,
    name VARCHAR(60) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- ============================================================================
-- Credit area (Home Credit Default Risk) - tables 13-20
-- ============================================================================

CREATE TABLE borrower (
    borrower_id BIGINT PRIMARY KEY,
    gender CHAR(1),
    birth_date DATE,
    family_status_id SMALLINT,
    cnt_children SMALLINT NOT NULL DEFAULT 0,
    cnt_fam_members DECIMAL(5,1),
    income_type_id SMALLINT,
    education_type_id SMALLINT,
    occupation_type_id SMALLINT,
    organization_type_id SMALLINT,
    housing_type_id SMALLINT,
    own_car TINYINT(1) NOT NULL DEFAULT 0,
    own_realty TINYINT(1) NOT NULL DEFAULT 0,
    own_car_age DECIMAL(6,1),
    days_employed INT,
    amt_income_total DECIMAL(14,2),
    region_population_relative DECIMAL(8,4),
    region_rating_client SMALLINT,
    ext_source_1 DECIMAL(8,6),
    ext_source_2 DECIMAL(8,6),
    ext_source_3 DECIMAL(8,6),
    cnt_obs_30_social_circle SMALLINT,
    cnt_def_30_social_circle SMALLINT,
    flag_work_phone TINYINT(1),
    flag_phone TINYINT(1),
    flag_email TINYINT(1),
    CONSTRAINT chk_borrower_gender CHECK (gender IN ('M','F','X')),
    CONSTRAINT fk_borrower_family FOREIGN KEY (family_status_id) REFERENCES ref_family_status (family_status_id),
    CONSTRAINT fk_borrower_income FOREIGN KEY (income_type_id) REFERENCES ref_income_type (income_type_id),
    CONSTRAINT fk_borrower_education FOREIGN KEY (education_type_id) REFERENCES ref_education_type (education_type_id),
    CONSTRAINT fk_borrower_occupation FOREIGN KEY (occupation_type_id) REFERENCES ref_occupation_type (occupation_type_id),
    CONSTRAINT fk_borrower_organization FOREIGN KEY (organization_type_id) REFERENCES ref_organization_type (organization_type_id),
    CONSTRAINT fk_borrower_housing FOREIGN KEY (housing_type_id) REFERENCES ref_housing_type (housing_type_id)
) ENGINE=InnoDB;

CREATE TABLE loan_application (
    application_id BIGINT PRIMARY KEY,
    borrower_id BIGINT NOT NULL,
    contract_type_id SMALLINT,
    amt_credit DECIMAL(14,2),
    amt_annuity DECIMAL(14,2),
    amt_goods_price DECIMAL(14,2),
    target SMALLINT,
    week_appr_process_start VARCHAR(9),
    hour_appr_process_start SMALLINT,
    days_birth INT,
    days_last_phone_change INT,
    amt_req_credit_bureau_year DECIMAL(8,2),
    amt_req_credit_bureau_quarter DECIMAL(8,2),
    amt_req_credit_bureau_month DECIMAL(8,2),
    amt_req_credit_bureau_week DECIMAL(8,2),
    amt_req_credit_bureau_day DECIMAL(8,2),
    amt_req_credit_bureau_hour DECIMAL(8,2),
    flags_document JSON,
    extra JSON,
    CONSTRAINT chk_app_target CHECK (target IN (0,1)),
    CONSTRAINT fk_app_borrower FOREIGN KEY (borrower_id) REFERENCES borrower (borrower_id),
    CONSTRAINT fk_app_contract FOREIGN KEY (contract_type_id) REFERENCES ref_contract_type (contract_type_id)
) ENGINE=InnoDB;

CREATE TABLE previous_application (
    previous_application_id BIGINT PRIMARY KEY,
    application_id BIGINT NOT NULL,
    contract_type_id SMALLINT,
    portfolio_id SMALLINT,
    channel_id SMALLINT,
    payment_type_id SMALLINT,
    contract_status VARCHAR(20) NOT NULL DEFAULT 'Approved',
    days_decision INT,
    amt_application DECIMAL(14,2),
    amt_credit DECIMAL(14,2),
    amt_annuity DECIMAL(14,2),
    amt_goods_price DECIMAL(14,2),
    amt_down_payment DECIMAL(14,2),
    client_type VARCHAR(40),
    product_type VARCHAR(40),
    sellerplace_area INT,
    seller_industry VARCHAR(60),
    extra JSON,
    CONSTRAINT fk_prev_app FOREIGN KEY (application_id) REFERENCES loan_application (application_id),
    CONSTRAINT fk_prev_contract FOREIGN KEY (contract_type_id) REFERENCES ref_contract_type (contract_type_id),
    CONSTRAINT fk_prev_portfolio FOREIGN KEY (portfolio_id) REFERENCES ref_portfolio (portfolio_id),
    CONSTRAINT fk_prev_channel FOREIGN KEY (channel_id) REFERENCES ref_channel (channel_id),
    CONSTRAINT fk_prev_payment_type FOREIGN KEY (payment_type_id) REFERENCES ref_payment_type (payment_type_id)
) ENGINE=InnoDB;

CREATE TABLE bureau_record (
    bureau_record_id BIGINT PRIMARY KEY,
    borrower_id BIGINT NOT NULL,
    credit_status_id SMALLINT,
    contract_type_id SMALLINT,
    credit_currency VARCHAR(20),
    days_credit INT,
    days_credit_enddate INT,
    credit_day_overdue INT,
    amt_credit_max_overdue DECIMAL(14,2),
    cnt_credit_prolong SMALLINT,
    amt_credit_sum DECIMAL(14,2),
    amt_credit_sum_debt DECIMAL(14,2),
    amt_credit_sum_limit DECIMAL(14,2),
    amt_credit_sum_overdue DECIMAL(14,2),
    amt_annuity DECIMAL(14,2),
    days_enddate_fact INT,
    CONSTRAINT fk_bureau_borrower FOREIGN KEY (borrower_id) REFERENCES borrower (borrower_id),
    CONSTRAINT fk_bureau_credit_status FOREIGN KEY (credit_status_id) REFERENCES ref_credit_status (credit_status_id),
    CONSTRAINT fk_bureau_contract FOREIGN KEY (contract_type_id) REFERENCES ref_contract_type (contract_type_id)
) ENGINE=InnoDB;

CREATE TABLE bureau_balance (
    bureau_record_id BIGINT NOT NULL,
    months_balance INT NOT NULL,
    status CHAR(1) NOT NULL,
    PRIMARY KEY (bureau_record_id, months_balance),
    CONSTRAINT chk_bureau_balance_status CHECK (status IN ('C','X','0','1','2','3','4','5')),
    CONSTRAINT fk_bureau_balance_record FOREIGN KEY (bureau_record_id) REFERENCES bureau_record (bureau_record_id)
) ENGINE=InnoDB;

CREATE TABLE credit_card_balance (
    balance_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    application_id BIGINT NOT NULL,
    previous_application_id BIGINT NOT NULL,
    months_balance INT NOT NULL,
    amt_balance DECIMAL(14,2),
    amt_credit_limit_actual DECIMAL(14,2),
    amt_drawings_atm_current DECIMAL(14,2),
    amt_drawings_current DECIMAL(14,2),
    amt_drawings_other_current DECIMAL(14,2),
    amt_drawings_pos_current DECIMAL(14,2),
    cnt_drawings_atm_current DECIMAL(7,2),
    cnt_drawings_current DECIMAL(7,2),
    cnt_drawings_other_current DECIMAL(7,2),
    cnt_drawings_pos_current DECIMAL(7,2),
    amt_inst_min_regularity DECIMAL(14,2),
    amt_payment_total_current DECIMAL(14,2),
    sk_dpd INT,
    sk_dpd_def INT,
    CONSTRAINT fk_ccb_app FOREIGN KEY (application_id) REFERENCES loan_application (application_id),
    CONSTRAINT fk_ccb_prev FOREIGN KEY (previous_application_id) REFERENCES previous_application (previous_application_id)
) ENGINE=InnoDB;

CREATE TABLE installment_payment (
    payment_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    application_id BIGINT NOT NULL,
    previous_application_id BIGINT NOT NULL,
    installment_version INT NOT NULL,
    installment_number INT NOT NULL,
    days_installment INT,
    days_entry_payment INT,
    amt_installment DECIMAL(14,2),
    amt_payment DECIMAL(14,2),
    UNIQUE KEY ux_installment (previous_application_id, installment_version, installment_number),
    CONSTRAINT fk_inst_app FOREIGN KEY (application_id) REFERENCES loan_application (application_id),
    CONSTRAINT fk_inst_prev FOREIGN KEY (previous_application_id) REFERENCES previous_application (previous_application_id)
) ENGINE=InnoDB;

CREATE TABLE pos_cash_balance (
    pos_balance_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    application_id BIGINT NOT NULL,
    previous_application_id BIGINT NOT NULL,
    months_balance INT NOT NULL,
    cnt_installment INT,
    cnt_installment_future INT,
    contract_status VARCHAR(30),
    sk_dpd INT,
    sk_dpd_def INT,
    CONSTRAINT fk_pos_app FOREIGN KEY (application_id) REFERENCES loan_application (application_id),
    CONSTRAINT fk_pos_prev FOREIGN KEY (previous_application_id) REFERENCES previous_application (previous_application_id)
) ENGINE=InnoDB;

-- ============================================================================
-- Fraud area (Credit Card Fraud Detection, ULB) - tables 21-22
-- ============================================================================

CREATE TABLE card_transaction (
    transaction_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    occurred_at DATETIME NOT NULL,
    amount DECIMAL(14,2) NOT NULL,
    v1 DECIMAL(20,10), v2 DECIMAL(20,10), v3 DECIMAL(20,10), v4 DECIMAL(20,10),
    v5 DECIMAL(20,10), v6 DECIMAL(20,10), v7 DECIMAL(20,10), v8 DECIMAL(20,10),
    v9 DECIMAL(20,10), v10 DECIMAL(20,10), v11 DECIMAL(20,10), v12 DECIMAL(20,10),
    v13 DECIMAL(20,10), v14 DECIMAL(20,10), v15 DECIMAL(20,10), v16 DECIMAL(20,10),
    v17 DECIMAL(20,10), v18 DECIMAL(20,10), v19 DECIMAL(20,10), v20 DECIMAL(20,10),
    v21 DECIMAL(20,10), v22 DECIMAL(20,10), v23 DECIMAL(20,10), v24 DECIMAL(20,10),
    v25 DECIMAL(20,10), v26 DECIMAL(20,10), v27 DECIMAL(20,10), v28 DECIMAL(20,10)
) ENGINE=InnoDB;

CREATE TABLE fraud_case (
    fraud_case_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    transaction_id BIGINT NOT NULL,
    is_fraud TINYINT(1) NOT NULL DEFAULT 0,
    risk_score DECIMAL(4,3),
    rule_triggered VARCHAR(40),
    status VARCHAR(10) NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_fraud_risk_score CHECK (risk_score BETWEEN 0 AND 1),
    CONSTRAINT chk_fraud_status CHECK (status IN ('open','reviewing','confirmed','dismissed')),
    CONSTRAINT fk_fraud_txn FOREIGN KEY (transaction_id) REFERENCES card_transaction (transaction_id)
) ENGINE=InnoDB;

-- ============================================================================
-- Secondary loan book (LendingClub) - tables 23-25
-- ============================================================================

CREATE TABLE loan_origination (
    loan_id BIGINT PRIMARY KEY,
    borrower_id BIGINT,
    loan_status_id SMALLINT,
    loan_amount DECIMAL(14,2) NOT NULL,
    funded_amount DECIMAL(14,2),
    term_months SMALLINT NOT NULL,
    interest_rate DECIMAL(7,6),
    installment DECIMAL(14,2),
    grade CHAR(1),
    sub_grade VARCHAR(2),
    purpose VARCHAR(40),
    home_ownership VARCHAR(20),
    annual_income DECIMAL(14,2),
    verification_status VARCHAR(20),
    issue_date DATE NOT NULL,
    dti DECIMAL(6,2),
    delinq_2yrs SMALLINT,
    open_acc SMALLINT,
    total_acc SMALLINT,
    revol_balance DECIMAL(14,2),
    revol_util DECIMAL(6,2),
    earliest_cr_line DATE,
    CONSTRAINT chk_loan_term CHECK (term_months IN (36,60)),
    CONSTRAINT chk_loan_rate CHECK (interest_rate >= 0 AND interest_rate < 1),
    CONSTRAINT fk_loan_borrower FOREIGN KEY (borrower_id) REFERENCES borrower (borrower_id),
    CONSTRAINT fk_loan_status FOREIGN KEY (loan_status_id) REFERENCES ref_loan_status (loan_status_id)
) ENGINE=InnoDB;

CREATE TABLE loan_payment (
    loan_payment_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    loan_id BIGINT NOT NULL,
    installment_no INT NOT NULL,
    due_date DATE,
    payment_date DATE,
    amount_due DECIMAL(14,2),
    amount_paid DECIMAL(14,2) NOT NULL DEFAULT 0,
    CONSTRAINT fk_loan_payment_loan FOREIGN KEY (loan_id) REFERENCES loan_origination (loan_id)
) ENGINE=InnoDB;

CREATE TABLE loan_rejection (
    rejection_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    amount_requested DECIMAL(14,2),
    application_date DATE,
    risk_score DECIMAL(8,2),
    debt_to_income DECIMAL(6,2),
    state VARCHAR(2),
    employment_length VARCHAR(30),
    policy_code SMALLINT
) ENGINE=InnoDB;

-- ============================================================================
-- Shared date dimension (table 26)
-- ============================================================================

CREATE TABLE dim_date (
    date_id INT PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year SMALLINT NOT NULL,
    quarter SMALLINT NOT NULL,
    month SMALLINT NOT NULL,
    day SMALLINT NOT NULL,
    day_of_week SMALLINT NOT NULL,
    week_of_year SMALLINT NOT NULL,
    is_weekend TINYINT(1) NOT NULL
) ENGINE=InnoDB;

-- ============================================================================
-- Indexes (foreign keys + common dashboard/ML filters)
-- ============================================================================
CREATE INDEX ix_app_borrower ON loan_application (borrower_id);
CREATE INDEX ix_app_contract ON loan_application (contract_type_id);
CREATE INDEX ix_prev_app_app ON previous_application (application_id);
CREATE INDEX ix_bureau_borrower ON bureau_record (borrower_id);
CREATE INDEX ix_bureau_credit_status ON bureau_record (credit_status_id);
CREATE INDEX ix_ccb_app ON credit_card_balance (application_id, months_balance);
CREATE INDEX ix_inst_app ON installment_payment (application_id);
CREATE INDEX ix_inst_prev ON installment_payment (previous_application_id);
CREATE INDEX ix_pos_app ON pos_cash_balance (application_id, months_balance);
CREATE INDEX ix_card_time ON card_transaction (occurred_at);
CREATE INDEX ix_fraud_status ON fraud_case (status);
CREATE INDEX ix_loan_status ON loan_origination (loan_status_id);
CREATE INDEX ix_loan_issue ON loan_origination (issue_date);
CREATE INDEX ix_loan_payment_loan ON loan_payment (loan_id);

-- ============================================================================
-- Reference data
-- ============================================================================
INSERT INTO ref_contract_type VALUES
    (1,'Cash loans'),(2,'Revolving loans'),(3,'Consumer loans'),(4,'Consumer credit'),
    (5,'Credit card'),(6,'Mortgage'),(7,'Car loan'),(8,'Microloan'),
    (9,'Loan for business development'),(10,'Loan for purchase of equipment'),
    (11,'Loan for working capital replenishment'),(12,'Real estate loan'),
    (13,'Another type of loan'),(14,'Unknown');

INSERT INTO ref_income_type VALUES
    (1,'Working'),(2,'State servant'),(3,'Commercial associate'),(4,'Pensioner'),
    (5,'Unemployed'),(6,'Student'),(7,'Businessman'),(8,'Maternity leave'),(9,'XNA');

INSERT INTO ref_education_type VALUES
    (1,'Secondary / secondary special'),(2,'Higher education'),(3,'Incomplete higher'),
    (4,'Lower secondary'),(5,'Academic degree'),(6,'XNA');

INSERT INTO ref_family_status VALUES
    (1,'Married'),(2,'Single'),(3,'Civil marriage'),(4,'Separated'),(5,'Widow'),(6,'XNA');

INSERT INTO ref_housing_type VALUES
    (1,'House / apartment'),(2,'Rented apartment'),(3,'With parents'),
    (4,'Municipal apartment'),(5,'Office apartment'),(6,'Co-op apartment'),(7,'XNA');

INSERT INTO ref_occupation_type VALUES
    (1,'Laborers'),(2,'Core staff'),(3,'Accountants'),(4,'Managers'),(5,'Drivers'),
    (6,'Sales staff'),(7,'Cleaning staff'),(8,'Cooking staff'),(9,'Private service staff'),
    (10,'Medicine staff'),(11,'Security staff'),(12,'High skill tech staff'),
    (13,'Low-skill Laborers'),(14,'Waiters/barmen staff'),(15,'Secretaries'),
    (16,'Realty agents'),(17,'HR staff'),(18,'IT staff'),(19,'XNA');

INSERT INTO ref_organization_type VALUES
    (1,'Business Entity Type 3'),(2,'School'),(3,'Trade: type 7'),(4,'Self-employed'),
    (5,'Transport: type 3'),(6,'Industry: type 3'),(7,'Bank'),(8,'Construction'),
    (9,'Agriculture'),(10,'Housing'),(11,'Kindergarten'),(12,'Trade: type 2'),
    (13,'Industry: type 11'),(14,'Military'),(15,'XNA');

INSERT INTO ref_credit_status VALUES
    (1,'Active'),(2,'Closed'),(3,'Sold'),(4,'Bad debt'),(5,'XNA');

INSERT INTO ref_loan_status VALUES
    (1,'current',0),(2,'performing',0),(3,'in_grace_period',0),
    (4,'late_16_30',1),(5,'late_31_120',1),(6,'delinquent',1),
    (7,'default',1),(8,'charged_off',1),(9,'paid_off',0),(10,'canceled',0);

INSERT INTO ref_portfolio VALUES
    (1,'POS'),(2,'Cards'),(3,'Cash'),(4,'Car'),(5,'Mortgage'),(6,'XNA');

INSERT INTO ref_channel VALUES
    (1,'Credit and cash offices'),(2,'Country-wide'),(3,'Regional'),(4,'Stone'),
    (5,'AP+ (Cash loan)'),(6,'Contact center'),(7,'Car dealer'),
    (8,'Channel of corporate sales'),(9,'XNA');

INSERT INTO ref_payment_type VALUES
    (1,'Cash through the bank'),(2,'Cashless from the account of employer'),
    (3,'Non-cash from your account'),(4,'XNA');

-- ============================================================================
-- Analytical views (read by the dashboard, ML and NPL pipelines)
-- ============================================================================

CREATE VIEW v_application_overview AS
SELECT a.application_id,
       b.borrower_id,
       b.gender,
       b.birth_date,
       ct.name AS contract_type,
       it.name AS income_type,
       et.name AS education_type,
       fs.name AS family_status,
       a.amt_credit,
       a.amt_annuity,
       a.amt_goods_price,
       a.target AS default_flag,
       b.amt_income_total,
       b.ext_source_1,
       b.ext_source_2,
       b.ext_source_3
FROM loan_application a
JOIN borrower b ON b.borrower_id = a.borrower_id
LEFT JOIN ref_contract_type ct ON ct.contract_type_id = a.contract_type_id
LEFT JOIN ref_income_type it ON it.income_type_id = b.income_type_id
LEFT JOIN ref_education_type et ON et.education_type_id = b.education_type_id
LEFT JOIN ref_family_status fs ON fs.family_status_id = b.family_status_id;

CREATE VIEW v_default_features AS
SELECT a.application_id,
       a.target,
       a.amt_credit,
       a.amt_annuity,
       a.amt_goods_price,
       b.amt_income_total,
       b.days_employed,
       a.days_birth,
       b.cnt_children,
       b.cnt_fam_members,
       b.ext_source_1,
       b.ext_source_2,
       b.ext_source_3,
       b.region_rating_client,
       a.contract_type_id,
       b.income_type_id,
       b.education_type_id,
       b.family_status_id,
       b.housing_type_id,
       b.occupation_type_id
FROM loan_application a
JOIN borrower b ON b.borrower_id = a.borrower_id;

CREATE VIEW v_loan_portfolio AS
SELECT ls.name AS loan_status,
       ls.is_npl,
       lo.grade,
       lo.purpose,
       COUNT(*) AS loans,
       SUM(lo.loan_amount) AS total_principal,
       ROUND(AVG(lo.interest_rate) * 100, 2) AS avg_rate_pct
FROM loan_origination lo
JOIN ref_loan_status ls ON ls.loan_status_id = lo.loan_status_id
GROUP BY ls.name, ls.is_npl, lo.grade, lo.purpose;

CREATE VIEW v_fraud_overview AS
SELECT fc.fraud_case_id,
       fc.transaction_id,
       ct.amount,
       ct.occurred_at,
       fc.is_fraud,
       fc.risk_score,
       fc.rule_triggered,
       fc.status
FROM fraud_case fc
JOIN card_transaction ct ON ct.transaction_id = fc.transaction_id;

CREATE VIEW v_overdue_installments AS
SELECT ip.previous_application_id,
       ip.application_id,
       ip.installment_number,
       ip.days_installment,
       ip.amt_installment,
       ip.amt_payment,
       (ip.amt_installment - ip.amt_payment) AS amount_outstanding
FROM installment_payment ip
WHERE ip.amt_payment < ip.amt_installment;

CREATE VIEW v_npl_export AS
SELECT lo.loan_id,
       lo.borrower_id,
       lo.issue_date,
       lo.loan_amount,
       lo.interest_rate,
       lo.term_months,
       ls.name AS loan_status,
       ls.is_npl
FROM loan_origination lo
JOIN ref_loan_status ls ON ls.loan_status_id = lo.loan_status_id
WHERE ls.is_npl;

-- Monthly transaction summary. In PostgreSQL this was a MATERIALIZED VIEW; MySQL has
-- no materialized views, so it is a regular table refreshed by the ETL (or manually):
--   INSERT INTO monthly_transaction_summary (month, txn_count, total_amount, fraud_count)
--   SELECT DATE_FORMAT(occurred_at, '%Y-%m-01'), COUNT(*), SUM(amount),
--          SUM(CASE WHEN fc.is_fraud THEN 1 ELSE 0 END)
--   FROM card_transaction ct LEFT JOIN fraud_case fc ON fc.transaction_id = ct.transaction_id
--   GROUP BY 1
--   ON DUPLICATE KEY UPDATE
--     txn_count = VALUES(txn_count), total_amount = VALUES(total_amount), fraud_count = VALUES(fraud_count);
CREATE TABLE monthly_transaction_summary (
    month DATE PRIMARY KEY,
    txn_count BIGINT NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    fraud_count BIGINT NOT NULL
) ENGINE=InnoDB;
