"""Org L5 Phase 4 — Field ops (W7): live unlock evaluation + checklist.

Outbound HTTP is a separate gate (`org_live_adapter.live_io_gates`).
This module's `live_io_enabled` stays false: written unlock is intent only.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _workspace_root() -> Path:
    # core/apps/org/service/org_field_ops.py → parents[5]=repo root (aiPlatform)
    return Path(__file__).resolve().parents[5]


def live_unlock_marker_path() -> Path:
    return _workspace_root() / "docs" / "contracts" / "ORG_L5_LIVE_UNLOCK.md"


def evaluate_live_unlock() -> Dict[str, Any]:
    """Dual gate for acknowledging live intent — does not enable SQL adapters."""
    env_on = (os.getenv("AIPLAT_ORG_IO_LIVE_UNLOCK") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    marker = live_unlock_marker_path()
    written = False
    if marker.is_file():
        try:
            text = marker.read_text(encoding="utf-8")
            written = "UNLOCK_STATUS: signed" in text
        except Exception:
            written = False
    return {
        "unlock_env": env_on,
        "unlock_doc_signed": written,
        "unlock_doc": str(marker) if marker.is_file() else "",
        "live_io_enabled": False,
        "status": "acknowledged" if (env_on and written) else "blocked",
        "authority_note": (
            "W7: env+doc is unlock intent only (this flag stays false). "
            "Outbound calls use http_json allowlist via live_io_gates; never arbitrary SQL. "
            "M4 still requires a real customer sandbox plus human sign-off"
        ),
    }


def field_ops_checklist(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Readiness checklist for field / customer sandbox (sign-off aid)."""
    from core.apps.org.service.org_fleet import evaluate_fleet_gate
    from core.apps.org.service.org_runtime import ensure_pilot_goal, list_runs

    ensure_pilot_goal(domain_id)
    live = evaluate_live_unlock()
    fleet = evaluate_fleet_gate(domain_id=domain_id)
    runs = list_runs(limit=5).get("runs") or []

    items: List[Dict[str, Any]] = [
        {
            "id": "runbook",
            "label": "ORG_L5_RUNBOOK.md 已读",
            "ok": (_workspace_root() / "docs" / "contracts" / "ORG_L5_RUNBOOK.md").is_file(),
            "href": "/docs/contracts/ORG_L5_RUNBOOK.md",
        },
        {
            "id": "sandbox_io",
            "label": "IO 默认 sandbox（D3）",
            "ok": (os.getenv("AIPLAT_ORG_IO_MODE") or "sandbox").lower()
            in ("", "sandbox", "readonly_graph"),
        },
        {
            "id": "pilot_runs",
            "label": "至少 1 次 OrgRun 记录",
            "ok": len(runs) >= 1,
            "detail": f"runs={len(runs)}",
        },
        {
            "id": "fleet_default_deny",
            "label": "Fleet 默认拒绝（allow_fleet=false）",
            "ok": not bool(fleet.get("allow_fleet")),
            "detail": fleet.get("status"),
        },
        {
            "id": "live_unlock",
            "label": "Live 解锁双门（env + 书面）— 仍无生产适配器",
            "ok": live.get("status") == "acknowledged",
            "detail": live.get("authority_note"),
        },
        {
            "id": "customer_sandbox_stub",
            "label": "客户沙箱 stub 种子存在（非生产）",
            "ok": False,
            "detail": "overlay _customer_sandbox",
        },
        {
            "id": "http_json_adapter",
            "label": "InterfaceSpec 已登记（默认关；解锁后才出站）",
            "ok": False,
            "detail": "connector.live / interface_ref",
        },
        {
            "id": "oncall",
            "label": "值班 / 回滚联系人已填（Runbook §值班）",
            "ok": False,
            "detail": "人工勾选；本 API 不替代签字",
        },
        {
            "id": "channel_charter",
            "label": "Phase C Charter 已落盘",
            "ok": (_workspace_root() / "docs" / "contracts" / "ORG_CHANNEL_INTERFACE_CHARTER.md").is_file(),
        },
        {
            "id": "signoff_pack",
            "label": "M4 签收包文档已落盘（≠ 客户已签字）",
            "ok": (_workspace_root() / "docs" / "contracts" / "ORG_M4_SIGNOFF_PACK.md").is_file(),
        },
        {
            "id": "digital_post",
            "label": "DigitalPost 种子可加载且绑定 OrgGoal",
            "ok": False,
            "detail": "org_ingress/pilot_post.json",
        },
        {
            "id": "usage_ledger",
            "label": "用量账本可重放且 billing 为空",
            "ok": False,
            "detail": "GET /org/usage/weekly",
        },
        {
            "id": "feishu_ingress",
            "label": "飞书单渠入站门存在（不要求已配密钥）",
            "ok": False,
            "detail": "confirm_required; second_channel=false",
        },
    ]
    try:
        from core.apps.org.service.org_interface import get_interface_spec

        pack = get_interface_spec(domain_id)
        spec = pack.get("spec") or {}
        val = pack.get("validation") or {}
        for it in items:
            if it["id"] == "http_json_adapter":
                # C1: seed must have interface_ref + valid structure; enabled stays false
                it["ok"] = bool(val.get("ok")) and bool(spec.get("interface_ref"))
                it["detail"] = (
                    f"ref={spec.get('interface_ref')} enabled={spec.get('enabled')} "
                    f"hosts={len(spec.get('allowed_hosts') or [])} "
                    f"warn={len(val.get('warnings') or [])}"
                )
    except Exception:
        logger.warning("InterfaceSpec checklist failed", exc_info=True)

    # detect customer sandbox stub seed
    try:
        from core.apps.fde.service.abox_connector import _sandbox_overlay_path
        import json

        p = _sandbox_overlay_path(domain_id)
        if p.is_file():
            raw = json.loads(p.read_text(encoding="utf-8")) or {}
            has = isinstance(raw.get("_customer_sandbox"), dict) and bool(raw.get("_customer_sandbox"))
            for it in items:
                if it["id"] == "customer_sandbox_stub":
                    it["ok"] = has
                    it["detail"] = str(p) if has else "missing _customer_sandbox"
    except Exception:  # noqa: cleanup-best-effort
        pass

    try:
        from core.apps.org.service.org_post import list_posts

        posted = list_posts()
        ok_posts = [
            row
            for row in (posted.get("items") or [])
            if (row.get("validation") or {}).get("ok")
            and (row.get("post") or {}).get("org_goal_id")
        ]
        for it in items:
            if it["id"] == "digital_post":
                it["ok"] = bool(ok_posts)
                post = (ok_posts[0].get("post") or {}) if ok_posts else {}
                it["detail"] = f"post={post.get('post_id')} goal={post.get('org_goal_id')}"
    except Exception:
        logger.warning("DigitalPost checklist failed", exc_info=True)

    try:
        from core.apps.org.service.org_usage import weekly_usage

        roll = weekly_usage(domain_id)
        for it in items:
            if it["id"] == "usage_ledger":
                it["ok"] = roll.get("billing") is None and roll.get("status") == "ok"
                it["detail"] = f"runs={roll.get('run_count')} billing=null"
    except Exception:
        logger.warning("usage ledger checklist failed", exc_info=True)

    try:
        from core.apps.org.service.org_ingress import ingress_status

        ing = ingress_status()
        for it in items:
            if it["id"] == "feishu_ingress":
                it["ok"] = (
                    ing.get("channel") == "feishu"
                    and ing.get("confirm_required") is True
                    and ing.get("second_channel") is False
                )
                it["detail"] = (
                    f"sign_configured={ing.get('sign_configured')} "
                    f"post={((ing.get('post') or {}).get('status'))}"
                )
    except Exception:
        logger.warning("ingress checklist failed", exc_info=True)

    try:
        from core.apps.org.service.org_signoff_progress import load_signoff_progress

        prog = load_signoff_progress()
        oncall_ok = bool(str(prog.get("oncall_name") or "").strip()) and bool(
            str(prog.get("oncall_contact") or "").strip()
        )
        for it in items:
            if it["id"] == "oncall":
                it["ok"] = oncall_ok
                it["detail"] = (
                    f"name={prog.get('oncall_name') or '—'} "
                    f"contact={prog.get('oncall_contact') or '—'} "
                    f"rollback={prog.get('rollback_owner') or '—'}"
                )
            if it["id"] == "live_unlock" and prog.get("intent_recorded") and not it["ok"]:
                it["detail"] = (
                    f"{it.get('detail') or ''} · intent_recorded=true（仍须 env+书面）"
                )
    except Exception:
        logger.warning("signoff progress checklist failed", exc_info=True)

    auto_ids = (
        "runbook",
        "sandbox_io",
        "pilot_runs",
        "fleet_default_deny",
        "customer_sandbox_stub",
    )
    pack_ids = (
        "runbook",
        "channel_charter",
        "signoff_pack",
        "sandbox_io",
        "fleet_default_deny",
        "http_json_adapter",
        "digital_post",
        "usage_ledger",
        "feishu_ingress",
    )
    by_id = {i["id"]: i for i in items}
    pack_ready = all(by_id[i]["ok"] for i in pack_ids if i in by_id) and not live.get(
        "live_io_enabled"
    )
    return {
        "domain_id": domain_id,
        "items": items,
        "live": live,
        "fleet": {
            "allowed": fleet.get("allowed"),
            "status": fleet.get("status"),
            "goal_id": fleet.get("goal_id"),
        },
        "signoff_ready": all(i["ok"] for i in items if i["id"] in auto_ids),
        "c5_pack_ready": pack_ready,
        "m4_claim_allowed": False,
        "human_pending": [
            i["id"] for i in items if i["id"] in ("live_unlock", "oncall") and not i["ok"]
        ],
        "authority_note": (
            "c5_pack_ready 只表示签收包（清单/门禁/Runbook）就绪，不是客户已签字。"
            "m4_claim_allowed 恒 false，直至客户沙箱真线 + 人工签收。"
            "customer_sandbox_stub ≠ 生产对接；signoff_ready 仅覆盖可自动项"
        ),
    }


