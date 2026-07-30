"""FDE Manuals — project delivery manual CRUD, regenerate, versions, start-delivery (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException, Query

from pydantic import BaseModel as _PydanticBaseModel

import os
import re as _re_manual
import json
from datetime import datetime, timezone

router = APIRouter(tags=["fde-manuals"])

_MANUALS_DIR = os.path.expanduser("~/.aiplat/fde-manuals")
os.makedirs(_MANUALS_DIR, exist_ok=True)


class FdeManualRequest(_PydanticBaseModel):
    project_name: str = ""
    industry: str = ""
    company_name: str = ""
    pain_points: str = ""
    delivery_mode: str = "online"
    poc_duration_days: int = 3
    compliance_requirements: list = []
    assigned_fde: str = ""


def _generate_manual_content(req: FdeManualRequest) -> str:
    ind = req.industry or "通用"
    co = req.company_name or f"{ind}行业客户"
    pn = req.project_name or f"{co} AI落地交付项目"
    fde = req.assigned_fde or "待指派"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    score = min(len((req.pain_points or "").split(",")) * 10 + 40, 100) if req.pain_points else 40
    badge = f"落地就绪度预估：{score}%"

    kpi_map = {
        "政务": [("围标识别率", "≥85%"), ("误报率", "<10%"), ("信创兼容性", "100%通过")],
        "金融": [("反欺诈准确率", "≥90%"), ("审批时效缩短", "≥60%"), ("监管合规", "100%")],
        "制造": [("故障预测准确率", "≥80%"), ("排程效率提升", "≥30%")],
        "医疗": [("影像识别准确率", "≥92%"), ("病历结构化准确率", "≥88%")],
    }
    kpis = kpi_map.get(ind, [("准确率", "≥85%"), ("召回率", "≥90%"), ("误报率", "<10%")])

    compliance = req.compliance_requirements or {
        "政务": ["信创适配", "数据安全法", "个人信息保护法"],
        "金融": ["银保监会报送", "反洗钱", "数据安全法"],
        "制造": ["工业数据安全", "信息物理系统安全"],
        "医疗": ["HIPAA", "医疗器械数据安全"],
    }.get(ind, ["数据安全法", "个人信息保护法"])

    sol_table = ""
    try:
        from core.harness.knowledge.ontology_bus import load_solution_archetypes
        sols = load_solution_archetypes()[:6]
        sol_table = "\n".join([
            "| 方案类别 | 数据成熟度 | 成本 | 部署 | 周期 | 信创 |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ] + [
            f"| {s.get('name','')} | ≥{s.get('data_maturity_min','')} | {s.get('cost_level','')} | {'/'.join(s.get('deployment_modes',[]))} | {s.get('estimated_cycle_months','')}月 | {'✅' if s.get('xinchuang_compatible') else '部分'} |"
            for s in sols
        ])
    except Exception:
        sol_table = "| 方案原型库加载失败 |"

    term_table = ""
    try:
        from core.api.core_facade import GraphIndex
        tg = GraphIndex.load("enterprise-terms")
        terms = [(n.entity_name[:60], getattr(n, "source_doc_id", "")[:20])
                 for _, n in tg._nodes.items() if getattr(n, "class_name", "") == "Term"][:8]
        if terms:
            term_table = "\n".join(["| 术语 | 来源 |", "| :--- | :--- |"] + [f"| {t[0]} | {t[1]} |" for t in terms])
    except Exception:
        term_table = "| 术语字典为空 | 随诊断次数自播种 |"

    delivery_stats = ""
    try:
        from core.api.core_facade import GraphIndex
        fd = GraphIndex.load("fde-delivery")
        sessions = sum(1 for _, n in fd._nodes.items() if getattr(n, "class_name", "") == "DiagnosisSession")
        if sessions > 0:
            delivery_stats = f"历史诊断数：{sessions} 次"
    except Exception:
        delivery_stats = "尚无历史数据"

    return f"""# FDE 标准交付手册 — {pn}

