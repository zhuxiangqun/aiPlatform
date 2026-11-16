"""W10 Conformance / 认证证据包最小切片（附录 N + 计划 §9.4）。

职责：加载 N24 目录；校验证据路径；组装认证槽位；门槛门（结构完整 ≠ 24/24 认证）。
非目标：不自动改写差距表；不宣称 Core/认证通过；不做生产 SLO 采集。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ALLOWED_STATUS = frozenset({"exists", "partial", "missing"})
REQUIRED_CERT_SLOTS = (
    "architecture",
    "data_contracts",
    "permission_matrix",
    "eval_reports",
    "migration_rollback",
    "slo",
    "exception_adr",
)


def _repo_root() -> Path:
    """仓库根（aiPlat-core/core/harness/... → parents[4]）。"""
    return Path(__file__).resolve().parents[4]


def default_catalog_path() -> Path:
    """默认 N24 目录路径。

    Returns:
        相对仓库根的 catalog YAML。
    """
    return (
        _repo_root()
        / "reports"
        / "products"
        / "knowledge-system"
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
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "status": status,
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

    domain = pilot_domain or cat.get("pilot_domain") or "lock-service"
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
        "n24_full_conformance": False,
        "accuracy_claim": False,
        "core_claim": False,
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
