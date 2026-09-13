#!/usr/bin/env python3
"""存量 agent_manifest 迁移：不合规 multi_agent → single（+ 补 ui_bindings）。

策略（与晋升契约一致）：
  - multi_agent 缺 rationale / success_metrics / upgrade_criteria → 降为 mode=single
  - 缺 ui_bindings → 用 skill_routing 首个 Skill 生成 {"main": <skill>}
  - 写盘前备份为 *.bak（已存在则不覆盖）
  - 损坏 JSON 仅报告，不改写

用法：
  python3 scripts/migrate_factory_manifests.py --dry-run
  python3 scripts/migrate_factory_manifests.py --apply
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _load_gc():
    path = _repo_root() / "aiPlat-platform" / "builder" / "generated_conformance.py"
    spec = importlib.util.spec_from_file_location("gc_migrate", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _find_manifests(apps_root: Path) -> List[Path]:
    if not apps_root.is_dir():
        return []
    return sorted(p for p in apps_root.rglob("agent_manifest.json") if p.is_file())


def _needs_downgrade(data: Dict[str, Any]) -> bool:
    if (data.get("mode") or "single") != "multi_agent":
        return False
    rationale = data.get("multi_agent_rationale")
    if not isinstance(rationale, str) or len(rationale.strip()) < 16:
        return True
    metrics = data.get("success_metrics")
    if not isinstance(metrics, dict):
        return True
    try:
        if int(metrics.get("min_runs") or 0) < 20:
            return True
    except (TypeError, ValueError):
        return True
    crit = data.get("upgrade_criteria")
    if not isinstance(crit, dict):
        return True
    return False


def _ensure_ui_bindings(data: Dict[str, Any]) -> bool:
    ui = data.get("ui_bindings")
    if isinstance(ui, dict) and ui:
        return False
    routing = data.get("skill_routing")
    if not isinstance(routing, dict) or not routing:
        return False
    first = next(iter(routing))
    data["ui_bindings"] = {"main": first}
    return True


def migrate_one(
    path: Path,
    *,
    apply: bool,
    validate,
) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:
        return {"path": str(path), "status": "invalid_json", "error": str(e)}

    if not isinstance(data, dict):
        return {"path": str(path), "status": "invalid_root", "error": "not object"}

    before = validate(data)
    changed = False
    actions: List[str] = []

    if _needs_downgrade(data):
        old = data.get("mode")
        data["mode"] = "single"
        data["_migration"] = {
            "from_mode": old,
            "to_mode": "single",
            "reason": "missing multi_agent five-AND fields (rationale/metrics/upgrade_criteria)",
            "ts": time.time(),
            "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        actions.append("downgrade_multi_to_single")
        changed = True

    if _ensure_ui_bindings(data):
        actions.append("synthesize_ui_bindings")
        changed = True

    after = validate(data)
    result: Dict[str, Any] = {
        "path": str(path),
        "status": "unchanged" if not changed else ("would_write" if not apply else "written"),
        "actions": actions,
        "violations_before": before,
        "violations_after": after,
        "ok_after": len(after) == 0,
    }

    if changed and apply:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_text(raw, encoding="utf-8")
            result["backup"] = str(bak)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate legacy factory agent_manifest.json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Report only")
    g.add_argument("--apply", action="store_true", help="Write changes with .bak")
    ap.add_argument(
        "--apps-root",
        default="",
        help="Override apps root (default: AIPLAT_HOME/apps)",
    )
    args = ap.parse_args()

    apps_root = Path(args.apps_root) if args.apps_root else (_aiplat_home() / "apps")
    gc = _load_gc()
    validate = gc.validate_manifest

    rows = []
    for path in _find_manifests(apps_root):
        rows.append(migrate_one(path, apply=bool(args.apply), validate=validate))

    ok_n = sum(1 for r in rows if r.get("ok_after"))
    written = sum(1 for r in rows if r.get("status") == "written")
    would = sum(1 for r in rows if r.get("status") == "would_write")
    invalid = sum(1 for r in rows if r.get("status") in ("invalid_json", "invalid_root"))

    print("=== migrate_factory_manifests ===")
    print(f"apps_root={apps_root}")
    print(f"manifests={len(rows)} written={written} would_write={would} "
          f"ok_after={ok_n} invalid={invalid}")
    for r in rows:
        print("---")
        print(r["path"])
        print(f"  status={r['status']} actions={r.get('actions')} ok_after={r.get('ok_after')}")
        if r.get("violations_before"):
            print(f"  before={r['violations_before'][:3]}")
        if r.get("violations_after"):
            print(f"  after={r['violations_after'][:3]}")
        if r.get("error"):
            print(f"  error={r['error']}")

    # exit 1 only if apply left remaining violations on valid files
    if args.apply:
        remaining = [
            r for r in rows
            if r.get("status") not in ("invalid_json", "invalid_root") and not r.get("ok_after")
        ]
        return 1 if remaining else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
