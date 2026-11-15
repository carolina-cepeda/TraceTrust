"""Auditable domain contracts for the TraceTrust MVP."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventType(StrEnum):
    PRODUCTION = "production"
    TRANSFER = "transfer"
    RECEIPT = "receipt"
    TRANSFORMATION = "transformation"
    SPLIT = "split"
    MERGE = "merge"


class RelationKind(StrEnum):
    RECORDED = "RECORDED"
    DERIVED = "DERIVED"
    INFERRED = "INFERRED"


class MatchStatus(StrEnum):
    MATCH = "match"
    REVIEW = "review"
    NON_MATCH = "non_match"


class FindingSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)


class EvidenceRef(SourceRef):
    evidence_type: str = Field(min_length=1)


class CanonicalTraceabilityEvent(BaseModel):
    """Normalized event retaining normalized and original source values."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    event_type: EventType
    timestamp: datetime
    original_timestamp: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    input_lots: list[str] = Field(default_factory=list)
    output_lots: list[str] = Field(default_factory=list)
    quantity: float = Field(ge=0)
    original_quantity: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    location: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    raw_payload: dict[str, Any]

    @field_validator("input_lots", "output_lots")
    @classmethod
    def unique_lots(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("lot references must be unique within an event")
        return value


class SourceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_engine: str = Field(min_length=1)
    migration_ids: list[str] = Field(min_length=1)


class AnonymizationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str = Field(min_length=1)
    names_removed: bool = True
    phones_removed: bool = True
    actor_ids_pseudonymized: bool = True
    precise_locations_removed: bool = True
    media_refs_removed: bool = True

    @field_validator(
        "names_removed",
        "phones_removed",
        "actor_ids_pseudonymized",
        "precise_locations_removed",
        "media_refs_removed",
    )
    @classmethod
    def must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("TraceTrust exports require strict anonymization flags")
        return value


class SnapshotFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    format: str
    row_count: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    min_server_seq: int | None = Field(default=None, ge=0)
    max_server_seq: int | None = Field(default=None, ge=0)

    @field_validator("format")
    @classmethod
    def supported_format(cls, value: str) -> str:
        if value not in {"jsonl", "csv"}:
            raise ValueError("format must be jsonl or csv")
        return value


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    extracted_at: datetime
    schema_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    source_schema: SourceSchema
    exporter_version: str = Field(min_length=1)
    anonymization: AnonymizationPolicy
    files: list[SnapshotFile]


class MatchComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    weight: float = Field(ge=0, le=1)
    similarity: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=1)
    explanation: str = Field(min_length=1)


class ReconciliationMatch(BaseModel):
    """Auditable comparison between two source records."""

    model_config = ConfigDict(extra="forbid")

    match_id: str = Field(min_length=1)
    left_event_id: str = Field(min_length=1)
    right_event_id: str = Field(min_length=1)
    left_snapshot_id: str = Field(min_length=1)
    right_snapshot_id: str = Field(min_length=1)
    status: MatchStatus
    relation_kind: RelationKind
    score: float = Field(ge=0, le=1)
    components: list[MatchComponent] = Field(min_length=1)
    candidate_reasons: list[str] = Field(min_length=1)
    algorithm_version: str = Field(min_length=1)


class Finding(BaseModel):
    """A deterministic, reproducible analytical finding."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    severity: FindingSeverity
    snapshot_id: str = Field(min_length=1)
    entity_ids: list[str] = Field(min_length=1)
    source_event_ids: list[str] = Field(min_length=1)
    values: dict[str, Any]
    explanation: str = Field(min_length=1)
    algorithm_version: str = Field(min_length=1)
