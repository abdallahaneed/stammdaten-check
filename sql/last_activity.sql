-- Last posting and open items per partner, across all company codes.
-- In the real system this comes from BSID/BSAD (customers) and BSIK/BSAK (vendors).
SELECT
    OBJECT,
    ID,
    MAX(LAST_POSTING)               AS last_posting,
    SUM(CAST(OPEN_ITEMS AS INTEGER)) AS open_items,
    COUNT(DISTINCT BUKRS)           AS company_codes
FROM activity
GROUP BY OBJECT, ID;
