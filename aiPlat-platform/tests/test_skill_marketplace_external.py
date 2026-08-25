"""Skill Marketplace external-discover endpoint tests.

覆盖：
- discover_external_skills 端点：unsupported source → 400；external 源 best-effort
  （mock discover_external 返回值，避免真实网络）
- SkillMarketplace.supports_external_source：agentskills.io 支持
"""

import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, ".")

import pytest

# platform 路由需要 api/auth 包在 path 上
sys.path.insert(0, "aiPlat-platform")


def _fresh_home():
    tmp = tempfile.mkdtemp()
    os.environ["AIPLAT_HOME"] = tmp
    return tmp


class TestSkillMarketplaceExternalDiscover:
    def test_supports_agentskills_source(self):
        """agentskills.io 是受支持的外部源。"""
        _fresh_home()
        from core.harness.knowledge.skill_marketplace import SkillMarketplace

        m = SkillMarketplace(db_path=os.path.join(os.environ["AIPLAT_HOME"], "mp.db"))
        assert m.supports_external_source("agentskills.io") is True
        assert m.supports_external_source("no_such_source") is False

    def test_discover_external_best_effort_unreachable(self):
        """外部源不可达 → 返回 error 列表（best-effort，不抛异常）。"""
        _fresh_home()
        from core.harness.knowledge.skill_marketplace import SkillMarketplace

        m = SkillMarketplace(db_path=os.path.join(os.environ["AIPLAT_HOME"], "mp.db"))
        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            items = m.discover_external("agentskills.io", limit=5)
        assert items and items[0].get("error")

    def test_discover_external_mocked_index(self):
        """外部源可达（mock）→ 返回 skills 列表。"""
        _fresh_home()
        from core.harness.knowledge.skill_marketplace import SkillMarketplace

        m = SkillMarketplace(db_path=os.path.join(os.environ["AIPLAT_HOME"], "mp.db"))

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                import json
                return json.dumps({"skills": [
                    {"name": "code-review", "description": "PR review skill"},
                    {"name": "doc-writer", "description": "docs skill"},
                ]}).encode()

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            items = m.discover_external("agentskills.io", limit=5)
        assert len(items) == 2
        assert items[0]["name"] == "code-review"
        assert items[0]["source"] == "agentskills.io"

    def test_endpoint_unsupported_source_400(self):
        """discover_external_skills 端点：unsupported source → 400。"""
        _fresh_home()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import api.routers.skill_marketplace as sm
        from core.harness.knowledge.skill_marketplace import SkillMarketplace

        app = FastAPI()
        app.include_router(sm.router)

        # 绕过 require_auth + 用临时 db（默认 ~/.aiplat 在测试沙箱不可写）
        # 路由器内是局部 import，patch 源模块 SkillMarketplace
        _RealMP = SkillMarketplace
        with patch.object(sm, "require_auth", lambda: "tester"), \
             patch("core.harness.knowledge.skill_marketplace.SkillMarketplace",
                   lambda *a, **k: _RealMP(
                       db_path=os.path.join(os.environ["AIPLAT_HOME"], "mp.db"))):
            with TestClient(app) as client:
                r = client.get("/skills/marketplace/external?source=nope")
        assert r.status_code == 400

    def test_endpoint_external_discover_ok(self):
        """discover_external_skills 端点：可达源返回 skills（mock discover）。"""
        _fresh_home()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import api.routers.skill_marketplace as sm
        from core.harness.knowledge.skill_marketplace import SkillMarketplace

        app = FastAPI()
        app.include_router(sm.router)

        with patch.object(sm, "require_auth", lambda: "tester"), \
             patch("core.harness.knowledge.skill_marketplace.SkillMarketplace",
                   lambda *a, **k: SkillMarketplace(
                       db_path=os.path.join(os.environ["AIPLAT_HOME"], "mp.db"))), \
             patch.object(SkillMarketplace, "discover_external",
                          return_value=[{"name": "s1", "description": "d", "source": "agentskills.io"}]):
            with TestClient(app) as client:
                r = client.get("/skills/marketplace/external?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert body["external_source"] == "agentskills.io"
        assert len(body["skills"]) == 1
        assert body["total"] == 1
