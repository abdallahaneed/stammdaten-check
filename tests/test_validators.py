from stammdaten_check.validators import (
    de_iban_matches, de_vat_check_digit_ok, iban_checksum_ok, iban_problems,
    make_de_vat, make_iban, postal_ok, vat_problems,
)

# The IBAN everyone uses in documentation. Not a real account.
DOC_IBAN = "DE89370400440532013000"


def test_iban_checksum():
    assert iban_checksum_ok(DOC_IBAN)
    assert iban_checksum_ok("de89 3704 0044 0532 0130 00")
    assert not iban_checksum_ok("DE89370400440532013001")


def test_iban_swapped_digits_are_caught():
    swapped = DOC_IBAN[:14] + DOC_IBAN[15] + DOC_IBAN[14] + DOC_IBAN[16:]
    assert swapped != DOC_IBAN
    assert "IBAN_CHECKSUM" in iban_problems(swapped)


def test_iban_length_and_country():
    assert "IBAN_LENGTH" in iban_problems(DOC_IBAN[:-1])
    assert "IBAN_COUNTRY_DIFFERS" in iban_problems(DOC_IBAN, "AT")
    assert iban_problems(DOC_IBAN, "DE") == []


def test_make_iban_round_trip():
    iban = make_iban("DE", "37040044" + "0532013000")
    assert iban == DOC_IBAN


def test_german_iban_contains_blz_and_account():
    assert de_iban_matches(DOC_IBAN, "37040044", "532013000")
    assert de_iban_matches(DOC_IBAN, "37040044", "0532013000")
    assert not de_iban_matches(DOC_IBAN, "37040044", "532013001")
    assert not de_iban_matches(DOC_IBAN, "37040045", "532013000")


def test_german_vat_check_digit():
    # example number published by the Bundeszentralamt fuer Steuern
    assert de_vat_check_digit_ok("DE136695976")
    assert not de_vat_check_digit_ok("DE136695977")
    assert de_vat_check_digit_ok(make_de_vat("12345678"))


def test_vat_problems():
    assert vat_problems("DE136695976", "DE") == []
    assert vat_problems("DE13669597", "DE") == ["VAT_FORMAT"]
    assert "VAT_COUNTRY_DIFFERS" in vat_problems("DE136695976", "AT")
    assert vat_problems("ATU12345678", "AT") == []
    assert vat_problems("NL123456789B01", "NL") == []
    assert vat_problems("", "DE") == []


def test_postal_rules():
    de = {"length": "5", "numeric": "1", "pattern": ""}
    nl = {"length": "", "numeric": "", "pattern": r"\d{4} ?[A-Z]{2}"}
    assert postal_ok("53115", de)
    assert not postal_ok("5311", de)
    assert not postal_ok("D-53115", de)
    assert postal_ok("1012 AB", nl)
    assert not postal_ok("1012", nl)


def test_placeholders_count_as_empty():
    from stammdaten_check.normalize import blank
    for v in ["", "  ", "-", "xxx", "XXX", "unbekannt", "k.a.", None]:
        assert blank(v), v
    for v in ["Bonn", "53115", "x-ray GmbH"]:
        assert not blank(v), v
