"""End-to-end on a small generated data set, plus a few hand-built cases
for the SQL-based rules."""
import pandas as pd
import pytest

from stammdaten_check import engine, generator, staging, extracts
from stammdaten_check.evaluate import evaluate


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    folder = tmp_path_factory.mktemp("sample")
    generator.generate(folder, seed=11, customers=600, vendors=250, materials=300)
    result = engine.run(folder)
    return folder, result


def test_every_rule_produces_findings(sample):
    _, result = sample
    found = set(result.findings["rule"])
    assert {f"R{i:02d}" for i in range(0, 14)} <= found


def test_recall_on_planted_errors(sample):
    folder, result = sample
    labels = pd.read_csv(folder / "labels.csv", dtype=str, keep_default_na=False)
    scores, _, _ = evaluate(result.findings, labels)
    for r in scores.to_dict("records"):
        # duplicates are fuzzy, everything else is exact
        floor = 0.9 if r["rule"] == "R01" else 1.0
        assert r["recall"] >= floor, r


def test_greenfield_skips_cvi_rules(sample):
    folder, _ = sample
    cfg = engine.load_config()
    cfg["run"]["path"] = "greenfield"
    result = engine.run(folder, cfg)
    assert not set(result.findings["rule"]) & {"R07", "R08", "R09", "R12"}


def test_partner_with_open_items_is_never_archived(sample):
    folder, result = sample
    act = pd.read_csv(folder / "activity.csv", dtype=str, keep_default_na=False)
    open_ids = set(act.loc[act["OPEN_ITEMS"].astype(int) > 0, "ID"])
    archived = set(result.findings.loc[result.findings["rule"] == "R06", "key"])
    assert not archived & open_ids


def test_staging_leaves_out_blocked_and_duplicates(sample):
    folder, result = sample
    tables = extracts.load(folder)
    ref = extracts.load_reference(engine.ROOT / "reference")
    rows, excluded = staging.build(tables, ref, result.findings, "customer")
    blockers = set(result.findings.loc[(result.findings["severity"] == "blocker")
                                       & (result.findings["object"] == "customer"), "key"])
    assert not set(rows["LEGACY_KEY"]) & blockers
    assert len(rows) + len(excluded) == len(tables["kna1"])
    assert (rows["BU_GROUP"] != "").all()


def test_missing_required_file_gives_clear_error(tmp_path):
    with pytest.raises(extracts.ExtractError, match="kna1.csv is missing"):
        extracts.load(tmp_path)


def test_split_street():
    assert staging.split_street("Kölner Straße 12a") == ("Kölner Straße", "12a")
    assert staging.split_street("Am Hof 3-5") == ("Am Hof", "3-5")
    assert staging.split_street("Postfach") == ("Postfach", "")
