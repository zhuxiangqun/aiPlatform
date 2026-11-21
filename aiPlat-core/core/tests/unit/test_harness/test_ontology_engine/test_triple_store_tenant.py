"""TripleStore tenant 隔离（SECURITY V2 / N09 deepen）。

覆盖：显式 tenant 只见本租户+共享空串；跨租户行不可见；空 tenant 兼容全量扫描。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.harness.ontology_engine.triple_store import TripleStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    """临时 SQLite TripleStore。"""
    s = TripleStore(db_path=str(tmp_path / "triples.sqlite3"))
    yield s
    s._conn.close()


def test_explicit_tenant_hides_other_tenant(store):
    """t1 查询不可见 t2 三元组；可见本租户与共享。"""
    store.add("urn:a", "uses", "urn:shared-obj", tenant_id="")
    store.add("urn:a", "uses", "urn:t1-obj", tenant_id="t1")
    store.add("urn:a", "uses", "urn:t2-obj", tenant_id="t2")

    down = store.get_downstream("urn:a", depth=1, tenant_id="t1")
    objs = {e["object"] for e in down}
    assert "urn:shared-obj" in objs
    assert "urn:t1-obj" in objs
    assert "urn:t2-obj" not in objs


def test_empty_tenant_sees_all_legacy(store):
    """空 tenant_id 保持旧行为：全量扫描。"""
    store.add("urn:a", "uses", "urn:t1-obj", tenant_id="t1")
    store.add("urn:a", "uses", "urn:t2-obj", tenant_id="t2")
    down = store.get_downstream("urn:a", depth=1, tenant_id="")
    objs = {e["object"] for e in down}
    assert objs == {"urn:t1-obj", "urn:t2-obj"}


def test_upstream_tenant_filter(store):
    """上游 BFS 同样按租户过滤。"""
    store.add("urn:t1-subj", "depends_on", "urn:target", tenant_id="t1")
    store.add("urn:t2-subj", "depends_on", "urn:target", tenant_id="t2")
    up = store.get_upstream("urn:target", depth=1, tenant_id="t1")
    subjs = {e["subject"] for e in up}
    assert subjs == {"urn:t1-subj"}


def test_stats_and_predicate_scoped(store):
    """stats / get_by_predicate 显式 tenant 过滤。"""
    store.add("urn:a", "uses_skill", "urn:s1", tenant_id="t1")
    store.add("urn:a", "uses_skill", "urn:s2", tenant_id="t2")
    store.add("urn:a", "uses_tool", "urn:tool", tenant_id="")

    st = store.stats(tenant_id="t1")
    assert st["tenant_scoped"] is True
    assert st["total_triples"] == 2  # t1 + shared

    preds = store.get_by_predicate("uses_skill", tenant_id="t1")
    assert len(preds) == 1
    assert preds[0]["object"] == "urn:s1"


@pytest.mark.asyncio
async def test_sys_ontology_context_passes_tenant(tmp_path, monkeypatch):
    """URN syscall 把 tenant_id 传到 TripleStore。"""
    seen = {}

    class _Store:
        def get_downstream(self, urn, depth, *, tenant_id=""):
            seen["down"] = tenant_id
            return []

        def get_upstream(self, urn, depth, *, tenant_id=""):
            seen["up"] = tenant_id
            return []

    monkeypatch.setattr(
        "core.harness.ontology_engine.triple_store.get_triple_store",
        lambda: _Store(),
    )
    monkeypatch.delenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", raising=False)

    from core.harness.syscalls.ontology import sys_ontology_context

    out = await sys_ontology_context("urn:x", depth=1, tenant_id="t-pass")
    assert seen == {"down": "t-pass", "up": "t-pass"}
    assert out.get("certified") is False
