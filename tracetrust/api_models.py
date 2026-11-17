"""Stable HTTP response contracts for the versioned TraceTrust API."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .models import EvidenceRef, Finding, ReconciliationMatch, TrustAssessment


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)
    has_more: bool


class SnapshotSummaryResponse(BaseModel):
    snapshot_id: str
    source_system: str
    event_count: int
    lot_count: int
    finding_count: int
    average_trust_score: float | None


class LotSummaryResponse(BaseModel):
    lot_id: str
    event_count: int
    finding_count: int
    trust_score: float | None


class GraphNodeResponse(BaseModel):
    id: str
    node_type: str
    label: str
    properties: dict[str, Any]


class GraphEdgeResponse(BaseModel):
    source: str
    target: str
    relation: str
    properties: dict[str, Any]


class GraphResponse(BaseModel):
    snapshot_id: str
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]


class TraversalResponse(BaseModel):
    query: str
    direction: str
    nodes: list[GraphNodeResponse]
    distances: dict[str, int]


class LineageResponse(BaseModel):
    ancestors: TraversalResponse | None = None
    descendants: TraversalResponse | None = None


class FindingResponse(Finding):
    pass


class RelationResponse(ReconciliationMatch):
    pass


class EvidenceResponse(EvidenceRef):
    pass


class TrustResponse(TrustAssessment):
    pass
