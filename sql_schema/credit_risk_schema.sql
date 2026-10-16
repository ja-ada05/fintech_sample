-- ============================================================================
-- Consolidated Credit Risk & Fraud Analytics schema for PostgreSQL 14+
--
-- Data sources (see docs/data_provenance.md for downloads, licenses, mapping):
--   1. Home Credit Default Risk (Kaggle / HuggingFace mirror)  -> credit & bureau area
--   2. Credit Card Fraud Detection (Kaggle, ULB ML Group)      -> card fraud area
--   3. LendingClub accepted/rejected loans + payment history   -> secondary loan book
--
-- These sources do NOT share natural keys, so the three subject areas are linked
-- by conformed reference dimensions and dim_date, exactly like a consolidated
-- analytics warehouse. Cross-area keys (e.g. borrower_id in the loan book) are
-- synthetic and marked [synthetic-link] in the provenance doc.
--
-- Table count: 26 base tables + views (exceeds the >= 20 requirement).
--   12 reference dimensions, 8 credit/bureau entities, 2 fraud entities,
--   3 secondary loan-book entities, 1 shared date dimension.
--
-- Run:  psql -v ON_ERROR_STOP=1 -d <your_db> -f credit_risk_schema.sql
-- ============================================================================

DROP SCHEMA IF EXISTS credit CASCADE;
CREATE SCHEMA credit;
SET search_path = credit, public;

-- ============================================================================
-- Reference dimensions (tables 1-12)
-- ============================================================================

CREATE TABLE ref_contract_type (
    contract_type_id smallint     PRIMARY KEY,
    name             varchar(60)  NOT NULL UNIQUE
);

CREATE TABLE ref_income_type (
    income_type_id  smallint     PRIMARY KEY,
    name            varchar(40)  NOT NULL UNIQUE
);

CREATE TABLE ref_education_type (
    education_type_id smallint     PRIMARY KEY,
    name              varchar(40)  NOT NULL UNIQUE
);

CREATE TABLE ref_family_status (
    family_status_id smallint     PRIMARY KEY,
    name             varchar(30)  NOT NULL UNIQUE
);

CREATE TABLE ref_housing_type (
    housing_type_id smallint     PRIMARY KEY,
    name            varchar(40)  NOT NULL UNIQUE
);

CREATE TABLE ref_occupation_type (
    occupation_type_id smallint     PRIMARY KEY,
    name               varchar(50)  NOT NULL UNIQUE
);

CREATE TABLE ref_organization_type (
    organization_type_id smallint     PRIMARY KEY,
    name                 varchar(60)  NOT NULL UNIQUE
);

CREATE TABLE ref_credit_status (
    credit_status_id smallint     PRIMARY KEY,
    name             varchar(20)  NOT NULL UNIQUE
);

CREATE TABLE ref_loan_status (
    loan_status_id smallint     PRIMARY KEY,
    name           varchar(30)  NOT NULL UNIQUE,
    is_npl         boolean      NOT NULL DEFAULT false
);

CREATE TABLE ref_portfolio (
    portfolio_id smallint     PRIMARY KEY,
    name         varchar(20)  NOT NULL UNIQUE
);

CREATE TABLE ref_channel (
    channel_id smallint     PRIMARY KEY,
    name       varchar(50)  NOT NULL UNIQUE
);

CREATE TABLE ref_payment_type (
    payment_type_id smallint     PRIMARY KEY,
    name            varchar(60)  NOT NULL UNIQUE
);

-- ============================================================================
-- Credit area (Home Credit Default Risk) - tables 13-20
-- ============================================================================

-- One row per borrower. Home Credit does not expose a person-level key, so the
-- borrower id is the current application id (SK_ID_CURR) -- the join hub of the
-- source. Static/personal attributes live here; loan-specific facts live on
-- loan_application.
CREATE TABLE borrower (
    borrower_id               bigint        PRIMARY KEY,
    gender                    char(1)       CHECK (gender IN ('M','F','X')),
    birth_date                date,
    family_status_id          smallint      REFERENCES ref_family_status (family_status_id),
    cnt_children              smallint      NOT NULL DEFAULT 0,
    cnt_fam_members           numeric(5,1),
    income_type_id            smallint      REFERENCES ref_income_type (income_type_id),
    education_type_id         smallint      REFERENCES ref_education_type (education_type_id),
    occupation_type_id        smallint      REFERENCES ref_occupation_type (occupation_type_id),
    organization_type_id      smallint      REFERENCES ref_organization_type (organization_type_id),
    housing_type_id           smallint      REFERENCES ref_housing_type (housing_type_id),
    own_car                   boolean       NOT NULL DEFAULT false,
    own_realty                boolean       NOT NULL DEFAULT false,
    own_car_age               numeric(6,1),
    days_employed             integer,
    amt_income_total          numeric(14,2),
    region_population_relative numeric(8,4),
    region_rating_client      smallint,
    ext_source_1              numeric(8,6),
    ext_source_2              numeric(8,6),
    ext_source_3              numeric(8,6),
    cnt_obs_30_social_circle  smallint,
    cnt_def_30_social_circle  smallint,
    flag_work_phone           boolean,
    flag_phone                boolean,
    flag_email                boolean
);

