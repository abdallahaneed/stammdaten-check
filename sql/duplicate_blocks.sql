-- How big are the comparison blocks? Comparing every partner with every
-- other one is n*(n-1)/2 pairs. Grouping by postal code first keeps it small.
-- This query shows the largest blocks so you can see where it still hurts.
SELECT
    LAND1,
    PSTLZ,
    COUNT(*)                                              AS partners,
    COUNT(*) * (COUNT(*) - 1) / 2                         AS pairs,
    RANK() OVER (ORDER BY COUNT(*) DESC)                  AS size_rank,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)    AS share_pct
FROM kna1
WHERE PSTLZ <> ''
GROUP BY LAND1, PSTLZ
ORDER BY partners DESC
LIMIT 20;
