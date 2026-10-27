"""Duplicate matching for business partners.

Two steps. Blocking first: only compare partners that share the postal code,
the VAT ID, or the start of the name in the same city. Then score each
candidate pair. Comparing everyone with everyone would be 1.1 million pairs
for 1,500 customers, blocking brings that down to a few thousand.
"""
from collections import defaultdict
from itertools import combinations

from rapidfuzz import fuzz

from .normalize import blank, norm_city, norm_street, split_legal_form
from .validators import clean


def prepare(df, id_col: str) -> list[dict]:
    rows = []
    for r in df.to_dict("records"):
        name, form = split_legal_form(f"{r.get('NAME1', '')} {r.get('NAME2', '')}")
        street, house = norm_street(r.get("STRAS", ""))
        rows.append({
            "id": r[id_col],
            "name": name,
            "form": form,
            "street": street,
            "house": house,
            "city": norm_city(r.get("ORT01", "")),
            "postal": clean(r.get("PSTLZ", "")),
            "country": clean(r.get("LAND1", "")),
            "vat": clean(r.get("STCEG", "")),
        })
    return rows


# Weights for the composite score, see docs/decisions.md
W_NAME, W_STREET, W_HOUSE, W_CITY = 0.55, 0.25, 0.10, 0.10
PENALTY_LEGAL_FORM = 15
PENALTY_COUNTRY = 20
CAP_DIFFERENT_VAT = 75
SAME_VAT_OTHER_CITY = 85.0


def score(a: dict, b: dict) -> tuple[float, list[str]]:
    """Return (score 0..100, list of reasons)."""
    if a["vat"] and a["vat"] == b["vat"]:
        if a["city"] == b["city"] or not a["city"] or not b["city"]:
            return 100.0, ["same VAT ID"]
        # One legal entity, two places: often a branch or a ship-to account
        # that exists on purpose. Send it to review instead of calling it a duplicate.
        return SAME_VAT_OTHER_CITY, ["same VAT ID", "different city, branch?"]

    name = fuzz.token_sort_ratio(a["name"], b["name"])
    street = fuzz.ratio(a["street"], b["street"]) if a["street"] and b["street"] else 0
    house = 100 if a["house"] and a["house"] == b["house"] else 0
    city = 100 if a["city"] == b["city"] else fuzz.ratio(a["city"], b["city"])

    s = W_NAME * name + W_STREET * street + W_HOUSE * house + W_CITY * city
    reasons = [f"name {name:.0f}", f"street {street:.0f}"]
    if house:
        reasons.append("same house no.")
    s = _apply_penalties(a, b, s, reasons)
    return round(max(s, 0), 1), reasons


def _apply_penalties(a, b, s, reasons):
    if a["form"] and b["form"] and a["form"] != b["form"]:
        # Mueller GmbH and Mueller KG are two companies, not a typo
        s -= PENALTY_LEGAL_FORM
        reasons.append(f"legal form {a['form']} vs {b['form']}")
    if a["vat"] and b["vat"] and a["vat"] != b["vat"]:
        s = min(s, CAP_DIFFERENT_VAT)
        reasons.append("different VAT IDs")
    if a["country"] and b["country"] and a["country"] != b["country"]:
        s -= PENALTY_COUNTRY
        reasons.append("different country")
    return s


def block_keys(r: dict) -> list[tuple]:
    keys = []
    if r["postal"]:
        keys.append(("P", r["country"], r["postal"]))
    if r["vat"]:
        keys.append(("V", r["vat"]))
    if len(r["name"]) >= 4:
        keys.append(("N", r["name"][:4], r["city"]))
    if r["street"] and r["house"]:
        # catches the same firm entered with a wrong postal code or a district name
        keys.append(("S", r["country"], r["street"], r["house"]))
    return keys


def candidate_pairs(rows_a: list[dict], rows_b: list[dict] | None = None):
    """Pairs within one list, or across two lists (customer vs vendor)."""
    cross = rows_b is not None
    blocks = defaultdict(lambda: ([], []))
    sides = ((0, rows_a), (1, rows_b)) if cross else ((0, rows_a),)
    for side, rows in sides:
        for i, r in enumerate(rows):
            for k in block_keys(r):
                blocks[k][side].append(i)

    rows_b = rows_b if cross else rows_a
    seen = set()
    for left, right in blocks.values():
        if cross:
            pairs = ((i, j) for i in left for j in right)
        else:
            pairs = combinations(sorted(set(left)), 2)
        for pair in pairs:
            if pair not in seen:
                seen.add(pair)
                yield rows_a[pair[0]], rows_b[pair[1]]


def find_matches(rows_a: list[dict], rows_b: list[dict] | None = None, min_score: float = 80) -> list[tuple]:
    out = []
    for a, b in candidate_pairs(rows_a, rows_b):
        if rows_b is None and a["id"] == b["id"]:
            continue
        s, reasons = score(a, b)
        if s >= min_score:
            out.append((a["id"], b["id"], s, reasons))
    return out


def match_one(record: dict, rows: list[dict], min_score: float = 80, top: int = 5) -> list[dict]:
    """Score a single new partner against the existing master. Used by the API."""
    hits = []
    for r in rows:
        if blank(r["name"]):
            continue
        s, reasons = score(record, r)
        if s >= min_score:
            hits.append({"id": r["id"], "score": s, "reasons": reasons})
    hits.sort(key=lambda h: -h["score"])
    return hits[:top]
