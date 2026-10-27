-- Readiness per object type. Each record gets the penalty of its worst finding
-- (blocker 1.0, error 0.6, warning 0.25, info 0). Records without findings count as 0.
-- Score = 100 * (1 - average penalty).
WITH worst AS (
    SELECT object, key, MAX(weight) AS penalty
    FROM findings
    GROUP BY object, key
),
per_object AS (
    SELECT object, COUNT(*) AS records_with_findings, SUM(penalty) AS penalty_sum
    FROM worst
    GROUP BY object
)
SELECT
    t.object,
    t.total,
    COALESCE(p.records_with_findings, 0) AS records_with_findings,
    ROUND(100.0 * (1 - COALESCE(p.penalty_sum, 0) / t.total), 1) AS readiness
FROM totals t
LEFT JOIN per_object p ON p.object = t.object
ORDER BY t.object;
