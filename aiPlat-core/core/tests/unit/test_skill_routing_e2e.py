"""
生成物路由 E2E 测试（2026-08-26）：真实生成物（含 triggers）从落盘到路由命中的全链路。

链路：SKILL.md（frozen fixture，合规生成物）→ 写入 AIPLAT_HOME/skills/
     → SkillDiscovery.discover() 全量发现 → trigger_conditions 并入 triggers
     → SkillMatcher.match 用户自然语言命中
     → SkillRegistry workspace 扫描（registry.match 读 triggers）亦命中

运行方式（仓库根）：
    TMPDIR=$(pwd)/../.tmp_pytest AIPLAT_HOME=$(pwd)/../.tmp_pytest/home \
        python3 -m pytest aiPlat-core/core/tests/unit/test_skill_routing_e2e.py -v
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = CORE_ROOT.parent

import sys
sys.path.insert(0, str(CORE_ROOT))


FIXTURE = (REPO_ROOT / "aiPlat-platform" / "tests" / "fixtures" / "generated"
           / "video_sense_template_skill.md")

GENERATED_SKILL = """---
name: video_analysis
description: 上传视频并解析视频内容，生成场景、物体、字幕分析结果
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 上传视频
  - 解析视频
effects:
  - type: read
    resources: [filesystem:~/.aiplat]
    idempotent: true
    rollback_available: false
input_schema:
  video_id:
    type: string
    required: true
    description: 视频ID
output_schema:
  analysis_result:
    type: object
    required: true
    description: 分析结果（场景/物体/字幕）
---

# 视频分析

## 输入校验
- 格式校验: video_id 必须非空字符串（长度 1-128）
- 校验失败 → 返回"video_id 不能为空"

## 核心处理
1. 加载视频元数据
2. 执行场景切分与物体识别

## 错误处理
- 输入无效 → 提示修正
- 处理超时 → 提示重试
"""


class TestGeneratedRoutingE2E:
    """真实生成物从落盘到路由命中的端到端链路。"""

    @pytest.fixture
    def skills_home(self, tmp_path, monkeypatch):
        """tmp AIPLAT_HOME + 生成物 SKILL.md 落盘到 skills/ 子目录。"""
        home = tmp_path / "home"
        skills = home / "skills" / "video_analysis"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(GENERATED_SKILL, encoding="utf-8")
        monkeypatch.setenv("AIPLAT_HOME", str(home))
        # seed_for_platform 用 AIPLAT_WORKSPACE_SKILLS（默认 ~/.aiplat/skills）——指向 tmp
        monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS", str(home / "skills"))
        return home

    def test_discovery_and_matcher_hit(self, skills_home):
        """链路 1：discovery 发现（triggers 进路由表）→ SkillMatcher 用户输入命中。"""
        from core.apps.skills.discovery import SkillDiscovery, SkillMatcher

        d = SkillDiscovery(base_path="", workspace_path=str(skills_home / "skills"))
        found = asyncio.run(d.discover())
        info = found.get("video_analysis")
        assert info is not None, f"discovery 未发现生成物: {list(found.keys())}"
        assert info.trigger_conditions == ["上传视频", "解析视频"], info.trigger_conditions

        matched = SkillMatcher().match("请帮我上传视频并解析", [info])
        assert any(s.name == "video_analysis" for s in matched), "E2E 失败：生成物未被路由命中"

    def test_registry_workspace_scan_hits(self, skills_home):
        """链路 2：SkillRegistry workspace 扫描（registry.match 读 triggers）命中。"""
        from core.apps.skills.registry import get_skill_registry

        reg = get_skill_registry()
        reg.seed_for_platform()
        results = reg.search_corpus("上传视频")
        assert any(r.get("name") == "video_analysis" for r in results), \
            f"registry.search_corpus('上传视频') 未命中生成物: {results}"
