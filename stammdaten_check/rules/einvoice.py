from ..normalize import blank
from ..validators import email_ok
from .base import Finding, rule


@rule("R11", "E-invoice readiness")
def einvoice(ctx):
    """From January 2027 firms with more than 800k EUR prior-year revenue must
    issue B2B invoices to German customers as structured e-invoices, from
    2028 everyone. An XRechnung or ZUGFeRD invoice needs the seller and
    buyer data clean: tax ID, full address, a delivery channel. Public
    sector customers also need a Leitweg-ID."""
    public = set(ctx.cfg("einvoice", "public_sector_groups", []))
    for r in ctx.tables["kna1"].to_dict("records"):
        if r.get("LOEVM") == "X" or r.get("LAND1") != "DE":
            continue
        k = r["KUNNR"]
        if blank(r.get("STCEG")) and blank(r.get("STCD1")):
            yield Finding("R11", "warning", "customer", k, "KNA1-STCEG",
                          "neither VAT ID nor tax number stored",
                          "Store the VAT ID; the buyer is identified by it in the e-invoice.")
        if blank(r.get("SMTP_ADDR")):
            yield Finding("R11", "warning", "customer", k, "ADR6-SMTP_ADDR",
                          "no email address for invoice delivery",
                          "Ask the customer for their invoice receiving address.")
        elif not email_ok(r["SMTP_ADDR"]):
            yield Finding("R11", "error", "customer", k, "ADR6-SMTP_ADDR",
                          f"invoice email '{r['SMTP_ADDR']}' is not a valid address",
                          "Correct the address.")
        if r.get("KTOKD") in public and blank(r.get("ZZ_LEITWEG")):
            yield Finding("R11", "error", "customer", k, "KNA1-ZZ_LEITWEG",
                          "public sector customer without Leitweg-ID",
                          "Request the Leitweg-ID, invoices without it are rejected.")