def customer_signoff_view(domain_id: str = "it-ops") -> Dict[str, Any]:
    """V3 read model. Pack readiness is not a signature. No write, no button."""
    cl = field_ops_checklist(domain_id or "it-ops")
    return {
        "layer": "customer_signoff",
        "domain_id": cl.get("domain_id") or domain_id,
        "c5_pack_ready": bool(cl.get("c5_pack_ready")),
        "m4_claim_allowed": False,
        "signoff_button": False,
        "writable": False,
        "platform_layer": "value_dashboard",
        "authority_note": "材料包就绪不等于客户已签收。本视图不提供签收写入。",
    }


def signoff_prep_view(
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    *,
    as_markdown: bool = False,
) -> Dict[str, Any]:
    """Read-only prep score for customer review. Never flips m4_claim_allowed."""
    did = (domain_id or "").strip() or "it-ops"
    gid = (goal_id or "").strip() or "goal-it-ops-alert-sla"
    cl = field_ops_checklist(did)
    by_id = {i["id"]: i for i in (cl.get("items") or []) if isinstance(i, dict)}

    baseline_ok = False
    try:
        from core.apps.org.service.org_value_translation import load_value_baseline

        baseline_ok = (load_value_baseline(tenant_id="default").get("baseline_source") or "") != "missing"
    except Exception:
        baseline_ok = False

    weekly_ok = False
    run_count = 0
    kpis_ok = False
    weekly: Dict[str, Any] = {}
    try:
        from core.apps.org.service.org_kpi import weekly_kpi_report

        weekly = weekly_kpi_report(did, gid, week="")
        run_count = int(weekly.get("run_count") or 0)
        weekly_ok = run_count >= 1
        kpis = weekly.get("kpis") if isinstance(weekly.get("kpis"), dict) else {}
        # A3: keys must exist; null values allowed (no fabrication)
        kpis_ok = weekly_ok and all(
            k in kpis for k in ("mtta_seconds", "root_cause_rate", "exception_ratio")
        )
    except Exception:
        weekly_ok = False
        kpis_ok = False

    oncall_ok = bool((by_id.get("oncall") or {}).get("ok"))
    pack_ok = bool(cl.get("c5_pack_ready"))
    runs_ok = bool((by_id.get("pilot_runs") or {}).get("ok")) or weekly_ok
    evidence_ok = runs_ok  # export needs at least one run/trace

    rollback_ok = False
    rollback_at = ""
    try:
        from core.apps.org.service.org_signoff_progress import load_signoff_progress

        prog = load_signoff_progress()
        rollback_ok = bool(prog.get("rollback_drill_done"))
        rollback_at = str(prog.get("rollback_drill_at") or "")
    except Exception:
        rollback_ok = False

    inbox_ok = False
    try:
        from core.apps.org.service.org_approvals import _list_arbitration

        _list_arbitration(did)  # empty list still means inbox path works
        inbox_ok = True
    except Exception:
        inbox_ok = False

    meta = _signoff_gate_meta()
    gates = [
        {
            "id": "c5_pack",
            "label": "平台签收包齐套",
            "ok": pack_ok,
            **meta["c5_pack"],
        },
        {
            "id": "pilot_run",
            "label": "至少 1 次 OrgRun / 周报可出数",
            "ok": runs_ok,
            "detail": f"runs={run_count}",
            **meta["pilot_run"],
        },
        {
            "id": "kpis_visible",
            "label": "三 KPI 可看（可空值，不伪造）",
            "ok": kpis_ok,
            "detail": "mtta/root_cause/exception",
            **meta["kpis_visible"],
        },
        {
            "id": "inbox_readable",
            "label": "待批快照路径可读",
            "ok": inbox_ok,
            "detail": "arbitration list probe",
            **meta["inbox_readable"],
        },
        {
            "id": "oncall",
            "label": "值班联系人已记",
            "ok": oncall_ok,
            **meta["oncall"],
        },
        {
            "id": "baseline",
            "label": "价值基线已填（才算人时）",
            "ok": baseline_ok,
            **meta["baseline"],
        },
        {
            "id": "evidence",
            "label": "证据包可导出（有 run）",
            "ok": evidence_ok,
            **meta["evidence"],
        },
        {
            "id": "rollback_drill",
            "label": "回滚演练已记（暂停 Goal + IO deny）",
            "ok": rollback_ok,
            "detail": rollback_at or "",
            **meta["rollback_drill"],
        },
    ]
    done = sum(1 for g in gates if g["ok"])
    playbook = signoff_playbook_steps()
    out = {
        "ok": True,
        "domain_id": did,
        "goal_id": gid,
        "gates": gates,
        "playbook": playbook,
        "prep_score": f"{done}/{len(gates)}",
        "prep_complete": done == len(gates),
        "materials_ready_for_review": pack_ok and runs_ok and evidence_ok,
        "c5_pack_ready": pack_ok,
        "m4_claim_allowed": False,
        "signoff_button": False,
        "wrote_live_yaml": False,
        "doc": "docs/contracts/ORG_M4_SIGNOFF_PACK.md",
        "cover_statement": "本清单不是签字。m4_claim_allowed=false。客户尚未签收。",
        "authority_note": (
            "准备度只读。材料齐可送客户审，不等于已签收。"
            "m4_claim_allowed 恒 false。"
        ),
    }
    if as_markdown:
        out["markdown"] = render_signoff_prep_markdown(out)
    return out


