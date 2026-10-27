-- Clearing progress per rule for one run.
SELECT
    rule,
    COUNT(*)                                            AS total,
    SUM(status = 'open')                                AS open,
    SUM(status = 'accepted')                            AS accepted,
    SUM(status = 'fixed')                               AS fixed,
    SUM(status = 'false_positive')                      AS false_positive,
    ROUND(100.0 * SUM(status IN ('fixed', 'false_positive')) / COUNT(*), 1) AS done_pct
FROM findings
WHERE run_id = :run_id
GROUP BY rule
ORDER BY rule;
