"""Constitution card + on-demand CAPABILITIES / controlled Wiki pack for 小朱."""
from pathlib import Path

import pytest

from core.harness.digital_human.consultant_knowledge import (
    _WIKI_PREFIX,
    build_controlled_wiki_excerpts,
    build_on_demand_pack,
    clear_knowledge_caches,
    ensure_generic_disclaimer,
    ensure_unreported_page_field_note,
    load_constitution_card,
    looks_external_generic_question,
    page_data_has_glossary,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_knowledge_caches()
    yield
    clear_knowledge_caches()


def test_constitution_card_loads():
    card = load_constitution_card()
    assert "平台心智卡" in card
    assert "unified_pipeline" in card or "选模" in card
    assert "简报" in card


def test_on_demand_pack_for_model_question():
    pack = build_on_demand_pack("选模链路是怎么工作的？purpose 和 unified_pipeline 什么关系？")
    assert pack
    assert "按需能力摘录" in pack
    assert "模型" in pack or "purpose" in pack.lower() or "九、" in pack


def test_on_demand_skips_inventory_list():
    pack = build_on_demand_pack("工作区有哪些 Agent？")
    assert pack == ""


def test_on_demand_skips_audit_followup():
    assert build_on_demand_pack("精简一点") == ""


def test_payload_order_helper():
    from core.harness.digital_human.voice_pipeline import _consultant_user_payload

    out = _consultant_user_payload(
        "选模怎么走",
        "简报: agents=1",
        dialogue="本会话刚才：\n用户: hi",
        about="关于你: 短答",
        constitution="平台心智卡：选模",
        knowledge="按需能力摘录：模型",
    )
    assert out.index("选模怎么走") < out.index("本会话刚才")
    assert out.index("关于你") < out.index("平台心智卡")
    assert out.index("平台心智卡") < out.index("按需能力摘录")
    assert out.index("按需能力摘录") < out.index("简报: agents=1")


def test_capabilities_path_resolves():
    from core.harness.digital_human import consultant_knowledge as ck

    path = ck._capabilities_path()
    assert path.name == "AIPLAT_CAPABILITIES.md"
    # In-repo checkout should see the file
    if Path(ck._repo_root()).joinpath("AIPLAT_CAPABILITIES.md").is_file():
        assert path.is_file()


def test_external_generic_question_detection():
    assert looks_external_generic_question("Kubernetes 和 Docker Compose 有什么区别？")
    assert looks_external_generic_question("什么是 OSS 对象存储？")
    assert not looks_external_generic_question("工作区有哪些 Agent？")
    assert not looks_external_generic_question("选模链路怎么走？")
    assert not looks_external_generic_question("Skill 和 Agent 的区别？")


def test_ensure_generic_disclaimer_adds_prefix():
    out = ensure_generic_disclaimer(
        "OSS 是对象存储，按桶管理文件。",
        "什么是 OSS 对象存储？",
    )
    assert out.startswith("（通用说明，非 aiPlat 既有）")
    assert "对象存储" in out


def test_ensure_generic_disclaimer_skips_platform_answer():
    out = ensure_generic_disclaimer(
        "去 /infra/models 看名单；简报未见 DeepSeek 时写未见。",
        "什么是 OSS？",  # would be generic, but answer cites platform
    )
    assert "通用说明" not in out


def test_ensure_generic_disclaimer_skips_platform_question():
    out = ensure_generic_disclaimer(
        "Skill 是可复用动作，Agent 是编排角色。",
        "Skill 和 Agent 的区别是什么？",
    )
    assert "通用说明" not in out


def test_ensure_generic_disclaimer_skips_page_only():
    out = ensure_generic_disclaimer(
        "OSS 是对象存储。",
        "什么是 OSS？",
        page_only=True,
    )
    assert "通用说明" not in out


def test_page_data_has_glossary():
    assert page_data_has_glossary('{"guideGlossary":"κ≠accuracy"}')
    assert not page_data_has_glossary('{"setsCount":3}')
    assert not page_data_has_glossary("")


def test_on_demand_skips_when_page_glossary_field_question():
    pack = build_on_demand_pack(
        "accuracy_claim 是什么意思？",
        page_has_glossary=True,
    )
    assert pack == ""


def test_wiki_excerpts_disabled_by_empty_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_CONSULTANT_WIKI_COLLECTIONS", "")
    assert build_controlled_wiki_excerpts("FDE 交付引擎怎么用？") == ""


def test_wiki_excerpts_allowlist_hit(monkeypatch, tmp_path):
    root = tmp_path / "wiki" / "collections" / "aiplat-system"
    root.mkdir(parents=True)
    (root / "选模链路说明.md").write_text(
        "# 选模\n\n唯一链 best_model_for_purpose → unified_pipeline。\n界面 /infra/models。\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_CONSULTANT_WIKI_COLLECTIONS", "aiplat-system")
    out = build_controlled_wiki_excerpts("选模链路是怎么工作的？")
    assert _WIKI_PREFIX in out
    assert "unified_pipeline" in out
    assert "aiplat-system" in out


def test_on_demand_pack_can_include_wiki(monkeypatch, tmp_path):
    root = tmp_path / "wiki" / "collections" / "aiplat-system"
    root.mkdir(parents=True)
    (root / "选模链路说明.md").write_text(
        "# 选模\n\n唯一链 best_model_for_purpose → unified_pipeline。\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_CONSULTANT_WIKI_COLLECTIONS", "aiplat-system")
    pack = build_on_demand_pack("选模链路是怎么工作的？purpose 和 unified_pipeline 什么关系？")
    assert pack
    assert "按需能力摘录" in pack
    assert _WIKI_PREFIX in pack


def test_inventory_still_skips_wiki(monkeypatch, tmp_path):
    root = tmp_path / "wiki" / "collections" / "aiplat-system"
    root.mkdir(parents=True)
    (root / "Agent名单.md").write_text("# Agent\n有很多 Agent。\n", encoding="utf-8")
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_CONSULTANT_WIKI_COLLECTIONS", "aiplat-system")
    assert build_on_demand_pack("工作区有哪些 Agent？") == ""


def test_unreported_page_field_note_when_no_glossary():
    out = ensure_unreported_page_field_note(
        "这个字段表示超时阈值。",
        "这个字段是什么意思？",
        page_data="",
    )
    assert out.startswith("本页未上报该科目的结构化释义")
    assert "超时阈值" in out


def test_unreported_page_field_note_skips_when_glossary_present():
    out = ensure_unreported_page_field_note(
        "accuracy_claim 必须为 false。",
        "accuracy_claim 是什么意思？",
        page_data="guideGlossary: accuracy_claim=必须false",
    )
    assert "未上报" not in out


def test_unreported_page_field_note_skips_non_field_question():
    out = ensure_unreported_page_field_note(
        "选模走 unified_pipeline。",
        "选模链路怎么用？",
        page_data="",
    )
    assert "未上报" not in out
