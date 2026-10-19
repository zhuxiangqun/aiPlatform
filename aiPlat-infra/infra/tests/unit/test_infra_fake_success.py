"""Infra must not report failure, fiction, or unprobed state as success."""

import asyncio

import pytest

from infra.llm.providers.openai_compatible import OpenAICompatibleClient
from infra.management.api.auth import InfraTokenMiddleware, is_loopback_host, tokens_match
from infra.management.llm.manager import LLMManager
from infra.management.model.health_checker import HealthChecker
from infra.management.scheduler.manager import get_real_gpu_info
from infra.management.vector.manager import VectorManager
from infra.memory.manager import VRAMMemoryManager
from infra.memory.schemas import MemoryConfig, MemoryRequest


def test_loopback_and_token_compare():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("0.0.0.0")
    assert tokens_match("secret", "secret")
    assert not tokens_match("secret", "nope")
    assert not tokens_match("secret", None)


def test_token_middleware_blocks_non_health(monkeypatch):
    monkeypatch.setenv("AIPLAT_INFRA_API_TOKEN", "secret")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(InfraTokenMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/")
    def root():
        return {"name": "infra"}

    @app.get("/api/infra/nodes")
    def nodes():
        return {"nodes": []}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 401
    assert client.get("/api/infra/nodes").status_code == 401
    ok = client.get("/api/infra/nodes", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200


def test_llm_metrics_are_synthetic_zeros():
    metrics = asyncio.run(LLMManager({}).get_metrics())
    assert metrics
    assert all(item.labels.get("synthetic") == "true" for item in metrics)
    assert all(item.value == 0 for item in metrics)


def test_rotatable_error_does_not_fail_open():
    assert OpenAICompatibleClient._is_rotatable_error(ValueError("boom")) is False
    assert OpenAICompatibleClient._is_rotatable_error(TimeoutError()) is True


def test_vector_search_uses_cosine_not_placeholder():
    mgr = VectorManager({})

    async def run():
        await mgr.create_collection("c")
        await mgr.insert_vectors(
            "c",
            [
                {"vector": [0.0, 1.0], "metadata": {}},
                {"vector": [1.0, 0.0], "metadata": {}},
            ],
            ids=["far", "near"],
        )
        return await mgr.search_vectors("c", [1.0, 0.0], top_k=2)

    hits = asyncio.run(run())
    assert hits[0]["id"] == "near"
    assert hits[0]["score"] == pytest.approx(1.0)
    assert all(hit["score"] != 0.95 for hit in hits)


def test_gpu_allocate_fails_without_nvml(monkeypatch):
    monkeypatch.delenv("AIPLAT_MEMORY_SIMULATE", raising=False)
    mgr = VRAMMemoryManager(MemoryConfig())
    mgr._initialized = False
    with pytest.raises(MemoryError):
        mgr.allocate(MemoryRequest(size=128))


def test_gpu_detect_failure_reports_zero(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("no profiler")

    monkeypatch.setattr("subprocess.run", boom)
    info = get_real_gpu_info()
    assert info["total_gpus"] == 0
    assert info["available_gpus"] == 0


def test_clarify_keywords_not_hardcoded_fde(monkeypatch):
    from infra.management.model.quality_validator import QualityValidator

    monkeypatch.delenv("AIPLAT_CLARIFY_KEYWORDS", raising=False)
    # Without env keywords, domain words like fde alone must not boost.
    text = "这是关于 fde 客户流程需求的一段超过五十字的说明文字用来触发叙事分支。" * 2
    result = QualityValidator.validate("clarify", text)
    assert result.details.get("keyword_hits", 0) == 0
    assert "keyword_hits" not in result.details or result.details.get("keyword_hits") == 0


def test_mineru_word_in_stderr_is_not_healthy(monkeypatch):
    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "mineru: command not found"

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: _Proc())

    class _Model:
        id = "mineru"

    checker = HealthChecker.__new__(HealthChecker)
    result = checker._check_mineru_connectivity(_Model())
    assert result["success"] is False
