"""Business Partner staging file for a new implementation (greenfield).

The columns follow the structure of the Migration Cockpit customer and
supplier templates (general data, address, tax number, bank), flattened into
one CSV per object. It is a simplified version: the real template is an XML
spreadsheet with one sheet per structure. The point is the selection logic:
what gets migrated, what gets left behind, and why.
"""
import re

import pandas as pd

# Tax number category per country for the VAT ID. Check against your
# customizing (table TFKTAXNUMTYPE) before loading.
TAX_TYPE = {"DE": "DE0", "AT": "AT0", "NL": "NL0", "BE": "BE0"}


def split_street(s):
    m = re.match(r"^(.*?)[\s,]+(\d+\s*[a-zA-Z]?(?:\s*-\s*\d+)?)$", str(s).strip())
    return (m.group(1), m.group(2).replace(" ", "")) if m else (s, "")


def survivors(findings, activity, obj):
    """For each duplicate pair, keep the record with the newer posting."""
    last = {r["ID"]: r["LAST_POSTING"] for r in activity[activity["OBJECT"] == obj].to_dict("records")}
    drop = {}
    dups = findings[(findings["rule"] == "R01") & (findings["object"] == obj) & (findings["severity"] == "error")]
    for a, b in zip(dups["key"], dups["related"]):
        keep, lose = sorted((a, b), key=lambda k: (last.get(k, ""), -int(k) if k.isdigit() else 0), reverse=True)
        drop[lose] = f"duplicate of {keep}"
    return drop


def build(tables, ref, findings, obj):
    if obj == "customer":
        master, key, group_col, bank_tab = tables["kna1"], "KUNNR", "KTOKD", tables["knbk"]
    else:
        master, key, group_col, bank_tab = tables["lfa1"], "LIFNR", "KTOKK", tables["lfbk"]

    grouping = ref["cvi_grouping"]
    bp_group = dict(zip(grouping.loc[grouping["object"] == obj, "account_group"],
                        grouping.loc[grouping["object"] == obj, "bp_grouping"]))
    title = dict(zip(ref["form_of_address"]["anred"], ref["form_of_address"]["bp_title"]))
    tiban = {(r["BANKS"], r["BANKL"], r["BANKN"]): r["IBAN"] for r in tables["tiban"].to_dict("records")}
    bank = {}
    for r in bank_tab.to_dict("records"):
        bank.setdefault(r[key], tiban.get((r["BANKS"], r["BANKL"], r["BANKN"]), ""))

    of_obj = findings[findings["object"] == obj]
    blockers = of_obj[of_obj["severity"] == "blocker"]
    blocked = {k: f"{r} {m}" for k, r, m in zip(blockers["key"], blockers["rule"], blockers["message"])}
    archive = set(of_obj.loc[of_obj["rule"] == "R06", "key"])
    dup_drop = survivors(findings, tables["activity"], obj)

    rows, excluded = [], []
    for r in master.to_dict("records"):
        k = r[key]
        reason = None
        if r.get("LOEVM") == "X":
            reason = "deletion flag"
        elif k in archive:
            reason = "archive candidate (no activity)"
        elif k in dup_drop:
            reason = dup_drop[k]
        elif k in blocked:
            reason = "blocker: " + blocked[k]
        if reason:
            excluded.append({"object": obj, "legacy_key": k, "name": r["NAME1"], "reason": reason})
            continue
        street, house = split_street(r["STRAS"])
        rows.append({
            "LEGACY_KEY": k,
            "BU_GROUP": bp_group.get(r[group_col], ""),
            "BU_TYPE": "2",  # organization
            "TITLE": title.get(r.get("ANRED", ""), ""),
            "NAME_ORG1": r["NAME1"],
            "NAME_ORG2": r["NAME2"],
            "STREET": street,
            "HOUSE_NUM1": house,
            "POST_CODE1": r["PSTLZ"],
            "CITY1": r["ORT01"],
            "COUNTRY": r["LAND1"],
            "LANGU": r["SPRAS"],
            "TAXTYPE": TAX_TYPE.get(r["LAND1"], "") if r["STCEG"] else "",
            "TAXNUM": r["STCEG"],
            "SMTP_ADDR": r.get("SMTP_ADDR", ""),
            "IBAN": bank.get(k, ""),
        })
    return pd.DataFrame(rows), pd.DataFrame(excluded)
