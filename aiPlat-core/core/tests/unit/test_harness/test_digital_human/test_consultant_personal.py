from pathlib import Path

from core.harness.digital_human.consultant_personal import (
    load_personal_notes,
    looks_like_lasting_note,
    memory_path,
    remember_from_turn,
    remember_from_user,
    sanitize_tenant_id,
)


def test_skips_audit_and_questions(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    assert not looks_like_lasting_note("解读一下这个画面的审核结果")
    assert not looks_like_lasting_note("我在做什么 Skill？")
    assert not looks_like_lasting_note("我是想做一个视频分析应用")
    assert not looks_like_lasting_note("不对，应该是走工厂")
    assert looks_like_lasting_note("请叫我老王，回答尽量短")
    assert looks_like_lasting_note("我负责交付，以后都先给结论")
    assert remember_from_user("请记住我不是技术人员")
    notes = load_personal_notes()
    assert "关于你" in notes
    assert "我不是技术人员" in notes
    assert not remember_from_user("请记住我不是技术人员")


def test_style_pref_once(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    assert remember_from_turn("能不能把解读精简一点解释？")
    assert not remember_from_turn("太啰嗦了")
    text = (tmp_path / "memory" / "tenants" / "default" / "xiaozhu.md").read_text(
        encoding="utf-8"
    )
    assert text.count("回答先结论、尽量短") == 1


def test_sanitize_tenant_id():
    assert sanitize_tenant_id(None) == "default"
    assert sanitize_tenant_id("") == "default"
    assert sanitize_tenant_id("acme_corp") == "acme_corp"
    assert sanitize_tenant_id("../etc") == "default"
    assert sanitize_tenant_id("a/b") == "default"


def test_tenant_isolation(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    assert remember_from_user("请叫我甲租户", tenant_id="tenant_a")
    assert remember_from_user("请叫我乙租户", tenant_id="tenant_b")
    a = load_personal_notes(tenant_id="tenant_a")
    b = load_personal_notes(tenant_id="tenant_b")
    assert "甲租户" in a and "乙租户" not in a
    assert "乙租户" in b and "甲租户" not in b
    assert memory_path("tenant_a") == tmp_path / "memory" / "tenants" / "tenant_a" / "xiaozhu.md"
    assert memory_path("tenant_b") == tmp_path / "memory" / "tenants" / "tenant_b" / "xiaozhu.md"


def test_default_legacy_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    legacy = tmp_path / "memory" / "xiaozhu.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("# 小朱个人笔记\n\n- 旧笔记叫我老王\n", encoding="utf-8")
    assert memory_path("default") == legacy
    notes = load_personal_notes(tenant_id="default")
    assert "老王" in notes
    # first write migrates legacy → tenants/default then appends
    assert remember_from_user("请记住新路径偏好短答", tenant_id="default")
    tenant_file = tmp_path / "memory" / "tenants" / "default" / "xiaozhu.md"
    assert tenant_file.is_file()
    assert memory_path("default") == tenant_file
    body = tenant_file.read_text(encoding="utf-8")
    assert "老王" in body
    assert "新路径偏好短答" in body
    assert "新路径偏好短答" in load_personal_notes(tenant_id="default")
