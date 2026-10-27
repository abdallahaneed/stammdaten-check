-- Archive candidates: no posting for :years years before cutover and nothing open.
-- Partners with open items are never archive candidates, whatever their age.
WITH act AS (
    SELECT OBJECT, ID,
           MAX(LAST_POSTING) AS last_posting,
           SUM(CAST(OPEN_ITEMS AS INTEGER)) AS open_items
    FROM activity
    GROUP BY OBJECT, ID
),
partners AS (
    SELECT 'customer' AS object, KUNNR AS id, LOEVM, ERDAT FROM kna1
    UNION ALL
    SELECT 'vendor', LIFNR, LOEVM, ERDAT FROM lfa1
)
SELECT p.object, p.id, a.last_posting, COALESCE(a.open_items, 0) AS open_items
FROM partners p
LEFT JOIN act a ON a.OBJECT = p.object AND a.ID = p.id
WHERE p.LOEVM = ''
  AND COALESCE(a.open_items, 0) = 0
  AND COALESCE(a.last_posting, p.ERDAT) < date(:cutover, '-' || :years || ' years');
