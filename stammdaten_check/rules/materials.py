from .base import Finding, rule


@rule("R13", "Material basics")
def materials(ctx):
    """Two checks only: the base unit must exist in T006, and every material
    needs a description in the languages the company uses. Missing English
    texts show up later as empty lines on export documents."""
    units = set(ctx.ref["t006_units"]["msehi"])
    langs = ctx.cfg("materials", "required_languages", ["D"])
    texts = {}
    for r in ctx.tables["makt"].to_dict("records"):
        if r["MAKTX"].strip():
            texts.setdefault(r["MATNR"], set()).add(r["SPRAS"])
    for r in ctx.tables["mara"].to_dict("records"):
        if r.get("LVORM") == "X":
            continue
        if r["MEINS"] not in units:
            yield Finding("R13", "blocker", "material", r["MATNR"], "MARA-MEINS",
                          f"base unit '{r['MEINS']}' does not exist in T006",
                          "Map to a valid unit of measure.")
        missing = [l for l in langs if l not in texts.get(r["MATNR"], set())]
        if missing:
            yield Finding("R13", "warning", "material", r["MATNR"], "MAKT-MAKTX",
                          f"no description in language {', '.join(missing)}",
                          "Add the translation.")
