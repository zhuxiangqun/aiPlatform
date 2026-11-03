"""Architecture consolidation v1 freeze — ratchet mounts + core eval routers."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SCRIPT = ROOT / "scripts/arch_consolidation_v1_gate.sh"
DOC = ROOT / "docs/a3/ARCH_CONSOLIDATION_V1.md"


def test_arch_doc_exists():
    assert DOC.is_file()
    text = DOC.read_text(encoding="utf-8")
    assert "/api/platform/apps/eval" in text
    assert "Freeze" in text or "freeze" in text.lower()


def test_routes_mount_ratchet():
    routes = (REPO / "aiPlat-platform/api/rest/routes.py").read_text(encoding="utf-8")
    mounts = len(re.findall(r"include_router\(\s*eval_platform_router", routes))
    assert mounts == 2
    assert 'prefix="/api/platform/apps/eval"' in routes


def test_core_eval_router_allowlist():
    names = sorted(
        p.name
        for p in (REPO / "aiPlat-core/core/api/routers").glob("*eval*")
        if p.suffix == ".py"
    )
    assert names == ["eval_legacy_shim.py", "kb_eval.py"]


def test_platform_eval_sqlite_cleared():
    api = REPO / "aiPlat-platform/apps/eval/api"
    hit = sorted(p.name for p in api.glob("*.py") if "sqlite3" in p.read_text(encoding="utf-8"))
    assert hit == []
    prompt = (api / "prompt_eval.py").read_text(encoding="utf-8")
    assert "prompt_eval_list_test_cases" in prompt
    assert "get_db_connection" not in prompt
    runs = (api / "runs_eval.py").read_text(encoding="utf-8")
    assert "runs_eval_submit" in runs
    assert "LearningManager" not in runs
    skill = (api / "skill_evals.py").read_text(encoding="utf-8")
    assert "skill_eval_upsert_suite" in skill
    assert "record_changeset" not in skill


def test_arch_consolidation_gate_script():
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "PASS" in proc.stdout
