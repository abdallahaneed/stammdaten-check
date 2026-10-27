# Data model

One CSV per table. Column names are the SAP field names. Comma or semicolon, UTF-8. Dates as `20240131`, `31.01.2024` or `2024-01-31`.

| File | SAP source | Fields used | Needed |
|---|---|---|---|
| kna1.csv | KNA1 + ADR6 | KUNNR, KTOKD, ANRED, NAME1, NAME2, STRAS, PSTLZ, ORT01, LAND1, SPRAS, STCEG, STCD1, LIFNR, LOEVM, SMTP_ADDR, ZZ_LEITWEG, ERDAT | yes |
| knb1.csv | KNB1 | KUNNR, BUKRS, AKONT, LOEVM | yes |
| knbk.csv | KNBK | KUNNR, BANKS, BANKL, BANKN, BKONT | no |
| knvk.csv | KNVK | PARNR, KUNNR, NAMEV, NAME1, ABTNR, TELF1 | no |
| lfa1.csv | LFA1 | LIFNR, KTOKK, ANRED, NAME1, NAME2, STRAS, PSTLZ, ORT01, LAND1, SPRAS, STCEG, STCD1, KUNNR, LOEVM, SPERR, ERDAT | yes |
| lfb1.csv | LFB1 | LIFNR, BUKRS, AKONT, ZTERM | yes |
| lfbk.csv | LFBK | LIFNR, BANKS, BANKL, BANKN, BKONT, KOINH | yes |
| tiban.csv | TIBAN | BANKS, BANKL, BANKN, BKONT, IBAN | yes |
| bnka.csv | BNKA | BANKS, BANKL, BANKA, SWIFT, LOEVM | yes |
| mara.csv | MARA | MATNR, MTART, MEINS, LVORM | no |
| makt.csv | MAKT | MATNR, SPRAS, MAKTX | no |
| activity.csv | built from BSID/BSAD, BSIK/BSAK | OBJECT, ID, BUKRS, LAST_POSTING, OPEN_ITEMS | no, but R06 and R10 need it |

## Notes

**SMTP_ADDR** is not in KNA1. It comes from ADR6 through KNA1-ADRNR. Join it before export, for example with a QuickViewer (SQVI) join of KNA1 and ADR6.

**ZZ_LEITWEG** stands for wherever your company keeps the Leitweg-ID. Rename the column to match.

**activity.csv** is one row per partner and company code: date of the last posting and number of open items. For customers: open items from BSID, cleared items from BSAD. For vendors: BSIK and BSAK. `OBJECT` is `customer` or `vendor`.

**Leading zeros.** Do not open the CSV in Excel and save it again. Excel turns the postal code 01067 into 1067 and account numbers lose their zeros too. If you must edit, import the file with every column set to text.

**SAP language keys** are single letters in the tables (D, E, N), not ISO codes.

## Reference files

| File | Modeled on | Used by |
|---|---|---|
| t005_postal.csv | T005, postal code length and check rule | R05 |
| t006_units.csv | T006 | R13 |
| cvi_grouping.csv | CVI customizing, account group to BP grouping | R02, staging |
| form_of_address.csv | CVI customizing, form of address to BP title | R09, staging |

Replace them with the values from your system before a real run.
