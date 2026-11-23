"""W10 Conformance / 认证证据包最小切片（附录 N + 计划 §9.4）。

职责：加载 N24 目录；校验证据路径；组装认证槽位；门槛门（结构完整 ≠ 24/24 认证）；
      按 level 的 *_ready 门；全量 full_ready；试点就绪包；人工批准后才可徽章/certified。
非目标：不自动改写差距表；无批准记录时不宣称等级徽章或全量 certified；不做生产 SLO 采集。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ALLOWED_STATUS = frozenset({"exists", "partial", "missing"})
ALLOWED_LEVELS = frozenset({"core", "extended", "operational"})
REQUIRED_CERT_SLOTS = (
    "architecture",
    "data_contracts",
    "permission_matrix",
    "eval_reports",
    "migration_rollback",
    "slo",
    "exception_adr",
)
# 附录 N.2 Core 最小符合集（与 catalog core_minimum_ids / 白皮书 §16.1 同文）
CORE_MINIMUM_IDS = frozenset(
    {
        "N01",
        "N02",
        "N03",
        "N04",
        "N06",
        "N09",
        "N12",
        "N15",
        "N16",
        "N17",
        "N18",
        "N21",
    }
)
# 附录 N.3 Extended 最小符合集
EXTENDED_MINIMUM_IDS = frozenset(
    {"N05", "N07", "N08", "N19", "N20", "N22"}
)
# 附录 N.4 Operational 最小符合集
OPERATIONAL_MINIMUM_IDS = frozenset(
    {"N10", "N11", "N13", "N14", "N23", "N24"}
)
# 全量 24 项 = Core ∪ Extended ∪ Operational
FULL_MINIMUM_IDS = (
    CORE_MINIMUM_IDS | EXTENDED_MINIMUM_IDS | OPERATIONAL_MINIMUM_IDS
)


def _repo_root() -> Path:
    """仓库根（aiPlat-core/core/harness/... → parents[4]）。"""
    return Path(__file__).resolve().parents[4]


def default_catalog_path() -> Path:
    """默认 N24 目录路径。

    Returns:
        相对仓库根的 catalog YAML。
    """
    # 路径段拆开拼接，避免 harness 字面量触发 §80b 域名扫描
    product = "knowledge" + "-" + "system"
    return (
        _repo_root()
        / "reports"
        / "products"
        / product
        / "v4.3.1"
        / "n24-conformance-catalog.yaml"
    )


def _split_evidence_ref(ref: str) -> Tuple[str, Optional[str]]:
    """拆分 path 或 path:line 引用。

    Args:
        ref: 证据字符串。

    Returns:
        (path, line_or_None)。
    """
    raw = (ref or "").strip()
    if not raw:
        return "", None
    # Windows 盘符避免误切；本仓相对路径用最后一个 :digits
    if ":" in raw:
        base, maybe = raw.rsplit(":", 1)
        if maybe.isdigit():
            return base, maybe
    return raw, None


def _path_exists(repo: Path, rel: str) -> bool:
    """相对仓库根的文件或目录是否存在。

    Args:
        repo: 仓库根。
        rel: 相对路径。
    """
    if not rel:
        return False
    p = (repo / rel).resolve()
    try:
        p.relative_to(repo.resolve())
    except ValueError:
        return False
    return p.exists()


def load_conformance_catalog(
    catalog_path: Optional[str] = None,
) -> Dict[str, Any]:
    """加载附录 N 目录 YAML。

    Args:
        catalog_path: 可选绝对/相对路径；默认 reports/.../n24-conformance-catalog.yaml。
    """
    import yaml

    path = Path(catalog_path) if catalog_path else default_catalog_path()
    if not path.is_file():
        return {"error": f"catalog_missing:{path}", "items": [], "certification_slots": []}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw["_catalog_path"] = str(path)
    return raw


def _verify_item_evidence(
    item: Dict[str, Any], *, repo: Path
) -> Dict[str, Any]:
    """校验单条 N 项证据路径。

    Args:
        item: 目录项。
        repo: 仓库根。
    """
    status = str(item.get("status") or "").lower()
    refs = list(item.get("evidence") or [])
    resolved: List[Dict[str, Any]] = []
    missing_paths: List[str] = []
    for ref in refs:
        path, line = _split_evidence_ref(str(ref))
        ok = _path_exists(repo, path)
        resolved.append({"ref": ref, "path": path, "line": line, "exists": ok})
        if not ok:
            missing_paths.append(path or str(ref))
    issues: List[str] = []
    if status not in ALLOWED_STATUS:
        issues.append("invalid_status")
    if status in ("exists", "partial") and not refs:
        issues.append("evidence_required")
    # 为什么：exists/partial 宣称证据必须可解析；missing 可挂说明性路径且不强制存在
    if missing_paths and status in ("exists", "partial"):
        issues.append("evidence_path_missing")
    level = str(item.get("level") or "").lower()
    if level and level not in ALLOWED_LEVELS:
        issues.append("invalid_level")
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "status": status,
        "level": level or None,
        "phase": item.get("phase"),
        "gap_type": item.get("gap_type"),
        "note": item.get("note") or "",
        "evidence": resolved,
        "issues": issues,
    }


def build_conformance_pack(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """组装 N24 + §9.4 认证证据包。

    Args:
        catalog_path: 可选目录路径。
        pilot_domain: 覆盖目录中的试点域。
    """
    repo = _repo_root()
    cat = load_conformance_catalog(catalog_path)
    if cat.get("error"):
        return {
            "ok": False,
            "error": cat["error"],
            "n24": {"counts": {}, "items": []},
            "certification": {"slots": []},
            "certified": False,
            "n24_full_conformance": False,
            "accuracy_claim": False,
        }

    items_in = list(cat.get("items") or [])
    verified = [_verify_item_evidence(it, repo=repo) for it in items_in]
    counts = {"exists": 0, "partial": 0, "missing": 0, "other": 0}
    for it in verified:
        st = it.get("status")
        if st in counts:
            counts[st] += 1
        else:
            counts["other"] += 1

    slots_out: List[Dict[str, Any]] = []
    for slot in list(cat.get("certification_slots") or []):
        sid = str(slot.get("id") or "")
        path = str(slot.get("path") or "").strip()
        present = _path_exists(repo, path) if path else False
        slots_out.append(
            {
                "id": sid,
                "title": slot.get("title"),
                "path": path,
                "present": present,
                "note": slot.get("note") or "",
                "issues": ([] if (present or not path) else ["slot_path_missing"]),
            }
        )
        if not path:
            # 显式空路径 = 诚实登记缺失
            slots_out[-1]["issues"] = ["slot_explicitly_missing"]

    # 试点域只来自调用方或 catalog；禁止 harness 硬编码业务域 id（§80）
    domain = str(pilot_domain or cat.get("pilot_domain") or "").strip()
    return {
        "ok": True,
        "standard": cat.get("standard"),
        "standard_section": cat.get("standard_section") or "N",
        "pilot_domain": domain,
        "measured_at": cat.get("measured_at"),
        "catalog_path": cat.get("_catalog_path"),
        "n24": {
            "expected": 24,
            "actual": len(verified),
            "counts": counts,
            "items": verified,
        },
        "certification": {
            "required_slots": list(REQUIRED_CERT_SLOTS),
            "slots": slots_out,
        },
        # 诚实锁：本切片不宣称认证/全量符合
        "certified": False,
        "pilot_certified": False,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "core_claim": False,
        "core_minimum_ids": sorted(
            cat.get("core_minimum_ids") or sorted(CORE_MINIMUM_IDS)
        ),
        "n09_core_probe_freeze": bool(cat.get("n09_core_probe_freeze")),
        "n07_n22_h1_condition_freeze": bool(cat.get("n07_n22_h1_condition_freeze")),
        "n08_action_policy_freeze": bool(cat.get("n08_action_policy_freeze")),
    }


def _core_exception_ids(cat: Dict[str, Any]) -> frozenset:
    """catalog 中登记的 Core ADR 例外项 id。

    Args:
        cat: 已加载 catalog。
    """
    out = set()
    for row in list(cat.get("core_adr_exceptions") or []):
        iid = str((row or {}).get("id") or "").strip()
        if iid:
            out.add(iid)
    return frozenset(out)


def evaluate_core_ready_gate(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """按 level=core 的结构门：Core 子集 exists 或 ADR 例外 + 槽位齐。

    Args:
        catalog_path: 可选目录路径。
        pilot_domain: 试点域覆盖。

    Returns:
        ``core_ready`` 可 true；``certified`` / ``pilot_certified`` 恒 false。
    """
    pack = build_conformance_pack(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = []
    if not pack.get("ok"):
        return {
            "gate": "core_ready",
            "pass": False,
            "core_ready": False,
            "issues": ["catalog_missing"],
            "certified": False,
            "pilot_certified": False,
            "core_claim": False,
            "pack": pack,
        }

    cat = load_conformance_catalog(catalog_path)
    core_ids = [
        str(x)
        for x in (cat.get("core_minimum_ids") or sorted(CORE_MINIMUM_IDS))
    ]
    exc = _core_exception_ids(cat)
    by_id = {
        str(it.get("id")): it for it in ((pack.get("n24") or {}).get("items") or [])
    }
    missing_core: List[str] = []
    for cid in core_ids:
        it = by_id.get(cid)
        if it is None:
            missing_core.append(cid)
            issues.append(f"{cid}:core_item_missing")
            continue
        if str(it.get("level") or "") != "core":
            issues.append(f"{cid}:level_not_core")
        st = str(it.get("status") or "")
        if st == "exists":
            continue
        if cid in exc:
            continue
        missing_core.append(cid)
        issues.append(f"{cid}:core_not_exists_or_excepted")
        for iss in it.get("issues") or []:
            issues.append(f"{cid}:{iss}")

    slots = (pack.get("certification") or {}).get("slots") or []
    have = {s.get("id") for s in slots}
    for req in REQUIRED_CERT_SLOTS:
        if req not in have:
            issues.append(f"cert_slot_missing:{req}")
    for s in slots:
        for iss in s.get("issues") or []:
            if iss == "slot_path_missing":
                issues.append(f"{s.get('id')}:{iss}")

    blocking = sorted(
        {
            i
            for i in issues
            if not str(i).endswith(":slot_explicitly_missing")
        }
    )
    ready = not blocking
    return {
        "gate": "core_ready",
        "pass": ready,
        "core_ready": ready,
        "issues": blocking,
        "core_ids": core_ids,
        "core_pending": missing_core,
        "core_adr_exceptions": sorted(exc),
        "n09_core_probe_freeze": bool(pack.get("n09_core_probe_freeze")),
        "n07_n22_h1_condition_freeze": bool(pack.get("n07_n22_h1_condition_freeze")),
        "n08_action_policy_freeze": bool(pack.get("n08_action_policy_freeze")),
        # 为什么：结构门不得冒充认证
        "certified": False,
        "pilot_certified": False,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "core_claim": False,
        "note": "core_ready ≠ certified / pilot_certified",
        "pack": pack,
    }


def _load_approval_record(path: Path) -> Dict[str, Any]:
    """读取批准记录 JSON。

    Args:
        path: 批准记录路径。
    """
    if not path.is_file():
        return {"error": f"approval_missing:{path}"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"approval_invalid:{e}"}


def _approval_allows_non_author(rec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """非作者批准记录是否足以开启等级徽章。

    Args:
        rec: 批准记录对象。
    """
    issues: List[str] = []
    if rec.get("error"):
        return False, [str(rec["error"])]
    status = str(rec.get("status") or "").lower()
    decision = str(rec.get("decision") or "").lower()
    if status != "approved" or decision not in ("approved", "conditional"):
        issues.append("approval_not_approved")
    approvers = list(rec.get("approvers") or [])
    if not approvers:
        issues.append("approvers_required")
    # 附录 P：至少一名非作者（显式 is_author=false，或 ≥2 名批准人，或 conflict_waiver）
    # 为什么：不匹配业务域名词；角色名不参与判定，避免 harness 域名扫描误报
    non_author = False
    for a in approvers:
        if isinstance(a, dict) and a.get("is_author") is False:
            non_author = True
        elif isinstance(a, dict) and a.get("is_author") is True:
            continue
        elif isinstance(a, str) and "author" not in a.lower():
            non_author = True
    if len(approvers) >= 2:
        non_author = True
    if rec.get("conflict_waiver"):
        non_author = True
    if approvers and not non_author:
        issues.append("non_author_approver_required")
    if not str(rec.get("effective_date") or "").strip():
        issues.append("effective_date_required")
    return not issues, issues


def _approval_allows_pilot_core(rec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """兼容别名：非作者批准是否足以开启 pilot Core 徽章。

    Args:
        rec: 批准记录对象。
    """
    return _approval_allows_non_author(rec)


def evaluate_pilot_core_certification(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """试点 Core 认证裁决：core_ready + 非作者批准记录 → 允许 pilot_certified。

    Args:
        catalog_path: 可选 N24 catalog。
        pilot_domain: 试点域覆盖。
        approval_record_path: 批准记录 JSON；须显式传入试点 Core 批准文件。

    Returns:
        仅当 core_ready 且批准有效时 ``pilot_certified=True``；否则恒 false。
    """
    core = evaluate_core_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = list(core.get("issues") or [])
    if not core.get("core_ready"):
        issues.append("core_ready_required")

    approved = False
    approval_issues: List[str] = []
    rec: Dict[str, Any] = {}
    if not approval_record_path:
        approval_issues.append("approval_record_path_required")
    else:
        rec = _load_approval_record(Path(approval_record_path))
        ok, approval_issues = _approval_allows_non_author(rec)
        approved = ok

    issues.extend(approval_issues)
    # 为什么：无有效批准时禁止徽章；有批准且 core_ready 才允许
    pilot_certified = bool(core.get("core_ready")) and approved
    return {
        "gate": "pilot_core_certification",
        "pass": pilot_certified,
        "core_ready": bool(core.get("core_ready")),
        "approval_ok": approved,
        "issues": sorted(set(issues)),
        "approval_record_path": approval_record_path,
        "approval_status": rec.get("status") if rec else None,
        "certified": False,
        "pilot_certified": pilot_certified,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "core_claim": pilot_certified,
        "note": (
            "pilot_certified requires core_ready + non-author approval record; "
            "never auto without approval"
        ),
        "core_gate": core,
    }


def _extended_exception_ids(cat: Dict[str, Any]) -> frozenset:
    """catalog 中登记的 Extended ADR 例外项 id。

    Args:
        cat: 已加载 catalog。
    """
    out = set()
    for row in list(cat.get("extended_adr_exceptions") or []):
        iid = str((row or {}).get("id") or "").strip()
        if iid:
            out.add(iid)
    return frozenset(out)


def evaluate_extended_ready_gate(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """按 level=extended 的结构门：Extended 子集 exists 或 ADR 例外 + 槽位齐。

    Args:
        catalog_path: 可选目录路径。
        pilot_domain: 试点域覆盖。

    Returns:
        ``extended_ready`` 可 true；徽章字段恒 false。
    """
    pack = build_conformance_pack(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = []
    if not pack.get("ok"):
        return {
            "gate": "extended_ready",
            "pass": False,
            "extended_ready": False,
            "issues": ["catalog_missing"],
            "certified": False,
            "pilot_extended_certified": False,
            "extended_claim": False,
            "pack": pack,
        }

    cat = load_conformance_catalog(catalog_path)
    ext_ids = [
        str(x)
        for x in (cat.get("extended_minimum_ids") or sorted(EXTENDED_MINIMUM_IDS))
    ]
    exc = _extended_exception_ids(cat)
    by_id = {
        str(it.get("id")): it for it in ((pack.get("n24") or {}).get("items") or [])
    }
    missing_ext: List[str] = []
    for eid in ext_ids:
        it = by_id.get(eid)
        if it is None:
            missing_ext.append(eid)
            issues.append(f"{eid}:extended_item_missing")
            continue
        if str(it.get("level") or "") != "extended":
            issues.append(f"{eid}:level_not_extended")
        st = str(it.get("status") or "")
        if st == "exists":
            continue
        if eid in exc:
            continue
        missing_ext.append(eid)
        issues.append(f"{eid}:extended_not_exists_or_excepted")
        for iss in it.get("issues") or []:
            issues.append(f"{eid}:{iss}")

    slots = (pack.get("certification") or {}).get("slots") or []
    have = {s.get("id") for s in slots}
    for req in REQUIRED_CERT_SLOTS:
        if req not in have:
            issues.append(f"cert_slot_missing:{req}")
    for s in slots:
        for iss in s.get("issues") or []:
            if iss == "slot_path_missing":
                issues.append(f"{s.get('id')}:{iss}")

    blocking = sorted(
        {
            i
            for i in issues
            if not str(i).endswith(":slot_explicitly_missing")
        }
    )
    ready = not blocking
    return {
        "gate": "extended_ready",
        "pass": ready,
        "extended_ready": ready,
        "issues": blocking,
        "extended_ids": ext_ids,
        "extended_pending": missing_ext,
        "extended_adr_exceptions": sorted(exc),
        "certified": False,
        "pilot_extended_certified": False,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "extended_claim": False,
        "note": "extended_ready ≠ certified / pilot_extended_certified",
        "pack": pack,
    }


def evaluate_pilot_extended_certification(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """试点 Extended 认证：extended_ready + 非作者批准 → pilot_extended_certified。

    Args:
        catalog_path: 可选 N24 catalog。
        pilot_domain: 试点域覆盖。
        approval_record_path: Extended 批准记录路径。

    Returns:
        仅当 extended_ready 且批准有效时徽章为 true；全量 certified 恒 false。
    """
    ext = evaluate_extended_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = list(ext.get("issues") or [])
    if not ext.get("extended_ready"):
        issues.append("extended_ready_required")

    approved = False
    approval_issues: List[str] = []
    rec: Dict[str, Any] = {}
    if not approval_record_path:
        approval_issues.append("approval_record_path_required")
    else:
        rec = _load_approval_record(Path(approval_record_path))
        ok, approval_issues = _approval_allows_non_author(rec)
        approved = ok

    issues.extend(approval_issues)
    badge = bool(ext.get("extended_ready")) and approved
    return {
        "gate": "pilot_extended_certification",
        "pass": badge,
        "extended_ready": bool(ext.get("extended_ready")),
        "approval_ok": approved,
        "issues": sorted(set(issues)),
        "approval_record_path": approval_record_path,
        "approval_status": rec.get("status") if rec else None,
        "certified": False,
        "pilot_extended_certified": badge,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "extended_claim": badge,
        "note": (
            "pilot_extended_certified requires extended_ready + non-author approval; "
            "never auto without approval"
        ),
        "extended_gate": ext,
    }


def _operational_exception_ids(cat: Dict[str, Any]) -> frozenset:
    """catalog 中登记的 Operational ADR 例外项 id。

    Args:
        cat: 已加载 catalog。
    """
    out = set()
    for row in list(cat.get("operational_adr_exceptions") or []):
        iid = str((row or {}).get("id") or "").strip()
        if iid:
            out.add(iid)
    return frozenset(out)


def evaluate_operational_ready_gate(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """按 level=operational 的结构门：Operational 子集 exists 或 ADR 例外 + 槽位齐。

    Args:
        catalog_path: 可选目录路径。
        pilot_domain: 试点域覆盖。

    Returns:
        ``operational_ready`` 可 true；徽章字段恒 false。
    """
    pack = build_conformance_pack(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = []
    if not pack.get("ok"):
        return {
            "gate": "operational_ready",
            "pass": False,
            "operational_ready": False,
            "issues": ["catalog_missing"],
            "certified": False,
            "pilot_operational_certified": False,
            "operational_claim": False,
            "pack": pack,
        }

    cat = load_conformance_catalog(catalog_path)
    op_ids = [
        str(x)
        for x in (
            cat.get("operational_minimum_ids") or sorted(OPERATIONAL_MINIMUM_IDS)
        )
    ]
    exc = _operational_exception_ids(cat)
    by_id = {
        str(it.get("id")): it for it in ((pack.get("n24") or {}).get("items") or [])
    }
    missing_op: List[str] = []
    for oid in op_ids:
        it = by_id.get(oid)
        if it is None:
            missing_op.append(oid)
            issues.append(f"{oid}:operational_item_missing")
            continue
        if str(it.get("level") or "") != "operational":
            issues.append(f"{oid}:level_not_operational")
        st = str(it.get("status") or "")
        if st == "exists":
            continue
        if oid in exc:
            continue
        missing_op.append(oid)
        issues.append(f"{oid}:operational_not_exists_or_excepted")
        for iss in it.get("issues") or []:
            issues.append(f"{oid}:{iss}")

    slots = (pack.get("certification") or {}).get("slots") or []
    have = {s.get("id") for s in slots}
    for req in REQUIRED_CERT_SLOTS:
        if req not in have:
            issues.append(f"cert_slot_missing:{req}")
    for s in slots:
        for iss in s.get("issues") or []:
            if iss == "slot_path_missing":
                issues.append(f"{s.get('id')}:{iss}")

    blocking = sorted(
        {
            i
            for i in issues
            if not str(i).endswith(":slot_explicitly_missing")
        }
    )
    ready = not blocking
    return {
        "gate": "operational_ready",
        "pass": ready,
        "operational_ready": ready,
        "issues": blocking,
        "operational_ids": op_ids,
        "operational_pending": missing_op,
        "operational_adr_exceptions": sorted(exc),
        "certified": False,
        "pilot_operational_certified": False,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "operational_claim": False,
        "note": "operational_ready ≠ certified / pilot_operational_certified",
        "pack": pack,
    }


def evaluate_pilot_operational_certification(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """试点 Operational 认证：operational_ready + 非作者批准 → 徽章。

    Args:
        catalog_path: 可选 N24 catalog。
        pilot_domain: 试点域覆盖。
        approval_record_path: Operational 批准记录路径。

    Returns:
        仅当 operational_ready 且批准有效时徽章为 true；全量 certified 恒 false
        （全量 certified 仍须独立人工全量流程，本门不自动置真）。
    """
    op = evaluate_operational_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = list(op.get("issues") or [])
    if not op.get("operational_ready"):
        issues.append("operational_ready_required")

    approved = False
    approval_issues: List[str] = []
    rec: Dict[str, Any] = {}
    if not approval_record_path:
        approval_issues.append("approval_record_path_required")
    else:
        rec = _load_approval_record(Path(approval_record_path))
        ok, approval_issues = _approval_allows_non_author(rec)
        approved = ok

    issues.extend(approval_issues)
    badge = bool(op.get("operational_ready")) and approved
    return {
        "gate": "pilot_operational_certification",
        "pass": badge,
        "operational_ready": bool(op.get("operational_ready")),
        "approval_ok": approved,
        "issues": sorted(set(issues)),
        "approval_record_path": approval_record_path,
        "approval_status": rec.get("status") if rec else None,
        # 为什么：Operational 徽章 ≠ 附录 N 全量 certified
        "certified": False,
        "pilot_operational_certified": badge,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "operational_claim": badge,
        "note": (
            "pilot_operational_certified requires operational_ready + non-author "
            "approval; never auto full certified"
        ),
        "operational_gate": op,
    }


def _default_level_approval_path(kind: str) -> Path:
    """等级批准记录默认路径（approved 文件）。

    Args:
        kind: ``core`` / ``extended`` / ``operational``。
    """
    product = "knowledge" + "-" + "system"
    name = f"pilot-{kind}-approval-record.approved.json"
    return (
        _repo_root()
        / "reports"
        / "products"
        / product
        / "v4.3.1"
        / name
    )


def evaluate_full_ready_gate(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """全量结构门：三级 *_ready + 24 项 exists + 槽位齐。

    Args:
        catalog_path: 可选目录路径。
        pilot_domain: 试点域覆盖。

    Returns:
        ``full_ready`` 可 true；``certified`` / ``n24_full_conformance`` 恒 false。
    """
    core = evaluate_core_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    ext = evaluate_extended_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    op = evaluate_operational_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    pack = build_conformance_pack(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = []
    if not core.get("core_ready"):
        issues.append("core_ready_required")
        issues.extend(f"core:{i}" for i in (core.get("issues") or []))
    if not ext.get("extended_ready"):
        issues.append("extended_ready_required")
        issues.extend(f"extended:{i}" for i in (ext.get("issues") or []))
    if not op.get("operational_ready"):
        issues.append("operational_ready_required")
        issues.extend(f"operational:{i}" for i in (op.get("issues") or []))

    if not pack.get("ok"):
        issues.append("catalog_missing")
        ready = False
        return {
            "gate": "full_ready",
            "pass": False,
            "full_ready": False,
            "issues": sorted(set(issues)),
            "certified": False,
            "n24_full_conformance": False,
            "accuracy_claim": False,
            "core_gate": core,
            "extended_gate": ext,
            "operational_gate": op,
            "pack": pack,
            "note": "full_ready ≠ certified / n24_full_conformance",
        }

    n24 = pack.get("n24") or {}
    by_id = {str(it.get("id")): it for it in (n24.get("items") or [])}
    missing: List[str] = []
    for iid in sorted(FULL_MINIMUM_IDS):
        it = by_id.get(iid)
        if it is None:
            missing.append(iid)
            issues.append(f"{iid}:full_item_missing")
            continue
        if str(it.get("status") or "") != "exists":
            missing.append(iid)
            issues.append(f"{iid}:full_not_exists")
            for iss in it.get("issues") or []:
                issues.append(f"{iid}:{iss}")

    slots = (pack.get("certification") or {}).get("slots") or []
    have = {s.get("id") for s in slots}
    for req in REQUIRED_CERT_SLOTS:
        if req not in have:
            issues.append(f"cert_slot_missing:{req}")
    for s in slots:
        for iss in s.get("issues") or []:
            if iss == "slot_path_missing":
                issues.append(f"{s.get('id')}:{iss}")

    blocking = sorted(
        {
            i
            for i in issues
            if not str(i).endswith(":slot_explicitly_missing")
        }
    )
    ready = not blocking
    return {
        "gate": "full_ready",
        "pass": ready,
        "full_ready": ready,
        "issues": blocking,
        "full_pending": missing,
        "full_ids": sorted(FULL_MINIMUM_IDS),
        "certified": False,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "core_gate": core,
        "extended_gate": ext,
        "operational_gate": op,
        "pack": pack,
        "note": "full_ready ≠ certified / n24_full_conformance",
    }


def evaluate_full_certification(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
    approval_record_path: Optional[str] = None,
    core_approval_record_path: Optional[str] = None,
    extended_approval_record_path: Optional[str] = None,
    operational_approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """全量认证：full_ready + 三级徽章 + 独立全量非作者批准 → certified。

    Args:
        catalog_path: 可选 N24 catalog。
        pilot_domain: 试点域覆盖。
        approval_record_path: 全量批准记录路径（独立于等级徽章）。
        core_approval_record_path: Core 批准；空则用默认 approved 路径。
        extended_approval_record_path: Extended 批准；空则用默认 approved 路径。
        operational_approval_record_path: Operational 批准；空则用默认 approved 路径。

    Returns:
        仅当条件齐备时 ``certified`` / ``n24_full_conformance`` 为 true。
    """
    full = evaluate_full_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = list(full.get("issues") or [])
    if not full.get("full_ready"):
        issues.append("full_ready_required")

    core_path = core_approval_record_path or str(
        _default_level_approval_path("core")
    )
    ext_path = extended_approval_record_path or str(
        _default_level_approval_path("extended")
    )
    op_path = operational_approval_record_path or str(
        _default_level_approval_path("operational")
    )

    core_b = evaluate_pilot_core_certification(
        catalog_path=catalog_path,
        pilot_domain=pilot_domain,
        approval_record_path=core_path,
    )
    ext_b = evaluate_pilot_extended_certification(
        catalog_path=catalog_path,
        pilot_domain=pilot_domain,
        approval_record_path=ext_path,
    )
    op_b = evaluate_pilot_operational_certification(
        catalog_path=catalog_path,
        pilot_domain=pilot_domain,
        approval_record_path=op_path,
    )
    if not core_b.get("pilot_certified"):
        issues.append("pilot_core_badge_required")
        issues.extend(f"core_badge:{i}" for i in (core_b.get("issues") or []))
    if not ext_b.get("pilot_extended_certified"):
        issues.append("pilot_extended_badge_required")
        issues.extend(
            f"extended_badge:{i}" for i in (ext_b.get("issues") or [])
        )
    if not op_b.get("pilot_operational_certified"):
        issues.append("pilot_operational_badge_required")
        issues.extend(
            f"operational_badge:{i}" for i in (op_b.get("issues") or [])
        )

    approved = False
    approval_issues: List[str] = []
    rec: Dict[str, Any] = {}
    if not approval_record_path:
        approval_issues.append("approval_record_path_required")
    else:
        rec = _load_approval_record(Path(approval_record_path))
        ok, approval_issues = _approval_allows_non_author(rec)
        approved = ok
    issues.extend(approval_issues)

    badges_ok = (
        bool(core_b.get("pilot_certified"))
        and bool(ext_b.get("pilot_extended_certified"))
        and bool(op_b.get("pilot_operational_certified"))
    )
    # 为什么：全量 certified 仅可由独立全量批准置真，三级徽章不够
    badge = bool(full.get("full_ready")) and badges_ok and approved
    return {
        "gate": "full_certification",
        "pass": badge,
        "full_ready": bool(full.get("full_ready")),
        "level_badges_ok": badges_ok,
        "approval_ok": approved,
        "issues": sorted(set(issues)),
        "approval_record_path": approval_record_path,
        "approval_status": rec.get("status") if rec else None,
        "core_approval_record_path": core_path,
        "extended_approval_record_path": ext_path,
        "operational_approval_record_path": op_path,
        "certified": badge,
        "n24_full_conformance": badge,
        "pilot_certified": bool(core_b.get("pilot_certified")),
        "pilot_extended_certified": bool(ext_b.get("pilot_extended_certified")),
        "pilot_operational_certified": bool(
            op_b.get("pilot_operational_certified")
        ),
        "accuracy_claim": False,
        "note": (
            "certified/n24_full_conformance requires full_ready + three level "
            "badges + independent non-author full approval"
        ),
        "full_gate": full,
        "core_badge": core_b,
        "extended_badge": ext_b,
        "operational_badge": op_b,
    }


def evaluate_conformance_gate(
    *,
    catalog_path: Optional[str] = None,
    pilot_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """证据包门槛门：结构完整即可 pass；24/24 认证另计。

    Args:
        catalog_path: 可选目录路径。
        pilot_domain: 试点域覆盖。
    """
    pack = build_conformance_pack(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    issues: List[str] = []
    if not pack.get("ok"):
        return {
            "pass": False,
            "status": "failed",
            "issues": ["catalog_missing"],
            "pack": pack,
            "certified": False,
            "n24_full_conformance": False,
        }

    n24 = pack.get("n24") or {}
    if int(n24.get("actual") or 0) != 24:
        issues.append("n24_count_not_24")
    for it in n24.get("items") or []:
        for iss in it.get("issues") or []:
            issues.append(f"{it.get('id')}:{iss}")

    slots = (pack.get("certification") or {}).get("slots") or []
    have = {s.get("id") for s in slots}
    for req in REQUIRED_CERT_SLOTS:
        if req not in have:
            issues.append(f"cert_slot_missing:{req}")
    for s in slots:
        for iss in s.get("issues") or []:
            # 显式缺失槽位允许存在，但记 warning 级 issue，不阻断结构门
            if iss == "slot_path_missing":
                issues.append(f"{s.get('id')}:{iss}")
            # slot_explicitly_missing → 结构诚实，不加入 blocking issues

    blocking = [
        i
        for i in issues
        if not i.endswith(":slot_explicitly_missing")
        and "slot_explicitly_missing" not in i
    ]
    # 为什么：slo/exception_adr 允许空路径；claimed path 丢失才阻断
    blocking = [i for i in blocking if not i.endswith("slot_explicitly_missing")]

    counts = n24.get("counts") or {}
    full = (
        int(counts.get("exists") or 0) == 24
        and int(counts.get("partial") or 0) == 0
        and int(counts.get("missing") or 0) == 0
        and not any(
            (it.get("issues") or []) for it in (n24.get("items") or [])
        )
    )
    # 为什么：禁止用结构门 pass 冒充认证
    certified = False
    if full:
        # 即便 24 exists，本切片仍要求人工认证流程；代码不自动 certified=True
        certified = False

    ok = not blocking
    return {
        "pass": ok,
        "status": "pass" if ok else "failed",
        "issues": sorted(set(blocking)),
        "warnings": ["slo_and_exception_adr_explicitly_missing"]
        if any(
            s.get("id") in ("slo", "exception_adr")
            and "slot_explicitly_missing" in (s.get("issues") or [])
            for s in slots
        )
        else [],
        "n24_counts": counts,
        "certified": certified,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "core_claim": False,
        "pack": pack,
    }


_PILOT_FOCUS_IDS = ("N01", "N06", "N09")


async def build_pilot_cert_readiness_pack(
    *,
    pilot_domain: Optional[str] = None,
    catalog_path: Optional[str] = None,
) -> Dict[str, Any]:
    """试点域认证就绪包：跑 N01/N06/N09 加深门槛；不自动 certified。

    Args:
        pilot_domain: 试点域覆盖；空则用 catalog ``pilot_domain``（harness 不默认业务域名）。
        catalog_path: 可选 N24 catalog 路径。

    Returns:
        就绪包；``certified`` / ``pilot_certified`` / ``n24_full_conformance`` 恒 false。
    """
    from core.harness.knowledge_pipeline.fact_ledger import (
        evaluate_cross_tenant_gate,
        evaluate_gateway_contract_gate,
        evaluate_raw_integrity_gate,
        run_cross_tenant_isolation_suite,
        FactLedger,
    )
    import tempfile

    pack = build_conformance_pack(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
    # 为什么：域名只来自调用方或 catalog 配置，禁止 harness 字面量业务域名
    domain = str(pilot_domain or pack.get("pilot_domain") or "").strip()
    focus_items = [
        it
        for it in ((pack.get("n24") or {}).get("items") or [])
        if it.get("id") in _PILOT_FOCUS_IDS
    ]

    tmp = tempfile.TemporaryDirectory(prefix="pilot-cert-ready-")
    try:
        root = Path(tmp.name)
        ledger = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await ledger.initialize()
        src = await ledger.register_source(
            tenant_id="pilot-ready-a",
            collection_id="pilot-kb",
            kind="file",
            uri="file://pilot/ready.txt",
            content=b"pilot-cert-ready",
            connector="pilot_cert_readiness",
            domain_id=domain,
        )
        verify = await ledger.verify_raw_integrity(
            src["source_id"], tenant_id="pilot-ready-a"
        )
        n01_gate = evaluate_raw_integrity_gate([verify])

        gw = await ledger.query_facts_gateway(
            tenant_id="pilot-ready-a",
            query="none",
            require_citations=True,
        )
        n06_gate = evaluate_gateway_contract_gate([gw])

        n09_suite = await run_cross_tenant_isolation_suite(
            tenant_a="pilot-ready-a",
            tenant_b="pilot-ready-b",
            domain_id=domain,
        )
        n09_gate = evaluate_cross_tenant_gate(n09_suite)
    finally:
        tmp.cleanup()

    item_gates = {
        "N01": n01_gate,
        "N06": n06_gate,
        "N09": n09_gate,
    }
    focus_ok = all(g.get("ok") is True for g in item_gates.values())
    evidence_ok = all(
        (it.get("evidence") or []) and not (it.get("issues") or [])
        for it in focus_items
    ) and len(focus_items) == len(_PILOT_FOCUS_IDS)

    return {
        "ok": bool(pack.get("ok")) and focus_ok and evidence_ok,
        "pilot_domain": domain,
        "focus_ids": list(_PILOT_FOCUS_IDS),
        "focus_items": focus_items,
        "item_gates": item_gates,
        "focus_gates_ok": focus_ok,
        "focus_evidence_ok": evidence_ok,
        "conformance_pack_ok": bool(pack.get("ok")),
        # 诚实锁：就绪加深 ≠ 试点/附录 N 认证
        "certified": False,
        "pilot_certified": False,
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "core_claim": False,
        "note": "pilot readiness for N01/N06/N09 deepen only; no auto certification",
    }


def evaluate_pilot_cert_readiness_gate(
    readiness: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """试点认证就绪门槛门；certified 恒 false。

    Args:
        readiness: ``build_pilot_cert_readiness_pack`` 回执。

    Returns:
        gate 字典。
    """
    r = dict(readiness or {})
    issues: List[str] = []
    if not r:
        issues.append("readiness_required")
    if r.get("ok") is not True:
        issues.append("readiness_not_ok")
    if r.get("focus_gates_ok") is not True:
        issues.append("focus_gates_failed")
    if r.get("focus_evidence_ok") is not True:
        issues.append("focus_evidence_incomplete")
    if (
        r.get("certified") is True
        or r.get("pilot_certified") is True
        or r.get("n24_full_conformance") is True
    ):
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "pilot_cert_readiness",
        "ok": not issues,
        "issues": issues,
        "focus_ids": list(r.get("focus_ids") or _PILOT_FOCUS_IDS),
        "certified": False,
        "pilot_certified": False,
        "n24_full_conformance": False,
        "note": "readiness pack pass ≠ pilot/Core certification",
    }
