"""Check one new or changed partner against the rules and the existing master.

This is what an onboarding workflow calls before a vendor is created:
are the fields valid, does the company exist already, and is the IBAN
already used by someone else.
"""
from functools import lru_cache

import pandas as pd

from .. import extracts
from ..engine import ROOT
from ..matching import match_one, prepare
from ..normalize import blank
from ..validators import clean, iban_problems, postal_ok, vat_problems

REQUIRED = {"name": "NAME1", "country": "LAND1", "city": "ORT01", "postalCode": "PSTLZ"}


@lru_cache(maxsize=1)
def _postal_rules():
    ref = extracts.read_csv(ROOT / "reference" / "t005_postal.csv", upper=False)
    return {r["land1"]: r for r in ref.to_dict("records")}


@lru_cache(maxsize=4)
def master(extract_dir):
    """Prepared rows and IBAN owners for one run. Cached, the extracts do not change."""
    t = extracts.load(extract_dir)
    rows = {"customer": prepare(t["kna1"], "KUNNR"), "vendor": prepare(t["lfa1"], "LIFNR")}
    names = {
        "customer": dict(zip(t["kna1"]["KUNNR"], t["kna1"]["NAME1"])),
        "vendor": dict(zip(t["lfa1"]["LIFNR"], t["lfa1"]["NAME1"])),
    }
    owners = {}
    for obj, table, key in (("vendor", "lfbk", "LIFNR"), ("customer", "knbk", "KUNNR")):
        merged = t[table].merge(t["tiban"], on=["BANKS", "BANKL", "BANKN", "BKONT"], how="inner")
        for iban, k in zip(merged["IBAN"], merged[key]):
            owners.setdefault(clean(iban), []).append({"object": obj, "id": k, "name": names[obj].get(k, "")})
    return rows, names, owners


def check(partner: dict, extract_dir=None, min_score=80):
    problems = []

    def add(code, field, severity, message):
        problems.append({"code": code, "field": field, "severity": severity, "message": message})

    for f in REQUIRED:
        if blank(partner.get(f)):
            add("REQUIRED", f, "blocker", f"{f} is empty or a placeholder")

    country = clean(partner.get("country"))
    rule = _postal_rules().get(country)
    if rule and not blank(partner.get("postalCode")) and not postal_ok(partner["postalCode"], rule):
        add("POSTAL_FORMAT", "postalCode", "error", f"not a valid postal code for {country}")

    if not blank(partner.get("vatId")):
        for p in vat_problems(partner["vatId"], country):
            add(p, "vatId", "error", p.replace("_", " ").lower())

    iban = clean(partner.get("iban"))
    if iban:
        for p in iban_problems(iban, country or None):
            sev = "warning" if p == "IBAN_COUNTRY_DIFFERS" else "blocker"
            add(p, "iban", sev, p.replace("_", " ").lower())

    duplicates, iban_owners = [], []
    if extract_dir is not None:
        rows, names, owners = master(str(extract_dir))
        record = prepare(pd.DataFrame([{
            "ID": "new", "NAME1": partner.get("name", ""), "NAME2": partner.get("name2", ""),
            "STRAS": partner.get("street", ""), "PSTLZ": partner.get("postalCode", ""),
            "ORT01": partner.get("city", ""), "LAND1": country, "STCEG": partner.get("vatId", ""),
        }]), "ID")[0]
        targets = [partner["object"]] if partner.get("object") in rows else list(rows)
        for obj in targets:
            for hit in match_one(record, rows[obj], min_score=min_score):
                hit.update(object=obj, name=names[obj].get(hit["id"], ""))
                duplicates.append(hit)
        duplicates.sort(key=lambda h: -h["score"])
        exclude = partner.get("existingId")
        iban_owners = [o for o in owners.get(iban, []) if o["id"] != exclude] if iban else []
        if iban_owners:
            who = ", ".join(f"{o['object']} {o['id']}" for o in iban_owners)
            add("IBAN_IN_USE", "iban", "error", f"IBAN already stored for {who}")

    worst = min((p["severity"] for p in problems),
                key=["blocker", "error", "warning", "info"].index, default=None)
    return {
        "ok": worst not in ("blocker", "error"),
        "worstSeverity": worst,
        "problems": problems,
        "duplicates": duplicates,
        "ibanOwners": iban_owners,
    }


def vendor(extract_dir, lifnr):
    """Current master record and bank accounts of one vendor, or None."""
    t = extracts.load(extract_dir)
    lfa1 = t["lfa1"][t["lfa1"]["LIFNR"] == lifnr]
    if lfa1.empty:
        return None
    v = lfa1.iloc[0]
    banks = t["lfbk"][t["lfbk"]["LIFNR"] == lifnr].merge(
        t["tiban"], on=["BANKS", "BANKL", "BANKN", "BKONT"], how="left").fillna("")
    return {
        "object": "vendor", "id": lifnr, "name": v["NAME1"], "name2": v["NAME2"],
        "street": v["STRAS"], "postalCode": v["PSTLZ"], "city": v["ORT01"], "country": v["LAND1"],
        "vatId": v["STCEG"], "phone": v["TELF1"], "email": v["SMTP_ADDR"],
        "blocked": v["SPERR"] == "X" or v["LOEVM"] == "X",
        "banks": [{"country": b["BANKS"], "bankKey": b["BANKL"], "account": b["BANKN"],
                   "iban": b["IBAN"], "holder": b["KOINH"]} for b in banks.to_dict("records")],
    }
