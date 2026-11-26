-- ============================================================================
-- NPL compliance schema — mirrors the openNPL EBA NPL template tables we use.
-- Field names follow openNPL's npl_portfolio models (Counterparty, Loan,
-- HistoricalRepayment, Enforcement, Forbearance). See docs/npl-mapping.md.
--
-- Populated by etl_scripts/npl_export.py from credit.loan_origination, then
-- read by etl_scripts/npl_report.py for NPL flagging + the compliance report.
-- ============================================================================

DROP SCHEMA IF EXISTS npl CASCADE;
CREATE SCHEMA npl;

-- EBA Template 1 (Counterparty) — private-individual fields we can map.
CREATE TABLE npl.counterparty (
    counterparty_identifier       text PRIMARY KEY,
    name_of_counterparty          text,
    date_of_birth                 date,
    legal_type_of_counterparty    text,
    industry_segment              text,
    country_of_registered_location text
);

-- EBA Template 3 (Loan) — identification + NPL-relevant mandatory fields.
CREATE TABLE npl.loan (
    loan_identifier          text PRIMARY KEY,
    counterparty_identifier  text REFERENCES npl.counterparty (counterparty_identifier),
    date_of_origination      date,
    loan_currency            text,
    principal_balance        numeric(14,2),
    origination_amount       numeric(14,2),
    current_interest_rate    numeric(7,6),
    original_maturity_date   date,
    days_in_pastdue          integer,
    date_of_default          date,
    loan_status              text,          -- 'performing' | 'non_performing'
    nonperforming_reason     text,
    severity                 text,          -- 'watch' | 'substandard' | 'doubtful' | 'loss'
    product_type             text,
    asset_class              text,
    total_pastdue_amount     numeric(14,2),
    forbearance_measure      boolean DEFAULT false
);

-- EBA Template 5 (Historical Repayment) — normalized to one row per loan/month.
CREATE TABLE npl.historical_repayment (
    loan_identifier               text REFERENCES npl.loan (loan_identifier),
    reference_year                integer,
    reference_month               integer,
    history_of_total_repayments  numeric(14,2),
    PRIMARY KEY (loan_identifier, reference_year, reference_month)
);

-- EBA Template 4 (Enforcement) — legal/collection status.
CREATE TABLE npl.enforcement (
    enforcement_identifier   text PRIMARY KEY,
    counterparty_identifier  text REFERENCES npl.counterparty (counterparty_identifier),
    indicator_of_enforcement boolean,
    enforcement_description  text
);

-- EBA Template 3 (Forbearance) — restructuring measures (N/A for our data).
CREATE TABLE npl.forbearance (
    forbearance_identifier    text PRIMARY KEY,
    loan_identifier           text REFERENCES npl.loan (loan_identifier),
    counterparty_identifier   text REFERENCES npl.counterparty (counterparty_identifier),
    type_of_forbearance       text,
    end_date_of_forbearance   date,
    description_of_forbearance text
);

-- ============================================================================
-- Compliance summary views (live-queryable for the website dashboard)
-- ============================================================================

CREATE VIEW npl.v_compliance_summary AS
SELECT count(*)                                                          AS total_loans,
       count(*) FILTER (WHERE loan_status = 'non_performing')            AS npl_count,
       round(100.0 * count(*) FILTER (WHERE loan_status = 'non_performing')
             / NULLIF(count(*), 0), 2)                                   AS npl_ratio_pct,
       coalesce(sum(principal_balance), 0)                               AS total_exposure,
       coalesce(sum(principal_balance) FILTER (WHERE loan_status = 'non_performing'), 0) AS npl_exposure,
       count(*) FILTER (WHERE forbearance_measure)                       AS forbearance_count,
       count(*) FILTER (WHERE severity = 'watch')                        AS watch_count,
       count(*) FILTER (WHERE severity = 'substandard')                  AS substandard_count,
       count(*) FILTER (WHERE severity = 'doubtful')                     AS doubtful_count,
       count(*) FILTER (WHERE severity = 'loss')                         AS loss_count
FROM npl.loan;

CREATE VIEW npl.v_compliance_by_severity AS
SELECT coalesce(severity, 'performing')                                  AS severity,
       count(*)                                                          AS loan_count,
       coalesce(sum(principal_balance), 0)                               AS exposure,
       round(100.0 * count(*) / NULLIF((SELECT count(*) FROM npl.loan), 0), 2) AS pct_of_portfolio
FROM npl.loan
GROUP BY 1
ORDER BY 1;
