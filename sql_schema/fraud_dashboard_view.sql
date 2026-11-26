-- Fraud dashboard aggregates (monthly KPIs for the future BI dashboard).
-- Reads card_transaction + fraud_case (risk_score populated by ml/train_fraud.py score).
CREATE OR REPLACE VIEW credit.v_fraud_dashboard AS
SELECT date_trunc('month', ct.occurred_at)::date AS month,
       count(*)                                          AS txn_count,
       count(*) FILTER (WHERE fc.is_fraud)               AS fraud_count,
       round(100.0 * count(*) FILTER (WHERE fc.is_fraud) / NULLIF(count(*), 0), 2) AS fraud_rate_pct,
       sum(ct.amount)                                    AS total_amount,
       coalesce(sum(ct.amount) FILTER (WHERE fc.is_fraud), 0) AS fraud_amount,
       count(*) FILTER (WHERE fc.risk_score >= 0.5)      AS flagged_count,
       count(*) FILTER (WHERE fc.risk_score >= 0.5 AND fc.is_fraud) AS true_positive_count
FROM credit.card_transaction ct
LEFT JOIN credit.fraud_case fc ON fc.transaction_id = ct.transaction_id
GROUP BY 1;