def _signoff_gate_meta() -> Dict[str, Dict[str, str]]:
    """Static how-to / owner / UI anchor per gate. Not a signature."""
    return {
        "c5_pack": {
            "acceptance": "A1",
            "how_to": "核对 field-ops/checklist 的 c5_pack_ready；缺文档见 ORG_M4_SIGNOFF_PACK §1",
            "owner_hint": "平台 Owner",
            "ui_anchor": "prep-gates",
        },
        "pilot_run": {
            "acceptance": "A2",
            "how_to": "本页「按岗位开跑」至少 1 次；或看周报 run_count≥1",
            "owner_hint": "试点操作员",
            "ui_anchor": "run-actions",
        },
        "kpis_visible": {
            "acceptance": "A3",
            "how_to": "看本页周报三 KPI；空值可接受，禁止编造",
            "owner_hint": "试点操作员",
            "ui_anchor": "weekly-kpis",
        },
        "inbox_readable": {
            "acceptance": "A4",
            "how_to": "打开待批 inbox，点开提案快照看 Diff",
            "owner_hint": "审批人",
            "ui_anchor": "approval-inbox",
        },
        "oncall": {
            "acceptance": "A6",
            "how_to": "本页「记录值班」写入姓名与联系方式",
            "owner_hint": "试点 Owner",
            "ui_anchor": "oncall-section",
        },
        "baseline": {
            "acceptance": "A7",
            "how_to": "可先「试算」再「写入基线」；禁止用行业均值冒充客户基线",
            "owner_hint": "客户业务方",
            "ui_anchor": "value-section",
        },
        "evidence": {
            "acceptance": "A5",
            "how_to": "有 run 后点「导出签收证据」；封面声明不是签字",
            "owner_hint": "试点 Owner",
            "ui_anchor": "run-actions",
        },
        "rollback_drill": {
            "acceptance": "A8",
            "how_to": "按签收包 §5 真做演练后点「记回滚演练」；按钮不自动改 Goal/IO",
            "owner_hint": "试点 Owner",
            "ui_anchor": "oncall-section",
        },
    }


