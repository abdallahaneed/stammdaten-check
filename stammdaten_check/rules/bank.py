from ..normalize import blank
from ..validators import SEPA_COUNTRIES, clean, de_iban_matches, iban_problems
from .base import Finding, rule

MESSAGES = {
    "IBAN_LENGTH": "IBAN has the wrong length for its country",
    "IBAN_CHECKSUM": "IBAN check digits are wrong",
    "IBAN_COUNTRY_DIFFERS": "IBAN country differs from bank country",
}


def _bank_rows(ctx, obj, table, key):
    tiban = ctx.tables["tiban"]
    iban_by_key = {
        (r["BANKS"], r["BANKL"], clean(r["BANKN"]), r["BKONT"]): r["IBAN"]
        for r in tiban.to_dict("records")
    }
    for r in ctx.tables[table].to_dict("records"):
        k = (r["BANKS"], r["BANKL"], clean(r["BANKN"]), r["BKONT"])
        yield r, iban_by_key.get(k, "")


@rule("R03", "Bank details")
def bank_details(ctx):
    """Bank data sits in LFBK/KNBK (bank country, bank key, account) and the
    IBAN in TIBAN under the same key. Bank keys must exist in BNKA. For
    Germany the bank key is the BLZ, and the IBAN must contain BLZ and
    account number. Old records often break one of these."""
    bnka = {(r["BANKS"], r["BANKL"]) for r in ctx.tables["bnka"].to_dict("records")
            if r.get("LOEVM") != "X"}
    for obj, table, key in (("vendor", "lfbk", "LIFNR"), ("customer", "knbk", "KUNNR")):
        for r, iban in _bank_rows(ctx, obj, table, key):
            field = f"{table.upper()}"
            if (r["BANKS"], r["BANKL"]) not in bnka:
                yield Finding("R03", "error", obj, r[key], f"{field}-BANKL",
                              f"bank key {r['BANKS']}/{r['BANKL']} not in BNKA",
                              "Create the bank in BNKA or correct the bank key.")
            if blank(iban):
                if r["BANKS"] in SEPA_COUNTRIES:
                    sev = "blocker" if obj == "vendor" else "warning"
                    yield Finding("R03", sev, obj, r[key], "TIBAN-IBAN",
                                  "no IBAN for an account in a SEPA country",
                                  "Generate the IBAN and confirm it with the partner.")
                continue
            for p in iban_problems(iban, r["BANKS"]):
                yield Finding("R03", "blocker", obj, r[key], "TIBAN-IBAN",
                              f"{MESSAGES[p]} ({iban})",
                              "Get a written bank confirmation, do not guess.")
            if r["BANKS"] == "DE" and not de_iban_matches(iban, r["BANKL"], r["BANKN"]):
                yield Finding("R03", "error", obj, r[key], f"{field}-BANKN",
                              f"IBAN {iban} does not contain BLZ {r['BANKL']} / account {r['BANKN']}",
                              "Old fields and IBAN disagree. Find out which one is current.")
