"""
Case Pack 运维：草稿扩包 / version++ / holdout / 难度与裁判校准 / 覆盖摘要。

职责
----
在非 frozen 工作区 pack 上追加用例、升版本、打 holdout、启发式/人工难度与
judge 校准 ticket；覆盖率仅做库存盘点。持久化经 case_pack_registry。

非目标
------
- 不把 ``claim_eligible`` / ``accuracy_claim`` 打开（诚实锁保持关闭）
- 不就地改写 frozen pack（必须 bump 出新 draft）
- 不做 HTTP；异常用 ``CasePackOpsError`` 留给上层映射
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_factory import (
    CaseFactoryError,
    dedupe_cases_by_hash,
    generate_cases_from_template,
)
from core.apps.eval.service.case_calibration import (
    CaseCalibrationError,
    apply_difficulty_labels,
    close_judge_ticket,
    create_judge_ticket,
    load_judge_ticket,
    record_judge_ratings,
    save_difficulty_calibration_record,
)
from core.apps.eval.service.case_generation import (
    CaseGenerationError,
    apply_holdout_flags,
    cases_from_trace,
    generate_llm_candidate_cases,
    mutate_cases,
    partition_holdout,
    propose_difficulty,
)
from core.apps.eval.service.case_pack_hash import compute_pack_hash
from core.apps.eval.service.case_pack_legacy import assert_claim_eligible_allowed
from core.apps.eval.service.case_pack_registry import (
    PackRegistryError,
    assert_pack_acl,
    get_pack_version,
    load_pack_payload,
    load_registry,
    register_pack_version,
    update_pack_version_meta,
    write_pack_payload,
)

_EXPANDABLE_STATUSES = frozenset({"draft", "in_review", "rejected"})


class CasePackOpsError(ValueError):
    """
    Case Pack 扩包 / 升版 / 覆盖操作失败。
    """


def _semver_bump_patch(version: str) -> str:
    ver = str(version or "").strip() or "0.1.0"
    parts = ver.split(".")
    if len(parts) >= 3 and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    if len(parts) == 2 and parts[-1].isdigit():
        return f"{parts[0]}.{int(parts[1]) + 1}.0"
    if ver.isdigit():
        return str(int(ver) + 1)
    return f"{ver}.1"


def expand_draft_workspace_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    template: Optional[Mapping[str, Any]] = None,
    variants: Optional[Sequence[Mapping[str, Any]]] = None,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    向非 frozen 的 draft/in_review/rejected pack 追加用例（去重）。

    Args:
        pack_id: 包 ID。
        version: 当前版本。
        workspace_id: 工作区 ID。
        cases: 直接追加的用例列表；与 template/variants 二选一。
        template: 用例模板（配合 variants）。
        variants: 模板变体列表。
        caller_workspace_id: ACL 调用方工作区；空则回落 workspace_id。

    Returns:
        含 ``n_cases`` / ``added`` / ``pack_hash``；诚实字段保持关闭。

    Raises:
        CasePackOpsError: 缺参、frozen、状态不可扩、或注册表失败。
    """
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CasePackOpsError("workspace_id required")
    pid = str(pack_id).strip()
    ver = str(version).strip()
    try:
        cur = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    st = str(cur.get("status") or "").lower()
    kind = str(cur.get("kind") or "").lower()
    if kind == "frozen":
        raise CasePackOpsError(
            "frozen pack immutable — use bump_workspace_pack_version (version++)"
        )
    if st not in _EXPANDABLE_STATUSES:
        raise CasePackOpsError(
            f"expand requires status in {sorted(_EXPANDABLE_STATUSES)}, got {st!r}"
        )

    try:
        payload = load_pack_payload(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    existing = list(payload.get("cases") or [])
    extra: List[Dict[str, Any]] = []
    if cases is not None:
        extra.extend(dict(c) for c in cases)
    elif template is not None or variants is not None:
        try:
            extra.extend(
                generate_cases_from_template(
                    dict(template or {}),
                    variants=list(variants or [{}]),
                )
            )
        except CaseFactoryError as e:
            raise CasePackOpsError(str(e)) from e
    else:
        raise CasePackOpsError("cases or template/variants required")

    before_n = len(existing)
    merged = dedupe_cases_by_hash([*existing, *extra])
    added = len(merged) - before_n
    if added <= 0 and len(merged) == before_n:
        return {
            "ok": True,
            "pack_id": pid,
            "version": ver,
            "n_cases": before_n,
            "added": 0,
            "noop": True,
            "pack_hash": cur.get("hash"),
            "claim_eligible": False,
            "accuracy_claim": False,
            "honesty": "no new cases after dedupe; claim closed",
        }

    ots = list(cur.get("object_types") or ["agent"])
    k = kind or "curated"
    assert_claim_eligible_allowed(kind=k, claim_eligible=False)
    new_hash = compute_pack_hash(
        pack_id=pid,
        version=ver,
        kind=k,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=merged,
    )
    try:
        meta = update_pack_version_meta(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
            pack_hash=new_hash,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    write_pack_payload(
        pack_id=pid,
        version=ver,
        scope="workspace",
        cases=merged,
        meta={
            "kind": k,
            "claim_eligible": False,
            "hash": new_hash,
            "object_types": ots,
            "status": st,
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "n_cases": len(merged),
        "added": max(0, len(merged) - before_n),
        "pack_hash": new_hash,
        "prior_hash": cur.get("hash"),
        "registry": meta,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "expanded non-frozen pack; claim_eligible=false",
    }


def bump_workspace_pack_version(
    *,
    pack_id: str,
    from_version: str,
    workspace_id: str,
    to_version: str = "",
    extra_cases: Optional[Sequence[Mapping[str, Any]]] = None,
    template: Optional[Mapping[str, Any]] = None,
    variants: Optional[Sequence[Mapping[str, Any]]] = None,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    version++：把用例拷到新 draft curated 版本（永不就地改 frozen）。

    Args:
        pack_id: 包 ID。
        from_version: 源版本。
        workspace_id: 工作区 ID。
        to_version: 目标版本；空则对 from_version 做 patch bump。
        extra_cases: 额外追加用例。
        template: 模板（可选）。
        variants: 模板变体（可选）。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        新版本元数据与 ``pack_hash``；``claim_eligible=false``。

    Raises:
        CasePackOpsError: 无用例、版本冲突或注册失败。
    """
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CasePackOpsError("workspace_id required")
    pid = str(pack_id).strip()
    src_ver = str(from_version).strip()
    try:
        src = get_pack_version(
            pack_id=pid,
            version=src_ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
        payload = load_pack_payload(
            pack_id=pid,
            version=src_ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    cases = [dict(c) for c in (payload.get("cases") or [])]
    if extra_cases:
        cases.extend(dict(c) for c in extra_cases)
    if template is not None or variants is not None:
        try:
            cases.extend(
                generate_cases_from_template(
                    dict(template or {}),
                    variants=list(variants or [{}]),
                )
            )
        except CaseFactoryError as e:
            raise CasePackOpsError(str(e)) from e
    cleaned = dedupe_cases_by_hash(cases)
    if not cleaned:
        raise CasePackOpsError("no cases to bump after dedupe")

    new_ver = str(to_version or "").strip() or _semver_bump_patch(src_ver)
    if new_ver == src_ver:
        raise CasePackOpsError("to_version must differ from from_version")

    ots = list(src.get("object_types") or ["agent"])
    # New lineage always starts as curated draft (even if source was frozen).
    kind = "curated"
    assert_claim_eligible_allowed(kind=kind, claim_eligible=False)
    pack_hash = compute_pack_hash(
        pack_id=pid,
        version=new_ver,
        kind=kind,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=cleaned,
    )
    try:
        meta = register_pack_version(
            pack_id=pid,
            version=new_ver,
            kind=kind,
            claim_eligible=False,
            scope="workspace",
            pack_hash=pack_hash,
            object_types=ots,
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
            status="draft",
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    write_pack_payload(
        pack_id=pid,
        version=new_ver,
        scope="workspace",
        cases=cleaned,
        meta={
            "kind": kind,
            "claim_eligible": False,
            "hash": pack_hash,
            "object_types": ots,
            "status": "draft",
            "bumped_from": src_ver,
            "source_kind": src.get("kind"),
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "from_version": src_ver,
        "version": new_ver,
        "kind": kind,
        "status": "draft",
        "n_cases": len(cleaned),
        "pack_hash": pack_hash,
        "registry": meta,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            "version++ creates draft curated; source frozen untouched; "
            "claim_eligible=false"
        ),
    }


def mark_pack_holdout(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    case_ids: Optional[Sequence[str]] = None,
    ratio: float = 0.0,
    seed: str = "0",
    holdout: bool = True,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    在非 frozen pack 上标记 holdout 并重算 hash。

    Args:
        pack_id: 包 ID。
        version: 版本。
        workspace_id: 工作区 ID。
        case_ids: 指定 case；空则按 ratio/seed 抽样。
        ratio: 抽样比例（无 case_ids 时）。
        seed: 抽样种子。
        holdout: True 标记为 holdout，False 取消。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        含 ``n_eval`` / ``n_holdout`` / ``pack_hash``。

    Raises:
        CasePackOpsError: frozen 或状态不允许。
    """
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CasePackOpsError("workspace_id required")
    pid = str(pack_id).strip()
    ver = str(version).strip()
    try:
        cur = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
        payload = load_pack_payload(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e
    if str(cur.get("kind") or "").lower() == "frozen":
        raise CasePackOpsError("frozen pack immutable — bump first")
    st = str(cur.get("status") or "").lower()
    if st not in _EXPANDABLE_STATUSES:
        raise CasePackOpsError(
            f"holdout mark requires status in {sorted(_EXPANDABLE_STATUSES)}, got {st!r}"
        )
    try:
        updated_cases = apply_holdout_flags(
            list(payload.get("cases") or []),
            case_ids=case_ids,
            ratio=ratio,
            seed=seed,
            holdout=holdout,
        )
    except CaseGenerationError as e:
        raise CasePackOpsError(str(e)) from e
    parts = partition_holdout(updated_cases)
    ots = list(cur.get("object_types") or ["agent"])
    kind = str(cur.get("kind") or "curated")
    assert_claim_eligible_allowed(kind=kind, claim_eligible=False)
    new_hash = compute_pack_hash(
        pack_id=pid,
        version=ver,
        kind=kind,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=updated_cases,
    )
    try:
        meta = update_pack_version_meta(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
            pack_hash=new_hash,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e
    write_pack_payload(
        pack_id=pid,
        version=ver,
        scope="workspace",
        cases=updated_cases,
        meta={
            "kind": kind,
            "claim_eligible": False,
            "hash": new_hash,
            "object_types": ots,
            "status": st,
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "pack_hash": new_hash,
        "n_eval": parts["n_eval"],
        "n_holdout": parts["n_holdout"],
        "registry": meta,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "holdout flags only; not an accuracy claim",
    }


def publish_generated_workspace_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    kind: str,
    cases: Sequence[Mapping[str, Any]],
    caller_workspace_id: str = "",
    object_types: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    发布 L3 draft pack（kind=generated|trace）；强制 ``claim_eligible=false``。

    Args:
        pack_id: 包 ID。
        version: 版本。
        workspace_id: 工作区 ID。
        kind: ``generated`` 或 ``trace``。
        cases: 用例序列。
        caller_workspace_id: ACL 调用方工作区。
        object_types: 对象类型列表；默认 agent。

    Returns:
        工厂发布结果 dict。

    Raises:
        CasePackOpsError: kind 非法或工厂失败。
    """
    from core.apps.eval.service.case_factory import publish_draft_workspace_pack

    k = str(kind or "").strip().lower()
    if k not in ("generated", "trace"):
        raise CasePackOpsError("kind must be generated|trace for L3 publish")
    try:
        return publish_draft_workspace_pack(
            pack_id=pack_id,
            version=version,
            cases=cases,
            workspace_id=workspace_id,
            caller_workspace_id=caller_workspace_id,
            object_types=object_types,
            kind=k,
        )
    except CaseFactoryError as e:
        raise CasePackOpsError(str(e)) from e


def build_mutation_draft_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    seed_cases: Sequence[Mapping[str, Any]],
    ops: Optional[Sequence[str]] = None,
    seed: str = "0",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    对种子用例做变异后发布 kind=generated 的 draft pack。

    Args:
        pack_id: 包 ID。
        version: 版本。
        workspace_id: 工作区 ID。
        seed_cases: 种子用例。
        ops: 变异操作名列表；空则用默认集。
        seed: 随机种子。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        发布结果，附 ``generator=case_mutation``。
    """
    try:
        cases = mutate_cases(seed_cases, ops=ops, seed=seed)
    except CaseGenerationError as e:
        raise CasePackOpsError(str(e)) from e
    out = publish_generated_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        kind="generated",
        cases=cases,
        caller_workspace_id=caller_workspace_id,
    )
    out["generator"] = "case_mutation"
    out["n_mutations"] = len(cases)
    return out


def build_trace_draft_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    traces: Sequence[Mapping[str, Any]],
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    从 trace 字典生成用例并发布 kind=trace 的 draft pack。

    Args:
        pack_id: 包 ID。
        version: 版本。
        workspace_id: 工作区 ID。
        traces: trace 对象序列。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        发布结果，附 ``generator=case_trace``。
    """
    cases: List[Dict[str, Any]] = []
    try:
        for i, tr in enumerate(traces):
            if not isinstance(tr, Mapping):
                raise CasePackOpsError(f"traces[{i}] must be object")
            cases.extend(cases_from_trace(tr))
    except CaseGenerationError as e:
        raise CasePackOpsError(str(e)) from e
    cleaned = dedupe_cases_by_hash(cases)
    out = publish_generated_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        kind="trace",
        cases=cleaned,
        caller_workspace_id=caller_workspace_id,
    )
    out["generator"] = "case_trace"
    return out


async def build_llm_candidate_draft_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    theme: str,
    n: int = 3,
    category: str = "normal",
    seed: str = "0",
    model_name: str = "",
    dry: bool = False,
    llm_generate_fn=None,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    LLM（或 dry stub）候选用例 → kind=generated draft（声明关闭）。

    Args:
        pack_id: 包 ID。
        version: 版本。
        workspace_id: 工作区 ID。
        theme: 生成主题。
        n: 候选条数。
        category: 用例类别（如 normal）。
        seed: 种子。
        model_name: 可选模型名。
        dry: True 时可用 stub（无真实 LLM）。
        llm_generate_fn: 可选注入的生成函数。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        发布结果，附 ``generator=case_llm``。
    """
    try:
        cases = await generate_llm_candidate_cases(
            theme=theme,
            n=n,
            category=category,
            seed=seed,
            model_name=model_name,
            dry=dry,
            llm_generate_fn=llm_generate_fn,
        )
    except CaseGenerationError as e:
        raise CasePackOpsError(str(e)) from e
    out = publish_generated_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        kind="generated",
        cases=cases,
        caller_workspace_id=caller_workspace_id,
    )
    out["generator"] = "case_llm"
    out["n_candidates"] = len(cases)
    out["dry"] = bool(dry and llm_generate_fn is None)
    return out


def propose_pack_difficulty(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    caller_workspace_id: str = "",
    persist: bool = False,
) -> Dict[str, Any]:
    """
    对 pack 用例做启发式难度提案；可选写回（仅非 frozen）。

    Args:
        pack_id: 包 ID。
        version: 版本。
        workspace_id: 工作区 ID。
        caller_workspace_id: ACL 调用方工作区。
        persist: True 时写回 payload 并重 hash。

    Returns:
        含每案 difficulty 提案；``calibrated=false``，非 accuracy 声明。
    """
    pid = str(pack_id or "").strip()
    ver = str(version or "").strip()
    wid = str(workspace_id or "").strip()
    if not pid or not ver or not wid:
        raise CasePackOpsError("pack_id, version, workspace_id required")
    try:
        cur = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
        payload = load_pack_payload(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e
    cases = list((payload or {}).get("cases") or [])
    labeled = propose_difficulty(cases)
    result: Dict[str, Any] = {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "n": len(labeled),
        "cases": [
            {
                "case_id": c.get("case_id"),
                "difficulty": c.get("difficulty"),
                "difficulty_proposal": c.get("difficulty_proposal"),
            }
            for c in labeled
        ],
        "calibrated": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "persisted": False,
        "honesty": "heuristic only — not calibrated; no accuracy_claim",
    }
    if not persist:
        return result
    if str(cur.get("kind") or "").lower() == "frozen":
        raise CasePackOpsError("frozen pack immutable — bump first")
    st = str(cur.get("status") or "").lower()
    if st not in _EXPANDABLE_STATUSES:
        raise CasePackOpsError(
            f"difficulty persist requires status in {sorted(_EXPANDABLE_STATUSES)}, got {st!r}"
        )
    ots = list(cur.get("object_types") or ["agent"])
    kind = str(cur.get("kind") or "curated")
    assert_claim_eligible_allowed(kind=kind, claim_eligible=False)
    new_hash = compute_pack_hash(
        pack_id=pid,
        version=ver,
        kind=kind,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=labeled,
    )
    try:
        meta = update_pack_version_meta(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
            pack_hash=new_hash,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e
    write_pack_payload(
        pack_id=pid,
        version=ver,
        scope="workspace",
        cases=labeled,
        meta={
            "kind": kind,
            "claim_eligible": False,
            "hash": new_hash,
            "object_types": ots,
            "status": st,
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    result["persisted"] = True
    result["pack_hash"] = new_hash
    result["registry"] = meta
    return result


def open_judge_calibration_ticket_for_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    sample_case_ids: Optional[Sequence[str]] = None,
    notes: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    创建并持久化 judge 校准 ticket（不解锁 claim）。

    Args:
        pack_id: 包 ID。
        version: 版本。
        workspace_id: 工作区 ID。
        sample_case_ids: 抽样 case_id；空则由校准模块决定。
        notes: 备注。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        ticket 记录 dict。
    """
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CasePackOpsError("workspace_id required")
    try:
        return create_judge_ticket(
            workspace_id=wid,
            pack_id=pack_id,
            version=version,
            sample_case_ids=sample_case_ids,
            notes=notes,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except (CaseCalibrationError, PackRegistryError) as e:
        raise CasePackOpsError(str(e)) from e


def record_judge_calibration_ratings_for_pack(
    *,
    workspace_id: str,
    ticket_id: str,
    ratings: Sequence[Mapping[str, Any]],
    rater: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    追加裁判评分并重算一致性。

    Args:
        workspace_id: 工作区 ID。
        ticket_id: ticket ID。
        ratings: 评分数列。
        rater: 评分人标识。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        更新后的 ticket / 一致性摘要。
    """
    try:
        return record_judge_ratings(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            ratings=ratings,
            rater=rater,
            caller_workspace_id=caller_workspace_id or workspace_id,
        )
    except (CaseCalibrationError, PackRegistryError) as e:
        raise CasePackOpsError(str(e)) from e


def close_judge_calibration_ticket_for_pack(
    *,
    workspace_id: str,
    ticket_id: str,
    notes: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    在有评分后关闭 ticket（工程校准完成；claim 仍关闭）。

    Args:
        workspace_id: 工作区 ID。
        ticket_id: ticket ID。
        notes: 关闭备注。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        关闭后的 ticket 记录。
    """
    try:
        return close_judge_ticket(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            notes=notes,
            caller_workspace_id=caller_workspace_id or workspace_id,
        )
    except (CaseCalibrationError, PackRegistryError) as e:
        raise CasePackOpsError(str(e)) from e


def get_judge_calibration_ticket_for_pack(
    *,
    workspace_id: str,
    ticket_id: str,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    读取 judge 校准 ticket。

    Args:
        workspace_id: 工作区 ID。
        ticket_id: ticket ID。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        ticket 内容 dict。

    Raises:
        CasePackOpsError: 加载失败。
    """
    try:
        return load_judge_ticket(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            caller_workspace_id=caller_workspace_id or workspace_id,
        )
    except (CaseCalibrationError, PackRegistryError) as e:
        raise CasePackOpsError(str(e)) from e


def calibrate_pack_difficulty(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    labels: Sequence[Mapping[str, Any]],
    rater: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    把人工难度标签写回非 frozen pack，并落校准记录。

    Args:
        pack_id: 包 ID。
        version: 版本。
        workspace_id: 工作区 ID。
        labels: ``case_id``→难度 标签序列。
        rater: 标注人。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        含 ``pack_hash`` / ``calibrated=true``；非 accuracy 声明。
    """
    pid = str(pack_id or "").strip()
    ver = str(version or "").strip()
    wid = str(workspace_id or "").strip()
    if not pid or not ver or not wid:
        raise CasePackOpsError("pack_id, version, workspace_id required")
    try:
        cur = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
        payload = load_pack_payload(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e
    if str(cur.get("kind") or "").lower() == "frozen":
        raise CasePackOpsError("frozen pack immutable — bump first")
    st = str(cur.get("status") or "").lower()
    if st not in _EXPANDABLE_STATUSES:
        raise CasePackOpsError(
            f"difficulty calibrate requires status in {sorted(_EXPANDABLE_STATUSES)}, got {st!r}"
        )
    cases = list((payload or {}).get("cases") or [])
    try:
        labeled = apply_difficulty_labels(cases, labels)
        rec = save_difficulty_calibration_record(
            workspace_id=wid,
            pack_id=pid,
            version=ver,
            labels=labels,
            rater=rater,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except (CaseCalibrationError, PackRegistryError) as e:
        raise CasePackOpsError(str(e)) from e
    ots = list(cur.get("object_types") or ["agent"])
    kind = str(cur.get("kind") or "curated")
    assert_claim_eligible_allowed(kind=kind, claim_eligible=False)
    new_hash = compute_pack_hash(
        pack_id=pid,
        version=ver,
        kind=kind,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=labeled,
    )
    try:
        meta = update_pack_version_meta(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
            pack_hash=new_hash,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e
    write_pack_payload(
        pack_id=pid,
        version=ver,
        scope="workspace",
        cases=labeled,
        meta={
            "kind": kind,
            "claim_eligible": False,
            "hash": new_hash,
            "object_types": ots,
            "status": st,
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "pack_hash": new_hash,
        "n_labeled": sum(
            1
            for c in labeled
            if isinstance(c.get("difficulty_proposal"), dict)
            and c["difficulty_proposal"].get("method") == "human_label_v1"
        ),
        "registry": meta,
        "record": {k: rec[k] for k in ("path", "updated_at", "rater") if k in rec},
        "calibrated": True,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "engineering difficulty calibration — not an accuracy claim",
    }


def summarize_workspace_pack_coverage(
    *,
    workspace_id: str,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """
    工作区 pack 覆盖摘要（按 status/kind 计数 + 每版本行）。

    Args:
        workspace_id: 工作区 ID。
        caller_workspace_id: ACL 调用方工作区。

    Returns:
        ``by_status`` / ``by_kind`` / ``items``；仅库存盘点。
    """
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CasePackOpsError("workspace_id required")
    assert_pack_acl(
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        write=False,
    )
    reg = load_registry(scope="workspace", workspace_id=wid)
    items: List[Dict[str, Any]] = []
    by_status: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    for pid, entry in (reg.get("packs") or {}).items():
        if not isinstance(entry, dict):
            continue
        for ver, meta in (entry.get("versions") or {}).items():
            if not isinstance(meta, dict):
                continue
            st = str(meta.get("status") or "").lower() or "unknown"
            kind = str(meta.get("kind") or "").lower() or "unknown"
            by_status[st] = by_status.get(st, 0) + 1
            by_kind[kind] = by_kind.get(kind, 0) + 1
            n_cases = None
            try:
                payload = load_pack_payload(
                    pack_id=pid,
                    version=ver,
                    scope="workspace",
                    workspace_id=wid,
                    caller_workspace_id=caller_workspace_id or wid,
                )
                n_cases = len(payload.get("cases") or [])
            except PackRegistryError:
                n_cases = None
            items.append(
                {
                    "pack_id": pid,
                    "version": ver,
                    "status": st,
                    "kind": kind,
                    "claim_eligible": bool(meta.get("claim_eligible")),
                    "hash": meta.get("hash"),
                    "n_cases": n_cases,
                }
            )
    items.sort(key=lambda r: (r["pack_id"], r["version"]))
    return {
        "ok": True,
        "workspace_id": wid,
        "n_versions": len(items),
        "by_status": by_status,
        "by_kind": by_kind,
        "items": items,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "coverage inventory only; not an accuracy claim",
    }
