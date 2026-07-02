"""
Model Audit router — LLM fingerprint probing and identity verification endpoints.

POST /model-audit/probe      — Run fingerprint probe against a model
POST /model-audit/report     — Generate full model identity audit report
POST /model-audit/compare    — Compare two model fingerprints
GET  /model-audit/signatures — List known model signatures
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter

router = APIRouter(prefix="/model-audit", tags=["model-audit"])


@router.post("/probe", response_model=Dict[str, Any])
async def probe_model(body: Dict[str, Any]):
    """Run fingerprint probe against a target model."""
    model_name = body.get("model_name", "")
    if not model_name:
        return {"error": "model_name is required"}

    try:
        from core.harness.knowledge.model_fingerprint import get_fingerprint_collector
        collector = get_fingerprint_collector()
        fp = await collector.probe(model_name, timeout_s=body.get("timeout_s", 30.0))
        return fp.to_dict()
    except Exception as e:
        return {"error": str(e), "model_name": model_name}


@router.post("/report", response_model=Dict[str, Any])
async def generate_report(body: Dict[str, Any]):
    """Generate a full model identity audit report."""
    model_name = body.get("model_name", "")
    if not model_name:
        return {"error": "model_name is required"}

    try:
        from core.harness.knowledge.model_audit import generate_audit_report
        report = await generate_audit_report(model_name)
        return report.to_dict()
    except Exception as e:
        return {"error": str(e), "model_name": model_name}


@router.post("/compare", response_model=Dict[str, Any])
async def compare_models(body: Dict[str, Any]):
    """Compare two model fingerprints to detect cloning or derivation."""
    model_a = body.get("model_a", "")
    model_b = body.get("model_b", "")
    if not model_a or not model_b:
        return {"error": "model_a and model_b are required"}

    try:
        from core.harness.knowledge.model_fingerprint import get_fingerprint_collector
        from core.harness.knowledge.model_audit import compare_fingerprints

        collector = get_fingerprint_collector()
        fp_a = await collector.probe(model_a, timeout_s=body.get("timeout_s", 30.0))
        fp_b = await collector.probe(model_b, timeout_s=body.get("timeout_s", 30.0))

        result = compare_fingerprints(fp_a, fp_b)
        return result.to_dict()
    except Exception as e:
        return {"error": str(e), "model_a": model_a, "model_b": model_b}


@router.get("/signatures", response_model=Dict[str, Any])
async def list_signatures():
    """List known model signature profiles."""
    from core.harness.knowledge.model_audit import KNOWN_SIGNATURES
    return {"signatures": KNOWN_SIGNATURES, "count": len(KNOWN_SIGNATURES)}