-- One row per current loan application. target is the default label (0/1);
-- NULL on rows that come from the unlabelled test split.
CREATE TABLE loan_application (
    application_id          bigint        PRIMARY KEY,
    borrower_id             bigint        NOT NULL REFERENCES borrower (borrower_id),
    contract_type_id        smallint      REFERENCES ref_contract_type (contract_type_id),
    amt_credit              numeric(14,2),
    amt_annuity             numeric(14,2),
    amt_goods_price         numeric(14,2),
    target                  smallint      CHECK (target IN (0,1)),
    week_appr_process_start varchar(9),
    hour_appr_process_start smallint,
    days_birth              integer,
    days_last_phone_change  integer,
    amt_req_credit_bureau_year  numeric(8,2),
    amt_req_credit_bureau_quarter numeric(8,2),
    amt_req_credit_bureau_month   numeric(8,2),
    amt_req_credit_bureau_week    numeric(8,2),
    amt_req_credit_bureau_day     numeric(8,2),
    amt_req_credit_bureau_hour    numeric(8,2),
    flags_document          jsonb,        -- FLAG_DOCUMENT_2..21
    extra                   jsonb         -- remaining source columns preserved as-is
);

CREATE TABLE previous_application (
    previous_application_id bigint        PRIMARY KEY,   -- SK_ID_PREV
    application_id          bigint        NOT NULL REFERENCES loan_application (application_id),
    contract_type_id        smallint      REFERENCES ref_contract_type (contract_type_id),
    portfolio_id            smallint      REFERENCES ref_portfolio (portfolio_id),
    channel_id              smallint      REFERENCES ref_channel (channel_id),
    payment_type_id         smallint      REFERENCES ref_payment_type (payment_type_id),
    contract_status         varchar(20)   NOT NULL DEFAULT 'Approved',
    days_decision           integer,
    amt_application         numeric(14,2),
    amt_credit              numeric(14,2),
    amt_annuity             numeric(14,2),
    amt_goods_price         numeric(14,2),
    amt_down_payment        numeric(14,2),
    client_type             varchar(40),
    product_type            varchar(40),
    sellerplace_area        integer,
    seller_industry         varchar(60),
    extra                   jsonb
);

CREATE TABLE bureau_record (
    bureau_record_id      bigint        PRIMARY KEY,   -- SK_ID_BUREAU
    borrower_id           bigint        NOT NULL REFERENCES borrower (borrower_id),
    credit_status_id      smallint      REFERENCES ref_credit_status (credit_status_id),
    contract_type_id      smallint      REFERENCES ref_contract_type (contract_type_id),
    credit_currency       varchar(3),
    days_credit           integer,
    days_credit_enddate   integer,
    credit_day_overdue    integer,
    amt_credit_max_overdue numeric(14,2),
    cnt_credit_prolong    smallint,
    amt_credit_sum        numeric(14,2),
    amt_credit_sum_debt   numeric(14,2),
    amt_credit_sum_limit  numeric(14,2),
    amt_credit_sum_overdue numeric(14,2),
    amt_annuity           numeric(14,2),
    days_enddate_fact     integer
);

CREATE TABLE bureau_balance (
    bureau_record_id bigint    NOT NULL REFERENCES bureau_record (bureau_record_id),
    months_balance   integer   NOT NULL,
    status           char(1)   NOT NULL CHECK (status IN ('C','X','0','1','2','3','4','5')),
    PRIMARY KEY (bureau_record_id, months_balance)
);

CREATE TABLE credit_card_balance (
    balance_id             bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id         bigint        NOT NULL REFERENCES loan_application (application_id),
    previous_application_id bigint       NOT NULL REFERENCES previous_application (previous_application_id),
    months_balance         integer       NOT NULL,
    amt_balance            numeric(14,2),
    amt_credit_limit_actual numeric(14,2),
    amt_drawings_atm_current numeric(14,2),
    amt_drawings_current   numeric(14,2),
    amt_drawings_other_current numeric(14,2),
    amt_drawings_pos_current numeric(14,2),
    cnt_drawings_atm_current numeric(7,2),
    cnt_drawings_current   numeric(7,2),
    cnt_drawings_other_current numeric(7,2),
    cnt_drawings_pos_current numeric(7,2),
    amt_inst_min_regularity numeric(14,2),
    amt_payment_total_current numeric(14,2),
    sk_dpd                 integer,
    sk_dpd_def             integer
);

