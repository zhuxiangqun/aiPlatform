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
RUNTIME_EXT_ENTERPRISE = RUNTIME_PKG / "extensions" / "enterprise_kb.ts"
RUNTIME_EXT_KB_CITATION = RUNTIME_PKG / "extensions" / "enterprise_kb_citation.ts"
RUNTIME_EXT_TOOLS = RUNTIME_PKG / "extensions" / "enterprise_tools.ts"
RUNTIME_EXT_TOOL_GATE = RUNTIME_PKG / "extensions" / "enterprise_tool_gate.ts"
RUNTIME_EXT_MEMORY = RUNTIME_PKG / "extensions" / "enterprise_memory.ts"
RUNTIME_EXT_APPROVAL = RUNTIME_PKG / "extensions" / "enterprise_approval.ts"
RUNTIME_EXT_KB_HEALTH = RUNTIME_PKG / "extensions" / "enterprise_kb_health.ts"
RUNTIME_HANDLER = RUNTIME_PKG / "fixtures" / "handler_echo.py"
RUNTIME_RUNNER = RUNTIME_PKG / "fixtures" / "handler_runner.py"
_SCAN_SCRIPT = WORKSPACE / "scripts" / "scan_pi_bundle_delivery.py"


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

    # Embed runtime extension + hybrid KB module + echo handler fixture
    ext_dir = out / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    if RUNTIME_EXT.is_file():
        shutil.copy2(RUNTIME_EXT, ext_dir / "aiplat-app.ts")
    else:
        _die(f"runtime extension missing: {RUNTIME_EXT}")
    if RUNTIME_EXT_ENTERPRISE.is_file():
        shutil.copy2(RUNTIME_EXT_ENTERPRISE, ext_dir / "enterprise_kb.ts")
    else:
        _die(f"enterprise KB extension missing: {RUNTIME_EXT_ENTERPRISE}")
    # enterprise_kb.ts imports ./enterprise_kb_citation — must ship together
    if RUNTIME_EXT_KB_CITATION.is_file():
        shutil.copy2(RUNTIME_EXT_KB_CITATION, ext_dir / "enterprise_kb_citation.ts")
    else:
        _die(f"enterprise KB citation helper missing: {RUNTIME_EXT_KB_CITATION}")
    if RUNTIME_EXT_TOOLS.is_file():
        shutil.copy2(RUNTIME_EXT_TOOLS, ext_dir / "enterprise_tools.ts")
    else:
        _die(f"enterprise tools extension missing: {RUNTIME_EXT_TOOLS}")
    if RUNTIME_EXT_TOOL_GATE.is_file():
        shutil.copy2(RUNTIME_EXT_TOOL_GATE, ext_dir / "enterprise_tool_gate.ts")
    else:
        _die(f"enterprise tool gate extension missing: {RUNTIME_EXT_TOOL_GATE}")
    if RUNTIME_EXT_MEMORY.is_file():
        shutil.copy2(RUNTIME_EXT_MEMORY, ext_dir / "enterprise_memory.ts")
    else:
        _die(f"enterprise memory extension missing: {RUNTIME_EXT_MEMORY}")
    if RUNTIME_EXT_APPROVAL.is_file():
        shutil.copy2(RUNTIME_EXT_APPROVAL, ext_dir / "enterprise_approval.ts")
    else:
        _die(f"enterprise approval extension missing: {RUNTIME_EXT_APPROVAL}")
    if RUNTIME_EXT_KB_HEALTH.is_file():
        shutil.copy2(RUNTIME_EXT_KB_HEALTH, ext_dir / "enterprise_kb_health.ts")
    else:
        _die(f"enterprise KB health extension missing: {RUNTIME_EXT_KB_HEALTH}")

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

Commands: `/aiplat-status`, `/aiplat-sop-check`, `/skill:<name>`, `/aiplat-enterprise`

Delivery: runtime.mode={runtime['mode']} (thin = snapshot only; hybrid stamp may set api_base).

Optional enterprise KB reconnect (default off — Pi-only):

