#!/usr/bin/env python3
"""Export an aiPlat Agent app directory as a Pi Package (Scheme A).

Copies agent_manifest.json, agents/, skills/ into an installable package that
depends on @aiplat/pi-runtime extension patterns (embeds a thin loader extension
or references the monorepo packages/aiplat-pi-runtime).

Usage:
  python3 scripts/export_pi_bundle.py \\
    --app-home ~/.aiplat/apps/<id>/current \\
    --out dist/aiplat-app-<id>

  python3 scripts/export_pi_bundle.py \\
    --app-home packages/aiplat-pi-runtime/fixtures/sample-app \\
    --out /tmp/aiplat-sample-pi
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

WORKSPACE = Path(__file__).resolve().parent.parent
RUNTIME_PKG = WORKSPACE / "packages" / "aiplat-pi-runtime"
RUNTIME_EXT = RUNTIME_PKG / "extensions" / "aiplat-app.ts"
RUNTIME_HANDLER = RUNTIME_PKG / "fixtures" / "handler_echo.py"
RUNTIME_RUNNER = RUNTIME_PKG / "fixtures" / "handler_runner.py"


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _resolve_runtime(*, runtime_mode: Optional[str], api_base: Optional[str]) -> dict:
    """Factory-out delivery mode: thin (default) | hybrid (Pi shell + hosted API)."""
    mode = (
        (runtime_mode or os.getenv("AIPLAT_PI_RUNTIME_MODE") or "thin").strip().lower()
    )
    if mode not in ("thin", "hybrid"):
        mode = "thin"
    base = (
        api_base
        or os.getenv("AIPLAT_API_BASE")
        or os.getenv("AIPLAT_PI_API_BASE")
        or ""
    ).strip().rstrip("/")
    return {"mode": mode, "api_base": base}


def export_bundle(
    *,
    app_home: Path,
    out: Path,
    project_id: str,
    runtime_mode: str | None = None,
    api_base: str | None = None,
) -> Path:
    app_home = app_home.resolve()
    if not app_home.is_dir():
        _die(f"app-home not a directory: {app_home}")
    manifest = app_home / "agent_manifest.json"
    if not manifest.is_file():
        _die(f"missing agent_manifest.json under {app_home}")

    out = out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    runtime = _resolve_runtime(runtime_mode=runtime_mode, api_base=api_base)

    # Core artifacts — stamp runtime block for hybrid/thin delivery boundary
    try:
        man_obj = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(man_obj, dict):
            man_obj = {}
    except Exception:
        man_obj = {}
    rt = man_obj.get("runtime") if isinstance(man_obj.get("runtime"), dict) else {}
    rt = dict(rt)
    rt["mode"] = runtime["mode"]
    if runtime["api_base"]:
        rt["api_base"] = runtime["api_base"]
    elif "api_base" in rt and runtime["mode"] == "thin":
        # thin export: do not require hosted API
        pass
    man_obj["runtime"] = rt
    (out / "agent_manifest.json").write_text(
        json.dumps(man_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    agents_src = app_home / "agents"
    if agents_src.is_dir():
        _copytree(agents_src, out / "agents")
    else:
        # flat AGENT.md at root
        for p in app_home.rglob("AGENT.md"):
            rel = p.parent.relative_to(app_home)
            target = out / "agents" / (rel if str(rel) != "." else Path("default"))
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target / "AGENT.md")

    skills_src = app_home / "skills"
    if skills_src.is_dir():
        _copytree(skills_src, out / "skills")
    else:
        # discover */SKILL.md
        for p in app_home.rglob("SKILL.md"):
            name = p.parent.name
            target = out / "skills" / name
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target / "SKILL.md")
            handler = p.parent / "handler.py"
            if handler.is_file():
                shutil.copy2(handler, target / "handler.py")

    # Embed runtime extension + echo handler fixture for bridge smoke
    ext_dir = out / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    if RUNTIME_EXT.is_file():
        shutil.copy2(RUNTIME_EXT, ext_dir / "aiplat-app.ts")
    else:
        _die(f"runtime extension missing: {RUNTIME_EXT}")

    fixtures = out / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    if RUNTIME_HANDLER.is_file():
        shutil.copy2(RUNTIME_HANDLER, fixtures / "handler_echo.py")
    if RUNTIME_RUNNER.is_file():
        shutil.copy2(RUNTIME_RUNNER, fixtures / "handler_runner.py")

    pkg = {
        "name": f"aiplat-app-{project_id}",
        "version": "0.1.0",
        "private": True,
        "description": f"Exported aiPlat Agent app ({project_id}) as Pi Package",
        "keywords": ["pi-package", "aiplat"],
        "type": "module",
        "pi": {
            "extensions": ["./extensions/aiplat-app.ts"],
            "skills": ["./skills"],
        },
        "peerDependencies": {
            "@earendil-works/pi-agent-core": "~1.1.0",
            "@earendil-works/pi-ai": "~1.1.0",
            "@earendil-works/pi-coding-agent": "~1.1.0",
            "@earendil-works/pi-tui": "~1.1.0",
            "typebox": "*",
        },
        "engines": {"node": ">=22.19.0"},
    }
    (out / "package.json").write_text(
        json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    readme = f"""# {pkg['name']}

Exported from `{app_home}`.

```bash
export AIPLAT_APP_HOME={out}
pi install {out}
# or one-shot:
pi -e {out}
```

Commands: `/aiplat-status`, `/aiplat-sop-check`, `/skill:<name>`

Delivery: runtime.mode={runtime['mode']} (thin = snapshot only; hybrid = set AIPLAT_API_BASE for hosted APIs).
"""
    (out / "README.md").write_text(readme, encoding="utf-8")

    # convenience: record source
    meta = {
        "source_app_home": str(app_home),
        "project_id": project_id,
        "scheme": "A",
        "skills_copied": True,
        "runtime": runtime,
    }
    (out / "aiplat-export.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Export aiPlat Agent app as Pi Package")
    ap.add_argument(
        "--app-home",
        type=Path,
        required=True,
        help="Path to app current/ dir (must contain agent_manifest.json)",
    )
    ap.add_argument("--out", type=Path, required=True, help="Output package directory")
    ap.add_argument(
        "--project-id",
        default="",
        help="Package name suffix (default: out directory name)",
    )
    ap.add_argument(
        "--runtime-mode",
        default="",
        help="thin|hybrid (default: AIPLAT_PI_RUNTIME_MODE or thin)",
    )
    ap.add_argument(
        "--api-base",
        default="",
        help="Hosted aiPlat API base for hybrid (or AIPLAT_API_BASE)",
    )
    args = ap.parse_args()
    pid = (args.project_id or args.out.name).strip().replace("/", "-")
    out = export_bundle(
        app_home=args.app_home,
        out=args.out,
        project_id=pid,
        runtime_mode=(args.runtime_mode or None),
        api_base=(args.api_base or None),
    )
    print(f"PASS: exported Pi package → {out}")
    print(f"  AIPLAT_APP_HOME={out}")
    print(f"  pi -e {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
