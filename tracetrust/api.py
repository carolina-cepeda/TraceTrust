"""FastAPI adapter for the TraceTrust analytical use cases."""

from __future__ import annotations

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .application import AnalysisService, FilesystemAnalysisRepository
from .storage import SQLiteAnalysisRepository
from .web import dashboard


def create_app(data_root: str | None = None, database: str | None = None) -> FastAPI:
    root = data_root or os.getenv("TRACETRUST_DATA_ROOT", "data/demo")
    repository = SQLiteAnalysisRepository(database) if database else FilesystemAnalysisRepository(root)
    service = AnalysisService(repository)
    app = FastAPI(title="TraceTrust API", version="0.1.0", description="Auditable traceability analytics")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home():
        return dashboard()

    @app.get("/snapshots/{snapshot_id}")
    def snapshot(snapshot_id: str):
        try:
            summary = service.snapshot_summary()
            if summary["snapshot_id"] != snapshot_id:
                raise ValueError(f"Unknown snapshot: {snapshot_id}")
            return summary
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/snapshots")
    def snapshots():
        try:
            return {"items": service.snapshots()}
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/lots/{snapshot_id}")
    def lots(snapshot_id: str):
        try:
            return {"items": service.lots(snapshot_id)}
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/lots/{snapshot_id}/{lot_id}/lineage")
    def lineage(snapshot_id: str, lot_id: str, direction: str = Query("both"), depth: int = Query(20, ge=1, le=100)):
        if direction not in {"ancestors", "descendants", "both"}:
            raise HTTPException(status_code=400, detail="direction must be ancestors, descendants or both")
        try:
            return service.lineage(snapshot_id, lot_id, direction, depth)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/findings/{snapshot_id}")
    def findings(snapshot_id: str, severity: str | None = None):
        try:
            return {"items": service.findings(snapshot_id, severity)}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/trust/{snapshot_id}/{lot_id}")
    def trust(snapshot_id: str, lot_id: str):
        try:
            return service.trust(snapshot_id, lot_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
