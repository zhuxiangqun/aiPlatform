"""安全威胁族目录与分族报告（SEC-P0a / P0c，工程态）。

职责
----
加载 threat-family catalog，校验 L1 case 的 ``threat_ids``，并聚合
分族 n/CI 门禁报告；供 CoreFacade / 安全评测面板只读消费。

非目标
------
- 不产出 ``accuracy_claim`` / ``security_certification``
- 不把跨族 Macro ASR 当作可声明指标
- L1 不得承载 T05-exec / T06 / T07 / T08 / T12；不等于工具执行安全
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

REPORT_SCHEMA = "eval.security_family_report.v1"
CATALOG_SCHEMA = "eval.security_threat_family_catalog.v1"


class SecurityFamilyReportError(ValueError):
    """威胁族目录/报告校验失败（fail-closed）。"""


def default_security_seed_dir() -> Path:
    """返回 workspace 内安全评测种子目录。

    Returns:
        ``workspace_seeds/eval/agent_capability/security`` 路径。
    """
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
        / "security"
    )


def default_catalog_path() -> Path:
    """返回默认威胁族目录 YAML 路径。

    Returns:
        ``threat_family_catalog.v1.yaml`` 路径。
    """
    return default_security_seed_dir() / "threat_family_catalog.v1.yaml"


def default_l3_deferred_path() -> Path:
    """返回 L3 执行类威胁延期清单路径。

    Returns:
        ``l3_exec_deferred.v1.json`` 路径。
    """
    return default_security_seed_dir() / "l3_exec_deferred.v1.json"


def load_threat_family_catalog(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """加载并校验威胁族目录 YAML。

    Args:
        path: 可选覆盖路径；默认 ``default_catalog_path()``。

    Returns:
        目录 dict（含 ``schema`` / ``families`` 等）。

    Raises:
        SecurityFamilyReportError: 文件缺失、schema 不匹配或 YAML 不可用。
    """
    p = Path(path) if path else default_catalog_path()
    if not p.is_file():
        raise SecurityFamilyReportError(f"catalog_missing:{p}")
    raw = p.read_text(encoding="utf-8")
    if yaml is None:
        raise SecurityFamilyReportError("pyyaml_required_for_threat_catalog")
    data = yaml.safe_load(raw)
    if not isinstance(data, Mapping):
        raise SecurityFamilyReportError("catalog_not_object")
    out = dict(data)
    if str(out.get("schema") or "") != CATALOG_SCHEMA:
        raise SecurityFamilyReportError(
            f"catalog_schema_mismatch:{out.get('schema')}"
        )
    return out


def l1_allowed_threats(catalog: Optional[Mapping[str, Any]] = None) -> List[str]:
    """列出 L1 允许的威胁族 id。

    Args:
        catalog: 已加载目录；``None`` 时现载默认目录。

    Returns:
        威胁 id 字符串列表。
    """
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    return [str(x) for x in (cat.get("l1_allowed") or [])]


def l1_forbidden_threats(catalog: Optional[Mapping[str, Any]] = None) -> List[str]:
    """列出 L1 禁止的威胁族 id。

    Args:
        catalog: 已加载目录；``None`` 时现载默认目录。

    Returns:
        威胁 id 字符串列表。
    """
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    return [str(x) for x in (cat.get("l1_forbidden") or [])]


def family_min_n(family_id: str, catalog: Optional[Mapping[str, Any]] = None) -> Optional[int]:
    """读取某威胁族的 L5 最小样本量 ``min_n_l5``。

    Args:
        family_id: 威胁族 id。
        catalog: 已加载目录；``None`` 时现载默认目录。

    Returns:
        整数阈值，或无法解析时 ``None``。
    """
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    fams = cat.get("families") if isinstance(cat.get("families"), Mapping) else {}
    row = fams.get(family_id) if isinstance(fams, Mapping) else None
    if not isinstance(row, Mapping):
        return None
    n = row.get("min_n_l5")
    if n is None:
        return None
    try:
        return int(n)
    except (TypeError, ValueError):
        return None


def validate_case_threat_ids(
    case: Mapping[str, Any],
    *,
    catalog: Optional[Mapping[str, Any]] = None,
    require_l1_layer: bool = False,
) -> List[str]:
    """校验 case 的 ``threat_ids``；空列表表示通过。

    Args:
        case: 单条安全 case（须含 ``threat_ids``；可含 ``eval_layer``）。
        catalog: 威胁族目录；``None`` 时现载。
        require_l1_layer: 为真时强制按 L1 允许/禁止表校验。

    Returns:
        错误码列表；空 = ok。
    """
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    errs: List[str] = []
    tids = case.get("threat_ids")
    if not isinstance(tids, list) or not tids:
        errs.append("threat_ids_missing")
        return errs
    fams = cat.get("families") if isinstance(cat.get("families"), Mapping) else {}
    forbidden = set(l1_forbidden_threats(cat))
    allowed_l1 = set(l1_allowed_threats(cat))
    layer = str(case.get("eval_layer") or "").strip().upper()
    for tid in tids:
        sid = str(tid)
        if sid not in fams:
            errs.append(f"unknown_threat_id:{sid}")
            continue
        if require_l1_layer or layer == "L1":
            if sid in forbidden:
                errs.append(f"l1_forbidden_threat:{sid}")
            elif sid not in allowed_l1:
                errs.append(f"l1_not_allowed_threat:{sid}")
    # 防止 L1 假绿：T05-exec 必须走 L3，禁止出现在 L1/空 layer
    if "T05-exec" in {str(x) for x in tids} and layer in {"", "L1"}:
        errs.append("t05_exec_requires_l3")
    return errs


def validate_l1_safety_cases(
    cases: Sequence[Mapping[str, Any]],
    *,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """批量校验 L1 safety cases 的威胁 id 约束。

    Args:
        cases: case 序列。
        catalog: 威胁族目录；``None`` 时现载。

    Returns:
        含 ``ok`` / ``rows`` / 诚实锁字段的校验结果（``accuracy_claim=False``）。
    """
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    rows: List[Dict[str, Any]] = []
    ok = True
    for case in cases:
        errs = validate_case_threat_ids(case, catalog=cat, require_l1_layer=True)
        cid = str(case.get("case_id") or "")
        if errs:
            ok = False
        rows.append({"case_id": cid, "threat_ids": list(case.get("threat_ids") or []), "errors": errs})
    return {
        "schema": "eval.security_l1_case_validate.v1",
        "ok": ok,
        "n_cases": len(cases),
        "rows": rows,
        "l1_allowed": l1_allowed_threats(cat),
        "l1_forbidden": l1_forbidden_threats(cat),
        "honesty": (
            "L1 validates text-layer threat_ids only; "
            "passing ≠ T05-exec / tool execution safety"
        ),
        "accuracy_claim": False,
        "security_certification": False,
    }


def empty_family_bucket(family_id: str, catalog: Mapping[str, Any]) -> Dict[str, Any]:
    """构造未测威胁族的空桶（``report_only``，不可声明）。

    Args:
        family_id: 威胁族 id。
        catalog: 已加载威胁族目录。

    Returns:
        分族统计桶 dict。
    """
    fams = catalog.get("families") if isinstance(catalog.get("families"), Mapping) else {}
    meta = fams.get(family_id) if isinstance(fams, Mapping) else {}
    meta = meta if isinstance(meta, Mapping) else {}
    min_n = family_min_n(family_id, catalog)
    return {
        "threat_id": family_id,
        "name": meta.get("name"),
        "metric": meta.get("metric"),
        "n": 0,
        "successes": 0,
        "rate": None,
        "wilson_ci95": None,
        "min_n_l5": min_n,
        "status": "report_only",  # P0c 在 n/CI 门禁落地后才会改状态
        "claim_eligible": False,
        "note": meta.get("note") or meta.get("status"),
    }


def build_security_family_report(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    catalog: Optional[Mapping[str, Any]] = None,
    subject: Optional[Mapping[str, Any]] = None,
    pack_id: str = "agent.safety.l1",
    eval_layer: str = "L1",
) -> Dict[str, Any]:
    """按威胁族聚合成功率；Macro ASR 标记为不可声明。

    Args:
        by_case: case_id → ``{threat_ids, ok, status?}``；缺族则 n=0 ``report_only``。
        catalog: 威胁族目录；``None`` 时现载。
        subject: 可选 Subject 元数据。
        pack_id: 评测包 id。
        eval_layer: 评测层标签（如 ``L1``）。

    Returns:
        分族报告 dict（``claim_eligible`` / ``accuracy_claim`` 恒为 False）。
    """
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    fams = cat.get("families") if isinstance(cat.get("families"), Mapping) else {}
    buckets: Dict[str, Dict[str, Any]] = {
        str(fid): empty_family_bucket(str(fid), cat) for fid in fams
    }

    total_ok = 0
    total_n = 0
    for _cid, row in (by_case or {}).items():
        if not isinstance(row, Mapping):
            continue
        tids = [str(t) for t in (row.get("threat_ids") or [])]
        if not tids:
            continue
        ok = bool(row.get("ok"))
        for tid in tids:
            if tid not in buckets:
                buckets[tid] = empty_family_bucket(tid, cat)
                buckets[tid]["note"] = "unknown_family_in_results"
            b = buckets[tid]
            b["n"] = int(b["n"]) + 1
            if ok:
                b["successes"] = int(b["successes"]) + 1
            total_n += 1
            if ok:
                total_ok += 1

    for b in buckets.values():
        apply_family_sample_gate(b)

    gate = summarize_family_gates(buckets)
    untested = sorted(fid for fid, b in buckets.items() if int(b["n"]) == 0)
    oos = [str(x) for x in (cat.get("out_of_scope") or [])]
    deferred = []
    for fid, meta in fams.items():
        if isinstance(meta, Mapping) and str(meta.get("status") or "").startswith("deferred"):
            deferred.append(str(fid))

    macro = (float(total_ok) / float(total_n)) if total_n else None
    return {
        "schema": REPORT_SCHEMA,
        "ok": True,
        "eval_layer": eval_layer,
        "pack_id": pack_id,
        "subject": dict(subject) if subject else {},
        "families": buckets,
        "family_gates": gate,
        "macro_asr": macro,
        "macro_asr_not_for_claim": True,
        "untested_threat_families": untested,
        "deferred_threat_families": sorted(deferred),
        "out_of_scope": oos,
        "below_min_n_families": list(gate.get("below_min_n_families") or []),
        "engineering_ready_families": list(gate.get("engineering_ready_families") or []),
        # 禁止自动放行 L5：须另走授权与签核
        "l5_declare_allowed_families": [],
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Per-family n/CI + report_only gate (SEC-P0c). Macro ASR dashboard-only. "
            "engineering_ready ≠ L5 declare ≠ certification. "
            "L1 pass ≠ T05-exec. admit ≠ isolation_covered."
        ),
    }


def apply_family_sample_gate(bucket: Dict[str, Any]) -> Dict[str, Any]:
    """就地写入 Wilson CI 与分族状态；永不把 claim 置真。

    Args:
        bucket: 单族统计桶（含 ``n`` / ``successes`` / ``min_n_l5``）。

    Returns:
        同一 ``bucket``（已突变）。
    """
    from core.apps.eval.service.mode_intersection_rank import wilson_score_ci

    n = int(bucket.get("n") or 0)
    successes = int(bucket.get("successes") or 0)
    min_n = bucket.get("min_n_l5")
    try:
        min_n_i = int(min_n) if min_n is not None else None
    except (TypeError, ValueError):
        min_n_i = None

    if n <= 0:
        bucket["rate"] = None
        bucket["wilson_ci95"] = None
        bucket["status"] = "untested"
        bucket["meets_min_n"] = False
        bucket["claim_eligible"] = False
        return bucket

    rate = float(successes) / float(n)
    lo, hi = wilson_score_ci(successes, n)
    bucket["rate"] = rate
    bucket["wilson_ci95"] = [lo, hi]
    meets = min_n_i is not None and n >= min_n_i
    bucket["meets_min_n"] = bool(meets)
    # 样本量够 → engineering_ready；仍禁止当作 accuracy_claim
    if meets:
        bucket["status"] = "engineering_ready"
    else:
        bucket["status"] = "report_only"
    bucket["claim_eligible"] = False
    return bucket


def summarize_family_gates(buckets: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """汇总分族门禁分组（below_min_n / engineering_ready / untested）。

    Args:
        buckets: threat_id → 分族桶。

    Returns:
        门禁摘要 dict（``accuracy_claim`` 恒 False）。
    """
    below: List[str] = []
    ready: List[str] = []
    untested: List[str] = []
    report_only: List[str] = []
    for fid, b in buckets.items():
        st = str(b.get("status") or "")
        if st == "untested":
            untested.append(str(fid))
        elif st == "engineering_ready":
            ready.append(str(fid))
        elif st == "report_only":
            report_only.append(str(fid))
            below.append(str(fid))
        n = int(b.get("n") or 0)
        min_n = b.get("min_n_l5")
        if n > 0 and min_n is not None and n < int(min_n) and str(fid) not in below:
            below.append(str(fid))
    return {
        "schema": "eval.security_family_gates.v1",
        "below_min_n_families": sorted(set(below)),
        "engineering_ready_families": sorted(ready),
        "report_only_families": sorted(set(report_only)),
        "untested_families": sorted(untested),
        "l5_declare_allowed_families": [],
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Per-threat-family min_n gate. "
            "engineering_ready means n>=min_n_l5 only; "
            "does not unlock L5 declare or accuracy_claim."
        ),
    }


def evaluate_security_family_gates(
    report: Mapping[str, Any],
) -> Dict[str, Any]:
    """从已有分族报告重算并暴露门禁。

    Args:
        report: ``build_security_family_report`` 产出（含 ``families``）。

    Returns:
        门禁摘要，并附回写后的 ``families``。
    """
    fams = report.get("families") if isinstance(report.get("families"), Mapping) else {}
    buckets = {k: dict(v) for k, v in fams.items() if isinstance(v, Mapping)}
    for b in buckets.values():
        apply_family_sample_gate(b)
    gate = summarize_family_gates(buckets)
    gate["families"] = buckets
    gate["macro_asr_not_for_claim"] = True
    return gate


def security_sec_p0c_status(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """SEC-P0c 快照：带 min_n/CI 门禁的分族报告。

    Args:
        by_case: 可选 case 结果映射；缺省空表。

    Returns:
        状态卡 dict（不可声明）。
    """
    report = build_security_family_report(by_case=by_case or {}, eval_layer="L1")
    return {
        "schema": "eval.security_sec_p0c_status.v1",
        "ok": True,
        "slice": "SEC-P0c",
        "family_report": report,
        "family_gates": report.get("family_gates"),
        "below_min_n_families": report.get("below_min_n_families"),
        "engineering_ready_families": report.get("engineering_ready_families"),
        "macro_asr_not_for_claim": True,
        "l5_declare_allowed_families": [],
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
    }


def load_l1_safety_cases_from_seed(
    *, seed_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """从种子目录加载 L1 safety.json cases。

    Args:
        seed_dir: 可选覆盖根目录；默认 ``agent_capability`` 种子根。

    Returns:
        case dict 列表。

    Raises:
        SecurityFamilyReportError: 文件缺失或非数组。
    """
    root = (
        Path(seed_dir)
        if seed_dir
        else Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
    )
    path = root / "cases" / "safety.json"
    if not path.is_file():
        raise SecurityFamilyReportError(f"safety_cases_missing:{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SecurityFamilyReportError("safety_cases_not_array")
    return [dict(x) for x in raw if isinstance(x, Mapping)]


def security_l1_p0a_status() -> Dict[str, Any]:
    """门面友好的 SEC-P0a 状态：目录 + L1 校验 + 标注覆盖报告。

    Returns:
        状态卡；标注覆盖 ≠ 已打分 live 安全跑，``accuracy_claim=False``。
    """
    cat = load_threat_family_catalog()
    cases = load_l1_safety_cases_from_seed()
    validation = validate_l1_safety_cases(cases, catalog=cat)
    # 仅按 case 标注聚合（无跑分结果 → 覆盖率，非攻击成功率）
    by_case = {
        str(c.get("case_id")): {
            "threat_ids": list(c.get("threat_ids") or []),
            "ok": True,  # 仅表示标注存在，不是得分 run
        }
        for c in cases
    }
    # 状态卡展示标注覆盖 n，并显式标 annotation_only，防止误当 claim
    report = build_security_family_report(
        by_case=by_case, catalog=cat, eval_layer="L1", pack_id="agent.safety.l1"
    )
    report["annotation_only"] = True
    report["honesty"] = (
        "SEC-P0a annotation coverage (threat_ids present). "
        "Not a scored live security run. accuracy_claim=false."
    )
    # 标注 n ≠ 攻击成功：清空 rate，改 tagged 状态
    for b in report["families"].values():
        if int(b["n"]) > 0:
            b["status"] = "annotated_l1"
            b["rate"] = None
            b["note"] = (str(b.get("note") or "") + "; annotation_only").strip("; ")

    l3 = {}
    lp = default_l3_deferred_path()
    if lp.is_file():
        l3 = json.loads(lp.read_text(encoding="utf-8"))

    return {
        "schema": "eval.security_sec_p0a_status.v1",
        "ok": bool(validation.get("ok")),
        "slice": "SEC-P0a",
        "validation": validation,
        "family_report": report,
        "l3_exec_deferred": {
            "path": str(lp),
            "status": l3.get("status"),
            "threat_families": l3.get("threat_families"),
            "n_cases": len(l3.get("cases") or []),
        },
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
    }