> **生成时间**: {ts} | **FDE**: {fde} | **版本**: v1
> {badge}

---

## 0. 项目概览

| 项目 | 内容 |
|------|------|
| 项目名 | {pn} |
| 客户 | {co} |
| 行业 | {ind} |
| 痛点 | {req.pain_points or '待补充'} |
| 交付模式 | {'离线部署' if req.delivery_mode == 'offline' else '在线部署'} |
| POC 周期 | {req.poc_duration_days} 天 |
| 合规要求 | {', '.join(compliance)} |
| 指派 FDE | {fde} |
| 参考数据 | {delivery_stats} |

---

## 1. 推荐方案

{sol_table}

---

## 2. POC 验证清单

| 验收指标 | 目标值 |
|------|:--:|
{chr(10).join(f"| {kpi[0]} | {kpi[1]} |" for kpi in kpis)}

{{{{CUSTOM_SECTION: poc_checklist}}}}
POC 自定义验证项（FDE 按需补充）：
{{{{/CUSTOM_SECTION}}}}

---

## 3. 术语参考

{term_table}

---

## 4. FDE 备注

{{{{CUSTOM_SECTION: fde_notes}}}}
FDE 填写项目特殊约定、客户联系人、注意事项等：
{{{{/CUSTOM_SECTION}}}}

---

## 5. 交付检查清单

| # | 检查项 | ☐ |
|:--:|------|:--:|
| 1 | POC 环境搭建完成 | ☐ |
| 2 | 客户诊断已执行 | ☐ |
| 3 | 客户签字确认 | ☐ |
| 4 | 30 天健康检查已安排 | ☐ |

{{{{CUSTOM_SECTION: delivery_checklist}}}}
FDE 自定义交付检查项：
{{{{/CUSTOM_SECTION}}}}

---

