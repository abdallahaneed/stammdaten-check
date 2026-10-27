-- With the "same number" strategy in CVI, customer 100045 and vendor 100045
-- both want to become BP 100045. That only works if they are the same
-- company and linked to each other. Otherwise the conversion stops.
SELECT
    c.KUNNR AS number,
    c.NAME1 AS customer_name,
    v.NAME1 AS vendor_name,
    c.LIFNR AS customer_points_to,
    v.KUNNR AS vendor_points_to
FROM kna1 c
JOIN lfa1 v ON v.LIFNR = c.KUNNR
WHERE NOT (c.LIFNR = v.LIFNR AND v.KUNNR = c.KUNNR);
