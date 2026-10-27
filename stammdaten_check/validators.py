"""Field-level checks: IBAN, VAT ID, postal codes, email.

None of these need a network connection. The VIES lookup lives in vies.py
and is off by default.
"""
import re

# IBAN length per country (ISO 13616 registry). Only countries we see in practice.
IBAN_LENGTH = {
    "DE": 22, "AT": 20, "NL": 18, "BE": 16, "CH": 21, "FR": 27, "IT": 27,
    "ES": 24, "PL": 28, "LU": 20, "DK": 18, "CZ": 24,
}

# Countries that use IBAN. A vendor here without an IBAN cannot be paid by SEPA.
SEPA_COUNTRIES = set(IBAN_LENGTH)

VAT_PATTERNS = {
    "DE": r"DE\d{9}",
    "AT": r"ATU\d{8}",
    "NL": r"NL\d{9}B\d{2}",
    "BE": r"BE[01]\d{9}",
    "FR": r"FR[0-9A-HJ-NP-Z]{2}\d{9}",
    "IT": r"IT\d{11}",
    "LU": r"LU\d{8}",
    "PL": r"PL\d{10}",
}


def clean(value):
    return re.sub(r"\s+", "", str(value or "")).upper()


def iban_checksum_ok(iban):
    """ISO 13616: move first 4 chars to the end, letters to numbers, mod 97 == 1."""
    s = clean(iban)
    if len(s) < 5 or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    rearranged = s[4:] + s[:4]
    digits = ""
    for ch in rearranged:
        if ch.isdigit():
            digits += ch
        elif ch.isalpha():
            digits += str(ord(ch) - 55)
        else:
            return False
    return int(digits) % 97 == 1


def iban_problems(iban, country=None):
    """Return a list of problem codes. Empty list means fine."""
    s = clean(iban)
    problems = []
    cc = s[:2]
    expected = IBAN_LENGTH.get(cc)
    if expected and len(s) != expected:
        problems.append("IBAN_LENGTH")
    if not iban_checksum_ok(s):
        problems.append("IBAN_CHECKSUM")
    if country and cc and country != cc:
        problems.append("IBAN_COUNTRY_DIFFERS")
    return problems


def make_iban(country, bban):
    """Build an IBAN with correct check digits. Used by the data generator and tests."""
    tmp = bban + country + "00"
    digits = "".join(str(int(c, 36)) for c in tmp)
    check = 98 - int(digits) % 97
    return f"{country}{check:02d}{bban}"


def de_iban_matches(iban, blz, account):
    """German IBAN = DE + 2 check digits + 8 digit BLZ + 10 digit account (left padded).

    In ECC the old fields LFBK-BANKL (BLZ) and LFBK-BANKN (account) still exist
    next to TIBAN. After years of manual edits they often disagree.
    """
    s = clean(iban)
    if not s.startswith("DE") or len(s) != 22:
        return True  # not our business here, length rule catches it
    acc = clean(account).lstrip("0").zfill(10)
    return s[4:12] == clean(blz) and s[12:22] == acc


def de_vat_check_digit_ok(vat):
    """German USt-IdNr check digit, ISO 7064 MOD 11,10 as used by the BZSt."""
    s = clean(vat)
    if not re.fullmatch(r"DE\d{9}", s):
        return False
    digits = s[2:]
    product = 10
    for d in digits[:8]:
        total = (int(d) + product) % 10
        if total == 0:
            total = 10
        product = (2 * total) % 11
    check = 11 - product
    if check == 10:
        check = 0
    return check == int(digits[8])


def make_de_vat(eight_digits):
    """Append the correct check digit. Used by the generator."""
    product = 10
    for d in eight_digits:
        total = (int(d) + product) % 10
        if total == 0:
            total = 10
        product = (2 * total) % 11
    check = 11 - product
    if check == 10:
        check = 0
    return f"DE{eight_digits}{check}"


def vat_problems(vat, country):
    s = clean(vat)
    if not s:
        return []
    problems = []
    prefix = "GR" if s.startswith("EL") else s[:2]
    if country and prefix != country and not (country == "GR" and s.startswith("EL")):
        problems.append("VAT_COUNTRY_DIFFERS")
    pattern = VAT_PATTERNS.get(s[:2])
    if pattern and not re.fullmatch(pattern, s):
        problems.append("VAT_FORMAT")
    elif s.startswith("DE") and not de_vat_check_digit_ok(s):
        problems.append("VAT_CHECK_DIGIT")
    return problems


def postal_ok(postal, rule):
    """rule is one row of reference/t005_postal.csv (length, numeric, pattern)."""
    p = str(postal or "").strip()
    if not p:
        return False
    if rule.get("pattern"):
        return re.fullmatch(rule["pattern"], p) is not None
    length = int(rule["length"]) if rule.get("length") else None
    if length and len(p) != length:
        return False
    if str(rule.get("numeric")).lower() in ("1", "true", "x") and not p.isdigit():
        return False
    return True


EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}")


def email_ok(value):
    return EMAIL.fullmatch(str(value or "").strip()) is not None
