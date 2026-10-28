import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from stammdaten_check import generator
from stammdaten_check.web.app import create_app

KEY = "test-key"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    c = TestClient(create_app(home, api_key=KEY))
    c.headers.update({"X-API-Key": KEY, "X-User": "tester"})
    return c


@pytest.fixture(scope="module")
def run(client):
    r = client.post("/api/v1/runs", data={"sample": "true", "seed": "5", "label": "Test"})
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_writes_need_the_key(client):
    r = client.post("/api/v1/runs", data={"sample": "true"}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_run_summary(client, run):
    assert run["label"] == "Test"
    assert {r["object"] for r in run["readiness"]} >= {"customer", "vendor"}
    assert client.get(f"/api/v1/runs/{run['id']}").json()["id"] == run["id"]
    assert any(r["id"] == run["id"] for r in client.get("/api/v1/runs").json())


def test_findings_filter_and_paging(client, run):
    r = client.get(f"/api/v1/runs/{run['id']}/findings", params={"rule": "R03", "limit": 5}).json()
    assert len(r["data"]) == 5
    assert all(f["rule"] == "R03" for f in r["data"])
    assert r["pagination"]["hasMore"] is True
    assert client.get(f"/api/v1/runs/{run['id']}/findings", params={"rule": "X1"}).status_code == 422


def test_status_change_is_logged_and_moves_readiness(client, run):
    page = client.get(f"/api/v1/runs/{run['id']}/findings", params={"severity": "blocker", "limit": 1}).json()
    fid = page["data"][0]["id"]
    before = {r["object"]: r["readinessNow"] for r in client.get(f"/api/v1/runs/{run['id']}").json()["readiness"]}

    r = client.patch(f"/api/v1/findings/{fid}", json={"status": "fixed", "owner": "Einkauf"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "fixed"
    assert body["history"][-1]["changedBy"] == "tester"
    assert body["history"][-1]["oldStatus"] == "open"

    after = {r["object"]: r["readinessNow"] for r in client.get(f"/api/v1/runs/{run['id']}").json()["readiness"]}
    obj = body["object"]
    assert after[obj] >= before[obj]


def test_false_positive_needs_a_reason(client, run):
    fid = client.get(f"/api/v1/runs/{run['id']}/findings", params={"rule": "R01", "limit": 1}).json()["data"][0]["id"]
    r = client.patch(f"/api/v1/findings/{fid}", json={"status": "false_positive"})
    assert r.status_code == 422
    r = client.patch(f"/api/v1/findings/{fid}", json={"status": "false_positive", "comment": "branch, keep both"})
    assert r.status_code == 200


def test_duplicate_pairs(client, run):
    pairs = client.get(f"/api/v1/runs/{run['id']}/duplicate-pairs").json()
    assert pairs and {"a", "b", "score", "reasons"} <= set(pairs[0])
    assert pairs[0]["a"]["id"] != pairs[0]["b"]["id"]


def test_report_download(client, run):
    r = client.get(f"/api/v1/runs/{run['id']}/report")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx is a zip


def test_partner_check_finds_existing_company_and_iban(client, run, tmp_path):
    folder = tmp_path / "x"
    generator.generate(folder, seed=5)
    import pandas as pd
    lfa1 = pd.read_csv(folder / "lfa1.csv", dtype=str, keep_default_na=False)
    lfbk = pd.read_csv(folder / "lfbk.csv", dtype=str, keep_default_na=False)
    tiban = pd.read_csv(folder / "tiban.csv", dtype=str, keep_default_na=False)
    v = lfa1[lfa1["LAND1"] == "DE"].iloc[0]
    bank = lfbk[lfbk["LIFNR"] == v["LIFNR"]].merge(tiban, on=["BANKS", "BANKL", "BANKN", "BKONT"]).iloc[0]

    r = client.post("/api/v1/partner-checks", json={
        "object": "vendor", "name": v["NAME1"].upper(), "street": v["STRAS"], "postalCode": v["PSTLZ"],
        "city": v["ORT01"], "country": "DE", "iban": bank["IBAN"],
    }).json()
    assert r["duplicates"][0]["id"] == v["LIFNR"]
    assert any(p["code"] == "IBAN_IN_USE" for p in r["problems"])
    assert r["ok"] is False


def test_partner_check_flags_bad_fields(client, run):
    r = client.post("/api/v1/partner-checks", json={
        "name": "xxx", "country": "DE", "city": "Bonn", "postalCode": "5311",
        "vatId": "DE136695977", "iban": "DE89370400440532013001",
    }).json()
    codes = {p["code"] for p in r["problems"]}
    assert {"REQUIRED", "POSTAL_FORMAT", "VAT_CHECK_DIGIT", "IBAN_CHECKSUM"} <= codes


def test_upload_zip_and_reject_bad_zip(client, tmp_path):
    folder = tmp_path / "ext"
    generator.generate(folder, seed=9, customers=200, vendors=80, materials=50)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in folder.glob("*.csv"):
            z.write(f, f"export/2026/{f.name}")   # nested folders are flattened
        z.writestr("../../evil.csv", "a,b\n1,2\n")  # must not escape the run folder
    r = client.post("/api/v1/runs", files={"file": ("export.zip", buf.getvalue(), "application/zip")},
                    data={"path": "greenfield"})
    assert r.status_code == 201, r.text
    assert r.json()["path"] == "greenfield"
    assert not (tmp_path.parent / "evil.csv").exists()

    r = client.post("/api/v1/runs", files={"file": ("x.zip", b"not a zip", "application/zip")})
    assert r.status_code == 422


def test_unknown_run(client):
    r = client.get("/api/v1/runs/9999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_bulk_update_is_all_or_nothing(client, run):
    page = client.get(f"/api/v1/runs/{run['id']}/findings", params={"rule": "R06", "limit": 3}).json()
    ids = [f["id"] for f in page["data"]]
    r = client.patch("/api/v1/findings", json={"ids": ids + [999999], "status": "accepted"})
    assert r.status_code == 404
    assert all(client.get(f"/api/v1/findings/{i}").json()["status"] == "open" for i in ids)
    r = client.patch("/api/v1/findings", json={"ids": ids, "status": "accepted", "owner": "Vertrieb"})
    assert r.json() == {"updated": 3}
    assert all(client.get(f"/api/v1/findings/{i}").json()["owner"] == "Vertrieb" for i in ids)


def test_vendor_lookup(client, run):
    r = client.get("/api/v1/vendors/300001")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["id"] == "300001" and v["phone"] and v["banks"]
    assert v["banks"][0]["iban"].startswith(v["banks"][0]["country"])
    assert client.get("/api/v1/vendors/999999").status_code == 404
