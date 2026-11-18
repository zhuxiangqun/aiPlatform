"""N09 K48 — icebreaker questions loaded from YAML (no business domain keys in code)."""
from __future__ import annotations

import re
from pathlib import Path

from core.apps.fde.service.rapid_insight_service import (
    _load_icebreaker_map,
    generate_icebreaker_questions,
)
from core.harness.knowledge.domain_router import DomainRouter

SERVICE = Path("aiPlat-core/core/apps/fde/service/rapid_insight_service.py")
YAML = Path("aiPlat-core/workspace_seeds/fde/icebreaker_questions.yaml")


def test_yaml_seed_exists_and_has_domains():
    assert YAML.is_file()
    text = YAML.read_text(encoding="utf-8")
    assert "questions_by_domain" in text
    assert "lock-service" in text
    assert DomainRouter.PLATFORM_COMPETITION_DOMAIN in text


def test_service_has_no_inline_business_domain_icebreaker_map():
    text = SERVICE.read_text(encoding="utf-8")
    assert "_load_icebreaker_map" in text
    # No Python dict keyed by business domain string literals for icebreakers.
    assert not re.search(r'icebreaker_map\s*=\s*\{', text)
    assert '"lock-service"' not in text
    assert '"supply-chain"' not in text


def test_load_and_generate_from_yaml():
    m = _load_icebreaker_map()
    assert "lock-service" in m
    assert m["lock-service"]
    qs = generate_icebreaker_questions(["lock-service", DomainRouter.PLATFORM_COMPETITION_DOMAIN])
    assert qs
    assert any("库存" in q or "设备" in q or "头部公司" in q for q in qs)
