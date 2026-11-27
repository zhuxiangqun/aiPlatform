"""小朱受控进化提案台账（习性自动；升生产须 HUMAN_GATE）。

非目标：不改 best_model_for_purpose；不自动切流；不宣称 E5。
状态子集对齐 evo_compute Candidate：DRAFT → HUMAN_GATE → APPROVED|REJECTED → APPLIED|ROLLED_BACK。
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import get_aiplat_home

logger = logging.getLogger("aiplat.digital_human.evolution_proposals")

PROPOSAL_KINDS = (
    "habit_promotion",
    "constitution_patch",
    "seed_qa",
    "sft_promote",
    "pilot_config",
    "purpose_bind",
    "knowledge_evolve",
    "eval_coverage",
    "fde_evolve",
)

# 顾问侧状态子集（与 evo Candidate.status 同词，不全量复制）
STATUS_DRAFT = "DRAFT"
STATUS_HUMAN_GATE = "HUMAN_GATE"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_APPLIED = "APPLIED"
STATUS_ROLLED_BACK = "ROLLED_BACK"

_DECIDE_RE = re.compile(
    r"^(?:批准|同意|通过)\s*(?:第\s*)?(\d+)|"
    r"^(?:拒绝|驳回)\s*(?:第\s*)?(\d+)|"
    r"^批准\s*([a-zA-Z0-9_-]{6,})|"
    r"^拒绝\s*([a-zA-Z0-9_-]{6,})",
    re.I,
)


def _store_path() -> Path:
    return Path(get_aiplat_home()) / "digital_human" / "evolution_proposals.jsonl"


def _approved_seed_path() -> Path:
    return Path(get_aiplat_home()) / "digital_human" / "approved_seed_qa.jsonl"


def _constitution_proposal_dir() -> Path:
    return Path(get_aiplat_home()) / "digital_human" / "constitution_proposals"


def _clear_proposals_for_tests() -> None:
    """单测清理提案文件。"""
    path = _store_path()
    if path.is_file():
        path.unlink()
    seed = _approved_seed_path()
    if seed.is_file():
        seed.unlink()


def _append_row(row: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rewrite_all(rows: List[Dict[str, Any]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def list_evolution_proposals(
    *,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """列出进化提案（新→旧）。

    Args:
        status: 按状态过滤。
        kind: 按类型过滤。
        limit: 最多条数。
    """
    path = _store_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if status and str(obj.get("status") or "") != status:
                continue
            if kind and str(obj.get("kind") or "") != kind:
                continue
            rows.append(obj)
    except OSError:
        return []
    rows.reverse()
    return rows[: max(1, int(limit))]


def get_evolution_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    """按 id 取提案。

    Args:
        proposal_id: 提案 id。
    """
    pid = (proposal_id or "").strip()
    if not pid:
        return None
    for row in list_evolution_proposals(limit=500):
        if str(row.get("id") or "") == pid:
            return row
    return None


def create_evolution_proposal(
    *,
    kind: str,
    title: str,
    summary: str = "",
    payload: Optional[Dict[str, Any]] = None,
    tenant_id: str = "default",
    session_id: str = "",
    status: str = STATUS_HUMAN_GATE,
) -> Dict[str, Any]:
    """创建进化提案（默认进入 HUMAN_GATE 待批）。

    Args:
        kind: 提案类型（见 PROPOSAL_KINDS）。
        title: 短标题。
        summary: 口述摘要。
        payload: 应用所需结构化字段。
        tenant_id: 租户。
        session_id: 来源会话。
        status: 初始状态。
    """
    k = (kind or "").strip()
    if k not in PROPOSAL_KINDS:
        return {"ok": False, "reason": "invalid_kind", "kind": k}
    st = (status or STATUS_HUMAN_GATE).strip().upper()
    if st not in (
        STATUS_DRAFT,
        STATUS_HUMAN_GATE,
        STATUS_APPROVED,
        STATUS_REJECTED,
        STATUS_APPLIED,
        STATUS_ROLLED_BACK,
    ):
        st = STATUS_HUMAN_GATE
    now = int(time.time())
    row: Dict[str, Any] = {
        "id": f"dhp_{uuid.uuid4().hex[:12]}",
        "kind": k,
        "title": (title or "").strip()[:120] or k,
        "summary": (summary or "").strip()[:500],
        "payload": dict(payload or {}),
        "tenant_id": (tenant_id or "default").strip() or "default",
        "session_id": (session_id or "").strip()[:64],
        "status": st,
        "created_at": now,
        "updated_at": now,
        "decision": None,
        "apply_result": None,
        # 诚实锁：任何提案默认声明未改生产选模
        "production_model_changed": False,
    }
    _append_row(row)
    return {"ok": True, "proposal": row}


def maybe_propose_from_feedback(
    *,
    rating: str,
    correction: str = "",
    tenant_id: str = "default",
    session_id: str = "",
) -> Dict[str, Any]:
    """反馈后 best-effort 写入提案（纠偏→seed_qa；有用→habit_promotion 可选）。

    Args:
        rating: good|bad。
        correction: 「应该是…」正文。
        tenant_id: 租户。
        session_id: 会话。
    """
    r = (rating or "").strip().lower()
    corr = (correction or "").strip()
    if r == "bad" and corr:
        return create_evolution_proposal(
            kind="seed_qa",
            title="金标纠偏→种子问答",
            summary=f"待批：把纠偏写入批准种子库。纠偏摘要：{corr[:80]}",
            payload={"correction": corr[:800], "rating": "bad"},
            tenant_id=tenant_id,
            session_id=session_id,
        )
    if r == "good":
        return create_evolution_proposal(
            kind="habit_promotion",
            title="有用样本→习性巩固",
            summary="待批：确认本条有用反馈可巩固为习惯提示（笔记已可能自动写入）。",
            payload={"rating": "good"},
            tenant_id=tenant_id,
            session_id=session_id,
            status=STATUS_HUMAN_GATE,
        )
    return {"ok": False, "reason": "noop"}


def maybe_propose_sft_promote(sft_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """SFT 自动提交成功后写入 sft_promote（人批≠换生产路由）。

    Args:
        sft_result: maybe_submit_digital_human_sft 回执。
    """
    if not isinstance(sft_result, dict):
        return {"ok": False, "reason": "no_result"}
    if not sft_result.get("submitted"):
        return {"ok": False, "reason": "not_submitted", "sft_reason": sft_result.get("reason")}
    job_id = str(sft_result.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "reason": "no_job_id"}
    # 防抖：同 job 已有待批/已批则跳过
    for row in list_evolution_proposals(kind="sft_promote", limit=100):
        if str((row.get("payload") or {}).get("job_id") or "") == job_id:
            return {"ok": False, "reason": "already_proposed", "proposal_id": row.get("id")}
    sample_count = sft_result.get("converted_count")
    if sample_count is None:
        sample_count = sft_result.get("sample_count")
    return create_evolution_proposal(
        kind="sft_promote",
        title=f"微调任务可审：{job_id[:16]}",
        summary=(
            f"Job {job_id} 已提交。批准前过顾问 holdout 门；通过后仅指引 /infra/finetune，"
            "不会自动改 best_model_for_purpose。"
        ),
        payload={
            "job_id": job_id,
            "dataset_id": sft_result.get("dataset_id"),
            "provider": sft_result.get("provider"),
            "base_model": sft_result.get("base_model"),
            "sample_count": sample_count,
            "guidance": "到 /infra/finetune 审评测后再绑定；顾问 Chat 仍走 best_model_for_purpose。",
        },
    )


def pending_human_gate_count() -> int:
    """待人工批准的提案数。"""
    return len(list_evolution_proposals(status=STATUS_HUMAN_GATE, limit=200))


def evolution_proposals_brief_line() -> str:
    """简报一行：待批进化提案。"""
    pending = list_evolution_proposals(status=STATUS_HUMAN_GATE, limit=20)
    n = len(pending)
    if n == 0:
        return "小朱进化提案: 0 条待批（习性笔记可自动；升生产须人批）"
    titles = "、".join(str(p.get("title") or p.get("id"))[:24] for p in pending[:3])
    more = f" 等{n}条" if n > 3 else ""
    return (
        f"小朱进化提案: {n} 条待批（{titles}{more}）。"
        "可说「批准第1条」/「拒绝第1条」，或浮层点同意。"
    )


def parse_evolution_decide_utterance(text: str) -> Optional[Dict[str, str]]:
    """解析「批准第N条 / 拒绝第N条 / 批准 <id>」。

    Args:
        text: 用户原话。
    """
    t = (text or "").strip()
    if not t:
        return None
    m = _DECIDE_RE.match(t)
    if not m:
        return None
    if m.group(1):
        return {"decision": "approve", "index": m.group(1)}
    if m.group(2):
        return {"decision": "reject", "index": m.group(2)}
    if m.group(3):
        return {"decision": "approve", "proposal_id": m.group(3)}
    if m.group(4):
        return {"decision": "reject", "proposal_id": m.group(4)}
    return None


def _update_proposal(proposal_id: str, mutator) -> Dict[str, Any]:
    path = _store_path()
    if not path.is_file():
        return {"ok": False, "reason": "empty_store"}
    rows: List[Dict[str, Any]] = []
    found: Optional[Dict[str, Any]] = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if str(obj.get("id") or "") == proposal_id:
                mutator(obj)
                obj["updated_at"] = int(time.time())
                found = obj
            rows.append(obj)
    except OSError as e:
        return {"ok": False, "reason": f"read_failed:{e}"}
    if not found:
        return {"ok": False, "reason": "not_found"}
    _rewrite_all(rows)
    return {"ok": True, "proposal": found}


def _apply_seed_qa(proposal: Dict[str, Any]) -> Dict[str, Any]:
    payload = proposal.get("payload") or {}
    corr = str(payload.get("correction") or "").strip()
    if not corr:
        return {"applied": False, "reason": "no_correction"}
    path = _approved_seed_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = ""
    if path.is_file():
        backup = str(path) + f".bak.{int(time.time())}"
        shutil.copy2(path, backup)
    row = {
        "q": "（金标纠偏）用户指出顾问应如何回答",
        "a": corr[:1200],
        "proposal_id": proposal.get("id"),
        "tenant_id": proposal.get("tenant_id"),
        "ts": int(time.time()),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "applied": True,
        "path": str(path),
        "backup": backup,
        "production_model_changed": False,
    }


def _apply_habit_promotion(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """巩固有用反馈：写入一条确认行到个人笔记（可回滚备份）。"""
    try:
        from core.harness.digital_human.consultant_personal import memory_path
    except Exception as e:
        return {"applied": False, "reason": f"import_failed:{e}"}
    tenant = str(proposal.get("tenant_id") or "default")
    path = memory_path(tenant, for_write=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = ""
    if path.is_file():
        backup = str(path) + f".bak.{int(time.time())}"
        shutil.copy2(path, backup)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    line = f"- ({stamp}) [进化批准] 巩固近期「有用」反馈为习惯提示（proposal={proposal.get('id')}）"
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if line in existing:
            return {
                "applied": True,
                "reason": "already_present",
                "backup": backup,
                "production_model_changed": False,
            }
        with path.open("a", encoding="utf-8") as fh:
            if not existing:
                fh.write("# 小朱个人笔记（主人可直接编辑）\n\n")
            fh.write(line + "\n")
    except OSError as e:
        return {"applied": False, "reason": f"write_failed:{e}"}
    return {
        "applied": True,
        "path": str(path),
        "backup": backup,
        "production_model_changed": False,
    }


def _apply_constitution_patch(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """仅落盘 diff 提案文件，不热改 AGENT.md。"""
    d = _constitution_proposal_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{proposal.get('id')}.md"
    payload = proposal.get("payload") or {}
    body = str(payload.get("diff") or payload.get("text") or proposal.get("summary") or "").strip()
    out.write_text(
        f"# constitution proposal {proposal.get('id')}\n\n"
        "人批后仍须人工合并 AGENT.md / consultant_constitution.md。\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return {
        "applied": True,
        "path": str(out),
        "note": "diff_only_no_hot_reload",
        "production_model_changed": False,
    }


def _apply_sft_promote(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """批准 sft_promote：先过顾问 holdout 门；通过才 APPLIED；永不改生产选模。"""
    payload = proposal.get("payload") or {}
    try:
        from core.harness.digital_human.consultant_sft_gate import (
            evaluate_sft_promote_gate,
        )

        gate = evaluate_sft_promote_gate(proposal=proposal)
    except Exception as e:
        gate = {
            "ok": False,
            "passed": False,
            "reason": f"gate_import_or_run_failed:{e}",
            "production_model_changed": False,
            "feeds_production_routing": False,
        }
    guidance = (
        payload.get("guidance")
        or "到 /infra/finetune 人工审评测并启用；Chat 仍走 best_model_for_purpose。"
    )
    base = {
        "guidance": guidance,
        "job_id": payload.get("job_id"),
        "production_model_changed": False,
        "feeds_production_routing": False,
        "finetune_path": "/infra/finetune",
        "eval_gate": gate,
    }
    if not gate.get("passed"):
        return {
            **base,
            "applied": False,
            "reason": "eval_gate_failed",
            "note": "HUMAN_GATE 已批但 holdout 未过 → 保持 APPROVED，不进 APPLIED",
        }
    # 链式：SFT 通过后自动生成 purpose_bind 待批（仍须第二道人批）
    chained: Dict[str, Any] = {}
    try:
        chained = maybe_propose_purpose_bind(
            job_id=str(payload.get("job_id") or ""),
            model=str(payload.get("base_model") or payload.get("result_model") or ""),
            purpose=str(payload.get("purpose") or "auto"),
            source_proposal_id=str(proposal.get("id") or ""),
            tenant_id=str(proposal.get("tenant_id") or "default"),
        )
    except Exception as e:
        chained = {"ok": False, "reason": f"chain_failed:{e}"}
    return {
        **base,
        "applied": True,
        "note": "eval_gate_passed; guidance_only_no_routing_change",
        "purpose_bind_proposal": chained,
    }


def _pilot_skill_name(genome_id: str) -> str:
    """genome_id → SkillRouter 键（沙箱灰度用）。"""
    gid = (genome_id or "").strip()
    if gid.endswith(".v1"):
        return gid[: -len(".v1")]
    return gid or "evo.pilot"


def _apply_purpose_bind(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """第二道人批：写入 purpose 绑定回执；默认不改顾问热路径（需 env）。"""
    payload = dict(proposal.get("payload") or {})
    try:
        from core.harness.digital_human.consultant_purpose_bind import (
            purpose_bind_enabled,
            write_purpose_bind,
        )
    except Exception as e:
        return {
            "applied": False,
            "reason": f"import_failed:{e}",
            "production_model_changed": False,
            "feeds_global_routing": False,
        }
    written = write_purpose_bind(
        model=str(payload.get("model") or payload.get("base_model") or ""),
        purpose=str(payload.get("purpose") or "auto"),
        job_id=str(payload.get("job_id") or ""),
        proposal_id=str(proposal.get("id") or ""),
        actor=str(payload.get("actor") or proposal.get("tenant_id") or "user"),
        note=str(payload.get("note") or proposal.get("summary") or ""),
    )
    return {
        "applied": bool(written.get("ok")),
        "bind": written.get("bind"),
        "path": written.get("path"),
        "production_model_changed": False,
        "feeds_global_routing": False,
        "consultant_override_active": purpose_bind_enabled()
        and bool(str(payload.get("model") or payload.get("base_model") or "").strip()),
        "note": (
            "receipt_written; set AIPLAT_DH_PURPOSE_BIND=1 for consultant hot-path read"
            if not purpose_bind_enabled()
            else "receipt_written; consultant may prefer bind model when env on"
        ),
    }


def maybe_propose_purpose_bind(
    *,
    job_id: str,
    model: str = "",
    purpose: str = "auto",
    source_proposal_id: str = "",
    tenant_id: str = "default",
    session_id: str = "",
) -> Dict[str, Any]:
    """在 sft_promote 通过后创建 purpose_bind 待批（防抖同 job）。

    Args:
        job_id: 微调任务 id。
        model: 建议模型名（可空）。
        purpose: purpose，默认 auto。
        source_proposal_id: 上游 sft_promote id。
        tenant_id: 租户。
        session_id: 会话。
    """
    jid = (job_id or "").strip()
    if not jid:
        return {"ok": False, "reason": "job_id_required"}
    for row in list_evolution_proposals(kind="purpose_bind", limit=100):
        pl = row.get("payload") or {}
        if str(pl.get("job_id") or "") == jid and str(row.get("status") or "") in (
            STATUS_HUMAN_GATE,
            STATUS_APPROVED,
            STATUS_APPLIED,
        ):
            return {"ok": False, "reason": "already_proposed", "proposal_id": row.get("id")}
    return create_evolution_proposal(
        kind="purpose_bind",
        title=f"绑定顾问模型建议：{jid[:16]}",
        summary=(
            f"第二道人批：确认将 Job {jid} 的建议模型写入绑定回执。"
            "默认不改选模；仅当 AIPLAT_DH_PURPOSE_BIND=1 时顾问热路径可读。"
        ),
        payload={
            "job_id": jid,
            "model": (model or "").strip(),
            "purpose": (purpose or "auto").strip() or "auto",
            "source_proposal_id": (source_proposal_id or "").strip(),
        },
        tenant_id=tenant_id,
        session_id=session_id,
    )


def propose_purpose_bind_from_latest(
    *,
    tenant_id: str = "default",
    session_id: str = "",
) -> Dict[str, Any]:
    """从最近 APPLIED 的 sft_promote 或 SFT 状态文件申请 purpose_bind。

    Args:
        tenant_id: 租户。
        session_id: 会话。
    """
    # 1) 最近 APPLIED sft_promote
    for row in list_evolution_proposals(kind="sft_promote", limit=50):
        if str(row.get("status") or "") != STATUS_APPLIED:
            continue
        pl = row.get("payload") or {}
        jid = str(pl.get("job_id") or "").strip()
        if not jid:
            continue
        return maybe_propose_purpose_bind(
            job_id=jid,
            model=str(pl.get("base_model") or pl.get("result_model") or pl.get("model") or ""),
            purpose=str(pl.get("purpose") or "auto"),
            source_proposal_id=str(row.get("id") or ""),
            tenant_id=tenant_id,
            session_id=session_id,
        )
    # 2) SFT auto state
    try:
        from core.utils.paths import get_aiplat_data_dir

        state_path = Path(get_aiplat_data_dir("training")) / "dh_sft_auto_state.json"
        if state_path.is_file():
            st = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(st, dict):
                jid = str(st.get("last_job_id") or "").strip()
                if jid:
                    return maybe_propose_purpose_bind(
                        job_id=jid,
                        model=str(st.get("base_model") or ""),
                        purpose="auto",
                        tenant_id=tenant_id,
                        session_id=session_id,
                    )
    except Exception as e:
        return {"ok": False, "reason": f"state_read_failed:{e}"}
    return {"ok": False, "reason": "no_sft_source"}


def _apply_pilot_config(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """试点配置：写入 evo HUMAN_GATE 台账 + 默认沙箱 Canary（不写全局路由）。"""
    payload = dict(proposal.get("payload") or {})
    genome_id = str(payload.get("genome_id") or "").strip()
    if not genome_id:
        return {
            "applied": False,
            "reason": "genome_id_required",
            "production_model_changed": False,
            "production_write": False,
        }
    candidate_id = str(
        payload.get("candidate_id") or f"dh_{proposal.get('id')}_{genome_id}"
    ).strip()
    skill_name = str(payload.get("skill_name") or _pilot_skill_name(genome_id)).strip()
    actor = str(payload.get("actor") or proposal.get("tenant_id") or "xiaozhu").strip()
    evidence = f"dh-evolution:{proposal.get('id')}"
    out: Dict[str, Any] = {
        "applied": False,
        "genome_id": genome_id,
        "candidate_id": candidate_id,
        "skill_name": skill_name,
        "production_model_changed": False,
        "production_write": False,
        "use_global_router": False,
    }
    try:
        from core.harness.evo_compute.candidate_ledger import record_human_gate_decision
        from core.harness.evo_compute.canary_bridge import request_evo_canary_cutover
    except Exception as e:
        out["reason"] = f"evo_import_failed:{e}"
        return out

    ledger = record_human_gate_decision(
        candidate_id=candidate_id,
        status="approved",
        actor=actor,
        evidence_ref=evidence,
        human_gate_passed=True,
        persist=True,
    )
    out["ledger"] = {
        "ok": bool(ledger.get("ok")),
        "production_write": bool(ledger.get("production_write")),
        "error": ledger.get("error") or "",
    }
    if not ledger.get("ok"):
        out["reason"] = f"ledger_failed:{ledger.get('error')}"
        return out

    # 默认沙箱：use_global_router=False → production_write 恒 false
    canary = request_evo_canary_cutover(
        candidate_id=candidate_id,
        skill_name=skill_name,
        version=str(payload.get("version") or f"dh-{proposal.get('id')}"),
        rollout_percentage=int(payload.get("rollout_percentage") or 5),
        actor=actor,
        evidence_ref=evidence,
        from_status="approved",
        use_global_router=False,
    )
    out["canary"] = {
        "ok": bool(canary.get("ok")),
        "cutover": bool(canary.get("cutover")),
        "production_write": bool(canary.get("production_write")),
        "error": canary.get("error") or "",
        "source": canary.get("source") or "",
    }
    out["applied"] = bool(canary.get("ok"))
    out["production_write"] = False
    if not canary.get("ok"):
        out["reason"] = f"canary_failed:{canary.get('error')}"
        # 台账已批，仍算部分应用；标记 APPLIED 由上层用 applied 字段
        out["applied"] = True
        out["partial"] = True
        out["note"] = "ledger_ok_canary_sandbox_failed"
    else:
        out["note"] = "ledger_ok_sandbox_canary"
    return out


def propose_pilot_config(
    *,
    genome_id: str,
    title: str = "",
    summary: str = "",
    candidate_id: str = "",
    skill_name: str = "",
    tenant_id: str = "default",
    session_id: str = "",
) -> Dict[str, Any]:
    """为 evo 三试点之一创建 pilot_config 待批提案。

    Args:
        genome_id: 如 routing.weights.v1。
        title: 标题。
        summary: 摘要。
        candidate_id: 可选候选 id。
        skill_name: 可选 Skill 键。
        tenant_id: 租户。
        session_id: 会话。
    """
    from core.harness.evo_compute.pilots import PILOT_GENOME_IDS

    gid = (genome_id or "").strip()
    if gid not in PILOT_GENOME_IDS:
        return {
            "ok": False,
            "reason": "unknown_pilot_genome",
            "allowed": list(PILOT_GENOME_IDS),
        }
    # 同 genome 已有待批则复用
    for row in list_evolution_proposals(kind="pilot_config", status=STATUS_HUMAN_GATE, limit=50):
        if str((row.get("payload") or {}).get("genome_id") or "") == gid:
            return {"ok": False, "reason": "already_pending", "proposal": row}
    return create_evolution_proposal(
        kind="pilot_config",
        title=title or f"试点参数：{gid}",
        summary=summary
        or (
            f"待批：将 {gid} 记入 evo 台账并跑沙箱 Canary。"
            "默认不切全局路由（production_write=false）。"
        ),
        payload={
            "genome_id": gid,
            "candidate_id": (candidate_id or "").strip(),
            "skill_name": (skill_name or _pilot_skill_name(gid)).strip(),
        },
        tenant_id=tenant_id,
        session_id=session_id,
    )


def ensure_pilot_config_proposals(*, tenant_id: str = "default") -> Dict[str, Any]:
    """确保三试点各有一条待批或已存在提案（幂等）。

    Args:
        tenant_id: 租户。
    """
    from core.harness.evo_compute.pilots import PILOT_GENOME_IDS

    created: List[str] = []
    skipped: List[str] = []
    for gid in PILOT_GENOME_IDS:
        r = propose_pilot_config(genome_id=gid, tenant_id=tenant_id)
        if r.get("ok"):
            created.append(gid)
        else:
            skipped.append(gid)
    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "pending": pending_human_gate_count(),
    }


def evo_pilot_candidates_brief_line() -> str:
    """简报：evo 台账生产路径候选 + 小朱 pilot 待批。"""
    pilot_pending = [
        p
        for p in list_evolution_proposals(kind="pilot_config", status=STATUS_HUMAN_GATE, limit=20)
    ]
    bits = [f"试点提案待批 {len(pilot_pending)}"]
    try:
        from core.harness.evo_compute.candidate_ledger import (
            list_production_path_candidates,
        )

        listed = list_production_path_candidates(production_path_only=True)
        n = int(listed.get("count") or 0)
        bits.append(f"evo台账路径候选 {n}")
        if listed.get("empty"):
            bits.append("空台账≠无生产流量宣称")
    except Exception:
        bits.append("evo台账(简报未见)")
    titles = "、".join(
        str(p.get("title") or (p.get("payload") or {}).get("genome_id") or p.get("id"))[:20]
        for p in pilot_pending[:2]
    )
    extra = f"；待批：{titles}" if titles else ""
    return "平台试点演化: " + "，".join(bits) + extra + "（沙箱 Canary；不自动 use_global_router）"


def _apply_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(proposal.get("kind") or "")
    if kind == "seed_qa":
        return _apply_seed_qa(proposal)
    if kind == "habit_promotion":
        return _apply_habit_promotion(proposal)
    if kind == "constitution_patch":
        return _apply_constitution_patch(proposal)
    if kind == "sft_promote":
        return _apply_sft_promote(proposal)
    if kind == "purpose_bind":
        return _apply_purpose_bind(proposal)
    if kind == "pilot_config":
        return _apply_pilot_config(proposal)
    if kind in ("knowledge_evolve", "eval_coverage", "fde_evolve"):
        try:
            from core.harness.digital_human.domain_evolution_bridge import (
                apply_domain_evolution_proposal,
            )

            return apply_domain_evolution_proposal(proposal)
        except Exception as e:
            return {
                "applied": False,
                "reason": f"domain_apply_failed:{e}",
                "production_model_changed": False,
                "production_write": False,
            }
    return {"applied": False, "reason": "unknown_kind", "production_model_changed": False}


def decide_evolution_proposal(
    *,
    decision: str,
    proposal_id: str = "",
    index: Optional[int] = None,
    actor: str = "user",
    apply: bool = True,
) -> Dict[str, Any]:
    """批准或拒绝提案；批准且 apply=True 时执行有界应用。

    Args:
        decision: approve|reject。
        proposal_id: 提案 id（优先）。
        index: 待批列表 1-based 序号。
        actor: 决策人。
        apply: 批准后是否立刻有界应用。
    """
    dec = (decision or "").strip().lower()
    if dec in ("批准", "同意", "通过", "yes", "y"):
        dec = "approve"
    if dec in ("拒绝", "驳回", "no", "n"):
        dec = "reject"
    if dec not in ("approve", "reject"):
        return {"ok": False, "reason": "invalid_decision"}

    pid = (proposal_id or "").strip()
    if not pid and index is not None:
        pending = list_evolution_proposals(status=STATUS_HUMAN_GATE, limit=50)
        # list 已是新→旧；第1条 = pending[0]
        i = int(index) - 1
        if i < 0 or i >= len(pending):
            return {"ok": False, "reason": "index_out_of_range", "pending": len(pending)}
        pid = str(pending[i].get("id") or "")
    if not pid:
        return {"ok": False, "reason": "missing_id"}

    target = get_evolution_proposal(pid)
    if not target:
        return {"ok": False, "reason": "not_found"}
    cur = str(target.get("status") or "")
    if cur not in (STATUS_HUMAN_GATE, STATUS_DRAFT):
        return {"ok": False, "reason": "not_pending", "status": cur}

    if dec == "reject":

        def _rej(obj: Dict[str, Any]) -> None:
            obj["status"] = STATUS_REJECTED
            obj["decision"] = {"actor": actor, "at": int(time.time()), "decision": "reject"}
            obj["production_model_changed"] = False

        return _update_proposal(pid, _rej)

    apply_result: Dict[str, Any] = {"applied": False, "skipped": True}
    if apply:
        apply_result = _apply_proposal(target)
    # 诚实锁：强制字段
    apply_result["production_model_changed"] = False

    def _ok(obj: Dict[str, Any]) -> None:
        obj["status"] = STATUS_APPLIED if apply_result.get("applied") else STATUS_APPROVED
        obj["decision"] = {"actor": actor, "at": int(time.time()), "decision": "approve"}
        obj["apply_result"] = apply_result
        obj["production_model_changed"] = False

    out = _update_proposal(pid, _ok)
    if out.get("ok"):
        out["apply_result"] = apply_result
        out["production_model_changed"] = False
    return out


def try_handle_evolution_utterance(
    text: str,
    *,
    actor: str = "user",
) -> Optional[Dict[str, Any]]:
    """若用户话是批准/拒绝指令则处理并返回口述结果，否则 None。

    Args:
        text: 用户原话。
        actor: 决策人。
    """
    parsed = parse_evolution_decide_utterance(text)
    if not parsed:
        return None
    kwargs: Dict[str, Any] = {
        "decision": parsed["decision"],
        "actor": actor,
    }
    if parsed.get("proposal_id"):
        kwargs["proposal_id"] = parsed["proposal_id"]
    if parsed.get("index"):
        kwargs["index"] = int(parsed["index"])
    result = decide_evolution_proposal(**kwargs)
    if not result.get("ok"):
        return {
            "handled": True,
            "ok": False,
            "reply": f"进化提案未能执行：{result.get('reason')}",
            "result": result,
        }
    prop = result.get("proposal") or {}
    st = prop.get("status")
    title = prop.get("title") or prop.get("id")
    if parsed["decision"] == "reject":
        reply = f"已拒绝提案「{title}」。"
    else:
        bits = [f"已批准提案「{title}」（状态 {st}）。"]
        ar = result.get("apply_result") or {}
        if ar.get("guidance"):
            bits.append(str(ar["guidance"]))
        bits.append("未改生产选模。")
        reply = "".join(bits)
    return {"handled": True, "ok": True, "reply": reply, "result": result}
