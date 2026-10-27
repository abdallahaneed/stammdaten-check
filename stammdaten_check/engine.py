"""Runs the rules and collects findings."""
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import db, extracts
from .rules import REGISTRY, SEVERITY_WEIGHT, Context

ROOT = Path(__file__).resolve().parent.parent


def load_config(path=None):
    with open(ROOT / "config" / "default.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    if path:
        with open(path, "rb") as fh:
            for section, values in tomllib.load(fh).items():
                cfg.setdefault(section, {}).update(values)
    return cfg


@dataclass
class Result:
    findings: pd.DataFrame
    readiness: pd.DataFrame
    totals: dict
    rule_times: dict = field(default_factory=dict)
    path: str = "both"


def run(input_dir, config: dict | None = None, ref_dir=None, vies=None, only: set | None = None) -> Result:
    cfg = config or load_config()
    tables = extracts.load(input_dir)
    ref = extracts.load_reference(ref_dir or ROOT / "reference")
    con = db.connect(tables)
    try:
        return _run(con, tables, ref, cfg, vies, only)
    finally:
        con.close()


def _run(con, tables, ref, cfg, vies, only):
    ctx = Context(tables=tables, ref=ref, config=cfg, db=con, vies=vies)

    path = cfg["run"].get("path", "both")
    rows, times = [], {}
    for rid in sorted(REGISTRY):
        r = REGISTRY[rid]
        if only and rid not in only:
            continue
        if path != "both" and path not in r.paths:
            continue
        t0 = time.perf_counter()
        for f in r.func(ctx):
            d = f.as_dict()
            d["weight"] = SEVERITY_WEIGHT[f.severity]
            rows.append(d)
        times[rid] = round(time.perf_counter() - t0, 3)

    columns = ["rule", "severity", "object", "key", "field", "message", "fix", "related", "weight"]
    findings = pd.DataFrame(rows, columns=columns)

    totals = {
        "customer": len(tables["kna1"]),
        "vendor": len(tables["lfa1"]),
        "material": len(tables["mara"]),
        "contact": len(tables["knvk"]),
    }
    readiness = score(con, findings, totals)
    return Result(findings, readiness, totals, times, path)


def score(con, findings, totals):
    findings.to_sql("findings", con, index=False, if_exists="replace")
    pd.DataFrame([{"object": k, "total": v} for k, v in totals.items() if v]) \
        .to_sql("totals", con, index=False, if_exists="replace")
    return pd.DataFrame(db.query(con, "readiness"))
