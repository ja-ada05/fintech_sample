-- Fraud dashboard aggregates (monthly KPIs for the future BI dashboard).
-- MySQL version (the PostgreSQL original lives in sql_schema/fraud_dashboard_view.sql).
-- Reads card_transaction + fraud_case (risk_score populated by the fraud model's batch scoring).
CREATE OR REPLACE VIEW v_fraud_dashboard AS
SELECT DATE_FORMAT(ct.occurred_at, '%Y-%m-01') AS month,
       COUNT(*) AS txn_count,
       SUM(CASE WHEN fc.is_fraud THEN 1 ELSE 0 END) AS fraud_count,
       ROUND(100.0 * SUM(CASE WHEN fc.is_fraud THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS fraud_rate_pct,
       SUM(ct.amount) AS total_amount,
       COALESCE(SUM(CASE WHEN fc.is_fraud THEN ct.amount ELSE 0 END), 0) AS fraud_amount,
       SUM(CASE WHEN fc.risk_score >= 0.5 THEN 1 ELSE 0 END) AS flagged_count,
       SUM(CASE WHEN fc.risk_score >= 0.5 AND fc.is_fraud THEN 1 ELSE 0 END) AS true_positive_count
FROM card_transaction ct
LEFT JOIN fraud_case fc ON fc.transaction_id = ct.transaction_id
GROUP BY DATE_FORMAT(ct.occurred_at, '%Y-%m-01');
