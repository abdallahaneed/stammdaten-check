-- Sanity checks on the extracts themselves, before any content rule.
-- An SE16N export with a join, or two exports pasted together in Excel,
-- easily produces the same key twice. Every later count would be wrong.
SELECT 'customer' AS object, KUNNR AS id, 'DUPLICATE_KEY' AS problem, 'KNA1-KUNNR' AS field, COUNT(*) AS n
FROM kna1 GROUP BY KUNNR HAVING COUNT(*) > 1
UNION ALL
SELECT 'vendor', LIFNR, 'DUPLICATE_KEY', 'LFA1-LIFNR', COUNT(*)
FROM lfa1 GROUP BY LIFNR HAVING COUNT(*) > 1
UNION ALL
SELECT 'material', MATNR, 'DUPLICATE_KEY', 'MARA-MATNR', COUNT(*)
FROM mara GROUP BY MATNR HAVING COUNT(*) > 1
UNION ALL
SELECT 'customer', KUNNR, 'DUPLICATE_KEY', 'KNB1-KUNNR/BUKRS', COUNT(*)
FROM knb1 GROUP BY KUNNR, BUKRS HAVING COUNT(*) > 1
UNION ALL
SELECT 'vendor', LIFNR, 'DUPLICATE_KEY', 'LFB1-LIFNR/BUKRS', COUNT(*)
FROM lfb1 GROUP BY LIFNR, BUKRS HAVING COUNT(*) > 1
UNION ALL
-- company code data without general data
SELECT 'customer', b.KUNNR, 'NO_GENERAL_DATA', 'KNB1-KUNNR', 1
FROM knb1 b LEFT JOIN kna1 a ON a.KUNNR = b.KUNNR WHERE a.KUNNR IS NULL
UNION ALL
SELECT 'vendor', b.LIFNR, 'NO_GENERAL_DATA', 'LFB1-LIFNR', 1
FROM lfb1 b LEFT JOIN lfa1 a ON a.LIFNR = b.LIFNR WHERE a.LIFNR IS NULL;
