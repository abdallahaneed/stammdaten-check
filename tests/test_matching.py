import pandas as pd

from stammdaten_check.matching import find_matches, prepare, score
from stammdaten_check.normalize import norm_street, split_legal_form


def rows(*records):
    df = pd.DataFrame(records)
    for c in ["NAME2", "STCEG", "LAND1"]:
        if c not in df:
            df[c] = "DE" if c == "LAND1" else ""
    return prepare(df.fillna(""), "KUNNR")


def test_legal_forms():
    assert split_legal_form("Müller GmbH & Co. KG") == ("mueller", "GMBH_CO_KG")
    assert split_legal_form("Mueller GmbH u. Co KG") == ("mueller", "GMBH_CO_KG")
    assert split_legal_form("Müller G.m.b.H.") == ("mueller", "GMBH")
    assert split_legal_form("Müller Gesellschaft mbH")[1] == "GMBH"
    assert split_legal_form("Schaaf UG (haftungsbeschränkt)") == ("schaaf", "UG")


def test_street_variants():
    assert norm_street("Hauptstraße 12a") == norm_street("Hauptstr. 12 a")
    assert norm_street("Hauptstrasse 12") == ("hauptstr", "12")


def test_same_firm_written_differently():
    a, b = rows(
        {"KUNNR": "1", "NAME1": "Bäckerei Schröder GmbH", "STRAS": "Kölner Straße 5", "PSTLZ": "53111", "ORT01": "Bonn"},
        {"KUNNR": "2", "NAME1": "BAECKEREI SCHROEDER G.m.b.H.", "STRAS": "Koelner Str. 5", "PSTLZ": "53111", "ORT01": "Bonn"},
    )
    s, _ = score(a, b)
    assert s >= 90


def test_gmbh_and_kg_are_different_companies():
    a, b = rows(
        {"KUNNR": "1", "NAME1": "Müller GmbH", "STRAS": "Am Markt 1", "PSTLZ": "53111", "ORT01": "Bonn"},
        {"KUNNR": "2", "NAME1": "Müller KG", "STRAS": "Am Markt 1", "PSTLZ": "53111", "ORT01": "Bonn"},
    )
    s, reasons = score(a, b)
    assert s < 90
    assert any("legal form" in r for r in reasons)


def test_same_vat_other_city_goes_to_review():
    a, b = rows(
        {"KUNNR": "1", "NAME1": "Nord Logistik GmbH", "STRAS": "Hafenweg 2", "PSTLZ": "28195", "ORT01": "Bremen", "STCEG": "DE136695976"},
        {"KUNNR": "2", "NAME1": "Nord Logistik GmbH", "STRAS": "Industriestr. 9", "PSTLZ": "50667", "ORT01": "Köln", "STCEG": "DE136695976"},
    )
    s, _ = score(a, b)
    assert 80 <= s < 90


def test_blocking_still_finds_pair_with_wrong_postal_code():
    data = rows(
        {"KUNNR": "1", "NAME1": "Weber Elektro GmbH", "STRAS": "Ringstraße 40", "PSTLZ": "53113", "ORT01": "Bonn"},
        {"KUNNR": "2", "NAME1": "Weber Elektro GmbH", "STRAS": "Ringstr. 40", "PSTLZ": "53114", "ORT01": "Bonn-Mitte"},
        {"KUNNR": "3", "NAME1": "Fischer Holz KG", "STRAS": "Waldweg 3", "PSTLZ": "53113", "ORT01": "Bonn"},
    )
    pairs = {(a, b) for a, b, _, _ in find_matches(data, min_score=80)}
    assert ("1", "2") in pairs
    assert not any("3" in p for p in pairs)
