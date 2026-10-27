"""Checks for the customer/vendor integration (CVI).

These only matter for a system conversion (brownfield). There, every customer
and vendor must already exist as a Business Partner in ECC before the
conversion runs. A new implementation (greenfield) loads BPs directly and
does not care about old links.
"""
from ..db import query
from ..matching import find_matches, prepare
from ..normalize import blank
from .base import Finding, rule

BROWNFIELD = ("brownfield",)


@rule("R07", "Customer-vendor links", paths=BROWNFIELD)
def links(ctx):
    """A company that is both customer and vendor should become one BP with
    two roles. That needs KNA1-LIFNR and LFA1-KUNNR to point at each other."""
    for row in query(ctx.db, "broken_links"):
        table, other = ("KNA1-LIFNR", "vendor") if row["object"] == "customer" else ("LFA1-KUNNR", "customer")
        if row["problem"] == "TARGET_MISSING":
            msg = f"points to {other} {row['target']}, which does not exist"
        else:
            msg = f"points to {other} {row['target']}, but that one points to {row['target_points_to'] or 'nothing'}"
        yield Finding("R07", "blocker", row["object"], row["id"], table, msg,
                      "Fix the link on both sides, then run CVI_COCKPIT again.",
                      related=row["target"])

    hi = ctx.cfg("duplicates", "match_threshold", 90)
    customers = ctx.extra.get("rows_customer") or prepare(ctx.tables["kna1"], "KUNNR")
    vendors = ctx.extra.get("rows_vendor") or prepare(ctx.tables["lfa1"], "LIFNR")
    linked_c = {r["KUNNR"] for r in ctx.tables["kna1"].to_dict("records") if not blank(r["LIFNR"])}
    linked_v = {r["LIFNR"] for r in ctx.tables["lfa1"].to_dict("records") if not blank(r["KUNNR"])}
    for kunnr, lifnr, s, reasons in find_matches(customers, vendors, min_score=hi):
        if kunnr in linked_c or lifnr in linked_v:
            continue
        yield Finding("R07", "warning", "customer", kunnr, "KNA1-LIFNR",
                      f"looks like the same company as vendor {lifnr} ({', '.join(reasons)}), not linked",
                      "Link them so CVI creates one BP with customer and supplier role.",
                      related=lifnr)


@rule("R08", "Number range collisions", paths=BROWNFIELD)
def collisions(ctx):
    """With the 'same number' strategy, BP number = customer number = vendor
    number. If customer 100045 and vendor 100045 are different companies,
    only one of them can get BP 100045."""
    if ctx.cfg("cvi", "number_strategy", "same") != "same":
        return
    for row in query(ctx.db, "number_collisions"):
        yield Finding("R08", "blocker", "customer", row["number"], "KNA1-KUNNR",
                      f"customer '{row['customer_name']}' and vendor '{row['vendor_name']}' share number {row['number']} but are not linked",
                      "Decide: link them (same company) or use internal numbering for one group.",
                      related=row["number"])


@rule("R09", "Form of address mapping", paths=BROWNFIELD)
def form_of_address(ctx):
    """ANRED in ECC is free text. CVI needs every value mapped to a BP title
    key in customizing. 'Fa.' and 'Firma' are not the same value to SAP."""
    mapped = set(ctx.ref["form_of_address"]["anred"])
    for obj, table, key in (("customer", "kna1", "KUNNR"), ("vendor", "lfa1", "LIFNR")):
        for r in ctx.tables[table].to_dict("records"):
            if not blank(r.get("ANRED")) and r["ANRED"] not in mapped:
                yield Finding("R09", "error", obj, r[key], f"{table.upper()}-ANRED",
                              f"form of address '{r['ANRED']}' has no BP title mapping",
                              "Map it in CVI customizing or clean the value to a mapped one.")


@rule("R12", "Contact persons", paths=BROWNFIELD)
def contacts(ctx):
    """KNVK contact persons become BPs of type person with a relationship to
    the company BP. A person BP needs a last name and a parent that exists."""
    customers = set(ctx.tables["kna1"]["KUNNR"])
    for r in ctx.tables["knvk"].to_dict("records"):
        if r["KUNNR"] not in customers:
            yield Finding("R12", "error", "contact", r["PARNR"], "KNVK-KUNNR",
                          f"contact belongs to customer {r['KUNNR']}, which does not exist",
                          "Delete the orphan contact or assign it.", related=r["KUNNR"])
        elif blank(r.get("NAME1")):
            yield Finding("R12", "error", "contact", r["PARNR"], "KNVK-NAME1",
                          "contact person has no last name",
                          "Add the last name or delete the contact.", related=r["KUNNR"])