def signoff_playbook_steps() -> List[Dict[str, str]]:
    """Customer-facing script from pilot start to review. Not a signature."""
    return [
        {
            "step": "1",
            "title": "开跑并看周报",
            "customer_sees": "岗位开跑 → 周报三 KPI（可空）",
            "customer_approves": "确认跑通一轮，不签 L5",
            "gates": "pilot_run,kpis_visible",
        },
        {
            "step": "2",
            "title": "待批可打开",
            "customer_sees": "inbox + 提案 Diff",
            "customer_approves": "确认人批路径可读；本步不批准写活本体",
            "gates": "inbox_readable",
        },
        {
            "step": "3",
            "title": "基线与收益",
            "customer_sees": "试算 → 写入基线 → 价值卡人时",
            "customer_approves": "确认数字来自客户基线，不是行业模板",
            "gates": "baseline",
        },
        {
            "step": "4",
            "title": "值班与回滚演练",
            "customer_sees": "值班联系人 + 回滚演练记录",
            "customer_approves": "确认演练做过；按钮只记结果",
            "gates": "oncall,rollback_drill",
        },
        {
            "step": "5",
            "title": "导出送审材料",
            "customer_sees": "证据包 + 准备度清单 Markdown",
            "customer_approves": "内部审计可看；仍声明材料齐 ≠ 已签收",
            "gates": "c5_pack,evidence",
        },
        {
            "step": "6",
            "title": "双签（人工）",
            "customer_sees": "签收包 §6 勾选表",
            "customer_approves": "客户+平台双签后才允许有条件 L5 话术；程序不打开 m4",
            "gates": "",
        },
    ]


