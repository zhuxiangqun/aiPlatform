"""Unit tests for weekly KB health archive."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from delivery.kb_health_archive import (
    archive_filename,
    archive_kb_health_report,
    iso_week_tag,
    list_kb_health_archives,
    read_kb_health_archive,
)


def test_iso_week_and_filename():
    tag = iso_week_tag()
    assert "-W" in tag
    assert archive_filename(tag) == f"kb-health-{tag}.md"


def test_archive_write_skip_and_force(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_KB_HEALTH_REPORT_DIR", str(tmp_path))
    fake_report = {
        "ok": True,
        "health": {"score": 70, "band": "良好"},
        "suggestions": ["ok"],
    }
    with patch(
        "delivery.kb_health.build_kb_health_report", return_value=fake_report
    ), patch(
        "delivery.kb_health.render_kb_health_markdown",
        return_value="# 知识库健康分: 70/100\n",
    ):
        r1 = archive_kb_health_report(tenant_id="t1")
        assert r1["ok"] is True and r1["skipped"] is False
        path = Path(r1["path"])
        assert path.is_file()
        r2 = archive_kb_health_report(tenant_id="t1")
        assert r2["skipped"] is True
        r3 = archive_kb_health_report(tenant_id="t1", force=True)
        assert r3["skipped"] is False
        listed = list_kb_health_archives()
        assert listed["ok"] and len(listed["items"]) >= 1
        got = read_kb_health_archive(r1["week"])
        assert got["ok"] and "知识库健康分" in got["markdown"]