```bash
export AIPLAT_ENTERPRISE=1
export AIPLAT_PLATFORM_URL=<platform base or …/api>
export AIPLAT_TENANT_TOKEN=<bearer with kb:read>
# optional: AIPLAT_KB_COLLECTION_ID=default
```

Tool: `aiplat_kb_retrieve` → POST /platform/kb/query (PolicyGate stays on platform).

Optional tool proxy (allowlist required):

```bash
export AIPLAT_ENTERPRISE_TOOLS=calculator,file_operations
# optional: AIPLAT_CORE_URL=http://127.0.0.1:8002  (or …/api/core via GW)
```

Tool: `aiplat_tool_execute` → POST …/tools/{{name}}/execute.
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

    # A: 出厂扫描 → DELIVERY_CHECKLIST.md + delivery_scan.json + USAGE_BOUNDARY.md
    # B: FDE 在清单上人工签收（不替代扫描）
    try:
        import importlib.util

        if _SCAN_SCRIPT.is_file():
            spec = importlib.util.spec_from_file_location(
                "aiplat_scan_pi_bundle_delivery", _SCAN_SCRIPT
            )
            if spec and spec.loader:
                scan_mod = importlib.util.module_from_spec(spec)
                # dataclasses need the module registered before exec (Py3.9)
                sys.modules[spec.name] = scan_mod
                spec.loader.exec_module(scan_mod)
                write_fn = getattr(scan_mod, "write_scan_artifacts", None)
                if callable(write_fn):
                    scan_res = write_fn(out, project_id=project_id)
                    meta["delivery_scan"] = {
                        "ok": bool(getattr(scan_res, "ok", False)),
                        "error_count": int(getattr(scan_res, "error_count", 0)),
                        "warning_count": int(getattr(scan_res, "warning_count", 0)),
                    }
                    (out / "aiplat-export.json").write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    if not meta["delivery_scan"]["ok"]:
                        print(
                            "WARNING: delivery scan found errors — see DELIVERY_CHECKLIST.md "
                            "(export not blocked; use scan --strict in CI to gate)",
                            file=sys.stderr,
                        )
    except Exception as exc:
        print(f"WARNING: delivery scan skipped: {exc}", file=sys.stderr)

    # §4 成本页：尽力写入 COST_REPORT.md（子系统不可用时仍有叙事骨架）
    try:
        _delivery_dir = WORKSPACE / "aiPlat-platform"
        if str(_delivery_dir) not in sys.path:
            sys.path.insert(0, str(_delivery_dir))
        from delivery.cost_report import (  # type: ignore
            build_delivery_cost_report,
            render_cost_report_markdown,
        )

        cost_report = build_delivery_cost_report(project_id=project_id)
        (out / "COST_REPORT.md").write_text(
            render_cost_report_markdown(cost_report), encoding="utf-8"
        )
        meta["delivery_cost_report"] = {
            "ok": bool(cost_report.get("ok")),
            "cache_available": bool((cost_report.get("cache") or {}).get("available")),
            "api_calls_available": bool((cost_report.get("api_calls") or {}).get("available")),
        }
        (out / "aiplat-export.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"WARNING: COST_REPORT.md skipped: {exc}", file=sys.stderr)

    # §④ 库健康分：尽力写入 KB_HEALTH.md
    try:
        _delivery_dir = WORKSPACE / "aiPlat-platform"
        if str(_delivery_dir) not in sys.path:
            sys.path.insert(0, str(_delivery_dir))
        from delivery.kb_health import (  # type: ignore
            build_kb_health_report,
            render_kb_health_markdown,
        )

        kb_report = build_kb_health_report(project_id=project_id)
        (out / "KB_HEALTH.md").write_text(
            render_kb_health_markdown(kb_report), encoding="utf-8"
        )
        meta["delivery_kb_health"] = {
            "ok": bool(kb_report.get("ok")),
            "score": (kb_report.get("health") or {}).get("score"),
        }
        (out / "aiplat-export.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"WARNING: KB_HEALTH.md skipped: {exc}", file=sys.stderr)

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
