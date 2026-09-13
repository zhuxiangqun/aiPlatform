#!/usr/bin/env python3
"""应用工厂多 Agent 只读基线 / 健康快照（不改行为）。

Phase 0 起：采集 multi 占比 / conformance / spawn。
Phase A–C 后：额外探测 spawn 门禁接线、hop 度量、promotion_gate 契约文件。

用法：
  python3 scripts/factory_multi_agent_baseline.py
  python3 scripts/factory_multi_agent_baseline.py --write
  python3 scripts/factory_multi_agent_baseline.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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
        mam = m.get("multi_agent_manifest")
        mam = mam if isinstance(mam, dict) else {}
        details.append({
            "path": str(path),
            "mode": mode,
            "has_rationale": bool(
                mam.get("rationale")
                or m.get("multi_agent_rationale")
                or m.get("rationale")
            ),
            "has_success_metrics": bool(
                mam.get("success_metrics") or m.get("success_metrics")
            ),
            "skill_routing_keys": (
                len(m.get("skill_routing") or {})
                if isinstance(m.get("skill_routing"), dict)
                else 0
            ),
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


def _load_generated_conformance():
    """Load generated_conformance without importing builder/__init__ (avoids core pull on 3.9)."""
    import importlib.util

    path = _repo_root() / "aiPlat-platform" / "builder" / "generated_conformance.py"
    spec = importlib.util.spec_from_file_location(
        "factory_generated_conformance", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def collect_conformance(apps_root: Path) -> Dict[str, Any]:
    """只读跑 generated_conformance（不写 rejection 审计）。"""
    try:
        gc = _load_generated_conformance()
        validate_file = gc.validate_file
        validate_manifest = gc.validate_manifest
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

    manifest_checked = 0
    manifest_passed = 0
    manifest_failed = 0
    try:
        gc = _load_generated_conformance()
        validate_manifest = gc.validate_manifest
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
    """spawn：持久化事件 + 工厂路径是否仍含 spawn 调用 + 门禁是否已接线。"""
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

    root = _repo_root()
    stage_runner = root / "aiPlat-core/core/harness/execution/langgraph/stage_runner.py"
    factory_profile = root / "aiPlat-core/core/harness/execution/factory_profile.py"
    spawn_policy = root / "aiPlat-core/core/harness/coordination/spawn_policy.py"
    agent_syscall = root / "aiPlat-core/core/harness/syscalls/agent.py"

    spawn_code_present = False
    if stage_runner.is_file():
        text = stage_runner.read_text(encoding="utf-8", errors="ignore")
        spawn_code_present = (
            "get_dynamic_orchestrator" in text and "orch.spawn" in text
        )

    factory_forces_deny = False
    if factory_profile.is_file():
        fp = factory_profile.read_text(encoding="utf-8", errors="ignore")
        factory_forces_deny = "allow_dynamic_spawn" in fp and "False" in fp

    policy_wired = spawn_policy.is_file()
    stage_honors_policy = False
    syscall_honors_policy = False
    if stage_runner.is_file():
        st = stage_runner.read_text(encoding="utf-8", errors="ignore")
        stage_honors_policy = "should_skip_dynamic_spawn" in st or "disable_dynamic_spawn" in st
    if agent_syscall.is_file():
        ag = agent_syscall.read_text(encoding="utf-8", errors="ignore")
        syscall_honors_policy = "is_dynamic_spawn_disabled" in ag

    gated = bool(policy_wired and factory_forces_deny and stage_honors_policy and syscall_honors_policy)

    return {
        "spawn_events_log": str(log_path),
        "persisted_spawn_events": events if events >= 0 else None,
        "spawn_code_present_on_factory_path": spawn_code_present,
        "factory_spawn_gated": gated,
        "checks": {
            "spawn_policy_module": policy_wired,
            "factory_profile_allow_dynamic_spawn_false": factory_forces_deny,
            "stage_runner_honors_policy": stage_honors_policy,
            "sys_agent_call_honors_policy": syscall_honors_policy,
        },
        "note": (
            "orch.spawn 代码可仍存在（降级/非工厂路径）；"
            "工厂契约路径靠 spawn_policy + allow_dynamic_spawn=False 阻断。"
        ),
    }


def _load_hop_metrics():
    import importlib.util

    path = _repo_root() / "aiPlat-platform" / "builder" / "hop_metrics.py"
    spec = importlib.util.spec_from_file_location("factory_hop_metrics", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    # hop_metrics imports builder.promotion_gate lazily inside evaluate_*; aggregate_hops is pure
    spec.loader.exec_module(mod)
    return mod


def collect_hops(home: Path) -> Dict[str, Any]:
    """聚合 AIPLAT_HOME/builder/hop_metrics/*.jsonl（只读摘要）。"""
    metrics_dir = home / "builder" / "hop_metrics"
    if not metrics_dir.is_dir():
        return {"projects": 0, "total_hops": 0, "by_project": []}

    by_project: List[Dict[str, Any]] = []
    total = 0
    try:
        hm = _load_hop_metrics()
        aggregate_hops = hm.aggregate_hops
    except Exception as e:
        return {"error": str(e), "projects": 0, "total_hops": 0, "by_project": []}

    for path in sorted(metrics_dir.glob("*.jsonl")):
        pid = path.stem
        agg = aggregate_hops(pid)
        total += int(agg.get("n_runs") or 0)
        by_project.append({
            "project_id": pid,
            "n_runs": agg.get("n_runs"),
            "effective_n": agg.get("effective_n"),
            "effective_success_rate": agg.get("effective_success_rate"),
            "failures_missing_stage": agg.get("failures_missing_stage"),
        })

    return {
        "metrics_dir": str(metrics_dir),
        "projects": len(by_project),
        "total_hops": total,
        "by_project": by_project[:50],
    }


def collect_promotion_contract() -> Dict[str, Any]:
    """确认 SoT 为 promotion_gate.yaml（无 multi_agent_gate 双文件）。"""
    root = _repo_root()
    promo = root / "aiPlat-platform/builder/promotion_gate.yaml"
    orphan = root / "aiPlat-platform/builder/multi_agent_gate.yaml"
    return {
        "promotion_gate_yaml": promo.is_file(),
        "promotion_gate_path": str(promo),
        "orphan_multi_agent_gate_yaml": orphan.is_file(),
        "sot": "promotion_gate.yaml",
    }


def build_baseline() -> Dict[str, Any]:
    home = _aiplat_home()
    apps_root = home / "apps"
    return {
        "schema_version": 2,
        "phase": "post-ABC",
        "ts": time.time(),
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "aiplat_home": str(home),
        "multi_agent": collect_multi_ratio(apps_root),
        "conformance": collect_conformance(apps_root),
        "spawn": collect_spawn(home),
        "hops": collect_hops(home),
        "promotion": collect_promotion_contract(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Factory multi-agent baseline / health snapshot (read-only)"
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="Write snapshot under AIPLAT_HOME/builder/baselines/",
    )
    ap.add_argument("--json", action="store_true", help="Print full JSON")
    args = ap.parse_args()

    baseline = build_baseline()
    multi = baseline["multi_agent"]
    conf = baseline["conformance"]
    spawn = baseline["spawn"]
    hops = baseline["hops"]
    promo = baseline["promotion"]

    print("=== Factory multi-agent baseline (post Phase A–C, read-only) ===")
    print(f"home: {baseline['aiplat_home']}")
    print(
        f"manifests: {multi['manifest_count']}  by_mode={multi['by_mode']}  "
        f"multi_ratio={multi['multi_agent_ratio']}"
    )
    print(
        f"conformance: checked={conf.get('checked')} passed={conf.get('passed')} "
        f"failed={conf.get('failed')} pass_rate={conf.get('pass_rate')}"
    )
    if conf.get("error"):
        print(f"conformance_error: {conf['error']}")
    man = conf.get("manifest") or {}
    if "error" in man:
        print(f"manifest_gate_error: {man['error']}")
    elif man:
        print(
            f"manifest_gate: checked={man.get('checked')} passed={man.get('passed')} "
            f"failed={man.get('failed')} pass_rate={man.get('pass_rate')}"
        )
    print(
        f"spawn: persisted={spawn.get('persisted_spawn_events')} "
        f"code_present={spawn.get('spawn_code_present_on_factory_path')} "
        f"factory_gated={spawn.get('factory_spawn_gated')}"
    )
    print(
        f"hops: projects={hops.get('projects')} total={hops.get('total_hops')}"
    )
    print(
        f"promotion_sot: {promo.get('sot')} present={promo.get('promotion_gate_yaml')} "
        f"orphan_multi_agent_gate={promo.get('orphan_multi_agent_gate_yaml')}"
    )

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