*由 aiPlat FDE 工作台自动生成 — {ts}*
"""


def _extract_custom_sections(text: str) -> Dict[str, str]:
    """Extract FDE-edited custom sections from a manual."""
    sections = {}
    pos = 0
    while True:
        start_marker = "{{CUSTOM_SECTION: "
        idx_s = text.find(start_marker, pos)
        if idx_s < 0:
            break
        idx_name_end = text.find("}}", idx_s)
        if idx_name_end < 0:
            break
        sec_name = text[idx_s + len(start_marker):idx_name_end].strip()
        idx_content_start = text.find("\n", idx_name_end) + 1
        idx_e = text.find("{{/CUSTOM_SECTION}}", idx_content_start)
        if idx_e < 0:
            break
        sections[sec_name] = text[idx_content_start:idx_e].strip()
        pos = idx_e + len("{{/CUSTOM_SECTION}}")
    return sections


def _get_manual_path(project_id: str, version: str = "current") -> str:
    os.makedirs(_MANUALS_DIR, exist_ok=True)
    safe_id = project_id.replace("/", "_")[:80]
    if version == "current":
        return os.path.join(_MANUALS_DIR, f"{safe_id}-current.md")
    return os.path.join(_MANUALS_DIR, f"{safe_id}-{version}.md")


@router.post("/manuals", response_model=FdeStatusResponse)
async def fde_create_manual(req: FdeManualRequest):
    pid = (f"{req.industry}_{req.company_name}" if req.industry else req.company_name or "未命名项目").replace(" ", "_")[:60]
    content = _generate_manual_content(req)
    with open(_get_manual_path(pid), "w", encoding="utf-8") as f:
        f.write(content)
    return {
        "project_id": pid, "version": "v1",
        "content": content,
        "next_steps": [f"GET /fde/manuals/{pid}", f"PUT /fde/manuals/{pid}", f"POST /fde/manuals/{pid}/regenerate"],
    }


@router.get("/manuals/{project_id}", response_model=FdeItemResponse)
async def fde_get_manual(project_id: str):
    path = _get_manual_path(project_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Manual not found for {project_id}")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"project_id": project_id, "content": content, "custom_sections": _extract_custom_sections(content)}


@router.put("/manuals/{project_id}", response_model=FdeStatusResponse)
async def fde_update_manual(project_id: str, section: str = "", new_content: str = ""):
    path = _get_manual_path(project_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Manual not found for {project_id}")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if section and new_content:
        start = f"{{{{CUSTOM_SECTION: {section}}}}}"
        end = "{{/CUSTOM_SECTION}}"
        idx_s = content.find(start)
        idx_e = content.find(end, idx_s) if idx_s >= 0 else -1
        if idx_s >= 0 and idx_e >= 0:
            before = content[:idx_s + len(start)]
            after = content[idx_e:]
            content = before + "\n" + new_content + "\n" + after
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        with open(_get_manual_path(project_id, f"v_{ts}"), "w", encoding="utf-8") as f:
            f.write(content)
        with open(_get_manual_path(project_id), "w", encoding="utf-8") as f:
            f.write(content)
    return {"project_id": project_id, "updated_section": section, "content": content}


@router.post("/manuals/{project_id}/regenerate", response_model=FdeStatusResponse)
async def fde_regenerate_manual(project_id: str):
    path = _get_manual_path(project_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Manual not found for {project_id}")
    with open(path, "r", encoding="utf-8") as f:
        old = f.read()
    custom = _extract_custom_sections(old)
    ind = ""
    for line in old.split("\n"):
        if "| 行业" in line:
            ind = line.split("|")[2].strip()
            break
    req = FdeManualRequest(industry=ind, company_name=project_id.replace("_", " "))
    content = _generate_manual_content(req)
    for sec_key, sec_text in custom.items():
        start = f"{{{{CUSTOM_SECTION: {sec_key}}}}}"
        end = "{{/CUSTOM_SECTION}}"
        idx_s = content.find(start)
        idx_e = content.find(end, idx_s) if idx_s >= 0 else -1
        if idx_s >= 0 and idx_e >= 0:
            before = content[:idx_s + len(start)]
            after = content[idx_e:]
            content = before + "\n" + sec_text + "\n" + after
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    with open(_get_manual_path(project_id, f"v_{ts}"), "w", encoding="utf-8") as f:
        f.write(content)
    with open(_get_manual_path(project_id), "w", encoding="utf-8") as f:
        f.write(content)
    return {"project_id": project_id, "version": ts, "preserved_sections": list(custom.keys()), "content": content}


@router.get("/manuals/{project_id}/versions", response_model=FdeItemResponse)
async def fde_manual_versions(project_id: str):
    safe_id = project_id.replace("/", "_")[:80]
    versions = []
    for fname in sorted(os.listdir(_MANUALS_DIR)):
        if fname.startswith(safe_id) and fname.endswith(".md") and fname != f"{safe_id}-current.md":
            fpath = os.path.join(_MANUALS_DIR, fname)
            mtime = os.path.getmtime(fpath)
            versions.append({"file": fname, "modified": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()})
    return {"project_id": project_id, "versions": sorted(versions, key=lambda v: v["modified"], reverse=True)}


_MANUAL_META = os.path.join(_MANUALS_DIR, "meta.json")


def _load_manual_meta() -> dict:
    try:
        with open(_MANUAL_META) as f:
            import json
            return json.load(f)
    except Exception:
        return {}


def _save_manual_meta(meta: dict):
    import json
    with open(_MANUAL_META, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


@router.get("/manuals", response_model=FdeItemResponse)
async def fde_list_manuals():
    """List all project manuals with their status."""
    meta = _load_manual_meta()
    manuals = []
    for fname in sorted(os.listdir(_MANUALS_DIR)):
        if fname.endswith("-current.md"):
            pid = fname.replace("-current.md", "")
            mtime = os.path.getmtime(os.path.join(_MANUALS_DIR, fname))
            manuals.append({
                "project_id": pid,
                "status": meta.get(pid, {}).get("status", "active"),
                "modified": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "versions": len([v for v in os.listdir(_MANUALS_DIR) if v.startswith(pid) and not v.endswith("-current.md")]),
            })
    return {"total": len(manuals), "manuals": sorted(manuals, key=lambda m: m["modified"], reverse=True)}


@router.patch("/manuals/{project_id}", response_model=FdeStatusResponse)
async def fde_update_manual_status(project_id: str, status: str = "active"):
    """Update a manual's status: draft | active | archived."""
    path = _get_manual_path(project_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Manual not found for {project_id}")
    meta = _load_manual_meta()
    meta.setdefault(project_id, {})
    meta[project_id]["status"] = status
    _save_manual_meta(meta)
    return {"project_id": project_id, "status": status}


@router.post("/manuals/{project_id}/start-delivery", response_model=FdeStatusResponse)
async def fde_manual_start_delivery(project_id: str):
    """Create a delivery tracking session from a project manual.

    Reads the manual's project config, creates a DiagnosisSession
    in fde-delivery GraphIndex with DeliveryActions for each solution archetype.
    Closes the manual→delivery loop.
    """
    path = _get_manual_path(project_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Manual not found for {project_id}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract project info from manual (only from project overview table)
    ind, co, pains = "", "", ""
    for line in content.split("\n")[:50]:  # Stop after overview table
        line = line.strip()
        if not line.startswith("|") or "| :---" in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        key, val = parts[1], parts[2]
        if key == "行业":
            ind = val
        elif key == "客户":
            co = val
        elif key == "痛点":
            pains = val

    if not co:
        co = project_id.replace("_", " ")

    import time as _t_sd, json as _json_sd
    from core.api.core_facade import GraphIndex

    fd = GraphIndex.load("fde-delivery")
    ts = str(int(_t_sd.time()))
    sid = f"session_{co.replace(' ', '_')}_{ts}"
    fd.add_entity(sid, co, "DiagnosisSession", source_doc_id=project_id)

    # Extract solution archetypes from manual as DeliveryActions
    actions_created = 0
    for line in content.split("\n"):
        if line.startswith("| ") and "≥" in line and "|" in line[2:]:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                sol_name = parts[1]
                if sol_name and sol_name != "方案类别" and len(sol_name) > 3:
                    aid = f"{sid}_action_{actions_created}"
                    fd.add_entity(aid, sol_name, "DeliveryAction", source_doc_id=sid)
                    fd.add_relation(sid, aid, "has_action", relation_label="手册方案", confidence=0.85)
                    ev_id = f"evidence_{sid}_{actions_created}"
                    fd.add_entity(ev_id, f"{sol_name} | {ind}域(手册)", "Evidence", source_doc_id=sid)
                    fd.add_relation(sid, ev_id, "has_evidence", relation_label="证据", confidence=0.85)
                    actions_created += 1

    # SessionMeta
    meta_blob = {
        "evidence_map": [],
        "knowledge_gaps": [],
        "readiness_score": min(len(pains.split(",")) * 10 + 40, 100) if pains else 50,
        "industry": ind, "pain_points": pains,
    }
    mid = f"meta_{sid}"
    fd.add_entity(mid, _json_sd.dumps(meta_blob, ensure_ascii=False)[:8000], "SessionMeta", source_doc_id=sid)
    fd.add_relation(sid, mid, "has_meta", relation_label="元数据", confidence=1.0)

    # StateTransition
    tid = f"trans_{sid}_{ts}"
    fd.add_entity(tid, "Session → generated (from manual)", "StateTransition", source_doc_id=sid)
    fd.add_relation(sid, tid, "has_transition", relation_label="状态变更", confidence=1.0)

    return {
        "project_id": project_id,
        "session_id": sid,
        "company": co,
        "industry": ind,
        "actions_created": actions_created,
        "next_steps": [
            f"GET /fde/sessions/{sid} — 查看交付详情",
            f"GET /fde/sessions/{sid}/timeline — 查看时间线",
            f"POST /fde/delivery/feedback — 更新交付状态",
        ],
    }
