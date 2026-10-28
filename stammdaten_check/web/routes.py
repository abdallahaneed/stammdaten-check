"""API routes. The store and the API key come from app.state, set in app.py."""
import io
import secrets
from types import SimpleNamespace
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, Header, Path, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader

from .. import extracts, generator, report_excel
from ..rules import REGISTRY
from . import partner_check
from .models import (BulkUpdate, FindingsPage, FindingUpdate, PartnerCheckOut, PartnerIn, Status,
                     camel)
from .store import BadInput, NotFound, Store

RunId = Annotated[int, Path(alias="runId", ge=1)]
FindingId = Annotated[int, Path(alias="findingId", ge=1)]
User = Annotated[str, Header(alias="X-User", max_length=80, description="who made the change")]

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False,
                              description="needed for writes when STAMMDATEN_API_KEY is set")


def get_store(request: Request) -> Store:
    return request.app.state.store


def require_key(request: Request, x_api_key: str | None = Depends(api_key_header)):
    # Read access stays open on purpose: the dashboard runs on localhost.
    # Anything that writes needs the key once one is configured.
    key = request.app.state.api_key
    if key and not secrets.compare_digest(x_api_key or "", key):
        raise PermissionError("missing or wrong X-API-Key")


StoreDep = Annotated[Store, Depends(get_store)]
writes = [Depends(require_key)]
router = APIRouter(prefix="/api/v1")


# ----- system -----

@router.get("/health", tags=["system"], summary="Liveness check")
def health():
    """Returns ok when the service is up. No database access."""
    return {"status": "ok"}


@router.get("/rules", tags=["system"], summary="All rules with path and explanation")
def rules(response: Response):
    """Every rule with the migration path it applies to and why it exists."""
    response.headers["Cache-Control"] = "public, max-age=3600"  # changes only with a new release
    return [{"id": r.id, "title": r.title, "paths": list(r.paths),
             "description": " ".join(r.description.split())} for r in REGISTRY.values()]


# ----- runs -----

@router.get("/runs", tags=["runs"], summary="List runs, newest first")
def list_runs(store: StoreDep):
    """Each run with its number of findings and how many are still open."""
    return camel(store.list_runs())


@router.post("/runs", tags=["runs"], status_code=201, dependencies=writes,
             summary="Start a run from a zip of CSV extracts, or from generated sample data")
def create_run(store: StoreDep, response: Response,
               file: UploadFile | None = File(None, description="zip with kna1.csv, lfa1.csv ..."),
               label: str = Form("", max_length=80),
               path: Literal["brownfield", "greenfield", "both"] = Form("both"),
               sample: bool = Form(False, description="ignore file, generate synthetic extracts"),
               seed: int = Form(42)):
    """Upload a zip with the table extracts (kna1.csv, lfa1.csv ...), or set sample to true for
    generated test data. Only CSV files are taken from the zip, folders inside it are ignored."""
    if sample:
        run_id = store.create_run(label or f"Sample seed {seed}", path, "sample",
                                  lambda folder: generator.generate(folder, seed=seed))
    elif file is not None:
        data = file.file.read()
        run_id = store.create_run(label or file.filename or "Upload", path, "upload",
                                  lambda folder: store.unpack(data, folder))
    else:
        raise BadInput("send a zip file or set sample=true")
    response.headers["Location"] = f"/api/v1/runs/{run_id}"
    return camel(store.get_run(run_id))


@router.get("/runs/{runId}", tags=["runs"], summary="Run summary: readiness then and now, progress per rule")
def get_run(store: StoreDep, run_id: RunId):
    """Readiness per object as found and now (fixed findings and false positives no longer
    count), plus clearing progress per rule."""
    return camel(store.get_run(run_id))


@router.delete("/runs/{runId}", tags=["runs"], status_code=204, dependencies=writes,
               summary="Delete a run with its extracts and findings")
def delete_run(store: StoreDep, run_id: RunId):
    """Removes the run, its uploaded extracts and every finding with its history."""
    store.get_run(run_id)
    store.delete_run(run_id)
    return Response(status_code=204)


@router.get("/runs/{runId}/findings", tags=["findings"], response_model=FindingsPage,
            summary="Findings of a run, filtered and paged")
def list_findings(store: StoreDep, run_id: RunId,
                  rule: str | None = Query(None, pattern=r"^R\d{2}$"),
                  severity: Literal["blocker", "error", "warning", "info"] | None = None,
                  object: Literal["customer", "vendor", "material", "contact"] | None = None,
                  status: Status | None = None,
                  q: str | None = Query(None, max_length=80, description="search in number, message, related"),
                  limit: int = Query(50, ge=1, le=500),
                  offset: int = Query(0, ge=0)):
    """Sorted by severity, then rule. Filter by rule, severity, object, status or a search text."""
    rows, total = store.findings(run_id, rule, severity, object, status, q, limit, offset)
    return {"data": camel(rows),
            "pagination": {"offset": offset, "limit": limit, "total": total,
                           "hasMore": offset + len(rows) < total}}