CREATE TABLE installment_payment (
    payment_id             bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id         bigint        NOT NULL REFERENCES loan_application (application_id),
    previous_application_id bigint       NOT NULL REFERENCES previous_application (previous_application_id),
    installment_version    integer       NOT NULL,
    installment_number     integer       NOT NULL,
    days_installment       integer,
    days_entry_payment     integer,
    amt_installment        numeric(14,2),
    amt_payment            numeric(14,2),
    UNIQUE (previous_application_id, installment_version, installment_number)
);

CREATE TABLE pos_cash_balance (
    pos_balance_id         bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id         bigint        NOT NULL REFERENCES loan_application (application_id),
    previous_application_id bigint       NOT NULL REFERENCES previous_application (previous_application_id),
    months_balance         integer       NOT NULL,
    cnt_installment        integer,
    cnt_installment_future integer,
    contract_status        varchar(20),
    sk_dpd                 integer,
    sk_dpd_def             integer
);

-- ============================================================================
-- Fraud area (Credit Card Fraud Detection, ULB ML Group) - tables 21-22
-- ============================================================================

-- One row per card transaction. V1..V28 are the PCA-transformed features from
-- the source (anonymised); amount and occurred_at are the only raw fields.
CREATE TABLE card_transaction (
    transaction_id bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at    timestamptz   NOT NULL,
    amount         numeric(14,2) NOT NULL,
    v1  numeric(20,10), v2  numeric(20,10), v3  numeric(20,10), v4  numeric(20,10),
    v5  numeric(20,10), v6  numeric(20,10), v7  numeric(20,10), v8  numeric(20,10),
    v9  numeric(20,10), v10 numeric(20,10), v11 numeric(20,10), v12 numeric(20,10),
    v13 numeric(20,10), v14 numeric(20,10), v15 numeric(20,10), v16 numeric(20,10),
    v17 numeric(20,10), v18 numeric(20,10), v19 numeric(20,10), v20 numeric(20,10),
    v21 numeric(20,10), v22 numeric(20,10), v23 numeric(20,10), v24 numeric(20,10),
    v25 numeric(20,10), v26 numeric(20,10), v27 numeric(20,10), v28 numeric(20,10)
);

CREATE TABLE fraud_case (
    fraud_case_id   bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_id  bigint        NOT NULL REFERENCES card_transaction (transaction_id),
    is_fraud        boolean       NOT NULL DEFAULT false,
    risk_score      numeric(4,3)  CHECK (risk_score BETWEEN 0 AND 1),
    rule_triggered  varchar(40),
    status          varchar(10)   NOT NULL DEFAULT 'open'
                                  CHECK (status IN ('open','reviewing','confirmed','dismissed')),
    created_at      timestamptz   NOT NULL DEFAULT now()
);

-- ============================================================================
-- Secondary loan book (LendingClub) - tables 23-25
-- ============================================================================

CREATE TABLE loan_origination (
    loan_id            bigint        PRIMARY KEY,
    borrower_id        bigint        REFERENCES borrower (borrower_id),   -- [synthetic-link]
    loan_status_id     smallint      REFERENCES ref_loan_status (loan_status_id),
    loan_amount        numeric(14,2) NOT NULL,
    funded_amount      numeric(14,2),
    term_months        smallint      NOT NULL CHECK (term_months IN (36,60)),
    interest_rate      numeric(7,6)  CHECK (interest_rate >= 0 AND interest_rate < 1),
    installment        numeric(14,2),
    grade              char(1),
    sub_grade          varchar(2),
    purpose            varchar(40),
    home_ownership     varchar(20),
    annual_income      numeric(14,2),
    verification_status varchar(20),
    issue_date         date          NOT NULL,
    dti                numeric(6,2),
    delinq_2yrs        smallint,
    open_acc           smallint,
    total_acc          smallint,
    revol_balance      numeric(14,2),
    revol_util         numeric(6,2),
    earliest_cr_line   date
);

CREATE TABLE loan_payment (
    loan_payment_id bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    loan_id         bigint        NOT NULL REFERENCES loan_origination (loan_id),
    installment_no  integer       NOT NULL,
    due_date        date,
    payment_date    date,
    amount_due      numeric(14,2),
    amount_paid     numeric(14,2) NOT NULL DEFAULT 0
);

CREATE TABLE loan_rejection (
    rejection_id      bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount_requested  numeric(14,2),
    application_date  date,
    risk_score        numeric(8,2),
    debt_to_income    numeric(6,2),
    state             varchar(2),
    employment_length varchar(30),
    policy_code       smallint
);

