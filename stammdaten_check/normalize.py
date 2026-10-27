"""Text normalization for matching names and addresses.

German master data is full of spelling variants for the same thing:
Müller / Mueller, Straße / Str. / Strasse, GmbH & Co. KG / GmbH u. Co KG.
Everything here turns those into one comparable form.
"""
import re
import unicodedata

UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}

# Order matters: longer forms first so "gmbh & co kg" wins over "gmbh".
LEGAL_FORMS = [
    ("GMBH_CO_KG", r"g\.?\s*m\.?\s*b\.?\s*h\.?\s*(?:&|und|u\.?)\s*co\.?\s*kg(?!aa)"),
    ("GMBH_CO_OHG", r"g\.?\s*m\.?\s*b\.?\s*h\.?\s*(?:&|und|u\.?)\s*co\.?\s*ohg"),
    ("AG_CO_KG", r"\bag\s*(?:&|und|u\.?)\s*co\.?\s*kg(?!aa)"),
    ("CO_KGAA", r"(?:&|und|u\.?)\s*co\.?\s*kgaa"),
    ("KGAA", r"\bkgaa\b"),
    ("EG", r"\be\.?\s*g\.?(?=\s|$)"),
    ("GMBH", r"gesellschaft\s+mbh|g\.?\s*m\.?\s*b\.?\s*h\.?"),
    ("UG", r"ug\s*\(?haftungsbeschr(?:ae|a)nkt\)?|\bug\b"),
    ("AG", r"\bag\b|aktiengesellschaft"),
    ("KG", r"\bkg\b|kommanditgesellschaft"),
    ("OHG", r"\bohg\b"),
    ("EK", r"\be\.?\s*k(?:fm|fr)?\.?(?=\s|$)"),
    ("GBR", r"\bgbr\b"),
    ("BV", r"\bb\.?v\.?(?=\s|$)"),
    ("SA", r"\bs\.?a\.?(?=\s|$)"),
]

STREET_SUFFIX = re.compile(r"(stra(?:ss|ß)e|str\.?)(?=\s|\d|$)")


def fold(text):
    """Lowercase, replace umlauts, strip accents and punctuation noise."""
    if text is None:
        return ""
    t = str(text).strip().lower()
    for k, v in UMLAUTS.items():
        t = t.replace(k, v)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t


def split_legal_form(name):
    """Return (name without legal form, canonical legal form or '')."""
    t = fold(name)
    for code, pattern in LEGAL_FORMS:
        m = re.search(pattern, t)
        if m:
            t = (t[: m.start()] + " " + t[m.end():]).strip()
            return _squash(t), code
    return _squash(t), ""


def norm_name(name):
    return split_legal_form(name)[0]


def legal_form(name):
    return split_legal_form(name)[1]


def norm_street(street):
    """'Hauptstraße 12a' and 'Hauptstr. 12 a' both become ('hauptstr', '12a')."""
    t = fold(street)
    t = STREET_SUFFIX.sub("str", t)
    m = re.search(r"(\d+\s*[a-z]?)\s*$", t)
    house = ""
    if m:
        house = m.group(1).replace(" ", "")
        t = t[: m.start()]
    return _squash(t), house


def norm_city(city):
    t = fold(city)
    t = re.sub(r"\(.*?\)", " ", t)  # "Bonn (Beuel)" -> "bonn"
    return _squash(t)


def _squash(t):
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# What people type when a mandatory field has to be filled and they do not know the value
PLACEHOLDERS = {"", "-", "--", ".", "..", "?", "x", "xx", "xxx", "n/a", "na", "null", "none",
                "unbekannt", "unknown", "k.a.", "ka", "0", "00000", "tbd", "folgt"}


def blank(value):
    if value is None or (isinstance(value, float) and value != value):
        return True
    return str(value).strip().lower() in PLACEHOLDERS
