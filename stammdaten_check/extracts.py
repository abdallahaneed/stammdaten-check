"""Loading the table extracts.

Each extract is a CSV named after the SAP table, e.g. kna1.csv. Column names
are the original SAP field names so a consultant can map them without a
translation table. Download via SE16N or a small ABAP report, save as CSV
(UTF-8, comma or semicolon).
"""
from pathlib import Path

import pandas as pd

SCHEMAS = {
    # customers
    "kna1": ["KUNNR", "KTOKD", "ANRED", "NAME1", "NAME2", "STRAS", "PSTLZ", "ORT01",
             "LAND1", "SPRAS", "STCEG", "STCD1", "LIFNR", "LOEVM", "SMTP_ADDR",
             "ZZ_LEITWEG", "ERDAT"],
    "knb1": ["KUNNR", "BUKRS", "AKONT", "LOEVM"],
    "knbk": ["KUNNR", "BANKS", "BANKL", "BANKN", "BKONT"],
    "knvk": ["PARNR", "KUNNR", "NAMEV", "NAME1", "ABTNR", "TELF1"],
    # vendors
    "lfa1": ["LIFNR", "KTOKK", "ANRED", "NAME1", "NAME2", "STRAS", "PSTLZ", "ORT01",
             "LAND1", "SPRAS", "STCEG", "STCD1", "KUNNR", "LOEVM", "SPERR", "ERDAT"],
    "lfb1": ["LIFNR", "BUKRS", "AKONT", "ZTERM"],
    "lfbk": ["LIFNR", "BANKS", "BANKL", "BANKN", "BKONT", "KOINH"],
    # bank data
    "tiban": ["BANKS", "BANKL", "BANKN", "BKONT", "IBAN"],
    "bnka": ["BANKS", "BANKL", "BANKA", "SWIFT", "LOEVM"],
    # materials
    "mara": ["MATNR", "MTART", "MEINS", "LVORM"],
    "makt": ["MATNR", "SPRAS", "MAKTX"],
    # one row per partner and company code, built from BSID/BSAD and BSIK/BSAK
    "activity": ["OBJECT", "ID", "BUKRS", "LAST_POSTING", "OPEN_ITEMS"],
}

OPTIONAL = {"knvk", "knbk", "mara", "makt", "activity"}

# Columns used when present, filled with "" when an older extract lacks them.
# TELF1 sits in LFA1, the email address comes from ADR6 like for customers.
EXTRA_COLUMNS = {"lfa1": ["TELF1", "SMTP_ADDR"]}


class ExtractError(Exception):
    pass


def read_csv(path, upper=True):
    with open(path, encoding="utf-8-sig") as fh:
        first = fh.readline()
    sep = ";" if first.count(";") > first.count(",") else ","
    df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [c.strip().upper() if upper else c.strip() for c in df.columns]
    return df.apply(lambda col: col.str.strip())


def load(folder):
    folder = Path(folder)
    tables, problems = {}, []
    for name, columns in SCHEMAS.items():
        path = folder / f"{name}.csv"
        if not path.exists():
            if name in OPTIONAL:
                tables[name] = pd.DataFrame(columns=columns + EXTRA_COLUMNS.get(name, []))
                continue
            problems.append(f"{name}.csv is missing")
            continue
        df = read_csv(path)
        missing = [c for c in columns if c not in df.columns]
        if missing:
            problems.append(f"{name}.csv lacks columns: {', '.join(missing)}")
            continue
        for col in EXTRA_COLUMNS.get(name, []):
            if col not in df.columns:
                df[col] = ""
        tables[name] = df
    if problems:
        raise ExtractError("; ".join(problems))
    return tables


def load_reference(folder):
    folder = Path(folder)
    ref = {}
    for path in folder.glob("*.csv"):
        ref[path.stem] = read_csv(path, upper=False)
    return ref
