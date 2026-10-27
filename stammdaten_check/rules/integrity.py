from ..db import query
from .base import Finding, rule

MESSAGES = {
    "DUPLICATE_KEY": ("blocker", "key appears {n} times in the extract",
                      "Check the export. Remove the duplicate rows before reading any other result."),
    "NO_GENERAL_DATA": ("error", "company code data exists, general data does not",
                        "Extract is incomplete, or the general record was deleted. Clarify before migration."),
}


@rule("R00", "Extract integrity")
def integrity(ctx):
    """Runs before the content rules. Duplicate keys and company code rows
    without a master record point at a broken export, not at bad data."""
    for row in query(ctx.db, "extract_integrity"):
        sev, msg, fix = MESSAGES[row["problem"]]
        yield Finding("R00", sev, row["object"], row["id"], row["field"], msg.format(n=row["n"]), fix)
