"""FDE / 评测 / 知识 → 小朱进化提案台账（受控自演进三域桥）。

扫描缺口或草稿 → 写入 HUMAN_GATE 提案；批准后只做有界落盘/指引，
不宣称 E5、不自动改生产路由/核心代码。

非目标：不绕过 ontology auto_apply=false；不强制跑满 SystemEvolver 发版。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from core.utils.paths import get_aiplat_home

logger = logging.getLogger("aiplat.digital_human.domain_evolution")

DOMAIN_KINDS = ("knowledge_evolve", "eval_coverage", "fde_evolve")


def _receipts_path() -> Path:
    return Path(get_aiplat_home()) / "digital_human" / "domain_evolution_receipts.jsonl"


def _append_receipt(row: Dict[str, Any]) -> str:
    path = _receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return str(path)


def _fp(*parts: str) -> str:
    raw = "|".join(str(p or "").strip() for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _already_pending(kind: str, fingerprint: str) -> Optional[Dict[str, Any]]:
    from core.harness.digital_human.evolution_proposals import (
        STATUS_APPLIED,
        STATUS_APPROVED,
        STATUS_HUMAN_GATE,
        list_evolution_proposals,
    )

    for row in list_evolution_proposals(kind=kind, limit=100):
        pl = row.get("payload") or {}
        if str(pl.get("fingerprint") or "") != fingerprint:
            continue
        if str(row.get("status") or "") in (
            STATUS_HUMAN_GATE,
            STATUS_APPROVED,
            STATUS_APPLIED,
        ):
            return row
    return None


def propose_knowledge_evolve(
    *,
    case_id: str,
    domain_id: str = "",
    reward_ema: float = 0.0,
    note: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    """知识案例 → knowledge_evolve 待批。

    Args:
        case_id: 案例 id。
        domain_id: 域。
        reward_ema: 奖励均值。
        note: 备注。
        tenant_id: 租户。
    """
    from core.harness.digital_human.evolution_proposals import create_evolution_proposal

    cid = (case_id or "").strip()
    if not cid:
        return {"ok": False, "reason": "case_id_required"}
    fingerprint = _fp("knowledge", cid, domain_id)
    existing = _already_pending("knowledge_evolve", fingerprint)
    if existing:
        return {"ok": False, "reason": "already_pending", "proposal": existing}
    from core.harness.digital_human.evolution_goals import goal_progress_for_kind
    from core.harness.digital_human.evolution_optimize import (
        knowledge_target_state_summary,
    )

    gp = goal_progress_for_kind("knowledge_evolve")
    target = knowledge_target_state_summary(
        case_id=cid, domain_id=domain_id, reward_ema=float(reward_ema or 0)
    )
    return create_evolution_proposal(
        kind="knowledge_evolve",
        title=f"知识演化：{cid[:24]}",
        summary=(
            f"案例 {cid}（域 {domain_id or '?'}，reward_ema={reward_ema:.2f}）"
            "建议进入本体演化审阅。批准后只写回执并指引 evolve_ontology_from_case；不自动改图。"
        ),
        payload={
            "fingerprint": fingerprint,
            "case_id": cid,
            "domain_id": domain_id,
            "reward_ema": reward_ema,
            "fitness": float(reward_ema or 0),
            "note": (note or "")[:200],
            "target_state_summary": target,
            "guidance": target + "；auto_apply=false",
            "goal_id": gp.get("goal_id"),
            "goal_progress": gp,
        },
        tenant_id=tenant_id,
    )


def propose_eval_coverage(
    *,
    coverage: float,
    threshold: float,
    missing_ids: Optional[Sequence[str]] = None,
    baseline_missing: bool = False,
    source: str = "scan",
    tenant_id: str = "",
) -> Dict[str, Any]:
    """评测覆盖缺口 → eval_coverage 待批。

    Args:
        coverage: 覆盖率 0-1。
        threshold: 门限。
        missing_ids: 缺失 id。
        baseline_missing: 是否缺测。
        source: 来源。
        tenant_id: 租户。
    """
    from core.harness.digital_human.evolution_proposals import create_evolution_proposal

    miss = [str(x) for x in (missing_ids or []) if str(x).strip()][:30]
    fingerprint = _fp(
        "eval",
        f"{coverage:.4f}",
        f"{threshold:.4f}",
        ",".join(miss[:8]),
        "missing" if baseline_missing else "ok",
    )
    existing = _already_pending("eval_coverage", fingerprint)
    if existing:
        return {"ok": False, "reason": "already_pending", "proposal": existing}
    from core.harness.digital_human.evolution_goals import goal_progress_for_kind
    from core.harness.digital_human.evolution_optimize import build_eval_remediation_plan

    title = "评测覆盖缺测" if baseline_missing else f"评测覆盖缺口 {coverage:.0%}<{threshold:.0%}"
    gp = goal_progress_for_kind("eval_coverage")
    remediation = build_eval_remediation_plan(miss)
    return create_evolution_proposal(
        kind="eval_coverage",
        title=title,
        summary=(
            "需补齐评测库存/能力覆盖后再宣称门禁。"
            if baseline_missing
            else f"覆盖率 {coverage:.2%} 低于门限 {threshold:.2%}；缺失 {len(miss)} 项。"
        ),
        payload={
            "fingerprint": fingerprint,
            "coverage": coverage,
            "threshold": threshold,
            "missing_ids": miss,
            "baseline_missing": baseline_missing,
            "source": source,
            "guidance": "补 inventory/capability report → measure_eval_coverage；不自动改 runs_eval 策略",
            "remediation_plan": remediation,
            "goal_id": gp.get("goal_id"),
            "goal_progress": gp,
        },
        tenant_id=tenant_id,
    )


def propose_fde_evolve(
    *,
    reason: str,
    drafted: int = 0,
    evolved: int = 0,
    coverage: Optional[float] = None,
    baseline_missing: bool = False,
    missing_ids: Optional[Sequence[str]] = None,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """FDE 证据/自演进草稿 → fde_evolve 待批。

    Args:
        reason: 短原因。
        drafted: SystemEvolver 草稿数。
        evolved: 已发布术语数（仅信息）。
        coverage: 证据覆盖。
        baseline_missing: 证据缺测。
        missing_ids: 缺失证据 id。
        tenant_id: 租户。
    """
    from core.harness.digital_human.evolution_proposals import create_evolution_proposal

    miss = [str(x) for x in (missing_ids or []) if str(x).strip()][:30]
    fingerprint = _fp(
        "fde",
        reason,
        str(drafted),
        f"{coverage if coverage is not None else 'na'}",
        ",".join(miss[:8]),
    )
    existing = _already_pending("fde_evolve", fingerprint)
    if existing:
        return {"ok": False, "reason": "already_pending", "proposal": existing}
    from core.harness.digital_human.evolution_goals import goal_progress_for_kind
    from core.harness.digital_human.evolution_optimize import build_fde_completion_plan

    gp = goal_progress_for_kind("fde_evolve")
    completion = build_fde_completion_plan(miss)
    return create_evolution_proposal(
        kind="fde_evolve",
        title=f"FDE 演化：{(reason or 'review')[:40]}",
        summary=(
            f"{reason}；草稿={drafted}，术语发布={evolved}。"
            "批准后写回执；可指引 GET /fde/evolve 审草稿，不自动切交付生产配置。"
        ),
        payload={
            "fingerprint": fingerprint,
            "reason": reason,
            "drafted": drafted,
            "evolved": evolved,
            "coverage": coverage,
            "baseline_missing": baseline_missing,
            "missing_ids": miss,
            "guidance": "审 SystemEvolver 草稿/证据缺口；SolutionArchetype 须人批；不宣称 E5",
            "completion_plan": completion,
            "goal_id": gp.get("goal_id"),
            "goal_progress": gp,
        },
        tenant_id=tenant_id,
    )


def collect_live_knowledge_cases(
    *,
    min_reward: float = 0.8,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """从各域 OntologyCaseStore 收集高奖励案例（只读）。

    Args:
        min_reward: reward_ema 下限。
        limit: 最多条数。
    """
    out: List[Dict[str, Any]] = []
    try:
        from core.harness.knowledge.domain_router import DomainRouter
        from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

        router = DomainRouter()
        domains = list(router.list_domains() or [])[:40]
    except Exception:
        logger.debug("list domains for knowledge cases failed", exc_info=True)
        return []
    for did in domains:
        try:
            store = OntologyCaseStore(str(did))
            cases = store._load() or {}
        except Exception:
            continue
        for cid, case in cases.items():
            try:
                ema = float(getattr(case, "reward_ema", 0) or 0)
            except (TypeError, ValueError):
                ema = 0.0
            if ema < float(min_reward):
                continue
            out.append(
                {
                    "case_id": str(getattr(case, "case_id", None) or cid),
                    "domain_id": str(getattr(case, "domain_id", None) or did),
                    "reward_ema": ema,
                }
            )
            if len(out) >= limit:
                return out
    out.sort(key=lambda r: float(r.get("reward_ema") or 0), reverse=True)
    return out[:limit]


def load_inventory_file(name: str) -> Optional[Dict[str, Any]]:
    """读 ``~/.aiplat/digital_human/{name}.json`` 库存（covered/required）。

    Args:
        name: 文件名不含扩展名，如 eval_inventory / fde_inventory。
    """
    path = Path(get_aiplat_home()) / "digital_human" / f"{name}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("load inventory %s failed", name, exc_info=True)
        return None


def _write_inventory_file(name: str, data: Dict[str, Any]) -> str:
    path = Path(get_aiplat_home()) / "digital_human" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = dict(data)
    blob["updated_at"] = int(time.time())
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def build_fde_inventory_from_delivery_plans() -> Dict[str, Any]:
    """从交付计划骨架 + 已落盘计划生成 FDE 证据库存。

    required_ids = 骨架全部 step id；covered_ids = 任一客户计划中 status=done 的交集。
    无计划时 covered 为空，仍返回完整 required（可扫描缺口）。

    Returns:
        ``{required_ids, covered_ids, source, plan_count, ok}``；骨架失败时 ``ok=False``。
    """
    try:
        # 为什么：harness 禁止直导 apps/；经 CoreFacade 消费 delivery_plan
        from core.api.core_facade import load_fde_delivery_plan_skeleton
    except Exception as e:
        return {"ok": False, "reason": f"import_delivery_plan:{e}", "required_ids": [], "covered_ids": []}

    try:
        sk = load_fde_delivery_plan_skeleton() or {}
    except Exception as e:
        return {"ok": False, "reason": f"skeleton_load_failed:{e}", "required_ids": [], "covered_ids": []}

    required: List[str] = []
    seen: set = set()
    for ph in sk.get("phases") or []:
        if not isinstance(ph, dict):
            continue
        for st in ph.get("steps") or []:
            if not isinstance(st, dict):
                continue
            sid = str(st.get("id") or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            required.append(sid)

    if not required:
        return {
            "ok": False,
            "reason": "empty_skeleton_steps",
            "required_ids": [],
            "covered_ids": [],
        }

    done: set = set()
    plan_count = 0
    plans_dir = Path(get_aiplat_home()) / "fde_delivery_plans"
    if plans_dir.is_dir():
        for path in sorted(plans_dir.glob("*.json")):
            try:
                plan = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                logger.debug("skip unreadable delivery plan %s", path, exc_info=True)
                continue
            if not isinstance(plan, dict):
                continue
            plan_count += 1
            for ph in plan.get("phases") or []:
                if not isinstance(ph, dict):
                    continue
                for st in ph.get("steps") or []:
                    if not isinstance(st, dict):
                        continue
                    if str(st.get("status") or "") != "done":
                        continue
                    sid = str(st.get("id") or "").strip()
                    if sid:
                        done.add(sid)

    covered = [r for r in required if r in done]
    return {
        "ok": True,
        "required_ids": required,
        "covered_ids": covered,
        "source": "delivery_plan_skeleton+plans",
        "plan_count": plan_count,
    }


def refresh_domain_inventories(
    *,
    persist: bool = True,
    only_missing: bool = False,
) -> Dict[str, Any]:
    """从评测能力覆盖刷新 eval 库存；从交付计划骨架/落盘计划生成 FDE 库存。

    Args:
        persist: 是否写入 digital_human/*.json。
        only_missing: True 时仅补写磁盘上缺失的库存（扫描前用，避免覆盖人工文件）。
    """
    out: Dict[str, Any] = {
        "ok": True,
        "eval": None,
        "fde": None,
        "production_write": False,
        "e5_claimed": False,
    }
    # —— 评测：capability coverage → inventory ——
    skip_eval = only_missing and bool((load_inventory_file("eval_inventory") or {}).get("required_ids"))
    if skip_eval:
        existing_ev = load_inventory_file("eval_inventory") or {}
        out["eval"] = {"ok": True, "source": "existing_file", **existing_ev}
    else:
        try:
            # 为什么：harness 禁止直导 apps/；经 CoreFacade 消费 capability coverage
            from core.api.core_facade import eval_analyze_capability_coverage

            report = eval_analyze_capability_coverage()
            gaps = report.get("gaps") if isinstance(report, dict) else None
            required: List[str] = []
            covered: List[str] = []
            if isinstance(gaps, list) and gaps:
                for g in gaps:
                    if not isinstance(g, dict):
                        continue
                    cid = str(g.get("capability_id") or "").strip()
                    if not cid:
                        continue
                    required.append(cid)
                    if g.get("ok"):
                        covered.append(cid)
            elif isinstance(report, dict):
                required = [str(x) for x in (report.get("in_scope") or []) if str(x).strip()]
                # 无 gaps 时用 covered 计数截断（弱信号，仅作扫描输入）
                n = int(report.get("covered_capabilities") or 0)
                covered = required[: max(0, min(n, len(required)))]
            if required:
                inv = {
                    "required_ids": required,
                    "covered_ids": covered,
                    "source": "capability_coverage",
                    "subject_kind": (report or {}).get("subject_kind"),
                }
                if persist:
                    inv["path"] = _write_inventory_file("eval_inventory", inv)
                out["eval"] = inv
            else:
                out["eval"] = {"ok": False, "reason": "empty_capability_scope"}
        except Exception as e:
            logger.debug("refresh eval inventory failed", exc_info=True)
            out["eval"] = {"ok": False, "reason": f"eval_refresh_failed:{e}"}

    # —— FDE：交付计划骨架 + 落盘计划；失败再回退 last_run / 已有文件 ——
    skip_fde = only_missing and bool((load_inventory_file("fde_inventory") or {}).get("required_ids"))
    if skip_fde:
        existing_fde = load_inventory_file("fde_inventory") or {}
        out["fde"] = {"ok": True, "source": "existing_file", **existing_fde}
    else:
        built = build_fde_inventory_from_delivery_plans()
        if built.get("ok") and built.get("required_ids"):
            inv = {
                "required_ids": list(built.get("required_ids") or []),
                "covered_ids": list(built.get("covered_ids") or []),
                "source": built.get("source") or "delivery_plan_skeleton+plans",
                "plan_count": int(built.get("plan_count") or 0),
            }
            if persist:
                inv["path"] = _write_inventory_file("fde_inventory", inv)
            out["fde"] = inv
        else:
            existing_fde = load_inventory_file("fde_inventory")
            if existing_fde and existing_fde.get("required_ids"):
                out["fde"] = {"ok": True, "source": "existing_file", **existing_fde}
            else:
                try:
                    path = Path(get_aiplat_home()) / "evolution" / "last_run.json"
                    if path.is_file():
                        data = json.loads(path.read_text(encoding="utf-8")) or {}
                        inv_raw = data.get("fde_inventory") if isinstance(data, dict) else None
                        if isinstance(inv_raw, dict) and inv_raw.get("required_ids"):
                            inv = {
                                "required_ids": list(inv_raw.get("required_ids") or []),
                                "covered_ids": list(inv_raw.get("covered_ids") or []),
                                "source": "evolution_last_run",
                            }
                            if persist:
                                inv["path"] = _write_inventory_file("fde_inventory", inv)
                            out["fde"] = inv
                        else:
                            out["fde"] = {
                                "ok": False,
                                "reason": str(built.get("reason") or "no_fde_inventory"),
                                "note": "delivery_plan skeleton empty; place fde_inventory.json",
                            }
                    else:
                        out["fde"] = {
                            "ok": False,
                            "reason": str(built.get("reason") or "no_fde_inventory"),
                        }
                except Exception as e:
                    out["fde"] = {"ok": False, "reason": f"fde_refresh_failed:{e}"}
    return out


def apply_domain_evolution_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """有界应用三域提案（回执 + 知识域尽力 enqueue，仍 auto_apply=false）。

    Args:
        proposal: 提案 dict。
    """
    kind = str(proposal.get("kind") or "")
    payload = dict(proposal.get("payload") or {})
    row = {
        "proposal_id": proposal.get("id"),
        "kind": kind,
        "payload": payload,
        "ts": int(time.time()),
        "production_write": False,
        "production_model_changed": False,
        "auto_apply": False,
        "e5_claimed": False,
    }
    enqueue: Dict[str, Any] = {"status": "skipped"}
    if kind == "knowledge_evolve":
        case_id = str(payload.get("case_id") or "").strip()
        if case_id:
            try:
                import asyncio

                from core.harness.knowledge.ontology_case_learning import (
                    maybe_enqueue_evolution_proposal,
                )

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    # WS/热路径：调度后台任务，避免 asyncio.run 嵌套
                    async def _bg() -> None:
                        try:
                            await maybe_enqueue_evolution_proposal(
                                case_id,
                                author="dh-domain-evolution",
                            )
                        except Exception:
                            logger.debug(
                                "background ontology enqueue failed case=%s",
                                case_id,
                                exc_info=True,
                            )

                    asyncio.create_task(_bg())
                    enqueue = {
                        "status": "scheduled",
                        "case_id": case_id,
                        "auto_apply": False,
                        "note": "create_task scheduled; still auto_apply=false",
                    }
                else:
                    enqueue = asyncio.run(
                        maybe_enqueue_evolution_proposal(
                            case_id,
                            author="dh-domain-evolution",
                        )
                    )
                    enqueue = dict(enqueue or {})
                    enqueue["auto_apply"] = False
            except Exception as e:
                enqueue = {"status": "error", "error": str(e)[:200], "auto_apply": False}
        row["enqueue"] = enqueue
    path = _append_receipt(row)
    return {
        "applied": True,
        "path": path,
        "guidance": payload.get("guidance") or "",
        "kind": kind,
        "enqueue": enqueue,
        "production_write": False,
        "production_model_changed": False,
        "auto_apply": False,
        "e5_claimed": False,
        "note": "receipt (+ optional ontology enqueue draft); native human gates remain",
    }


def scan_domain_evolution_proposals(
    *,
    eval_inventory: Optional[Dict[str, Any]] = None,
    fde_inventory: Optional[Dict[str, Any]] = None,
    knowledge_cases: Optional[Sequence[Dict[str, Any]]] = None,
    include_evolver_snapshot: bool = True,
    use_fixtures_if_empty: bool = False,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """扫描三域并幂等写入待批提案。

    Args:
        eval_inventory: ``{covered_ids, required_ids}`` 或 None。
        fde_inventory: 同上。
        knowledge_cases: ``[{case_id, domain_id, reward_ema}]``。
        include_evolver_snapshot: 读 evolution/last_run.json。
        use_fixtures_if_empty: 测试用夹具（生产默认 false）。
        tenant_id: 租户。
    """
    from core.harness.evo_compute.coverage import (
        EVAL_THRESHOLD,
        FDE_THRESHOLD,
        default_g2_eval_inventory_fixture,
        default_g2_fde_inventory_fixture,
        measure_eval_coverage_from_inventory,
        measure_fde_evidence_coverage_from_inventory,
        measure_eval_coverage,
        measure_fde_evidence_coverage,
    )

    created: List[str] = []
    skipped: List[Dict[str, str]] = []
    details: List[Dict[str, Any]] = []
    live_meta: Dict[str, Any] = {
        "knowledge": 0,
        "eval_file": False,
        "fde_file": False,
        "refreshed": False,
    }

    # 扫描前：未显式传入且非夹具时，补写磁盘缺失的 eval/fde 库存（only_missing 不覆盖人工文件）
    if not use_fixtures_if_empty and eval_inventory is None and fde_inventory is None:
        eval_missing = not bool((load_inventory_file("eval_inventory") or {}).get("required_ids"))
        fde_missing = not bool((load_inventory_file("fde_inventory") or {}).get("required_ids"))
        if eval_missing or fde_missing:
            try:
                refresh_meta = refresh_domain_inventories(persist=True, only_missing=True)
                live_meta["refreshed"] = True
                live_meta["refresh"] = {
                    "eval_ok": bool(
                        (refresh_meta.get("eval") or {}).get("required_ids")
                    ),
                    "fde_ok": bool((refresh_meta.get("fde") or {}).get("required_ids")),
                    "eval_missing": eval_missing,
                    "fde_missing": fde_missing,
                }
            except Exception:
                logger.debug("refresh_domain_inventories failed", exc_info=True)

    # 活源：未显式传入时读磁盘库存 + 高奖励案例
    if knowledge_cases is None:
        knowledge_cases = collect_live_knowledge_cases()
        live_meta["knowledge"] = len(knowledge_cases)
    if eval_inventory is None:
        loaded = load_inventory_file("eval_inventory")
        if loaded:
            eval_inventory = loaded
            live_meta["eval_file"] = True
    if fde_inventory is None:
        loaded = load_inventory_file("fde_inventory")
        if loaded:
            fde_inventory = loaded
            live_meta["fde_file"] = True

    # —— 评测 ——
    ev_inv = dict(eval_inventory or {})
    if not ev_inv.get("required_ids") and use_fixtures_if_empty:
        ev_inv = default_g2_eval_inventory_fixture(meet_threshold=False)
    if ev_inv.get("required_ids"):
        ev = measure_eval_coverage_from_inventory(
            covered_ids=ev_inv.get("covered_ids"),
            required_ids=ev_inv.get("required_ids"),
        )
    else:
        ev = measure_eval_coverage(None)
    if ev.get("baseline_missing") or not ev.get("meets_g2_threshold"):
        r = propose_eval_coverage(
            coverage=float(ev.get("coverage") or 0),
            threshold=float(ev.get("threshold") or EVAL_THRESHOLD),
            missing_ids=ev.get("missing_ids") or [],
            baseline_missing=bool(ev.get("baseline_missing")),
            source=str(ev.get("source") or "scan"),
            tenant_id=tenant_id,
        )
        details.append({"domain": "eval", **{k: r.get(k) for k in ("ok", "reason")}})
        if r.get("ok"):
            created.append("eval_coverage")
        else:
            skipped.append({"domain": "eval", "reason": str(r.get("reason"))})

    # —— FDE 证据 ——
    fd_inv = dict(fde_inventory or {})
    if not fd_inv.get("required_ids") and use_fixtures_if_empty:
        fd_inv = default_g2_fde_inventory_fixture(meet_threshold=False)
    if fd_inv.get("required_ids"):
        fd = measure_fde_evidence_coverage_from_inventory(
            covered_ids=fd_inv.get("covered_ids"),
            required_ids=fd_inv.get("required_ids"),
        )
    else:
        fd = measure_fde_evidence_coverage(None)
    need_fde = fd.get("baseline_missing") or not fd.get("meets_g2_threshold")

    drafted = 0
    evolved = 0
    if include_evolver_snapshot:
        try:
            path = Path(get_aiplat_home()) / "evolution" / "last_run.json"
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8")) or {}
                if isinstance(data, dict):
                    drafted = int(data.get("drafted") or data.get("draft_count") or 0)
                    evolved = int(data.get("evolved") or data.get("evolved_count") or 0)
        except Exception:
            logger.debug("read evolver snapshot failed", exc_info=True)

    if need_fde or drafted > 0:
        reason = (
            "证据缺测"
            if fd.get("baseline_missing")
            else (
                "证据覆盖不足"
                if not fd.get("meets_g2_threshold")
                else f"自演进草稿待审×{drafted}"
            )
        )
        r = propose_fde_evolve(
            reason=reason,
            drafted=drafted,
            evolved=evolved,
            coverage=None if fd.get("baseline_missing") else float(fd.get("coverage") or 0),
            baseline_missing=bool(fd.get("baseline_missing")),
            missing_ids=fd.get("missing_ids") or [],
            tenant_id=tenant_id,
        )
        details.append({"domain": "fde", **{k: r.get(k) for k in ("ok", "reason")}})
        if r.get("ok"):
            created.append("fde_evolve")
        else:
            skipped.append({"domain": "fde", "reason": str(r.get("reason"))})

    # —— 知识案例 ——
    cases = list(knowledge_cases or [])
    if not cases and use_fixtures_if_empty:
        cases = [
            {
                "case_id": "fixture.case.high",
                "domain_id": "fixture-domain",
                "reward_ema": 0.92,
            }
        ]
    for case in cases[:20]:
        if not isinstance(case, dict):
            continue
        cid = str(case.get("case_id") or "").strip()
        if not cid:
            continue
        try:
            ema = float(case.get("reward_ema") or 0)
        except (TypeError, ValueError):
            ema = 0.0
        if ema < 0.8 and not use_fixtures_if_empty:
            skipped.append({"domain": "knowledge", "reason": "reward_below_threshold", "case_id": cid})
            continue
        r = propose_knowledge_evolve(
            case_id=cid,
            domain_id=str(case.get("domain_id") or ""),
            reward_ema=ema,
            note=str(case.get("note") or ""),
            tenant_id=tenant_id,
        )
        details.append({"domain": "knowledge", "case_id": cid, **{k: r.get(k) for k in ("ok", "reason")}})
        if r.get("ok"):
            created.append(f"knowledge_evolve:{cid}")
        else:
            skipped.append({"domain": "knowledge", "reason": str(r.get("reason")), "case_id": cid})

    # —— Phase B1：低好评轨迹 → seed_qa 草稿（人批；不改选模）——
    if not use_fixtures_if_empty:
        try:
            from core.harness.digital_human.evolution_optimize import (
                propose_from_low_rated_trajectories,
            )

            low = propose_from_low_rated_trajectories(limit=5, tenant_id=tenant_id)
            live_meta["low_rated"] = {
                "created": len(low.get("created") or []),
                "skipped": int(low.get("skipped") or 0),
            }
            for pid in low.get("created") or []:
                created.append(f"seed_qa:{pid}")
            details.append(
                {
                    "domain": "consultant",
                    "ok": bool(low.get("ok")),
                    "created_n": len(low.get("created") or []),
                }
            )
        except Exception:
            logger.debug("low-rated trajectory scan failed", exc_info=True)

    from core.harness.digital_human.evolution_proposals import pending_human_gate_count

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "details": details,
        "live": live_meta,
        "pending": pending_human_gate_count(),
        "production_write": False,
        "e5_claimed": False,
        "note": "scan→HUMAN_GATE only; fixtures≠production L4; live files optional",
    }


def domain_evolution_brief_line() -> str:
    """简报：三域待批提案计数。"""
    from core.harness.digital_human.evolution_proposals import (
        STATUS_HUMAN_GATE,
        list_evolution_proposals,
    )

    counts = {k: 0 for k in DOMAIN_KINDS}
    for kind in DOMAIN_KINDS:
        counts[kind] = len(
            list_evolution_proposals(status=STATUS_HUMAN_GATE, kind=kind, limit=50)
        )
    total = sum(counts.values())
    if total == 0:
        return "领域进化(FDE/评测/知识): 0 条待批（可说「扫描领域进化」）"
    bits = "，".join(f"{k}×{v}" for k, v in counts.items() if v)
    return f"领域进化(FDE/评测/知识): {total} 条待批（{bits}）；批准只写回执，不宣称 E5"
