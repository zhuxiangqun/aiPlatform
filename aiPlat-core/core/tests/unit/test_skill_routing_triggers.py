"""
B2 注册路由侧改造测试（2026-08-26）：生成物 triggers 自动进路由表。

覆盖:
- discovery.py 解析：生成物 SKILL.md 的 `triggers:`（agent_engineering 产物，无
  trigger_conditions）必须并入 DiscoveredSkill.trigger_conditions（与 registry.match
  读 triggers 对齐，统一 trigger_conditions/triggers/trigger_keywords 三字段）
- SkillMatcher.match：用户自然语言命中生成物的触发短语（注册后立即路由可达）

运行方式（仓库根）：
    TMPDIR=$(pwd)/../.tmp_pytest AIPLAT_HOME=$(pwd)/../.tmp_pytest/home \
        python3 -m pytest aiPlat-core/core/tests/unit/test_skill_routing_triggers.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(CORE_ROOT))

from core.apps.skills.discovery import SKILLMD_parser, SkillMatcher


GENERATED_SKILL = """---
name: video_analysis
description: 上传视频并解析视频内容，生成场景、物体、字幕分析结果
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 上传视频
  - 解析视频
input_schema:
  video_id:
    type: string
    required: true
    description: 视频ID
output_schema:
  analysis_result:
    type: object
    required: true
    description: 分析结果
---

# 视频分析

## 输入校验
- video_id 非空

## 核心处理
1. 加载元数据

## 错误处理
- 输入无效 → 提示
"""


class TestGeneratedTriggersRoute:
    def test_triggers_flow_into_route_table(self):
        """生成物的 triggers 必须并入 trigger_conditions（discovery 路由表）。"""
        with tempfile.TemporaryDirectory(prefix="gen_skill_") as tmp:
            skill_dir = Path(tmp) / "video_analysis"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(GENERATED_SKILL, encoding="utf-8")
            info = SKILLMD_parser.parse(skill_dir)
            assert info is not None
            assert info.trigger_conditions == ["上传视频", "解析视频"], \
                f"B2 未修复：生成物 triggers 未进路由表（trigger_conditions={info.trigger_conditions}）"

    def test_skill_matcher_hits_generated_skill(self):
        """用户自然语言（触发短语）→ SkillMatcher 命中生成物。"""
        with tempfile.TemporaryDirectory(prefix="gen_skill2_") as tmp:
            skill_dir = Path(tmp) / "video_analysis"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(GENERATED_SKILL, encoding="utf-8")
            info = SKILLMD_parser.parse(skill_dir)
            matched = SkillMatcher().match("请帮我上传视频", [info])
            assert any(s.name == "video_analysis" for s in matched), \
                "B2 未修复：生成物（triggers）未被路由命中"

    def test_trigger_conditions_still_work(self):
        """显式 trigger_conditions 仍优先（兼容既有 skill，不回归）。"""
        md = GENERATED_SKILL.replace("triggers:\n  - 上传视频\n  - 解析视频\n",
                                     "trigger_conditions:\n  - 查询订单\n")
        with tempfile.TemporaryDirectory(prefix="gen_skill3_") as tmp:
            skill_dir = Path(tmp) / "order_query"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(md, encoding="utf-8")
            info = SKILLMD_parser.parse(skill_dir)
            assert info.trigger_conditions == ["查询订单"]
            assert not info.trigger_keywords
            matched = SkillMatcher().match("帮我查询订单", [info])
            assert matched, "trigger_conditions 兼容性回归（显式路由表字段未被命中）"
