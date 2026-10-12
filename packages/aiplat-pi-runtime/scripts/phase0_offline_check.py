#!/usr/bin/env python3
"""Offline Phase 0 structural checks (no pi CLI / no LLM required)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    if "pi" not in pkg:
        errors.append("package.json missing pi key")
    else:
        if "./extensions/aiplat-app.ts" not in pkg["pi"].get("extensions", []):
            errors.append("pi.extensions missing aiplat-app.ts")
        if "./skills" not in pkg["pi"].get("skills", []):
            errors.append("pi.skills missing ./skills")

    skill = ROOT / "skills" / "fixture-skill" / "SKILL.md"
    if not skill.is_file():
        errors.append("missing fixture-skill/SKILL.md")
    else:
        text = skill.read_text(encoding="utf-8")
        if "AIPLAT_FIXTURE_SKILL_OK" not in text:
            errors.append("fixture skill missing marker")

    ext = ROOT / "extensions" / "aiplat-app.ts"
    if not ext.is_file():
        errors.append("missing extensions/aiplat-app.ts")
    else:
        src = ext.read_text(encoding="utf-8")
        for needle in (
            "registerCommand",
            "registerTool",
            "before_agent_start",
            "forceSystemPrompt",
            "aiplat_handler",
        ):
            if needle not in src:
                errors.append(f"extension missing {needle}")

    handler = ROOT / "fixtures" / "handler_echo.py"
    if not handler.is_file():
        errors.append("missing handler_echo.py")
    else:
        proc = subprocess.run(
            ["python3", str(handler)],
            input='{"skill":"fixture","params":{"x":1}}',
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            errors.append(f"handler_echo exit {proc.returncode}: {proc.stderr}")
        else:
            try:
                data = json.loads(proc.stdout)
            except Exception as exc:
                errors.append(f"handler_echo bad json: {exc}")
            else:
                if not data.get("ok") or data.get("result", {}).get("marker") != "AIPLAT_HANDLER_ECHO_OK":
                    errors.append(f"handler_echo unexpected: {data}")

    sample = ROOT / "fixtures" / "sample-app" / "agent_manifest.json"
    if not sample.is_file():
        errors.append("missing sample-app manifest")

    if errors:
        print("FAIL: Phase 0 offline checks")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASS: Phase 0 offline structural checks")
    print("  Doc-backed: skills/ auto-discover + before_agent_start systemPrompt")
    print("  Remaining live gate: install pi and run PHASE0.md interactive checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
