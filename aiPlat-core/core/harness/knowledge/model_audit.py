"""
Model Audit — identity report generation and fingerprint comparison.

Generates structured model identity reports for enterprise procurement
due diligence, platform clone detection, and IP provenance verification.

Usage:
    from core.harness.knowledge.model_audit import generate_audit_report, compare_fingerprints

    report = await generate_audit_report(model_name="qwen2.5-coder:7b")
    # report.identity.confidence → 0.95
    # report.recommendations → ["Matches Qwen lineage", ...]

    diff = compare_fingerprints(fp_a, fp_b)
    # diff.similarity → 0.92  (likely same model or derivative)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.harness.knowledge.model_fingerprint import (
    FingerprintCollector,
    ModelFingerprint,
    get_fingerprint_collector,
)

KNOWN_SIGNATURES: Dict[str, Dict[str, Any]] = {
    "qwen2.5-coder:7b": {
        "family": "Qwen",
        "variant": "Coder",
        "size": "7B",
        "typical_latency_ms": (200, 800),
        "typical_refusal_rate": (0.05, 0.15),
        "format_compliance": (0.90, 1.0),
    },
    "qwen2.5-coder:14b": {
        "family": "Qwen",
        "variant": "Coder",
        "size": "14B",
        "typical_latency_ms": (400, 1500),
        "typical_refusal_rate": (0.05, 0.15),
        "format_compliance": (0.90, 1.0),
    },
    "deepseek-v4-pro": {
        "family": "DeepSeek",
        "variant": "Pro",
        "size": "~236B",
        "typical_latency_ms": (500, 3000),
        "typical_refusal_rate": (0.02, 0.10),
        "format_compliance": (0.95, 1.0),
    },
}


@dataclass
class ModelIdentity:
    model_name: str
    detected_family: str = "unknown"
    detected_variant: str = "unknown"
    estimated_size: str = "unknown"
    fingerprint_hash: str = ""
    confidence: float = 0.0
    match_reasons: List[str] = field(default_factory=list)


@dataclass
class AuditReport:
    identity: ModelIdentity
    fingerprint: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    generated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": {
                "model_name": self.identity.model_name,
                "detected_family": self.identity.detected_family,
                "detected_variant": self.identity.detected_variant,
                "estimated_size": self.identity.estimated_size,
                "fingerprint_hash": self.identity.fingerprint_hash,
                "confidence": round(self.identity.confidence, 3),
                "match_reasons": self.identity.match_reasons,
            },
            "fingerprint": self.fingerprint,
            "recommendations": self.recommendations,
            "risk_flags": self.risk_flags,
            "generated_at": self.generated_at,
        }


@dataclass
class ComparisonResult:
    model_a: str
    model_b: str
    similarity: float
    likely_relationship: str
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "similarity": round(self.similarity, 3),
            "likely_relationship": self.likely_relationship,
            "dimension_scores": {k: round(v, 3) for k, v in self.dimension_scores.items()},
            "details": self.details,
        }


async def generate_audit_report(model_name: str) -> AuditReport:
    import time as _time
    collector = get_fingerprint_collector()
    fp = await collector.probe(model_name)

    identity = _identify_model(model_name, fp)
    recommendations, risk_flags = _assess(fp, identity)

    return AuditReport(
        identity=identity,
        fingerprint=fp.to_dict(),
        recommendations=recommendations,
        risk_flags=risk_flags,
        generated_at=_time.time(),
    )


def compare_fingerprints(fp_a: ModelFingerprint, fp_b: ModelFingerprint) -> ComparisonResult:
    dim_scores: Dict[str, float] = {}
    details: List[str] = []

    lat_a = fp_a.avg_latency_ms
    lat_b = fp_b.avg_latency_ms
    if max(lat_a, lat_b) > 0:
        lat_sim = 1.0 - abs(lat_a - lat_b) / max(lat_a, lat_b)
        dim_scores["latency_profile"] = lat_sim
        if lat_sim < 0.6:
            details.append(f"Latency divergence: {lat_a:.0f}ms vs {lat_b:.0f}ms")

    token_sim = 1.0 - abs(fp_a.avg_token_count - fp_b.avg_token_count) / max(fp_a.avg_token_count, fp_b.avg_token_count, 1)
    dim_scores["token_output"] = token_sim

    refusal_diff = abs(fp_a.refusal_rate - fp_b.refusal_rate)
    dim_scores["refusal_alignment"] = 1.0 - refusal_diff
    if refusal_diff > 0.3:
        details.append(f"Refusal rate divergence: {fp_a.refusal_rate:.2f} vs {fp_b.refusal_rate:.2f}")

    dim_scores["format_compliance"] = 1.0 - abs(fp_a.format_compliance - fp_b.format_compliance)

    hash_overlap = _response_hash_overlap(fp_a, fp_b)
    dim_scores["response_similarity"] = hash_overlap
    if hash_overlap > 0.4:
        details.append(f"High response overlap ({hash_overlap:.0%}) — likely same model or derivative")

    scores = list(dim_scores.values())
    similarity = sum(scores) / len(scores) if scores else 0.0

    if similarity > 0.85:
        relationship = "likely_same_model_or_derivative"
    elif similarity > 0.65:
        relationship = "likely_same_family"
    elif similarity > 0.40:
        relationship = "possibly_related"
    else:
        relationship = "likely_different_models"

    return ComparisonResult(
        model_a=fp_a.model_name,
        model_b=fp_b.model_name,
        similarity=similarity,
        likely_relationship=relationship,
        dimension_scores=dim_scores,
        details=details,
    )


def _identify_model(model_name: str, fp: ModelFingerprint) -> ModelIdentity:
    identity = ModelIdentity(
        model_name=model_name,
        fingerprint_hash=fp.fingerprint_hash,
        confidence=fp.confidence,
    )

    best_match = None
    best_score = 0.0
    for sig_name, sig in KNOWN_SIGNATURES.items():
        score = 0.0
        reasons = []
        lo, hi = sig["typical_latency_ms"]
        if lo <= fp.avg_latency_ms <= hi:
            score += 0.3
            reasons.append("latency_in_range")
        lo, hi = sig["typical_refusal_rate"]
        if lo <= fp.refusal_rate <= hi:
            score += 0.25
            reasons.append("refusal_rate_in_range")
        lo, hi = sig["format_compliance"]
        if lo <= fp.format_compliance <= hi:
            score += 0.25
            reasons.append("format_compliance_in_range")
        if model_name.lower() in sig_name.lower() or sig_name.lower() in model_name.lower():
            score += 0.2
            reasons.append("name_partial_match")
        if score > best_score:
            best_score = score
            best_match = (sig, reasons, score)

    if best_match and best_score >= 0.5:
        sig, reasons, _score = best_match
        identity.detected_family = sig["family"]
        identity.detected_variant = sig["variant"]
        identity.estimated_size = sig["size"]
        identity.match_reasons = reasons

    return identity


def _assess(fp: ModelFingerprint, identity: ModelIdentity) -> tuple:
    recommendations = []
    risk_flags = []

    if identity.detected_family != "unknown":
        recommendations.append(f"Identified as {identity.detected_family} {identity.detected_variant} ({identity.estimated_size})")
    else:
        recommendations.append("Model family not recognized — manual audit recommended")
        risk_flags.append("unknown_model_family")

    if fp.confidence < 0.8:
        risk_flags.append("low_probe_completion")
        recommendations.append("Some probes failed — re-run with higher timeout")

    if fp.refusal_rate < 0.01:
        recommendations.append("Very low refusal rate — verify safety guardrails independently")
    elif fp.refusal_rate > 0.5:
        risk_flags.append("high_refusal_rate")
        recommendations.append("High refusal rate may indicate aggressive content filtering")

    if fp.format_compliance < 0.5:
        risk_flags.append("poor_format_following")
        recommendations.append("Low format compliance — may not be suitable for structured data extraction")

    return recommendations, risk_flags


def _response_hash_overlap(fp_a: ModelFingerprint, fp_b: ModelFingerprint) -> float:
    hashes_a = {r.probe_id: r.response_hash for r in fp_a.probe_results if r.response_hash}
    hashes_b = {r.probe_id: r.response_hash for r in fp_b.probe_results if r.response_hash}
    common = set(hashes_a.keys()) & set(hashes_b.keys())
    if not common:
        return 0.0
    matches = sum(1 for k in common if hashes_a[k] == hashes_b[k])
    return matches / len(common)
