"""FDE 交付计划 — 需求文本 → 实施计划骨架填空 + 与 pipeline 联动进度。

非目标：不替代⑦验收清单 / Org 签收；不从 FR 扫代码证成；不持久化需求原文。
进度禁止本地假百分比：done 仅来自 pipeline_snapshot 或已存 manual_done。
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import get_aiplat_home

logger = logging.getLogger(__name__)

AUTO_CHECK_KEYS = (
    "customer",
    "domain",
    "diagnosis",
    "pocProfile",
    "deployVersion",
    "canaryResult",
    "adopted",
)

_NEW_DOMAIN_HINTS = (
    "新域",
    "新建域",
    "无匹配域",
    "无现成域",
    "from scratch",
    "new domain",
    "无匹配",
)


def _plans_dir() -> Path:
    """计划持久化目录 ``~/.aiplat/fde_delivery_plans``。"""
    d = Path(get_aiplat_home()) / "fde_delivery_plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_ns(customer_namespace: str) -> str:
    """将命名空间规范为文件名安全片段。

    Args:
        customer_namespace: 客户命名空间。

    Returns:
        安全短串；空则 raise ValueError。
    """
    raw = (customer_namespace or "").strip()
    if not raw:
        raise ValueError("customer_namespace is required")
    safe = "".join(c for c in raw if c.isalnum() or c in "_-.")[:120]
    if not safe:
        raise ValueError("customer_namespace has no usable characters")
    return safe


def _plan_path(customer_namespace: str) -> Path:
    """计划 JSON 路径。

    Args:
        customer_namespace: 客户命名空间。
    """
    return _plans_dir() / f"{_safe_ns(customer_namespace)}.json"


def _skeleton_paths() -> List[Path]:
    """骨架 YAML 候选路径（home 覆盖 → 仓库种子）。"""
    home = Path(get_aiplat_home()) / "fde" / "delivery_plan_skeleton.yaml"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "fde"
        / "delivery_plan_skeleton.yaml"
    )
    return [home, seed]


def _fallback_skeleton() -> Dict[str, Any]:
    """代码内最小骨架（种子文件缺失时）。"""
    return {
        "version": 1,
        "phases": [
            {
                "id": "gate0",
                "title": "Gate0 决策锁定",
                "fde_tab": "customers",
                "steps": [
                    {
                        "id": "gate0.deploy_mode",
                        "title": "锁定部署模式",
                        "ops": ["确认 online/hybrid/airgap"],
                        "auto_check": None,
                    },
                    {
                        "id": "gate0.latency",
                        "title": "锁定性能口径",
                        "ops": ["确认一期延迟/并发验收线"],
                        "auto_check": None,
                    },
                    {
                        "id": "gate0.compliance",
                        "title": "锁定合规授权",
                        "ops": ["确认授权与留存策略"],
                        "auto_check": None,
                    },
                    {
                        "id": "gate0.scope",
                        "title": "锁定一期范围",
                        "ops": ["确认 In/Out"],
                        "auto_check": None,
                    },
                ],
            },
            {
                "id": "fde1",
                "title": "① 业务认知",
                "fde_tab": "customers",
                "steps": [
                    {
                        "id": "fde1.customer",
                        "title": "创建并切换客户 Profile",
                        "ops": ["①新建并切换客户"],
                        "auto_check": "customer",
                    }
                ],
            },
            {
                "id": "domain_new",
                "title": "新建域（插段）",
                "fde_tab": "capability",
                "steps": [
                    {
                        "id": "domain_new.yaml",
                        "title": "编写域本体",
                        "ops": ["/knowledge/business 建域"],
                        "auto_check": None,
                    },
                    {
                        "id": "domain_new.seed",
                        "title": "注入种子",
                        "ops": ["注入脱敏种子"],
                        "auto_check": None,
                    },
                ],
            },
            {
                "id": "fde2",
                "title": "② 评估域",
                "fde_tab": "capability",
                "steps": [
                    {
                        "id": "fde2.domain",
                        "title": "选择业务域",
                        "ops": ["②选域"],
                        "auto_check": "domain",
                    }
                ],
            },
            {
                "id": "fde3",
                "title": "③ 问题重构",
                "fde_tab": "assess",
                "steps": [
                    {
                        "id": "fde3.diagnosis",
                        "title": "诊断报告",
                        "ops": ["③运行诊断"],
                        "auto_check": "diagnosis",
                    }
                ],
            },
            {
                "id": "factory",
                "title": "应用工厂并行",
                "fde_tab": "poc",
                "steps": [
                    {
                        "id": "factory.project",
                        "title": "应用工厂项目",
                        "ops": ["打开 /app/factory"],
                        "auto_check": None,
                    }
                ],
            },
            {
                "id": "fde4",
                "title": "④ 验证价值",
                "fde_tab": "poc",
                "steps": [
                    {
                        "id": "fde4.poc",
                        "title": "POC 通过",
                        "ops": ["④ POC"],
                        "auto_check": "pocProfile",
                    },
                    {
                        "id": "fde4.gp1",
                        "title": "GP1",
                        "ops": ["主路径演示"],
                        "auto_check": None,
                    },
                    {
                        "id": "fde4.gp2",
                        "title": "GP2",
                        "ops": ["边界路径"],
                        "auto_check": None,
                    },
                    {
                        "id": "fde4.gp3",
                        "title": "GP3",
                        "ops": ["降级/负例"],
                        "auto_check": None,
                    },
                ],
            },
            {
                "id": "fde5",
                "title": "⑤ 快速构建",
                "fde_tab": "deploy",
                "steps": [
                    {
                        "id": "fde5.deploy",
                        "title": "打包",
                        "ops": ["⑤打包"],
                        "auto_check": "deployVersion",
                    }
                ],
            },
            {
                "id": "fde6",
                "title": "⑥ 评测护栏",
                "fde_tab": "canary",
                "steps": [
                    {
                        "id": "fde6.canary",
                        "title": "灰度通过",
                        "ops": ["⑥灰度"],
                        "auto_check": "canaryResult",
                    }
                ],
            },
            {
                "id": "fde7",
                "title": "⑦ 验收移交",
                "fde_tab": "accept",
                "steps": [
                    {
                        "id": "fde7.adopted",
                        "title": "签收",
                        "ops": ["⑦签收"],
                        "auto_check": "adopted",
                    }
                ],
            },
            {
                "id": "fde8",
                "title": "⑧ 运营监控",
                "fde_tab": "evolution",
                "steps": [
                    {
                        "id": "fde8.monitor",
                        "title": "监控护航",
                        "ops": ["⑧监控"],
                        "auto_check": None,
                    }
                ],
            },
        ],
    }


def load_delivery_plan_skeleton() -> Dict[str, Any]:
    """加载交付计划骨架 YAML；缺失则用代码 fallback。

    Returns:
        含 ``phases`` 的骨架 dict。
    """
    for p in _skeleton_paths():
        if not p.is_file():
            continue
        try:
            import yaml

            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("phases"), list):
                return data
        except Exception as e:
            logger.warning("skeleton load failed %s: %s", p, e)
    return _fallback_skeleton()


def _prompt_template() -> str:
    """读取填空 prompt 模板。"""
    p = Path(__file__).resolve().parents[1] / "prompts" / "delivery_plan_fill.md"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return (
        "根据需求输出 JSON：delivery_type, phase0_days, honesty_locks, "
        "summary_note, step_fills。客户: ${customer_namespace}\n${requirement_text}"
    )


def _sha256_text(text: str) -> str:
    """需求文本哈希（不落原文）。

    Args:
        text: 原文。
    """
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _heuristic_delivery_type(requirement_text: str) -> str:
    """启发式交付类型。

    Args:
        requirement_text: 需求文本。

    Returns:
        ``new_domain`` 或 ``standard``。
    """
    low = (requirement_text or "").lower()
    for h in _NEW_DOMAIN_HINTS:
        if h.lower() in low or h in (requirement_text or ""):
            return "new_domain"
    # 长规格默认按新建域保守处理（避免假 standard）
    if len(requirement_text or "") > 2000:
        return "new_domain"
    return "standard"


def _normalize_pipeline(snapshot: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    """规范化 pipeline 布尔快照。

    Args:
        snapshot: 前端或调用方传入的 pipeline 键值。
    """
    snap = snapshot or {}
    out: Dict[str, bool] = {}
    for k in AUTO_CHECK_KEYS:
        v = snap.get(k)
        out[k] = bool(v) if not isinstance(v, str) else v.strip().lower() in (
            "1",
            "true",
            "yes",
            "passed",
            "done",
        )
    return out


def _step_done(
    step: Dict[str, Any],
    pipeline: Dict[str, bool],
) -> bool:
    """判断单步是否完成。

    Args:
        step: 步骤对象。
        pipeline: 规范化 pipeline。
    """
    ac = step.get("auto_check")
    if ac:
        return bool(pipeline.get(str(ac), False))
    return bool(step.get("manual_done"))


def refresh_delivery_plan_progress(
    plan: Dict[str, Any],
    pipeline_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按 pipeline 与 manual_done 重算每步 status 与 progress。

    Args:
        plan: 计划对象（原地更新并返回）。
        pipeline_snapshot: pipeline 布尔快照。

    Returns:
        更新后的 plan。
    """
    pipeline = _normalize_pipeline(pipeline_snapshot)
    delivery_type = str((plan.get("summary") or {}).get("delivery_type") or "new_domain")
    done_n = 0
    total = 0
    for phase in plan.get("phases") or []:
        phase_id = phase.get("id")
        skip_phase = delivery_type == "standard" and phase_id == "domain_new"
        for step in phase.get("steps") or []:
            if skip_phase:
                step["status"] = "skipped"
                continue
            total += 1
            if _step_done(step, pipeline):
                step["status"] = "done"
                done_n += 1
            else:
                step["status"] = "pending"
    pct = int(100 * done_n / max(1, total))
    plan["progress"] = {
        "done": done_n,
        "total": total,
        "pct": pct,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return plan


def _normalize_source_kind(kind: Optional[str]) -> str:
    """规范化需求来源：paste | upload。

    Args:
        kind: 调用方传入的来源标记。
    """
    k = (kind or "paste").strip().lower()
    return "upload" if k in ("upload", "file", "upload_file") else "paste"


def _instantiate_skeleton(
    customer_namespace: str,
    title: str,
    requirement_text: str,
    delivery_type: str,
    source_kind: str = "paste",
    source_filename: str = "",
) -> Dict[str, Any]:
    """由骨架实例化计划（未填 LLM）。

    Args:
        customer_namespace: 命名空间。
        title: 计划标题。
        requirement_text: 需求（仅用于 hash）。
        delivery_type: new_domain|standard。
        source_kind: paste 或 upload。
        source_filename: 上传文件名（仅元数据，不存原文）。
    """
    sk = load_delivery_plan_skeleton()
    phases: List[Dict[str, Any]] = []
    for ph in sk.get("phases") or []:
        steps = []
        for st in ph.get("steps") or []:
            ac = st.get("auto_check", None)
            if ac in ("", "null", "None"):
                ac = None
            steps.append(
                {
                    "id": str(st.get("id") or ""),
                    "title": str(st.get("title") or ""),
                    "ops": list(st.get("ops") or []),
                    "auto_check": ac if ac in AUTO_CHECK_KEYS else None,
                    "manual_done": False,
                    "status": "pending",
                }
            )
        phases.append(
            {
                "id": str(ph.get("id") or ""),
                "title": str(ph.get("title") or ""),
                "fde_tab": str(ph.get("fde_tab") or "customers"),
                "steps": steps,
            }
        )
    kind = _normalize_source_kind(source_kind)
    fname = (source_filename or "").strip()[:200]
    source: Dict[str, Any] = {
        "kind": kind,
        "title": title or "未命名交付计划",
        "text_sha256": _sha256_text(requirement_text),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if kind == "upload" and fname:
        source["filename"] = fname
    plan = {
        "plan_id": str(uuid.uuid4()),
        "customer_namespace": customer_namespace,
        "source": source,
        "summary": {
            "delivery_type": delivery_type,
            "phase0_days": 7,
            "honesty_locks": [
                "实施计划完成度 ≠ ⑦签收完成",
                "禁止因计划生成宣称效度/生产性能已达标",
            ],
            "summary_note": "",
        },
        "phases": phases,
        "progress": {"done": 0, "total": 0, "pct": 0, "updated_at": ""},
        "llm_ok": False,
    }
    return plan


def _apply_llm_fill(plan: Dict[str, Any], fill: Dict[str, Any]) -> None:
    """将 LLM 填空合并进计划（只改允许字段）。

    Args:
        plan: 计划。
        fill: LLM JSON。
    """
    summary = plan.setdefault("summary", {})
    dt = str(fill.get("delivery_type") or "").strip()
    if dt in ("new_domain", "standard"):
        summary["delivery_type"] = dt
    try:
        days = int(fill.get("phase0_days"))
        if 1 <= days <= 30:
            summary["phase0_days"] = days
    except Exception:
        pass  # noqa: keep default days
    locks = fill.get("honesty_locks")
    if isinstance(locks, list) and locks:
        summary["honesty_locks"] = [str(x)[:200] for x in locks if str(x).strip()][:12]
    note = fill.get("summary_note")
    if isinstance(note, str) and note.strip():
        summary["summary_note"] = note.strip()[:500]

    fills = fill.get("step_fills") or {}
    if not isinstance(fills, dict):
        return
    by_id: Dict[str, Dict[str, Any]] = {}
    for ph in plan.get("phases") or []:
        for st in ph.get("steps") or []:
            by_id[str(st.get("id"))] = st
    for sid, patch in fills.items():
        st = by_id.get(str(sid))
        if not st or not isinstance(patch, dict):
            continue
        if isinstance(patch.get("title"), str) and patch["title"].strip():
            st["title"] = patch["title"].strip()[:200]
        ops = patch.get("ops")
        if isinstance(ops, list) and ops:
            st["ops"] = [str(o)[:300] for o in ops if str(o).strip()][:12]


def _parse_llm_json(content: str) -> Optional[Dict[str, Any]]:
    """从模型输出解析 JSON 对象。

    Args:
        content: 模型原文。
    """
    text = (content or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass  # noqa: try brace extract
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


async def _llm_fill(
    customer_namespace: str,
    title: str,
    requirement_text: str,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """调用 LLM 填空；失败返回 (None, error)。

    Args:
        customer_namespace: 命名空间。
        title: 标题。
        requirement_text: 需求文本。
    """
    try:
        from core.api.core_facade import best_model_for_purpose, sys_llm_generate

        tmpl = _prompt_template()
        prompt = (
            tmpl.replace("${title}", title or "")
            .replace("${customer_namespace}", customer_namespace)
            .replace("${requirement_text}", (requirement_text or "")[:12000])
        )
        model_name = best_model_for_purpose("skill_execution")
        result = await sys_llm_generate(
            None,
            [{"role": "user", "content": prompt}],
            model_name=model_name,
            temperature=0.2,
            max_tokens=2500,
            purpose="skill_execution",
            trace_context={"skip_claude_md": True, "purpose": "skill_execution"},
        )
        content = (
            result.get("content", "")
            if isinstance(result, dict)
            else str(getattr(result, "content", "") or result)
        )
        data = _parse_llm_json(content)
        if not data:
            return None, "llm_json_parse_failed"
        return data, None
    except Exception as e:
        logger.warning("delivery_plan llm fill failed: %s", e)
        return None, str(e)[:200]


def save_delivery_plan(plan: Dict[str, Any]) -> Path:
    """持久化计划（不含需求原文）。

    Args:
        plan: 计划对象。
    """
    ns = str(plan.get("customer_namespace") or "")
    path = _plan_path(ns)
    payload = copy.deepcopy(plan)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_delivery_plan(customer_namespace: str) -> Optional[Dict[str, Any]]:
    """读取已存计划。

    Args:
        customer_namespace: 客户命名空间。

    Returns:
        plan 或 None。
    """
    path = _plan_path(customer_namespace)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("load delivery plan failed: %s", e)
        return None


async def generate_delivery_plan(
    customer_namespace: str,
    requirement_text: str,
    title: str = "",
    pipeline_snapshot: Optional[Dict[str, Any]] = None,
    source_kind: str = "paste",
    source_filename: str = "",
) -> Dict[str, Any]:
    """生成交付计划：骨架 + LLM 填空；LLM 失败仍返回骨架。

    Args:
        customer_namespace: 客户命名空间。
        requirement_text: 需求文本（当次请求，不落盘原文）。
        title: 计划标题。
        pipeline_snapshot: 当前 pipeline 布尔快照。
        source_kind: 需求来源 paste|upload。
        source_filename: 上传文件名（元数据）。

    Returns:
        含 ``llm_ok`` / 可选 ``llm_error`` 的 plan。
    """
    ns = _safe_ns(customer_namespace)
    text = (requirement_text or "").strip()
    if len(text) < 20:
        raise ValueError("requirement_text too short (min 20 chars)")

    delivery_type = _heuristic_delivery_type(text)
    plan = _instantiate_skeleton(
        ns,
        title.strip(),
        text,
        delivery_type,
        source_kind=source_kind,
        source_filename=source_filename,
    )

    fill, err = await _llm_fill(ns, title.strip(), text)
    if fill:
        _apply_llm_fill(plan, fill)
        plan["llm_ok"] = True
        plan.pop("llm_error", None)
    else:
        plan["llm_ok"] = False
        plan["llm_error"] = err or "llm_unavailable"

    refresh_delivery_plan_progress(plan, pipeline_snapshot)
    # 保留既有 manual_done：若同 ns 已有计划，合并勾选
    prev = load_delivery_plan(ns)
    if prev:
        prev_done: Dict[str, bool] = {}
        for ph in prev.get("phases") or []:
            for st in ph.get("steps") or []:
                if st.get("manual_done"):
                    prev_done[str(st.get("id"))] = True
        if prev_done:
            for ph in plan.get("phases") or []:
                for st in ph.get("steps") or []:
                    if prev_done.get(str(st.get("id"))) and not st.get("auto_check"):
                        st["manual_done"] = True
            refresh_delivery_plan_progress(plan, pipeline_snapshot)

    save_delivery_plan(plan)
    return plan


def patch_delivery_plan_step(
    customer_namespace: str,
    step_id: str,
    manual_done: bool,
    pipeline_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """人工勾选仅允许 ``auto_check is null`` 的步骤。

    Args:
        customer_namespace: 命名空间。
        step_id: 步骤 id。
        manual_done: 是否完成。
        pipeline_snapshot: 可选，勾选后重算进度。

    Returns:
        更新后的 plan。

    Raises:
        FileNotFoundError: 无计划。
        KeyError: 步骤不存在。
        ValueError: 试图勾选 auto_check 步骤。
    """
    plan = load_delivery_plan(customer_namespace)
    if not plan:
        raise FileNotFoundError("delivery plan not found")
    sid = (step_id or "").strip()
    found = None
    for ph in plan.get("phases") or []:
        for st in ph.get("steps") or []:
            if str(st.get("id")) == sid:
                found = st
                break
        if found:
            break
    if not found:
        raise KeyError(f"step not found: {sid}")
    if found.get("auto_check"):
        raise ValueError("auto_check steps cannot be manually patched")
    found["manual_done"] = bool(manual_done)
    refresh_delivery_plan_progress(plan, pipeline_snapshot)
    save_delivery_plan(plan)
    return plan


def get_delivery_plan(
    customer_namespace: str,
    pipeline_snapshot: Optional[Dict[str, Any]] = None,
    refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    """读取计划；可选刷新进度。

    Args:
        customer_namespace: 命名空间。
        pipeline_snapshot: pipeline 快照。
        refresh: 为 True 时重算并落盘。
    """
    plan = load_delivery_plan(customer_namespace)
    if not plan:
        return None
    if refresh or pipeline_snapshot is not None:
        refresh_delivery_plan_progress(plan, pipeline_snapshot)
        if refresh:
            save_delivery_plan(plan)
    return plan
