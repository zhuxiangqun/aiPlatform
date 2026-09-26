#!/usr/bin/env python3
"""Phase 0：应用工厂多 Agent 只读基线埋点（不改行为）。

采集：
  1. ~/.aiplat/apps/*/agent_manifest.json 的 mode / multi 占比
  2. 生成物 conformance 通过率（对现有 AGENT.md/SKILL.md 只读校验）
  3. spawn 可达性 + 已持久化 spawn 事件数（若尚无日志则为 0）

用法：
  python3 scripts/factory_multi_agent_baseline.py
  python3 scripts/factory_multi_agent_baseline.py --write   # 写入 ~/.aiplat/builder/baselines/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _find_manifests(apps_root: Path) -> List[Path]:
    out: List[Path] = []
    if not apps_root.is_dir():
        return out
    for p in apps_root.rglob("agent_manifest.json"):
        if p.is_file():
            out.append(p)
    return out


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _infer_mode(manifest: Dict[str, Any]) -> str:
    mode = str(manifest.get("mode") or "").strip()
    if mode in ("single", "multi_agent"):
        return mode
    agents = manifest.get("agents")
    routing = manifest.get("skill_routing")
    if isinstance(agents, list) and len(agents) > 1:
        return "multi_agent"
    if isinstance(routing, dict) and len(set(routing.values())) > 1:
        return "multi_agent"
    return "single"


def collect_multi_ratio(apps_root: Path) -> Dict[str, Any]:
    manifests = _find_manifests(apps_root)
    by_mode = {"single": 0, "multi_agent": 0, "invalid": 0}
    details: List[Dict[str, Any]] = []
    for path in manifests:
        m = _load_json(path)
        if m is None:
            by_mode["invalid"] += 1
            details.append({"path": str(path), "mode": "invalid"})
            continue
        mode = _infer_mode(m)
        by_mode[mode] = by_mode.get(mode, 0) + 1
        details.append({
            "path": str(path),
            "mode": mode,
            "has_rationale": bool(
                ((m.get("multi_agent_manifest") or {}) if isinstance(m.get("multi_agent_manifest"), dict) else {}).get("rationale")
                or m.get("multi_agent_rationale")
                or m.get("rationale")
            ),
            "has_success_metrics": bool(
                ((m.get("multi_agent_manifest") or {}) if isinstance(m.get("multi_agent_manifest"), dict) else {}).get("success_metrics")
                or m.get("success_metrics")
            ),
            "skill_routing_keys": len(m.get("skill_routing") or {}) if isinstance(m.get("skill_routing"), dict) else 0,
        })
    total = sum(by_mode.values())
    multi = by_mode.get("multi_agent", 0)
    return {
        "apps_root": str(apps_root),
        "manifest_count": total,
        "by_mode": by_mode,
        "multi_agent_ratio": (multi / total) if total else None,
        "details": details,
    }


def collect_conformance(apps_root: Path) -> Dict[str, Any]:
    """只读跑 generated_conformance（不写 rejection 审计）。"""
    platform_root = Path(__file__).resolve().parents[1] / "aiPlat-platform"
    if str(platform_root) not in sys.path:
        sys.path.insert(0, str(platform_root))
    try:
        from builder.generated_conformance import validate_file
    except Exception as e:
        return {"error": f"import generated_conformance failed: {e}", "checked": 0}

    checked = 0
    passed = 0
    failed = 0
    by_kind = {"agent": {"pass": 0, "fail": 0}, "skill": {"pass": 0, "fail": 0}}
    sample_failures: List[Dict[str, Any]] = []

    if not apps_root.is_dir():
        return {"checked": 0, "passed": 0, "failed": 0, "pass_rate": None, "by_kind": by_kind}

    for path in apps_root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if name == "AGENT.md":
            kind = "agent"
        elif name == "SKILL.md":
            kind = "skill"
        else:
            continue
        checked += 1
        violations = validate_file(str(path), kind)
        if violations:
            failed += 1
            by_kind[kind]["fail"] += 1
            if len(sample_failures) < 10:
                sample_failures.append({
                    "path": str(path),
                    "kind": kind,
                    "violations": violations[:3],
                })
        else:
            passed += 1
            by_kind[kind]["pass"] += 1

    # also validate manifests if present
    manifest_checked = 0
    manifest_passed = 0
    manifest_failed = 0
    try:
        from builder.generated_conformance import validate_manifest
        for path in _find_manifests(apps_root):
            manifest_checked += 1
            m = _load_json(path) or {}
            v = validate_manifest(m)
            if v:
                manifest_failed += 1
                if len(sample_failures) < 15:
                    sample_failures.append({
                        "path": str(path),
                        "kind": "manifest",
                        "violations": v[:3],
                    })
            else:
                manifest_passed += 1
    except Exception as e:
        return {
            "checked": checked,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / checked) if checked else None,
            "by_kind": by_kind,
            "manifest": {"error": str(e)},
            "sample_failures": sample_failures,
        }

    return {
        "checked": checked,
        "passed": passed,
        "failed": failed,
        "pass_rate": (passed / checked) if checked else None,
        "by_kind": by_kind,
        "manifest": {
            "checked": manifest_checked,
            "passed": manifest_passed,
            "failed": manifest_failed,
            "pass_rate": (manifest_passed / manifest_checked) if manifest_checked else None,
        },
        "sample_failures": sample_failures,
    }


def collect_spawn(home: Path) -> Dict[str, Any]:
    """spawn 基线：持久化事件数 + 工厂路径是否仍可达（静态）。"""
    log_path = home / "builder" / "spawn_events.jsonl"
    events = 0
    if log_path.is_file():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events += 1
        except Exception:
            events = -1

    # 静态：stage_runner 仍含 DynamicOrchestrator.spawn（Phase B 前为 true）
    stage_runner = (
        Path(__file__).resolve().parents[1]
        / "aiPlat-core/core/harness/execution/langgraph/stage_runner.py"
    )
    spawn_reachable = False
    if stage_runner.is_file():
        text = stage_runner.read_text(encoding="utf-8", errors="ignore")
        spawn_reachable = (
            "get_dynamic_orchestrator" in text
            and "orch.spawn" in text
        )

    return {
        "spawn_events_log": str(log_path),
        "persisted_spawn_events": events if events >= 0 else None,
        "spawn_reachable_on_factory_path": spawn_reachable,
        "note": (
            "Phase A 出口不含 spawn=0；W3(P1) 在 Phase B 关闭工厂路径 spawn。"
            "本项只读采集基线。"
        ),
    }


def build_baseline() -> Dict[str, Any]:
    home = _aiplat_home()
    apps_root = home / "apps"
    return {
        "schema_version": 1,
        "phase": "0",
        "ts": time.time(),
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "aiplat_home": str(home),
        "multi_agent": collect_multi_ratio(apps_root),
        "conformance": collect_conformance(apps_root),
        "spawn": collect_spawn(home),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Factory multi-agent Phase 0 baseline (read-only)")
    ap.add_argument("--write", action="store_true", help="Write snapshot under AIPLAT_HOME/builder/baselines/")
    ap.add_argument("--json", action="store_true", help="Print full JSON")
    args = ap.parse_args()

    baseline = build_baseline()
    multi = baseline["multi_agent"]
    conf = baseline["conformance"]
    spawn = baseline["spawn"]

    print("=== Factory multi-agent baseline (Phase 0, read-only) ===")
    print(f"home: {baseline['aiplat_home']}")
    print(f"manifests: {multi['manifest_count']}  by_mode={multi['by_mode']}  "
          f"multi_ratio={multi['multi_agent_ratio']}")
    print(f"conformance: checked={conf.get('checked')} passed={conf.get('passed')} "
          f"failed={conf.get('failed')} pass_rate={conf.get('pass_rate')}")
    man = conf.get("manifest") or {}
    if "error" not in man:
        print(f"manifest_gate: checked={man.get('checked')} passed={man.get('passed')} "
              f"failed={man.get('failed')} pass_rate={man.get('pass_rate')}")
    print(f"spawn: persisted={spawn.get('persisted_spawn_events')} "
          f"reachable_on_factory_path={spawn.get('spawn_reachable_on_factory_path')}")

    if args.json:
        print(json.dumps(baseline, ensure_ascii=False, indent=2))

    if args.write:
        out_dir = _aiplat_home() / "builder" / "baselines"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        out_path = out_dir / f"multi_agent_baseline_{stamp}.json"
        latest = out_dir / "multi_agent_baseline_latest.json"
        payload = json.dumps(baseline, ensure_ascii=False, indent=2)
        out_path.write_text(payload, encoding="utf-8")
        latest.write_text(payload, encoding="utf-8")
        print(f"wrote: {out_path}")
        print(f"wrote: {latest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
