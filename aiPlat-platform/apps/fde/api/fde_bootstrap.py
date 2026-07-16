"""FDE Bootstrap — seed demo diagnosis sessions for all industries (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

import time
import json

router = APIRouter(tags=["fde-bootstrap"])


@router.post("/bootstrap-test-data", response_model=dict)
async def fde_bootstrap_test_data(
    industry: str = Query("政务", description="Industry for the demo session"),
    company: str = Query("", description="Company name override"),
):
    """Seed a complete demo diagnosis session.

    Use different industry values to populate the dashboard with diverse data.
    """
    import time as _t_bt
    import json as _json_bt

    company_name = company.strip() or {"政务":"某省政务服务中心","金融":"某市商业银行",
        "制造":"华东精密制造有限公司","医疗":"北京三甲医疗集团"}.get(industry,f"{industry}示范企业")
    pains = {"政务":"围标串标行为难以发现,招标信息检索效率低,关联方识别困难",
        "金融":"贷款审批冗长,信用评估依赖人工,反欺诈实时性不足",
        "制造":"设备故障预测不准确,生产排程响应慢,供应链协同缺失"}.get(industry,f"{industry}痛点1,{industry}痛点2,{industry}痛点3")

    readiness = {"政务":78, "金融":65, "制造":52, "医疗":70}.get(industry, 60)

    ts = str(int(_t_bt.time()))
    sid = f"session_{company_name.replace(' ', '')}_{ts}"

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        # fde-delivery: session + actions + evidence + meta + transitions
        fd = GraphIndex.load("fde-delivery")
        fd.add_entity(sid, company_name, "DiagnosisSession", source_doc_id="bootstrap")

        actions_data = {
            "政务": [("文本相似度检测系统", "招标文件自动对比"), ("RAG知识库构建", "政务法规智能问答"), ("关联图谱分析平台", "投标人关系网络发现")],
            "金融": [("智能风控引擎", "实时交易反欺诈检测"), ("信用评分模型", "自动化贷款审批"), ("监管报送自动化", "合规数据一键生成")],
            "制造": [("预测性维护系统", "设备故障提前预警"), ("生产排程优化", "AI驱动的产线调度"), ("供应链协同平台", "库存与物流智能匹配")],
            "医疗": [("AI影像诊断", "CT/X光自动识别病灶"), ("病历结构化", "非结构化病历自动抽取"), ("药品库存预警", "库存余量智能预测与补货")],
        }.get(industry, [("智能分析引擎", f"{industry}数据洞察"), ("流程自动化", f"{industry}流程优化"), ("知识管理", f"{industry}知识沉淀")])

        evidence_data = [(f"{a[0]} | {industry}域(跨域参考)", "ontology_instance") for a in actions_data[:1]] + \
                       [(f"{a[0]} | 行业普遍痛点", "llm_inference") for a in actions_data[1:2]] + \
                       [(f"{a[0]} | 历史案例支撑", "historical_case") for a in actions_data[2:3]]
        for i, (name, _) in enumerate(actions_data):
            aid = f"{sid}_action_{i}"
            fd.add_entity(aid, name, "DeliveryAction", source_doc_id=sid)
            fd.add_relation(sid, aid, "has_action", relation_label="交付行动", confidence=0.85)

        for i, (ev_name, _) in enumerate(evidence_data):
            ev_id = f"evidence_{sid}_{i}"
            fd.add_entity(ev_id, ev_name, "Evidence", source_doc_id=sid)
            fd.add_relation(sid, ev_id, "has_evidence", relation_label="证据", confidence=0.85)

        # SessionMeta
        meta_blob = {
            "evidence_map": [
                {"index": i, "pain_point": p.split(": ")[0] if ": " in p else p[:30],
                 "ai_opportunity": actions_data[i][0], "confidence": ["高","中","高"][i],
                 "dependency": "", "source": f"{industry}域"}
                for i, p in enumerate(pains.split(",")[:3])
            ],
            "knowledge_gaps": [],
            "readiness_score": readiness,
            "industry": industry,
            "pain_points": pains,
        }
        mid = f"meta_{sid}"
        fd.add_entity(mid, _json_bt.dumps(meta_blob, ensure_ascii=False)[:8000], "SessionMeta", source_doc_id=sid)
        fd.add_relation(sid, mid, "has_meta", relation_label="诊断元数据", confidence=1.0)

        # StateTransition
        tid = f"trans_{sid}_{ts}"
        fd.add_entity(tid, "Session → delivered (bootstrap)", "StateTransition", source_doc_id=sid)
        fd.add_relation(sid, tid, "has_transition", relation_label="状态变更", confidence=1.0)

        # enterprise-terms: seed terms
        tg = GraphIndex.load("enterprise-terms")
        for term_name in ["文本相似度检测", "关联图谱分析", "围标串标"]:
            term_id = f"term_bootstrap_{term_name.replace(' ', '_')[:40]}"
            tg.add_entity(term_id, term_name, "Term", source_doc_id=sid)

        return {
            "session_id": sid,
            "company": company_name,
            "industry": industry,
            "actions_created": len(actions_data),
            "evidence_created": len(evidence_data),
            "terms_seeded": 3,
            "status": "delivered (bootstrap)",
            "next_steps": [
                f"GET /fde/sessions/{sid} — 查看详情",
                f"GET /fde/sessions/{sid}/timeline — 查看时间线",
                f"GET /fde/sessions/{sid}/quality — 质量评分",
                f"GET /fde/sessions/{sid}/ontology-coverage — 本体覆盖率",
                "GET /fde/dashboard — 查看仪表板",
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bootstrap failed: {str(e)[:300]}")


@router.post("/bootstrap-all", response_model=dict)
async def fde_bootstrap_all():
    """Seed demo sessions for all 4 industries at once.

    Convenience endpoint — populates the entire system with one call.
    """
    industries = ["政务", "金融", "制造", "医疗"]
    results = []
    for ind in industries:
        # Reuse bootstrap logic inline
        import time as _t_ball, json as _json_ball
        from core.harness.ontology_engine.graph_index import GraphIndex

        company_names = {"政务":"某省政务服务中心","金融":"某市商业银行","制造":"华东精密制造有限公司","医疗":"北京三甲医疗集团"}
        actions_map = {
            "政务":[("文本相似度检测","招标对比"),("RAG知识库","政务问答"),("关联图谱分析","关系网络")],
            "金融":[("智能风控引擎","反欺诈"),("信用评分模型","贷款审批"),("监管报送","合规")],
            "制造":[("预测维护","故障预警"),("排程优化","产线调度"),("供应链协同","库存匹配")],
            "医疗":[("AI影像诊断","病灶识别"),("病历结构化","信息抽取"),("库存预警","智能补货")],
        }
        co = company_names.get(ind,f"{ind}示范企业")
        ts = str(int(_t_ball.time()))
        sid = f"session_{co.replace(' ','')}_{ts}"
        fd = GraphIndex.load("fde-delivery")
        fd.add_entity(sid, co, "DiagnosisSession", source_doc_id="bootstrap-all")
        acts = actions_map.get(ind,[("智能分析",f"{ind}洞察")])
        for i,(name,_) in enumerate(acts):
            aid = f"{sid}_action_{i}"
            fd.add_entity(aid, name, "DeliveryAction", source_doc_id=sid)
            fd.add_relation(sid, aid, "has_action", relation_label="交付行动", confidence=0.85)
            ev_id = f"evidence_{sid}_{i}"
            fd.add_entity(ev_id, f"{name} | {ind}域", "Evidence", source_doc_id=sid)
            fd.add_relation(sid, ev_id, "has_evidence", relation_label="证据", confidence=0.85)
        meta_blob = {"evidence_map":[],"knowledge_gaps":[],"readiness_score":{"政务":78,"金融":65,"制造":52,"医疗":70}.get(ind,60),"industry":ind,"pain_points":""}
        mid = f"meta_{sid}"
        fd.add_entity(mid, _json_ball.dumps(meta_blob,ensure_ascii=False)[:8000],"SessionMeta",source_doc_id=sid)
        fd.add_relation(sid,mid,"has_meta",relation_label="诊断元数据",confidence=1.0)
        tid = f"trans_{sid}_{ts}"
        fd.add_entity(tid,f"Session → delivered ({ind})","StateTransition",source_doc_id=sid)
        fd.add_relation(sid,tid,"has_transition",relation_label="状态变更",confidence=1.0)
        tg = GraphIndex.load("enterprise-terms")
        for tn in [acts[0][0][:20], acts[1][0][:20]]:
            ti = f"term_{ind}_{tn.replace(' ','_')[:40]}"
            tg.add_entity(ti, tn, "Term", source_doc_id=sid)
        results.append({"industry": ind, "session_id": sid, "company": co, "actions": len(acts)})

    return {
        "total_industries": len(industries),
        "total_sessions": len(results),
        "total_actions": sum(r["actions"] for r in results),
        "results": results,
        "next": "GET /fde/benchmark — 查看行业基准分析",
    }
