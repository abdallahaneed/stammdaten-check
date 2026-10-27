"""SQLite helpers. The extracts go into an in-memory database so the
set-based checks can be written as plain SQL (see the sql/ folder)."""
import re
import sqlite3
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

DATE_COLUMNS = {"ERDAT", "LAST_POSTING"}


def iso_date(value):
    """SAP exports dates as 20240131, 31.01.2024 or 2024-01-31. Make them ISO."""
    v = str(value or "").strip()
    if re.fullmatch(r"\d{8}", v):
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", v)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if v in ("00000000", "00.00.0000"):
        return ""
    return v


def connect(tables, path=":memory:"):
    con = sqlite3.connect(path)
    for name, df in tables.items():
        df = df.copy()
        for col in df.columns:
            if col in DATE_COLUMNS:
                df[col] = df[col].map(iso_date)
        df.to_sql(name, con, index=False, if_exists="replace")
    return con


def query(con, name, **params):
    sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