def _pair(finding, lookup):
    # message looks like "likely duplicate of 100553 (score 92.4: name 95, street 100)"
    inside = finding["message"].split("(score ", 1)[1].rstrip(")")
    score, reasons = inside.split(": ", 1)
    m = lookup[finding["object"]]
    return {"findingId": finding["id"], "object": finding["object"], "status": finding["status"],
            "severity": finding["severity"], "score": float(score), "reasons": reasons.split(", "),
            "a": {"id": finding["related"], **m.loc[finding["related"]].to_dict()},
            "b": {"id": finding["key"], **m.loc[finding["key"]].to_dict()}}


@router.get("/runs/{runId}/duplicate-pairs", tags=["findings"],
            summary="Duplicate findings with both records side by side")
def duplicate_pairs(store: StoreDep, run_id: RunId):
    """Every R01 finding with both partner records, so a person can decide which one survives."""
    rows, _ = store.findings(run_id, rule="R01", limit=10_000)
    t = extracts.load(store.extract_dir(run_id))
    cols = ["NAME1", "NAME2", "STRAS", "PSTLZ", "ORT01", "LAND1", "STCEG"]
    lookup = {
        "customer": t["kna1"].drop_duplicates("KUNNR").set_index("KUNNR")[cols],
        "vendor": t["lfa1"].drop_duplicates("LIFNR").set_index("LIFNR")[cols],
    }
    return [_pair(f, lookup) for f in rows]


@router.get("/runs/{runId}/report", tags=["runs"], summary="Excel worklist with current statuses",
            response_class=StreamingResponse)
def report(store: StoreDep, run_id: RunId):
    """The Excel worklist including status, owner and comment as set in the dashboard."""
    run = store.get_run(run_id)
    readiness = pd.DataFrame([{"object": r["object"], "total": r["total"],
                               "records_with_findings": r["records_open"],
                               "readiness": r["readiness_now"]} for r in run["readiness"]])
    result = SimpleNamespace(findings=store.findings_frame(run_id), readiness=readiness, path=run["path"])
    buf = io.BytesIO()
    report_excel.write(result, extracts.load(store.extract_dir(run_id)), buf,
                       title=f"Stammdaten-Check: {run['label']}")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="stammdaten-run-{run_id}.xlsx"'})


# ----- findings -----

@router.get("/findings/{findingId}", tags=["findings"], summary="One finding with its change history")
def get_finding(store: StoreDep, finding_id: FindingId):
    """One finding and every change made to it."""
    return camel(store.get_finding(finding_id))


@router.patch("/findings/{findingId}", tags=["findings"], dependencies=writes,
              summary="Set status, owner or comment. Every change is logged.")
def update_finding(store: StoreDep, finding_id: FindingId, body: FindingUpdate, x_user: User = "unknown"):
    """Changes are written to the history with the X-User header. A false positive needs a comment."""
    return camel(store.update_finding(finding_id, x_user, body.status, body.owner, body.comment))


@router.patch("/findings", tags=["findings"], dependencies=writes, summary="Change several findings at once")
def update_findings(store: StoreDep, body: BulkUpdate, x_user: User = "unknown"):
    """Same rules as the single update. Either all findings change or none."""
    return {"updated": store.update_many(body.ids, x_user, body.status, body.owner, body.comment)}


# ----- single partner -----

@router.post("/partner-checks", tags=["partners"], response_model=PartnerCheckOut, dependencies=writes,
             summary="Check one new or changed partner against the rules and the latest master data")
def partner_checks(store: StoreDep, body: PartnerIn, run_id: int | None = Query(None, alias="runId")):
    """Field checks (required fields, postal code, VAT ID, IBAN) plus duplicate search and IBAN
    owners against the extracts of the latest run, or of runId."""
    rid = run_id or store.latest_run_id()
    folder = store.extract_dir(rid) if rid else None
    return {"runId": rid, **partner_check.check(body.model_dump(), folder)}


@router.get("/vendors/{vendorId}", tags=["partners"], summary="Current master record and bank details of one vendor")
def get_vendor(store: StoreDep, vendor_id: Annotated[str, Path(alias="vendorId", max_length=10)],
               run_id: int | None = Query(None, alias="runId")):
    """Read from the extracts of the latest run, or of runId. An onboarding workflow uses this
    to compare a requested bank change with what is on file, including the phone number to call back."""
    rid = run_id or store.latest_run_id()
    if not rid:
        raise NotFound("no run yet, upload extracts first")
    record = partner_check.vendor(str(store.extract_dir(rid)), vendor_id)
    if record is None:
        raise NotFound(f"vendor {vendor_id} not found in run {rid}")
    return {"runId": rid, **record}
