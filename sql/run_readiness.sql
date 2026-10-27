-- Readiness for one run, twice: as found, and now. Fixed findings and
-- false positives no longer count against a record. Same formula as
-- readiness.sql: worst finding per record, blocker 1.0 ... info 0.
WITH totals AS (
    SELECT j.key AS object, CAST(j.value AS INTEGER) AS total
    FROM runs, json_each(runs.totals_json) AS j
    WHERE runs.id = :run_id AND CAST(j.value AS INTEGER) > 0
),
worst_then AS (
    SELECT object, key, MAX(weight) AS penalty
    FROM findings WHERE run_id = :run_id
    GROUP BY object, key
),
worst_now AS (
    SELECT object, key, MAX(weight) AS penalty
    FROM findings
    WHERE run_id = :run_id AND status IN ('open', 'accepted')
    GROUP BY object, key
)
SELECT
    t.object,
    t.total,
    ROUND(100.0 * (1 - COALESCE((SELECT SUM(penalty) FROM worst_then w WHERE w.object = t.object), 0) / t.total), 1) AS readiness_then,
    ROUND(100.0 * (1 - COALESCE((SELECT SUM(penalty) FROM worst_now w WHERE w.object = t.object), 0) / t.total), 1) AS readiness_now,
    (SELECT COUNT(*) FROM worst_now w WHERE w.object = t.object) AS records_open
FROM totals t
ORDER BY t.object;
