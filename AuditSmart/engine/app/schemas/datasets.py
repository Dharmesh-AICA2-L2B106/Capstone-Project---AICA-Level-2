from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class UploadStart(Strict):
    engagement_id: str
    file_name: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    kind: Literal["GL", "TB"] = "GL"


# D56: values are checked by the engine (importer.normalise_override) so a wrong type gets a
# plain-English 422 naming the field instead of a schema error list.
MAPPING_DOC = ("{field: column header}. Field names, labels or synonyms are accepted "
               "('posting_date', 'Posting Date', 'date'); {column header: field} also works. "
               "\"\" or null leaves a field unmapped. Unknown names are refused with 422.")


class UploadComplete(Strict):
    mapping_override: dict[str, Any] | None = Field(default=None, description=MAPPING_DOC)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


class MappingUpdate(Strict):
    mapping_override: dict[str, Any] = Field(description=MAPPING_DOC)


class ValidateRequest(Strict):
    tb_dataset_id: str | None = None


class UploadSession(BaseModel):
    dataset_id: str
    chunk_size_bytes: int
    max_upload_bytes: int
    status: str


class ChunkAck(BaseModel):
    dataset_id: str
    index: int
    chunks_received: int


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    engagement_id: str
    file_name: str
    kind: str
    status: str
    sha256: str | None
    size_bytes: int | None
    rows: int | None
    total_dr: str | None
    total_cr: str | None
    mapping: dict[str, Any] | None
    profile: dict[str, Any] | None
    created_at: datetime | None


class DatasetAccepted(BaseModel):
    dataset_id: str
    job_id: str
    sha256: str | None
    mapping_suggestion: dict[str, Any] | None
    profile: dict[str, Any] | None
    status: str


class ValidationIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    severity: str
    field: str | None
    rows: list[int]
    row_count: int
    message: str
    guidance: str


class ValidationResult(BaseModel):
    dataset_id: str
    status: str
    critical: int
    warnings: int
    blocked: bool
    row_note: str
    errors: list[ValidationIssueOut]


class JobAccepted(BaseModel):
    job_id: str
    dataset_id: str
    status: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    engagement_id: str | None = None
    status: str
    progress: int
    error: str | None
    result_ref: str | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None


class RowsPage(BaseModel):
    dataset_id: str
    total: int
    offset: int
    limit: int
    rows: list[dict[str, Any]]
