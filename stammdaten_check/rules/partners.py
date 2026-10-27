from ..matching import find_matches, prepare
from ..normalize import blank
from ..validators import postal_ok
from .base import Finding, rule

PARTNERS = (("customer", "kna1", "KUNNR", "KTOKD"), ("vendor", "lfa1", "LIFNR", "KTOKK"))


@rule("R01", "Duplicate business partners")
def duplicates(ctx):
    """Same company entered twice. After conversion you would have two BPs,
    split open items and split purchase/sales history."""
    hi = ctx.cfg("duplicates", "match_threshold", 90)
    lo = ctx.cfg("duplicates", "review_threshold", 80)
    for obj, table, key, _ in PARTNERS:
        rows = prepare(ctx.tables[table], key)
        ctx.extra[f"rows_{obj}"] = rows
        for a, b, s, reasons in find_matches(rows, min_score=lo):
            first, second = sorted((a, b))
            sev = "error" if s >= hi else "warning"
            label = "likely duplicate" if s >= hi else "possible duplicate, check"
            yield Finding("R01", sev, obj, second, f"{table.upper()}-NAME1",
                          f"{label} of {first} (score {s}: {', '.join(reasons)})",
                          "Pick one surviving record, move open items, block the other.",
                          related=first)


@rule("R02", "Fields required for the Business Partner")
def required_fields(ctx):
    """CVI and the Migration Cockpit both reject a BP without name, country,
    city and postal code, or with an account group that has no BP grouping."""
    grouping = ctx.ref["cvi_grouping"]
    for obj, table, key, group_col in PARTNERS:
        mapped = set(grouping.loc[grouping["object"] == obj, "account_group"])
        for r in ctx.tables[table].to_dict("records"):
            if r.get("LOEVM") == "X":
                continue
            for f in ("NAME1", "LAND1", "ORT01", "PSTLZ"):
                if blank(r.get(f)):
                    shown = f" ('{r.get(f)}')" if str(r.get(f) or "").strip() else ""
                    yield Finding("R02", "blocker", obj, r[key], f"{table.upper()}-{f}",
                                  f"{f} is empty or a placeholder{shown}", f"Fill {f} before conversion.")
            if not blank(r.get(group_col)) and r[group_col] not in mapped:
                yield Finding("R02", "blocker", obj, r[key], f"{table.upper()}-{group_col}",
                              f"account group {r[group_col]} has no BP grouping assigned",
                              "Add the account group to the CVI grouping customizing.")


@rule("R05", "Postal code format")
def postal_codes(ctx):
    """Checked against the country rules in reference/t005_postal.csv,
    modeled on T005 (length and check rule). Wrong formats stop the
    address check in S/4HANA."""
    rules = {r["land1"]: r for r in ctx.ref["t005_postal"].to_dict("records")}
    for obj, table, key, _ in PARTNERS:
        for r in ctx.tables[table].to_dict("records"):
            if blank(r.get("PSTLZ")) or r.get("LOEVM") == "X":
                continue  # missing postal code is R02
            country_rule = rules.get(r["LAND1"])
            if country_rule and not postal_ok(r["PSTLZ"], country_rule):
                yield Finding("R05", "error", obj, r[key], f"{table.upper()}-PSTLZ",
                              f"'{r['PSTLZ']}' is not a valid postal code for {r['LAND1']}",
                              "Correct the postal code; check city at the same time.")
