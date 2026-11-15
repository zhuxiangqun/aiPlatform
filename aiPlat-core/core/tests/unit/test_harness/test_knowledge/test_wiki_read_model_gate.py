"""Wiki 读模型硬门：配置驱动的 collection 禁止人工直接写。"""
from __future__ import annotations

import pytest

from core.harness.knowledge.wiki_read_model import (
    REASON_WIKI_IS_READ_MODEL,
    WikiManualWriteDenied,
    assert_manual_wiki_write_allowed,
    is_wiki_read_model_collection,
    read_model_collections,
)

# 测试用试点名单（非 harness 默认；生产靠 AIPLAT_WIKI_READ_MODEL_COLLECTIONS）
_PILOT = "lock-kb,lock-service"


@pytest.fixture()
def pilot_collections(monkeypatch):
    monkeypatch.setenv("AIPLAT_WIKI_READ_MODEL_COLLECTIONS", _PILOT)
    monkeypatch.delenv("AIPLAT_WIKI_ALLOW_MANUAL_WRITE", raising=False)


def test_unconfigured_means_no_read_model(monkeypatch):
    monkeypatch.delenv("AIPLAT_WIKI_READ_MODEL_COLLECTIONS", raising=False)
    assert read_model_collections() == frozenset()
    assert not is_wiki_read_model_collection("lock-kb")
    assert_manual_wiki_write_allowed("lock-kb")  # no raise


def test_env_configures_read_model_collections(pilot_collections):
    cols = read_model_collections()
    assert "lock-service" in cols
    assert "lock-kb" in cols
    assert is_wiki_read_model_collection("lock-kb")
    assert not is_wiki_read_model_collection("default")


def test_manual_write_denied_when_configured(pilot_collections):
    with pytest.raises(WikiManualWriteDenied) as ei:
        assert_manual_wiki_write_allowed("lock-service")
    assert ei.value.reason == REASON_WIKI_IS_READ_MODEL


def test_manual_write_allowed_on_non_configured(pilot_collections):
    assert_manual_wiki_write_allowed("default")  # no raise


def test_break_glass_allows_manual_write(pilot_collections, monkeypatch):
    monkeypatch.setenv("AIPLAT_WIKI_ALLOW_MANUAL_WRITE", "1")
    assert_manual_wiki_write_allowed("lock-kb")  # no raise


def test_compiler_write_page_unaffected(tmp_path, monkeypatch, pilot_collections):
    """编译器直调 write_page 不经人工门，读模型 collection 仍可写。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    from core.harness.knowledge.wiki_engine import read_page, write_page

    path = write_page(
        "pilot-derived-page",
        "derived body from compiler",
        category="entities",
        summary="compiler write",
        status="draft",
        collection_id="lock-kb",
        skip_validation=True,
    )
    assert path
    page = read_page("pilot-derived-page", collection_id="lock-kb")
    assert page is not None
    assert "derived body" in (page.get("body") or "")
