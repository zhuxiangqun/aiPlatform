import os
from pathlib import Path


def _write_skill(tmp: Path, name: str, skill_md: str, handler: bool = False) -> None:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(skill_md, encoding="utf-8")
    if handler:
        (d / "handler.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")


def test_skill_kind_explicit_and_security_degrade(monkeypatch, tmp_path):
    # skill manager in workspace scope should scan this directory
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path))

    _write_skill(
        tmp_path,
        "rule1",
        """---
name: rule1
description: just rules
executable: false
version: 1.0.0
---
SOP
""",
    )
    _write_skill(
        tmp_path,
        "exe1",
        """---
name: exe1
description: executable
executable: true
runtime: python
entrypoint: handler.py:main
permissions: [filesystem_read]
version: 1.0.0
---
SOP
""",
        handler=True,
    )
    # explicit executable but missing permissions -> degrade to rule
    _write_skill(
        tmp_path,
        "exe2",
        """---
name: exe2
description: executable missing perms
executable: true
runtime: python
entrypoint: handler.py:main
version: 1.0.0
---
SOP
""",
        handler=True,
    )

    from core.management.skill_manager import SkillManager

    mgr = SkillManager(seed=False, scope="workspace", reserved_ids=set())
    s1 = anyio_run(mgr.get_skill, "rule1")
    s2 = anyio_run(mgr.get_skill, "exe1")
    s3 = anyio_run(mgr.get_skill, "exe2")
    assert s1 and isinstance(s1.metadata, dict) and s1.metadata.get("skill_kind") == "rule"
    assert s2 and isinstance(s2.metadata, dict) and s2.metadata.get("skill_kind") == "executable"
    assert s3 and isinstance(s3.metadata, dict) and s3.metadata.get("skill_kind") == "rule"


def anyio_run(fn, *args, **kwargs):
    import anyio

    return anyio.run(lambda: fn(*args, **kwargs))

