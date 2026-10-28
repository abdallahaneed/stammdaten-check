"""Request and response models for the API, and the camelCase helper."""
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["open", "accepted", "fixed", "false_positive"]


def camel(value):
    """snake_case keys from SQLite to camelCase for JSON, nested lists included."""
    def conv(k):
        head, *rest = k.split("_")
        return head + "".join(w.title() for w in rest)
    if isinstance(value, dict):
        return {conv(k) if isinstance(k, str) and "_" in k else k: camel(v) for k, v in value.items()}
    if isinstance(value, list):
        return [camel(v) for v in value]
    return value


# ---------- request and response models ----------

class FindingUpdate(BaseModel):
    status: Status | None = None
    owner: str | None = Field(None, max_length=80)
    comment: str | None = Field(None, max_length=1000)


class BulkUpdate(FindingUpdate):
    ids: list[int] = Field(..., min_length=1, max_length=500, description="finding ids, at most 500")


class PartnerIn(BaseModel):
    object: Literal["customer", "vendor"] = Field("vendor", description="search duplicates among customers or vendors")
    name: str = Field("", max_length=80, description="company name, NAME1")
    name2: str = Field("", max_length=80, description="second name line, NAME2")
    street: str = Field("", max_length=80, description="street and house number")
    postalCode: str = Field("", max_length=10)
    city: str = Field("", max_length=40)
    country: str = Field("", max_length=2, description="ISO country code, DE, AT ...")
    vatId: str = Field("", max_length=20, description="USt-IdNr, e.g. DE136695976")
    iban: str = Field("", max_length=40)
    existingId: str | None = Field(None, max_length=10,
                                   description="number of the partner being changed, so its own IBAN is not reported")

    model_config = {"json_schema_extra": {"examples": [{
        "object": "vendor", "name": "Weber Elektro GmbH", "street": "Ringstraße 40",
        "postalCode": "53113", "city": "Bonn", "country": "DE",
        "vatId": "DE136695976", "iban": "DE89370400440532013000"}]}}


class Problem(BaseModel):
    code: str
    field: str
    severity: str
    message: str


class DuplicateHit(BaseModel):
    object: str
    id: str
    name: str
    score: float
    reasons: list[str]


class PartnerCheckOut(BaseModel):
    runId: int | None
    ok: bool
    worstSeverity: str | None
    problems: list[Problem]
    duplicates: list[DuplicateHit]
    ibanOwners: list[dict]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    error: ErrorDetail


ERRORS = {
    401: {"model": ErrorBody, "description": "missing or wrong X-API-Key"},
    404: {"model": ErrorBody, "description": "run or finding does not exist"},
    422: {"model": ErrorBody, "description": "invalid input"},
}


class Pagination(BaseModel):
    offset: int
    limit: int
    total: int
    hasMore: bool


class FindingsPage(BaseModel):
    data: list[dict]
    pagination: Pagination
