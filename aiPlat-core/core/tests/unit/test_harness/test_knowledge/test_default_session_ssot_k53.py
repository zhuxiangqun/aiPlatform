"""N09 K53 — session_id signature defaults via DomainRouter.default_session()."""
from __future__ import annotations

import re
from pathlib import Path

from core.harness.knowledge.domain_router import DomainRouter
from core.harness.kernel.execution_context import ActiveRequestContext
from core.harness.kernel.types import ExecutionRequest

TARGETS = [
    "aiPlat-core/core/harness/kernel/types.py",
    "aiPlat-core/core/harness/kernel/execution_context.py",
    "aiPlat-core/core/harness/syscalls/skill.py",
    "aiPlat-core/core/harness/syscalls/tool.py",
    "aiPlat-core/core/apps/fde/service/voice.py",
]


def test_platform_default_session_helper():
    assert DomainRouter.PLATFORM_DEFAULT_SESSION == "default"
    assert DomainRouter.default_session() == "default"
    assert ExecutionRequest(kind="skill", target_id="x").session_id == "default"
    assert ActiveRequestContext().session_id == "default"


def test_targets_use_default_session_ssot():
    for rel in TARGETS:
        text = Path(rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_session()" in text, rel
        assert 'session_id: str = "default"' not in text, rel


def test_production_session_signature_defaults_empty():
    rx = re.compile(r'session_id\s*:\s*str\s*=\s*["\']default["\']')
    hits = []
    for root in (Path("aiPlat-core/core"), Path("aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(ln):
                    hits.append(f"{p}:{i}")
    assert hits == [], hits
