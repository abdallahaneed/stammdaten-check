-- Flagged for deletion, but somebody still posted on it recently
-- or there are open items. Either the flag is wrong or the postings are.
WITH act AS (
    SELECT OBJECT, ID,
           MAX(LAST_POSTING) AS last_posting,
           SUM(CAST(OPEN_ITEMS AS INTEGER)) AS open_items
    FROM activity
    GROUP BY OBJECT, ID
),
partners AS (
    SELECT 'customer' AS object, KUNNR AS id, LOEVM FROM kna1
    UNION ALL
    SELECT 'vendor', LIFNR, LOEVM FROM lfa1
)
SELECT p.object, p.id, a.last_posting, a.open_items
FROM partners p
JOIN act a ON a.OBJECT = p.object AND a.ID = p.id
WHERE p.LOEVM = 'X'
  AND (a.last_posting >= date(:cutover, '-' || :months || ' months')
       OR a.open_items > 0);