-- ============================================================================
-- Shared date dimension (table 26)
-- ============================================================================

CREATE TABLE dim_date (
    date_id      integer  PRIMARY KEY,   -- YYYYMMDD
    full_date    date     NOT NULL UNIQUE,
    year         smallint NOT NULL,
    quarter      smallint NOT NULL,
    month        smallint NOT NULL,
    day          smallint NOT NULL,
    day_of_week  smallint NOT NULL,
    week_of_year smallint NOT NULL,
    is_weekend   boolean  NOT NULL
);

-- ============================================================================
-- Indexes (foreign keys + common dashboard/ML filters)
-- ============================================================================
CREATE INDEX ix_app_borrower        ON loan_application (borrower_id);
CREATE INDEX ix_app_contract        ON loan_application (contract_type_id);
CREATE INDEX ix_prev_app_app        ON previous_application (application_id);
CREATE INDEX ix_bureau_borrower     ON bureau_record (borrower_id);
CREATE INDEX ix_bureau_credit_status ON bureau_record (credit_status_id);
CREATE INDEX ix_ccb_app             ON credit_card_balance (application_id, months_balance);
CREATE INDEX ix_inst_app            ON installment_payment (application_id);
CREATE INDEX ix_inst_prev           ON installment_payment (previous_application_id);
CREATE INDEX ix_pos_app             ON pos_cash_balance (application_id, months_balance);
CREATE INDEX ix_card_time           ON card_transaction (occurred_at);
CREATE INDEX ix_fraud_status        ON fraud_case (status);
CREATE INDEX ix_loan_status         ON loan_origination (loan_status_id);
CREATE INDEX ix_loan_issue          ON loan_origination (issue_date);
CREATE INDEX ix_loan_payment_loan   ON loan_payment (loan_id);

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
    (1,'current',false),(2,'performing',false),(3,'in_grace_period',false),
    (4,'late_16_30',true),(5,'late_31_120',true),(6,'delinquent',true),
    (7,'default',true),(8,'charged_off',true),(9,'paid_off',false),(10,'canceled',false);

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
-- Analytical views (read by the dashboard, ML and openNPL pipelines)
-- ============================================================================

-- Application + borrower + ref names, one row per application (for dashboards)
CREATE VIEW v_application_overview AS
SELECT a.application_id,
       b.borrower_id,
       b.gender,
       b.birth_date,
       ct.name    AS contract_type,
       it.name    AS income_type,
       et.name    AS education_type,
       fs.name    AS family_status,
       a.amt_credit,
       a.amt_annuity,
       a.amt_goods_price,
       a.target   AS default_flag,
       b.amt_income_total,
       b.ext_source_1,
       b.ext_source_2,
       b.ext_source_3
FROM loan_application a
JOIN borrower b            ON b.borrower_id = a.borrower_id
LEFT JOIN ref_contract_type ct  ON ct.contract_type_id = a.contract_type_id
LEFT JOIN ref_income_type  it   ON it.income_type_id  = b.income_type_id
LEFT JOIN ref_education_type et ON et.education_type_id = b.education_type_id
LEFT JOIN ref_family_status fs ON fs.family_status_id = b.family_status_id;

-- Flat ML feature set for default-risk modelling (one row per application)
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

-- Secondary loan book by status/grade/purpose
CREATE VIEW v_loan_portfolio AS
SELECT ls.name                       AS loan_status,
       ls.is_npl,
       lo.grade,
       lo.purpose,
       count(*)                      AS loans,
       sum(lo.loan_amount)           AS total_principal,
       round(avg(lo.interest_rate)*100, 2) AS avg_rate_pct
FROM loan_origination lo
JOIN ref_loan_status ls ON ls.loan_status_id = lo.loan_status_id
GROUP BY ls.name, ls.is_npl, lo.grade, lo.purpose;

-- Fraud overview for dashboards
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

-- Installments past due (amount_due > amount_paid) for overdue reporting
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

-- NPL records for the openNPL compliance export
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

-- Monthly card transaction volume (materialised; refresh with:
--   REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_transaction_summary;)
CREATE MATERIALIZED VIEW mv_monthly_transaction_summary AS
SELECT date_trunc('month', occurred_at)::date AS month,
       count(*)                               AS txn_count,
       sum(amount)                            AS total_amount,
       sum(CASE WHEN fc.is_fraud THEN 1 ELSE 0 END) AS fraud_count
FROM card_transaction ct
LEFT JOIN fraud_case fc ON fc.transaction_id = ct.transaction_id
GROUP BY 1;

CREATE UNIQUE INDEX ux_mv_monthly_txn ON mv_monthly_transaction_summary (month);
