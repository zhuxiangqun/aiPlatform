"""Five-products first-slice API — Bundle export + Evidence MVP (Gate1 WP3/WP4)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.fde.api.schemas import FdeItemResponse

router = APIRouter(tags=["fde-slice"], prefix="/slice")


class SliceBundleExportRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1)
    app_home: str = Field(..., min_length=1)
    out_dir: Optional[str] = None
    runtime_mode: str = "thin"


class SliceEvidenceIngestRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1)
    run_id: str = ""
    bundle_version: str = ""
    runtime_version: str = ""
    events: List[Dict[str, Any]] = Field(default_factory=list)
    asset_versions: Dict[str, Any] = Field(default_factory=dict)
    aiplat_reachable: bool = True


class SliceEvidenceReportRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1)
    ingest_id: str = ""
    run_id: str = ""
    bundle_version: str = ""
    runtime_version: str = ""
    events: Optional[List[Dict[str, Any]]] = None
    asset_versions: Optional[Dict[str, Any]] = None
    aiplat_reachable: bool = True


@router.post("/bundle/export", response_model=FdeItemResponse)
async def slice_bundle_export(body: SliceBundleExportRequest):
    from core.api.core_facade import export_slice_bundle

    result = export_slice_bundle(
        scenario_id=body.scenario_id,
        app_home=body.app_home,
        out_dir=body.out_dir,
        runtime_mode=body.runtime_mode,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return FdeItemResponse(data=result)


@router.post("/evidence/ingest", response_model=FdeItemResponse)
async def slice_evidence_ingest(body: SliceEvidenceIngestRequest):
    from core.api.core_facade import ingest_slice_evidence

    result = ingest_slice_evidence(
        scenario_id=body.scenario_id,
        run_id=body.run_id,
        bundle_version=body.bundle_version,
        runtime_version=body.runtime_version,
        events=body.events,
        asset_versions=body.asset_versions,
        aiplat_reachable=body.aiplat_reachable,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return FdeItemResponse(data=result)


@router.post("/evidence/report", response_model=FdeItemResponse)
async def slice_evidence_report(body: SliceEvidenceReportRequest):
    from core.api.core_facade import build_slice_diagnosis_report

    result = build_slice_diagnosis_report(
        scenario_id=body.scenario_id,
        ingest_id=body.ingest_id,
        run_id=body.run_id,
        bundle_version=body.bundle_version,
        runtime_version=body.runtime_version,
        events=body.events,
        asset_versions=body.asset_versions,
        aiplat_reachable=body.aiplat_reachable,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return FdeItemResponse(data=result)


@router.get("/evidence/report/{report_id}", response_model=FdeItemResponse)
async def slice_evidence_get_report(report_id: str):
    from core.api.core_facade import get_slice_diagnosis_report

    result = get_slice_diagnosis_report(report_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    return FdeItemResponse(data=result)


class SliceOfflineEvalRequest(BaseModel):
    last_bundle_validated_at: str = Field(..., min_length=1)
    now: Optional[str] = None
    requested_ops: List[str] = Field(default_factory=list)
    has_revocation_channel: bool = False


@router.post("/offline/evaluate", response_model=FdeItemResponse)
async def slice_offline_evaluate(body: SliceOfflineEvalRequest):
    from core.api.core_facade import evaluate_slice_offline_policy

    result = evaluate_slice_offline_policy(
        last_bundle_validated_at=body.last_bundle_validated_at,
        now=body.now,
        requested_ops=body.requested_ops,
        has_revocation_channel=body.has_revocation_channel,
    )
    return FdeItemResponse(data=result)
