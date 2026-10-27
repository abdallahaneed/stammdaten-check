import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

from . import engine, extracts, generator, report_excel, staging
from .evaluate import evaluate, to_markdown


def cmd_generate(a):
    out = generator.generate(a.out, seed=a.seed, customers=a.customers,
                             vendors=a.vendors, materials=a.materials)
    print(f"Synthetic extracts written to {out}")


def cmd_run(a):
    cfg = engine.load_config(a.config)
    if a.path:
        cfg["run"]["path"] = a.path
    vies = None
    if a.vies:
        from .vies import Vies
        vies = Vies()
    t0 = time.perf_counter()
    try:
        result = engine.run(a.input, cfg, vies=vies)
    except extracts.ExtractError as e:
        sys.exit(f"Cannot read extracts: {e}")
    took = time.perf_counter() - t0

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tables = extracts.load(a.input)
    ref = extracts.load_reference(engine.ROOT / "reference")
    result.findings.to_csv(out / "findings.csv", index=False)
    report_excel.write(result, tables, out / "stammdaten-report.xlsx")

    excluded_all = []
    for obj in ("customer", "vendor"):
        rows, excluded = staging.build(tables, ref, result.findings, obj)
        rows.to_csv(out / f"bp_staging_{obj}.csv", index=False)
        excluded_all.append(excluded)
    pd.concat(excluded_all).to_csv(out / "not_migrated.csv", index=False)

    summary = {
        "path": result.path,
        "records": result.totals,
        "findings": int(len(result.findings)),
        "by_severity": result.findings["severity"].value_counts().to_dict(),
        "readiness": result.readiness.to_dict("records"),
        "seconds": round(took, 2),
        "rule_seconds": result.rule_times,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"{summary['findings']} findings in {took:.1f}s ({result.path})")
    for r in summary["readiness"]:
        print(f"  {r['object']:<9} {r['total']:>6} records  readiness {r['readiness']}%")
    print(f"Report: {out / 'stammdaten-report.xlsx'}")


def cmd_evaluate(a):
    findings = pd.read_csv(Path(a.out) / "findings.csv", dtype=str, keep_default_na=False)
    labels = pd.read_csv(Path(a.input) / "labels.csv", dtype=str, keep_default_na=False)
    scores, misses, extras = evaluate(findings, labels)
    text = "## Scores\n\n" + to_markdown(scores)
    text += "\n## Missed planted errors\n\n" + to_markdown(misses)
    text += "\n## Flagged but not planted\n\n" + to_markdown(extras)
    (Path(a.out) / "evaluation.md").write_text(text, encoding="utf-8")
    print(text)


def cmd_serve(a):
    import uvicorn
    from .web.app import create_app
    print(f"Dashboard: http://{a.host}:{a.port}   API docs: http://{a.host}:{a.port}/docs")
    uvicorn.run(create_app(a.home), host=a.host, port=a.port, log_level="warning")


def main(argv=None):
    p = argparse.ArgumentParser(prog="stammdaten-check",
                                description="Master data readiness checks before an S/4HANA move")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write synthetic ECC extracts with planted errors")
    g.add_argument("--out", default="data/sample")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--customers", type=int, default=1500)
    g.add_argument("--vendors", type=int, default=600)
    g.add_argument("--materials", type=int, default=1200)
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run", help="check a folder of extracts")
    r.add_argument("--input", default="data/sample")
    r.add_argument("--out", default="out")
    r.add_argument("--config")
    r.add_argument("--path", choices=["brownfield", "greenfield", "both"])
    r.add_argument("--vies", action="store_true", help="also ask EU VIES (needs internet)")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("evaluate", help="compare findings with labels.csv")
    e.add_argument("--input", default="data/sample")
    e.add_argument("--out", default="out")
    e.set_defaults(func=cmd_evaluate)

    s = sub.add_parser("serve", help="start the web dashboard and API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--home", default="var", help="folder for the database and uploaded extracts")
    s.set_defaults(func=cmd_serve)

    a = p.parse_args(argv)
    a.func(a)
