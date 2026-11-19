"""Versioned HTTP routes for TraceTrust."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .application import AnalysisService
from .integration import TrackupBatchRequest, TrackupBatchResult, ingest_trackup_batch
from .api_models import (
    EvidenceResponse,
    GraphResponse,
    FindingResponse,
    LineageResponse,
    LotSummaryResponse,
    Page,
    RelationResponse,
    SnapshotSummaryResponse,
    TraversalResponse,
    TrustResponse,
)


def _page(items: list, limit: int, offset: int) -> dict:
    total = len(items)
    return {"items": items[offset:offset + limit], "limit": limit, "offset": offset,
            "total": total, "has_more": offset + limit < total}


def build_v1_router(service: AnalysisService, ingestion_root: str | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["v1"])

    @router.post("/ingest/trackup", response_model=TrackupBatchResult, status_code=202)
    def ingest_trackup(request: TrackupBatchRequest):
        if ingestion_root is None:
            raise HTTPException(status_code=503, detail="Trackup ingestion is not configured")
        try:
            return ingest_trackup_batch(ingestion_root, request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/snapshots", response_model=Page[SnapshotSummaryResponse])
    def snapshots(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        return _page(service.snapshots(), limit, offset)

    @router.get("/snapshots/{snapshot_id}", response_model=SnapshotSummaryResponse)
    def snapshot(snapshot_id: str):
        try:
            return service.snapshot_summary(snapshot_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/snapshots/{snapshot_id}/lots", response_model=Page[LotSummaryResponse])
    def lots(snapshot_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        try:
            return _page(service.lots(snapshot_id), limit, offset)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/lots/{snapshot_id}/{lot_id}/lineage", response_model=LineageResponse)
    def lineage(snapshot_id: str, lot_id: str, direction: str = Query("both"), depth: int = Query(20, ge=1, le=100)):
        if direction not in {"ancestors", "descendants", "both"}:
            raise HTTPException(status_code=400, detail="direction must be ancestors, descendants or both")
        try:
            result = service.lineage(snapshot_id, lot_id, direction, depth)
            if direction == "ancestors":
                return {"ancestors": result, "descendants": None}
            if direction == "descendants":
                return {"ancestors": None, "descendants": result}
            return result
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/snapshots/{snapshot_id}/graph", response_model=GraphResponse)
    def graph(snapshot_id: str):
        try:
            return service.graph(snapshot_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/findings/{snapshot_id}", response_model=Page[FindingResponse])
    def findings(snapshot_id: str, severity: str | None = None,
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        try:
            return _page(service.findings(snapshot_id, severity), limit, offset)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/anomalies/{snapshot_id}", response_model=Page[FindingResponse])
    def anomalies(snapshot_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        try:
            return _page(service.anomalies(snapshot_id), limit, offset)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/trust/{snapshot_id}/{lot_id}", response_model=TrustResponse)
    def trust(snapshot_id: str, lot_id: str):
        try:
            return service.trust(snapshot_id, lot_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/relations/{match_id}", response_model=RelationResponse)
    def relation(match_id: str):
        try:
            return service.relation(match_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/events/{snapshot_id}/{event_id}/evidence", response_model=Page[EvidenceResponse])
    def evidence(snapshot_id: str, event_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        try:
            return _page(service.evidence(snapshot_id, event_id), limit, offset)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
