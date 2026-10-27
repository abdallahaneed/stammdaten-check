-- Customer-vendor links that do not point back at each other,
-- or point at a number that does not exist.
SELECT 'customer' AS object, c.KUNNR AS id, c.LIFNR AS target,
       CASE WHEN v.LIFNR IS NULL THEN 'TARGET_MISSING' ELSE 'NOT_MUTUAL' END AS problem,
       v.KUNNR AS target_points_to
FROM kna1 c
LEFT JOIN lfa1 v ON v.LIFNR = c.LIFNR
WHERE c.LIFNR <> ''
  AND (v.LIFNR IS NULL OR v.KUNNR <> c.KUNNR)
UNION ALL
SELECT 'vendor', v.LIFNR, v.KUNNR,
       CASE WHEN c.KUNNR IS NULL THEN 'TARGET_MISSING' ELSE 'NOT_MUTUAL' END,
       c.LIFNR
FROM lfa1 v
LEFT JOIN kna1 c ON c.KUNNR = v.KUNNR
WHERE v.KUNNR <> ''
  AND (c.KUNNR IS NULL OR c.LIFNR <> v.LIFNR);