def render_signoff_prep_markdown(view: Dict[str, Any]) -> str:
    """Customer-review checklist. Read-only text; never a signature."""
    gates = view.get("gates") or []
    lines = [
        "# it-ops 签收准备度清单",
        "",
        str(view.get("cover_statement") or "本清单不是签字。m4_claim_allowed=false。客户尚未签收。"),
        "",
        f"- domain: `{view.get('domain_id')}`",
        f"- goal: `{view.get('goal_id')}`",
        f"- prep_score: **{view.get('prep_score')}**",
        f"- materials_ready_for_review: `{view.get('materials_ready_for_review')}`",
        f"- prep_complete: `{view.get('prep_complete')}`（仍不等于已签收）",
        f"- m4_claim_allowed: `false`",
        "",
        "## 八闸门",
        "",
    ]
    for g in gates:
        if not isinstance(g, dict):
            continue
        mark = "[x]" if g.get("ok") else "[ ]"
        detail = f" · {g.get('detail')}" if g.get("detail") else ""
        acc = f" ({g.get('acceptance')})" if g.get("acceptance") else ""
        lines.append(f"- {mark} {g.get('label')}{acc}{detail}")
        if g.get("how_to"):
            lines.append(f"  - 如何核：{g.get('how_to')}")
        if g.get("owner_hint"):
            lines.append(f"  - 责任：{g.get('owner_hint')}")
    playbook = view.get("playbook") or []
    if playbook:
        lines.extend(["", "## 签收剧本（到送审为止）", ""])
        for step in playbook:
            if not isinstance(step, dict):
                continue
            lines.append(
                f"{step.get('step')}. **{step.get('title')}** — "
                f"看：{step.get('customer_sees')}；"
                f"批：{step.get('customer_approves')}"
            )
    lines.extend(
        [
            "",
            "## 用法",
            "",
            "1. 未勾项按闸门「如何核」在组织试点页补齐。",
            "2. 证据包另导出：`GET …/signoff/evidence-pack?format=markdown`。",
            "3. 送客户审阅时仍须声明：材料齐 ≠ 双签；不得称 L5 已达成。",
            "",
            f"权威文档：`{view.get('doc') or 'docs/contracts/ORG_M4_SIGNOFF_PACK.md'}`",
            "",
        ]
    )
    return "\n".join(lines)
