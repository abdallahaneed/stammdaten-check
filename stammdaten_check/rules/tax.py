from ..normalize import blank
from ..validators import vat_problems
from .base import Finding, rule
from .partners import PARTNERS

MESSAGES = {
    "VAT_FORMAT": "VAT ID does not match the format for its country",
    "VAT_CHECK_DIGIT": "German VAT ID has a wrong check digit",
    "VAT_COUNTRY_DIFFERS": "VAT ID country prefix differs from the partner country",
}


@rule("R04", "VAT ID")
def vat_ids(ctx):
    """STCEG is checked offline for format and, for Germany, the check digit.
    With --vies the number is also asked at the EU VIES service."""
    for obj, table, key, _ in PARTNERS:
        for r in ctx.tables[table].to_dict("records"):
            if blank(r.get("STCEG")) or r.get("LOEVM") == "X":
                continue
            problems = vat_problems(r["STCEG"], r["LAND1"])
            for p in problems:
                yield Finding("R04", "error", obj, r[key], f"{table.upper()}-STCEG",
                              f"{MESSAGES[p]} ({r['STCEG']})",
                              "Ask the partner for the VAT ID from their invoice letterhead.")
            if not problems and ctx.vies is not None:
                status = ctx.vies.check(r["STCEG"])
                if status == "invalid":
                    yield Finding("R04", "error", obj, r[key], f"{table.upper()}-STCEG",
                                  f"VIES says {r['STCEG']} is not valid",
                                  "Clarify with the partner, the number may be deregistered.")
                elif status == "unavailable":
                    yield Finding("R04", "info", obj, r[key], f"{table.upper()}-STCEG",
                                  "VIES not reachable, number not confirmed", "Run again later.")
