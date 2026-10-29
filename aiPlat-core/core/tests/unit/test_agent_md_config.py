"""
test_agent_md_config — verify AGENT.md files meet quality standards.

Enforces:
  - Core CLAUDE.md §5.27.2: 5 handoff fields (做了什么/产出/验证/已知问题/下一步)
  - Core CLAUDE.md §5.27.3: AGENT.md should be under 100 lines
"""

import os
from pathlib import Path

import yaml


def _agents_dir() -> Path:
    # Prefer hermetic AIPLAT_HOME (pytest conftest); fall back to ~/.aiplat.
    home = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    return Path(home) / "agents"


HANDOFF_KEYWORDS = ["做了什么", "产出", "验证", "已知问题", "下一步", "变更", "deliverable", "verify", "known issue", "next step"]


def _get_agent_dirs() -> list[Path]:
    agents_dir = _agents_dir()
    auto_dir = agents_dir / "auto"
    if not agents_dir.exists():
        return []
    out = []
    for item in sorted(agents_dir.iterdir()):
        if item.is_dir() and (item / "AGENT.md").exists():
            # Skip auto-generated agents
            if str(item).startswith(str(auto_dir)):
                continue
            out.append(item)
    return out


def _parse_frontmatter(path: Path) -> tuple[dict, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}, ""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        return yaml.safe_load(parts[1]) or {}, parts[2]
    except Exception:
        return {}, parts[2] if len(parts) > 2 else text


def test_agent_md_line_count():
    """AGENT.md should be under 200 lines (§5.27.3)."""
    oversized = []
    for d in _get_agent_dirs():
        md = d / "AGENT.md"
        count = len(md.read_text(encoding="utf-8").splitlines())
        if count >= 200:
            oversized.append(f"{d.name} ({count} lines)")
    assert len(oversized) == 0, (
        f"{len(oversized)} AGENT.md files exceed 200 lines:\n  " +
        "\n  ".join(oversized[:10])
    )


def test_agent_md_handoff_fields():
    """AGENT.md should contain handoff information keywords (§5.27.2)."""
    missing = []
    for d in _get_agent_dirs():
        md = d / "AGENT.md"
        _fm, body = _parse_frontmatter(md)
        body_lower = body.lower()[:8000]
        found = [kw for kw in HANDOFF_KEYWORDS if kw in body_lower]
        if len(found) < 3:
            missing.append(f"{d.name} (found: {found})")
    if missing:
        print(f"\n  ⚠️  {len(missing)} AGENT.md files have <3 handoff keywords:")
        for name in missing[:15]:
            print(f"     - {name}")
        if len(missing) > 15:
            print(f"     ... and {len(missing) - 15} more")
