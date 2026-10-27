# Rules

Severity tells the business how urgent a finding is:

- **blocker**: the conversion or load fails on this record, or money goes to the wrong account
- **error**: the record loads, but the data is wrong
- **warning**: worth fixing, nothing breaks
- **info**: a suggestion, for example an archive candidate

Path tells you whether a rule matters for a system conversion (brownfield), a new implementation (greenfield) or both.

---

## R00 Extract integrity
**Path:** both  **Severity:** blocker for duplicate keys, error for missing master records
**SQL:** `sql/extract_integrity.sql`

Runs before everything else. The same KUNNR twice in KNA1, or KNB1 rows for a customer that is not in KNA1, means the export went wrong (a join in SE16N, two files pasted together). Every count after that would be off, so fix the extract first.

## R01 Duplicate business partners
**Path:** both  **Severity:** error from score 90, warning from 80
**Fields:** NAME1, NAME2, STRAS, PSTLZ, ORT01, LAND1, STCEG

Two records for one company mean two BPs after the move, split history and open items in two places. Matching steps:

1. Normalize. Umlauts written out (ü becomes ue), ß becomes ss, case and punctuation removed, "Straße", "Str." and "Strasse" become one form. The legal form is cut off the name and stored on its own (GmbH, GmbH & Co. KG, KG, UG ...).
2. Block. Only partners sharing postal code, VAT ID, the first 4 letters of the name in the same city, or street plus house number are compared.
3. Score. Name 55 %, street 25 %, house number 10 %, city 10 %. Same VAT ID in the same city counts as 100. Then deductions: different legal forms minus 15, different countries minus 20, two different VAT IDs cap the score at 75.

Same VAT ID in another city scores 85. That is review, not duplicate, because branches and ship-to accounts often share one VAT ID on purpose.

## R02 Fields required for the Business Partner
**Path:** both  **Severity:** blocker
**Fields:** NAME1, LAND1, ORT01, PSTLZ, KNA1-KTOKD, LFA1-KTOKK

A BP needs a name, a country, a city and a postal code. Placeholders count as empty: "xxx", "-", "unbekannt", "k.a." and similar. People type them when a mandatory field blocks saving and they do not know the value. CVI also needs every account group assigned to a BP grouping, otherwise it does not know which number range and BP type to use. The assignment is read from `reference/cvi_grouping.csv`. Records with deletion flag are skipped.

## R03 Bank details
**Path:** both  **Severity:** blocker for broken IBANs and vendors without IBAN, error for the rest
**Tables:** LFBK, KNBK, TIBAN, BNKA

In ECC the bank account sits in LFBK (vendors) and KNBK (customers) with bank country, bank key and account number. The IBAN is not in those tables. It sits in TIBAN under the same key. Checks:

- bank key exists in BNKA and is not flagged for deletion
- an IBAN exists for accounts in SEPA countries (blocker for vendors, because you cannot pay them)
- IBAN length for its country and check digits (ISO 13616, mod 97)
- IBAN country equals bank country
- for Germany: positions 5 to 12 of the IBAN equal the BLZ, positions 13 to 22 equal the account number

The last check catches records where someone changed the old account field and not the IBAN, or the other way round.

## R04 VAT ID
**Path:** both  **Severity:** error
**Field:** STCEG

Format per country (DE, AT, NL, BE, FR, IT, LU, PL), and for German numbers the check digit (ISO 7064 MOD 11,10, as published by the Bundeszentralamt für Steuern). A prefix that does not match the partner country is flagged too. With `--vies` every formally correct number is also asked at the EU VIES service, with three retries and a pause between calls.

## R05 Postal code format
**Path:** both  **Severity:** error
**Field:** PSTLZ

Rules per country in `reference/t005_postal.csv`, modeled on the postal code length and check rule in T005. "D-53115" and four-digit German codes are typical old entries.

## R06 Archive candidates
**Path:** both  **Severity:** info
**Source:** activity extract, SQL in `sql/inactive_partners.sql`

No posting for 3 years before cutover (configurable) and no open items. Partners with open items are never suggested, whatever their age. Every record you leave behind is one you do not have to clean.

## R07 Customer-vendor links
**Path:** brownfield  **Severity:** blocker for broken links, warning for missing ones
**Fields:** KNA1-LIFNR, LFA1-KUNNR, SQL in `sql/broken_links.sql`

A company that is customer and vendor should become one BP with two roles. For that, KNA1-LIFNR and LFA1-KUNNR have to point at each other. Flagged:

- a link to a number that does not exist
- a link that does not point back
- a customer and a vendor that look like the same company (same matching as R01, score 90+) but are not linked

## R08 Number range collisions
**Path:** brownfield, only with the "same number" strategy  **Severity:** blocker
**SQL:** `sql/number_collisions.sql`

With the same number strategy, customer 100045 becomes BP 100045, and so does vendor 100045. If those are two different companies, one of them cannot get its number. Fix it before the CVI run: link them if they are the same company, or move one group to internal numbering.

## R09 Form of address mapping
**Path:** brownfield  **Severity:** error
**Field:** ANRED

ANRED is free text in ECC. CVI needs each value mapped to a BP title key. "Firma" is mapped, "Fa.", "Fima" and "firma" are not. Mapping in `reference/form_of_address.csv`.

## R10 Deletion flag on active partners
**Path:** both  **Severity:** error
**Field:** LOEVM, SQL in `sql/deleted_but_active.sql`

Flagged records usually stay behind in a migration. If they still have open items or postings in the last 12 months, those items lose their partner.

## R11 E-invoice readiness
**Path:** both  **Severity:** warning, error for broken email addresses and missing Leitweg-IDs
**Fields:** STCEG, STCD1, ADR6-SMTP_ADDR, ZZ_LEITWEG

From January 2027 firms with more than 800,000 EUR revenue in the prior year have to send B2B invoices to German customers as structured e-invoices, from 2028 all firms. Checked for German customers:

- VAT ID or tax number present
- invoice email present and valid
- Leitweg-ID present for public sector customers (account group `OEFF` in the sample)

The Leitweg-ID field is an assumption. Many companies keep it in a custom field or a text. Change the column name in the extract if yours differs.

## R12 Contact persons
**Path:** brownfield  **Severity:** error
**Table:** KNVK

Contacts become person BPs with a relationship to the company BP. A person BP needs a last name, and the company it belongs to has to exist.

## R13 Material basics
**Path:** both  **Severity:** blocker for units, warning for texts
**Tables:** MARA, MAKT

Base unit must exist in T006 (`reference/t006_units.csv`). Each material needs a description in the languages set in the config, German and English by default. Kept small on purpose. Material master quality could be its own project.
