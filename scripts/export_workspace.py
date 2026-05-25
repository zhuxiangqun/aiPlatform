#!/usr/bin/env python3
"""导出 workspace 配置为种子文件，供首次启动自动加载。
只导出 status=listed 的内容（已上架）。
支持 --ids 参数过滤：--ids agent:site_tester,skill:my_skill
"""
import os
import re
import shutil
import sys
from pathlib import Path


def _read_frontmatter(filepath: Path) -> dict:
    """从 YAML frontmatter 读取元数据。"""
    if not filepath.exists():
        return {}
    try:
        text = filepath.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                meta = {}
                for line in frontmatter.split("\n"):
                    line = line.strip()
                    if ":" in line and not line.startswith("#"):
                        key, _, val = line.partition(":")
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        meta[key.lower()] = val
                return meta
    except Exception:
        pass
    return {}


def _is_published(item_dir: Path, definition_file: str) -> bool:
    """Check if item has status=published in its frontmatter."""
    meta = _read_frontmatter(item_dir / definition_file)
    return meta.get("status", "").lower() in ("listed", "published")


def main():
    aiplat_home = Path(os.environ.get("AIPLAT_HOME", Path.home() / ".aiplat"))
    seeds_dir = Path(__file__).parent.parent / "aiPlat-core" / "core" / "workspace_seeds"

    # Parse --ids argument
    selected_ids: set[str] = set()
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--ids" and i + 1 < len(args):
            selected_ids = set(args[i + 1].split(","))
            break

    sources = {
        "agents": {"subdir": "agents", "file": "AGENT.md"},
        "skills": {"subdir": "skills", "file": "SKILL.md"},
        "workflow_templates": {"subdir": "workflow_templates", "file": "WORKFLOW.md"},
        "mcp": {"subdir": "mcp", "file": "MCP.md"},
    }

    for name, cfg in sources.items():
        src_dir = aiplat_home / cfg["subdir"]
        if not src_dir.exists():
            continue
        dest_dir = seeds_dir / name
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        exported = 0
        for item in src_dir.iterdir():
            if not item.is_dir() or item.name.startswith("."):
                continue
            # Filter by --ids if provided (format: agent:site_tester)
            if selected_ids:
                item_tag = f"{name.rstrip('s')}:{item.name}"
                if item_tag not in selected_ids:
                    continue
            if not _is_published(item, cfg["file"]):
                print(f"[export] {name}/{item.name}: skipped (not published)")
                continue
            dest = dest_dir / item.name
            shutil.copytree(item, dest)
            exported += 1
            print(f"[export] {name}/{item.name}: exported")

        print(f"[export] {name}: {exported} items exported to {dest_dir}")

    print(f"[export] ✓ workspace 配置已导出到 {seeds_dir}")

if __name__ == "__main__":
    main()
