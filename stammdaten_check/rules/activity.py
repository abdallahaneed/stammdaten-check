from ..db import query
from .base import Finding, rule


@rule("R06", "Archive candidates")
def inactive(ctx):
    """Partners nobody has posted on for years. Every record you do not
    migrate is one you do not have to clean. Partners with open items are
    never suggested, no matter how old."""
    years = ctx.cfg("inactive", "years_without_posting", 3)
    cutover = ctx.cfg("run", "cutover_date")
    for row in query(ctx.db, "inactive_partners", cutover=cutover, years=years):
        last = row["last_posting"] or "never"
        yield Finding("R06", "info", row["object"], row["id"], "activity",
                      f"no posting since {last}, nothing open",
                      "Set the deletion flag and leave it out of the migration.")


@rule("R10", "Deletion flag on active partners")
def deleted_but_active(ctx):
    """LOEVM is set but the partner still has recent postings or open items.
    Flagged records are usually excluded from migration, so the open items
    would lose their partner."""
    months = ctx.cfg("deletion_flag", "recent_activity_months", 12)
    cutover = ctx.cfg("run", "cutover_date")
    for row in query(ctx.db, "deleted_but_active", cutover=cutover, months=months):
        field = "KNA1-LOEVM" if row["object"] == "customer" else "LFA1-LOEVM"
        yield Finding("R10", "error", row["object"], row["id"], field,
                      f"deletion flag set, but last posting {row['last_posting']} and {row['open_items']} open items",
                      "Remove the flag or clear the items first.")
