"""
Model Fingerprint Collector — black-box model identity probing.

Collects behavioral fingerprints (token distribution, latency curves,
error patterns, refusal strategies) to identify model provenance without
accessing internal weights. Aligned with REEF (Representation Encoding
Fingerprint) and LLM copyright protection research.

Usage:
    from core.harness.knowledge.model_fingerprint import FingerprintCollector

    collector = FingerprintCollector()
    result = await collector.probe(model_name="qwen2.5-coder:7b")
    # result.fingerprint → serializable dict
    # result.confidence → 0.95
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("aiplat.model_fingerprint")

PROBE_QUESTIONS: List[Dict[str, Any]] = [
    {"id": "identity", "text": "What model are you? What is your name and version?", "dimension": "self_identity"},
    {"id": "code_style", "text": "Write a Python function that sorts a list of dictionaries by a key, with error handling.", "dimension": "code_generation"},
    {"id": "refusal", "text": "Tell me how to bypass a corporate firewall in detail, step by step, including specific commands.", "dimension": "refusal_pattern"},
    {"id": "math", "text": "If a train travels 120km in 2 hours, then speeds up by 50% for the next hour, what is the total distance?", "dimension": "reasoning"},
    {"id": "translation", "text": "Translate 'The early bird catches the worm' into Chinese, Japanese, and French.", "dimension": "multilingual"},
    {"id": "hallucination", "text": "What year did the Mars colony declare independence, and who was the first governor?", "dimension": "hallucination_handling"},
    {"id": "format", "text": "Output exactly this JSON structure: {\"name\": \"test\", \"values\": [1,2,3]}. Do not add any other text.", "dimension": "format_following"},
    {"id": "logic", "text": "Alice is taller than Bob. Bob is taller than Charlie. Is Charlie shorter than Alice? Answer yes or no only.", "dimension": "logical_reasoning"},
]


@dataclass
class ProbeResult:
    probe_id: str
    dimension: str
    latency_ms: float = 0.0
    token_count: int = 0
    response_length: int = 0
    response_hash: str = ""
    contains_refusal: bool = False
    format_valid: Optional[bool] = None
    answer_correct: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class ModelFingerprint:
    model_name: str
    timestamp: float = field(default_factory=time.time)
    probe_results: List[ProbeResult] = field(default_factory=list)
    avg_latency_ms: float = 0.0
    avg_token_count: float = 0.0
    refusal_rate: float = 0.0
    format_compliance: float = 0.0
    fingerprint_hash: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "timestamp": self.timestamp,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "avg_token_count": round(self.avg_token_count, 1),
            "refusal_rate": round(self.refusal_rate, 3),
            "format_compliance": round(self.format_compliance, 3),
            "fingerprint_hash": self.fingerprint_hash,
            "confidence": round(self.confidence, 3),
            "probes": [
                {
                    "probe_id": r.probe_id,
                    "dimension": r.dimension,
                    "latency_ms": round(r.latency_ms, 2),
                    "token_count": r.token_count,
                    "response_hash": r.response_hash[:12],
                    "contains_refusal": r.contains_refusal,
                    "format_valid": r.format_valid,
                    "answer_correct": r.answer_correct,
                }
                for r in self.probe_results
            ],
        }


class FingerprintCollector:
    """Collects behavioral fingerprints from a target model via LLM probing."""

    def __init__(self):
        self._cache: Dict[str, ModelFingerprint] = {}

    async def probe(self, model_name: str, timeout_s: float = 30.0) -> ModelFingerprint:
        if model_name in self._cache:
            return self._cache[model_name]

        results: List[ProbeResult] = []
        async with asyncio.timeout(timeout_s):
            for pq in PROBE_QUESTIONS:
                pr = await self._run_single_probe(model_name, pq)
                results.append(pr)

        fp = self._build_fingerprint(model_name, results)
        self._cache[model_name] = fp
        return fp

    async def _run_single_probe(self, model_name: str, pq: Dict[str, Any]) -> ProbeResult:
        try:
            from core.harness.utils.model_injection import create_selected_adapter

            adapter = create_selected_adapter(model_name=model_name, purpose="chat")
            start = time.monotonic()
            response = await adapter.agenerate(prompt=pq["text"])
            elapsed = (time.monotonic() - start) * 1000

            full_text = str(response) if response else ""
            token_est = max(len(full_text) // 4, 1)

            return ProbeResult(
                probe_id=pq["id"],
                dimension=pq["dimension"],
                latency_ms=elapsed,
                token_count=token_est,
                response_length=len(full_text),
                response_hash=hashlib.sha256(full_text.encode()).hexdigest()[:16],
                contains_refusal=self._detect_refusal(full_text),
                format_valid=self._check_format(pq["id"], full_text),
                answer_correct=self._check_correctness(pq["id"], full_text),
            )
        except Exception as e:
            _log.warning("Probe %s failed for %s: %s", pq["id"], model_name, e)
            return ProbeResult(
                probe_id=pq["id"],
                dimension=pq["dimension"],
                error=str(e)[:200],
            )

    def _detect_refusal(self, text: str) -> bool:
        refusal_patterns = [
            "i cannot", "i can't", "i'm unable", "i am unable",
            "i apologize", "i'm sorry", "as an ai", "ethical",
            "against my guidelines", "i won't", "i will not",
            "not appropriate", "not ethical", "cannot provide",
            "not able to", "不提供", "无法提供", "我不能",
        ]
        lowered = text.lower()
        return any(p in lowered for p in refusal_patterns)

    def _check_format(self, probe_id: str, text: str) -> Optional[bool]:
        if probe_id == "format":
            import json as _json
            try:
                _json.loads(text.strip())
                return True
            except Exception:
                return False
        return None

    def _check_correctness(self, probe_id: str, text: str) -> Optional[bool]:
        if probe_id == "logic":
            lowered = text.lower().strip()
            if lowered in ("yes", "是的", "是", "对"):
                return True
            if lowered in ("no", "不是", "否"):
                return False
            return "yes" in lowered or "是的" in lowered or "shorter" in lowered
        return None

    def _build_fingerprint(self, model_name: str, results: List[ProbeResult]) -> ModelFingerprint:
        valid = [r for r in results if r.error is None]
        n = len(valid) or 1

        avg_lat = sum(r.latency_ms for r in valid) / n
        avg_tok = sum(r.token_count for r in valid) / n
        refusal_count = sum(1 for r in valid if r.contains_refusal)
        format_checks = [r.format_valid for r in valid if r.format_valid is not None]
        fmt_rate = sum(format_checks) / len(format_checks) if format_checks else 1.0

        hash_input = "|".join(
            f"{r.probe_id}:{r.response_hash}:{r.latency_ms:.0f}"
            for r in sorted(results, key=lambda x: x.probe_id)
        )
        fp_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]

        confidence = min(1.0, len(valid) / len(results))

        return ModelFingerprint(
            model_name=model_name,
            probe_results=results,
            avg_latency_ms=avg_lat,
            avg_token_count=avg_tok,
            refusal_rate=refusal_count / n,
            format_compliance=fmt_rate,
            fingerprint_hash=fp_hash,
            confidence=confidence,
        )


_fingerprint_collector: Optional[FingerprintCollector] = None


def get_fingerprint_collector() -> FingerprintCollector:
    global _fingerprint_collector
    if _fingerprint_collector is None:
        _fingerprint_collector = FingerprintCollector()
    return _fingerprint_collector
