"""
Shared smoke-test input generators for Skill / Agent / Tool / MCP execute UIs.

Produces plausible default_input + example chips from input_schema (flat) or
JSON Schema ({properties, required}).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

# Shared inspection-report API contract for all code-agent isolated smokes
# (frontend / backend / programmer). Keep in lockstep with executionSamples.ts.
_EXAMPLE_PREFIX_RE = re.compile(r"^示例[：:]\s*")
_PATHISH_RE = re.compile(r"^(?:[.]{0,2}/|[A-Za-z]:\\|https?://|/tmp/|~/|\$HOME/)")

_INSPECTION_API_CONTRACTS = (
    "- POST /api/v1/inspection/reports  body: reporter_id, equipment_id, description, photo_uris[]  response: { id, status }\n"
    "- GET  /api/v1/inspection/reports  item: { id, reporter_id, equipment_id, description, status }\n"
    "- POST /api/v1/inspection/reports/{id}/approve  body: approved, comment  response: { id, status }\n"
    "- POST /api/v1/inspection/reports/{id}/dispatch  body: assignee_id  response: { id, status }\n"
)


def _generic_scenario_simple(*, label: str, field_key: str, field_desc: str = "") -> str:
    """Skill-agnostic simple smoke: still has role / scope / one constraint / unknown."""
    topic = (field_desc or field_key or "主输入").strip()
    name = (label or "本能力").strip() or "本能力"
    return (
        f"【简单冒烟｜{name}】\n"
        f"围绕字段「{field_key}」（{topic}）给出最小可验收输入：\n"
        f"- 角色与目标：说明谁在什么场景下要用本能力；\n"
        f"- 范围：只做核心路径；明确 1 件「本次不做」；\n"
        f"- 约束：给出 1 条可检查边界（性能/权限/格式/时效均可，未知则标待确认）；\n"
        f"- 未知：列出 1 个待确认问题，禁止编造未提供的事实；\n"
        f"请按本 Skill 的输出契约返回可检查结果（勿空话、勿只回「已完成」）。"
    )


def _generic_scenario_complex(*, label: str, field_key: str, field_desc: str = "", skill_desc: str = "") -> str:
    """Skill-agnostic complex smoke: multi-constraint + explicit exclusions."""
    topic = (field_desc or field_key or "主输入").strip()
    name = (label or "本能力").strip() or "本能力"
    extra = (skill_desc or "").strip()
    extra_line = f"- 能力说明摘录：{extra[:160]}\n" if extra else ""
    return (
        f"【复杂冒烟｜{name}】\n"
        f"围绕字段「{field_key}」（{topic}）构造多约束场景：\n"
        f"{extra_line}"
        f"- 角色/干系人 ≥2（如一线用户 + 审批/管理者）；\n"
        f"- 范围：主流程 + 至少 1 个边界条件；明确 2 件「本次不做」；\n"
        f"- 约束：同时覆盖「集成/依赖未就绪」与「合规或安全」类边界（未知标待确认）；\n"
        f"- 验收：写明怎样算通过（可计数/可复现步骤），禁止「功能正常/清晰可见」；\n"
        f"- 禁止编造客户未提供的具体 SLA/密钥/渠道细节。\n"
        f"输出须能被对照本 Skill 的入参出参契约做冒烟验收。"
    )


def _prd_requirement_simple() -> str:
    """PRD skill: minimal but still exercises FR/AC/NFR/open_questions."""
    return (
        "【客户口述｜草稿轮冒烟】\n"
        "客户要在 B2B 商城加「商品关键词搜索」。\n"
        "- 用户：采购员在 PC 端按关键词找商品；\n"
        "- 范围：仅搜商品名称/SKU/规格，不做图片搜、不做个性化推荐；\n"
        "- 性能：常见词 1s 内出结果（口述，未给压测数据）；\n"
        "- 权限：未登录可搜，登录后才能看价；\n"
        "- 未知：是否要拼音/错别字容错——客户未说清。\n"
        "\n"
        "请输出结构化 PRD（Markdown 或 JSON+Markdown）：\n"
        "至少 3 条 FR（含可验证 AC）、user_stories、constraints.performance + security、\n"
        "decisions、open_questions（未知项进此或标「待确认」）。\n"
        "禁止编造未口述的 SLA/加密方案/渠道；禁止「功能正常」类软 AC。"
    )


def _prd_requirement_complex() -> str:
    """PRD skill: multi-constraint aligned with requirement_analysis 输出铁律."""
    return (
        "【客户口述｜请做可验收草稿，不要 PRD_READY】\n"
        "客户：江苏某制造企业，要做「现场巡检报障」小应用。\n"
        "- 一线工人手机拍照上报设备异常；班组长审批后派维修；\n"
        "- 希望和现有钉钉账号打通，但暂时没有开放 API 文档；\n"
        "- 管理层要看「本周报障量 / 平均闭环时长」；\n"
        "- 上线：6 周内试点 1 个车间；预算与编制未定；\n"
        "- 合规：照片可能含产线布局，不能传到公网；\n"
        "- 明确不做：OCR 自动识别铭牌、语音转写工单。\n"
        "\n"
        "硬性自检（缺任一条视为失败）：\n"
        "1) 正文显式保留「不上公网/照片不外传」与「钉钉 API 未开放/集成待确认」；\n"
        "2) ≥3 条 FR，每条含可验证 AC（禁止清晰可见/功能正常）；\n"
        "3) constraints.performance 与 constraints.security 非空；\n"
        "4) 未口述的多语言/具体 SLA/加密方案不得写成已确认；\n"
        "5) 不要输出 <!-- PRD_READY -->，不要文末 markdown 代码块复读全文。"
    )


def _leaf_is_typed_smoke(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, str):
        s = value.strip()
        if not s or _EXAMPLE_PREFIX_RE.match(s):
            return False
        if _PATHISH_RE.match(s) or s.startswith("sample_"):
            return True
        return False
    if isinstance(value, (list, dict)) and value:
        return True
    return False


def _dict_is_structured_smoke(obj: Dict[str, Any]) -> bool:
    """Parametric JSON (path + bytes + flags) is a valid smoke even when short."""
    if not obj:
        return False
    if any(isinstance(v, str) and _EXAMPLE_PREFIX_RE.match(v.strip()) for v in obj.values()):
        return False
    typed = sum(1 for v in obj.values() if _leaf_is_typed_smoke(v))
    return typed >= max(1, (len(obj) + 1) // 2)


def example_content_is_thin(content: Any, *, min_chars: int = 100) -> bool:
    """True when content is too weak to smoke-test a real skill (generic gate)."""
    if content is None:
        return True
    if isinstance(content, (dict, list)):
        try:
            s = json.dumps(content, ensure_ascii=False)
        except Exception:
            s = str(content)
    else:
        s = str(content).strip()
    if not s:
        return True
    legacy = (
        "请按本能力说明完成一次冒烟测试",
        "按本 Agent 的职责做一次冒烟验证",
    )
    if any(m in s for m in legacy) and len(s) < 200:
        return True
    obj: Any = None
    try:
        obj = json.loads(s)
    except Exception:
        obj = None
    if isinstance(obj, dict):
        if not obj:
            return True
        if any(isinstance(v, str) and _EXAMPLE_PREFIX_RE.match(v.strip()) for v in obj.values()):
            return True
        if _dict_is_structured_smoke(obj):
            return False
        str_vals = [str(v) for v in obj.values() if isinstance(v, (str, int, float))]
        nested = [v for v in obj.values() if isinstance(v, (dict, list))]
        if nested:
            try:
                nested_len = len(json.dumps(nested, ensure_ascii=False))
            except Exception:
                nested_len = 0
            if nested_len >= min_chars:
                return False
        if len(s) < min_chars:
            return True
        if str_vals and all(len(v) < 80 for v in str_vals) and len(s) < max(220, min_chars + 40):
            return True
        longest = max((len(v) for v in str_vals), default=0)
        if longest and longest < 80 and not nested:
            return True
        return False
    if isinstance(obj, list):
        return len(json.dumps(obj, ensure_ascii=False)) < min_chars
    if len(s) < min_chars:
        return True
    if s.count("\n") < 1 and ("。" not in s and "." not in s):
        return len(s) < max(min_chars, 160)
    return False


def filter_rich_execution_examples(
    examples: Optional[List[Dict[str, Any]]],
    *,
    min_keep: int = 1,
    min_chars: int = 100,
) -> List[Dict[str, str]]:
    """Drop thin LLM/heuristic chips; preserve title/content shape."""
    out: List[Dict[str, str]] = []
    for e in examples or []:
        if not isinstance(e, dict):
            continue
        title = str(e.get("title") or "").strip()
        content = e.get("content")
        if content is None:
            continue
        if isinstance(content, (dict, list)):
            content_s = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            content_s = str(content).strip()
        if not title or not content_s:
            continue
        if example_content_is_thin(content_s, min_chars=min_chars):
            continue
        out.append({"title": title[:80], "content": content_s[:8000]})
        if len(out) >= 5:
            break
    if len(out) < min_keep:
        return out  # caller decides fallback
    return out


def _pick_primary_text_field(flat: Dict[str, Any]) -> Optional[str]:
    """Prefer free-text input fields that usually carry the smoke scenario."""
    preferred = (
        "user_requirement", "requirement", "requirements", "prd_input",
        "message", "prompt", "query", "topic", "markdown", "text", "content", "input", "outline",
    )
    keys = {str(k): k for k in flat.keys()}
    for p in preferred:
        if p in keys:
            return str(keys[p])
        for k in keys:
            if k.lower() == p:
                return str(k)
    # First required string-ish field
    for k, spec in flat.items():
        if not isinstance(spec, dict):
            return str(k)
        typ = str(spec.get("type") or "string").lower()
        if typ in ("string", "text", "") and bool(spec.get("required")):
            return str(k)
    return str(next(iter(flat.keys()))) if flat else None


_SIZE_LIMIT_RE = re.compile(
    r"(?:不超过|不大于|最大|限制|max(?:imum)?|up\s*to|<=|<)\s*"
    r"(\d+(?:\.\d+)?)\s*(gb|g|mb|m|kb|k|b|字节)?"
    r"|"
    r"(\d+(?:\.\d+)?)\s*(gb|mb|kb)\s*(?:以内|以下|限制)",
    re.I,
)
_UNIT_BYTES = {
    "gb": 1024 ** 3,
    "g": 1024 ** 3,
    "mb": 1024 ** 2,
    "m": 1024 ** 2,
    "kb": 1024,
    "k": 1024,
    "b": 1,
    "字节": 1,
}
_FILE_EXT_HINTS = (
    ("mp4", ".mp4"),
    ("mov", ".mov"),
    ("avi", ".avi"),
    ("mkv", ".mkv"),
    ("webm", ".webm"),
    ("pdf", ".pdf"),
    ("png", ".png"),
    ("jpeg", ".jpg"),
    ("jpg", ".jpg"),
    ("gif", ".gif"),
    ("wav", ".wav"),
    ("mp3", ".mp3"),
    ("csv", ".csv"),
    ("xlsx", ".xlsx"),
    ("json", ".json"),
    ("zip", ".zip"),
    ("txt", ".txt"),
)


def _parse_size_limit_bytes(text: str) -> Optional[int]:
    """Parse 「不超过2GB」/ max 10MB from a field description. None if absent."""
    s = str(text or "").strip()
    if not s:
        return None
    m = _SIZE_LIMIT_RE.search(s)
    if not m:
        return None
    n_s = m.group(1) or m.group(3)
    unit = (m.group(2) or m.group(4) or "b").lower()
    try:
        n = float(n_s)
    except (TypeError, ValueError):
        return None
    mul = _UNIT_BYTES.get(unit, 1)
    val = int(n * mul)
    return val if val > 0 else None


def _looks_like_byte_size(key: str, desc: str, typ: str) -> bool:
    if typ not in ("integer", "int", "number", "float", ""):
        return False
    if any(tok in key for tok in ("_bytes", "filesize", "file_size", "byte_size", "content_length")):
        return True
    if key.endswith("_size") and "page" not in key and "batch" not in key:
        return True
    blob = f"{key} {desc}".lower()
    return any(tok in blob for tok in ("字节", "bytes", "byte"))


def _ext_from_desc(desc: str, *, key: str = "") -> str:
    blob = f"{desc} {key}".lower()
    for needle, ext in _FILE_EXT_HINTS:
        if needle in blob:
            return ext
    if any(tok in blob for tok in ("视频", "video")):
        return ".mp4"
    if any(tok in blob for tok in ("图片", "image", "photo")):
        return ".png"
    if any(tok in blob for tok in ("音频", "audio")):
        return ".wav"
    return ".bin"


def _sample_file_path(desc: str, *, key: str = "") -> str:
    """Plausible user-path placeholder (not a guarantee the file exists)."""
    ext = _ext_from_desc(desc, key=key)
    blob = f"{desc} {key}".lower()
    if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm") or any(t in blob for t in ("视频", "video")):
        return f"~/Movies/sprint_review_demo{ext}"
    if ext in (".png", ".jpg", ".jpeg", ".gif") or any(t in blob for t in ("图片", "image", "photo")):
        return f"~/Pictures/demo_upload{ext}"
    if ext in (".wav", ".mp3") or any(t in blob for t in ("音频", "audio")):
        return f"~/Music/demo_upload{ext}"
    if ext in (".pdf", ".doc", ".docx", ".xlsx", ".csv", ".txt"):
        return f"~/Documents/demo_upload{ext}"
    return f"~/Downloads/demo_upload{ext}"


def _sample_byte_size(desc: str) -> int:
    """Happy-path size in whole MiB, well under any parsed cap (default 5 MiB)."""
    mb = 1024 * 1024
    happy = 5 * mb
    limit = _parse_size_limit_bytes(desc)
    if not limit:
        return happy
    under = max(mb, min(limit // 4, 50 * mb))
    return int(min(happy, under)) if happy < limit else int(max(1, min(under, limit // 8)))


def _looks_like_file_ref(key: str, typ: str) -> bool:
    if typ in ("file", "binary", "blob", "path"):
        return True
    if any(tok in key for tok in ("_size", "_count", "_limit", "_bytes")):
        return False
    return key in (
        "file", "filename", "filepath", "video", "audio", "image",
        "attachment", "upload", "document", "doc",
    ) or key.endswith("_file") or key.endswith("_path")


def sample_value_for_field(name: str, spec: Any, *, skill_hint: str = "") -> Any:
    """Generate a plausible smoke-test value for one field."""
    key = str(name or "").strip().lower()
    typ = ""
    desc = ""
    enum_vals: list = []
    if isinstance(spec, dict):
        typ = str(spec.get("type") or "").lower()
        desc = str(spec.get("description") or "")
        if isinstance(spec.get("enum"), list) and spec["enum"]:
            enum_vals = list(spec["enum"])
        if spec.get("default") is not None:
            return spec["default"]
    elif isinstance(spec, str):
        typ = spec.lower()

    if enum_vals:
        return enum_vals[0]

    if key in ("outline",):
        return {
            "title": "aiPlat 产品介绍",
            "sections": [
                {
                    "title": "背景与目标",
                    "pages": [
                        {
                            "title": "我们要解决什么",
                            "bullets": ["交付慢", "知识难沉淀", "质量难度量"],
                        },
                        {
                            "title": "目标",
                            "bullets": ["缩短交付周期", "可治理执行"],
                        },
                    ],
                },
                {
                    "title": "方案概览",
                    "pages": [
                        {
                            "title": "八层架构",
                            "bullets": ["本体语义底座", "知识创造引擎", "上下文注入总线"],
                        },
                    ],
                },
            ],
        }

    # Rich prose for summarization / rewrite / QA style skills
    long_article = (
        "【产品周报｜2026-W38】\n"
        "\n"
        "一、本周进展\n"
        "资产审批增加 Agent 上架硬门禁：绑定 Skill/MCP 须已发布或已上架，Tool 须在注册表可用，"
        "否则拒绝上架并返回依赖明细。应用库 Skill/Agent/Tool/MCP 列表支持按名称与描述搜索。"
        "PPT 生成 Skill 可按大纲与模版写出 .pptx；审批流已打通提交审核→通过→上架。\n"
        "\n"
        "二、问题与风险\n"
        "1. 默认 PPT 模版视觉偏简，客户演示观感不足；\n"
        "2. 部分 Skill 冒烟用例仍是一句话占位，难以验证长文压缩/结构化输出质量；\n"
        "3. 若干 workspace Skill 停在 ready，阻塞依赖它们的 Agent 上架。\n"
        "\n"
        "三、下周计划\n"
        "- 按能力类型丰富执行测试用例（摘要/检索/生成等给出可执行样例）\n"
        "- 迭代 default.pptx 版式与拆页策略\n"
        "- 清理待审核 Skill 队列，优先 unblock 被依赖项\n"
        "\n"
        "请输出：3 条要点 + 1 条风险 + 1 条行动建议（中文，条目化，勿编造原文没有的事实）。"
    )
    _ = skill_hint  # reserved for future skill-specific variants

    string_samples = {
        "query": "企业知识库里，关于资产审批硬门禁与 Skill 上架依赖校验的最新规范是什么？请给出出处要点。",
        "topic": "为客户做一份「aiPlat 资产审批与上架治理」产品介绍，突出硬门禁与迭代路径",
        "markdown": (
            "# 资产审批周报\n\n"
            "## 进展\n"
            "- Agent 上架前校验 Skill/MCP/Tool 依赖\n"
            "- 应用库支持名称/描述搜索\n\n"
            "## 风险\n"
            "- 默认 PPT 模版过简\n"
            "- 冒烟用例偏弱\n\n"
            "## 行动\n"
            "- 丰富测试用例生成器\n"
            "- 迭代 default.pptx\n"
        ),
        "message": long_article,
        "prompt": long_article,
        "text": long_article,
        "content": long_article,
        "input": long_article,
        "template_name": "default",
        "template": "default",
        "url": "https://example.com",
        "path": "/tmp/example.txt",
        "directory": "/tmp",
        "command": "echo hello",
        "cmd": "echo hello",
        "name": "demo",
        "title": "资产审批与上架治理周报",
    }
    if key in string_samples:
        return string_samples[key]

    # Narrative free-text fields without dedicated samples — never「示例：前48字」
    narrative_keys = {
        "user_requirement", "requirement", "requirements", "prd_input", "需求",
        "instruction", "task", "goal", "brief", "scenario",
    }
    hint_l = str(skill_hint or "").lower()
    label = (skill_hint or "本能力").strip() or "本能力"
    if key in narrative_keys or (
        typ in ("string", "text", "")
        and any(m in desc for m in ("需求", "原始", "场景", "任务描述", "requirement", "brief"))
    ):
        if any(k in hint_l for k in ("requirement_analysis", "prd", "需求分析")):
            return _prd_requirement_complex() if any(k in hint_l for k in ("complex", "复杂")) else _prd_requirement_simple()
        if any(k in hint_l for k in ("complex", "复杂")):
            return _generic_scenario_complex(label=label, field_key=key, field_desc=desc)
        return _generic_scenario_simple(label=label, field_key=key, field_desc=desc)

    if key == "template_path":
        return ""

    if _looks_like_file_ref(key, typ) or key in ("source_path", "file_path"):
        return _sample_file_path(desc, key=key)

    if (
        key in ("duration", "time_str", "elapsed")
        or "hh:mm:ss" in desc.lower()
        or "HH:MM:SS" in desc
    ):
        return "00:01:30"
    if "email" in key or "邮箱" in desc:
        return "user@example.com"
    if "resolution" in key or "清晰度" in desc:
        return "1080p"

    if "max_chars" in key:
        return 200

    if typ in ("boolean", "bool") or key.startswith("is_") or key.startswith("enable_"):
        return True

    if _looks_like_byte_size(key, desc, typ):
        return _sample_byte_size(desc)

    if typ in ("integer", "int") or key.endswith("_count") or key.endswith("_limit"):
        if "percent" in key or "进度" in desc or "百分比" in desc:
            return 50
        return 3

    if typ in ("number", "float"):
        return 1.0

    if typ in ("array", "list"):
        return ["示例项1", "示例项2"]

    if typ in ("object", "dict"):
        return {"key": "value"}

    # Never copy the field description into the value (「示例：本地视频文件…」).
    return f"sample_{key or 'value'}"


def flatten_json_schema(schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize to flat {name: {type, required, description, ...}}.

    Accepts either:
    - JSON Schema object: {properties, required}
    - Flat skill-style schema: {name: {type, required, description}}
    """
    if not isinstance(schema, dict) or not schema:
        return {}
    props = schema.get("properties")
    if isinstance(props, dict):
        required = {str(x) for x in (schema.get("required") or [])}
        out: Dict[str, Any] = {}
        for k, v in props.items():
            if isinstance(v, dict):
                item = dict(v)
                item["required"] = str(k) in required or bool(v.get("required"))
                out[str(k)] = item
            else:
                out[str(k)] = {"type": "string", "required": str(k) in required}
        return out
    # Already flat (skill input_schema)
    return dict(schema)


def _field_descriptions(schema: Optional[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for spec in flatten_json_schema(schema).values():
        if isinstance(spec, dict):
            d = str(spec.get("description") or "").strip()
            if d:
                out.append(d)
    return out


def value_copies_field_description(
    value: Any,
    spec: Any = None,
    all_descs: Optional[List[str]] = None,
) -> bool:
    """True when a JSON leaf is the field description (or 「示例：」+ description)."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    body = _EXAMPLE_PREFIX_RE.sub("", s).strip()
    descs: List[str] = []
    if isinstance(spec, dict):
        d = str(spec.get("description") or "").strip()
        if d:
            descs.append(d)
    for d in all_descs or []:
        if d and d not in descs:
            descs.append(d)
    prefixed = bool(_EXAMPLE_PREFIX_RE.match(s))
    if prefixed and not descs:
        return True
    for d in descs:
        if len(d) < 4:
            continue
        if s == d or body == d or body == d[:48]:
            return True
        if prefixed and d[: min(12, len(d))] in s and len(s) <= len(d) + 12:
            return True
    return False


def rewrite_copied_description_values(
    obj: Any,
    schema: Optional[Dict[str, Any]] = None,
    *,
    skill_hint: str = "",
) -> Any:
    """Replace description-as-value leaves; keep unrelated keys."""
    if not isinstance(obj, dict):
        return obj
    flat = flatten_json_schema(schema)
    all_descs = _field_descriptions(schema)
    out = dict(obj)
    for k, v in list(out.items()):
        spec = flat.get(k) if isinstance(flat.get(k), dict) else {"type": "string"}
        key_l = str(k).lower()
        typ = str((spec or {}).get("type") or "").lower()
        desc = str((spec or {}).get("description") or "")
        if isinstance(v, dict) and typ in ("object", "dict", ""):
            out[k] = rewrite_copied_description_values(v, spec if typ in ("object", "dict") else None, skill_hint=skill_hint)
            continue
        if value_copies_field_description(v, spec, all_descs):
            out[k] = sample_value_for_field(k, spec, skill_hint=skill_hint)
            continue
        if (
            _looks_like_byte_size(key_l, desc, typ)
            and isinstance(v, (int, float))
            and 0 < int(v) < 1024
        ):
            out[k] = sample_value_for_field(k, spec, skill_hint=skill_hint)
    return out


def examples_copy_field_descriptions(
    examples: Optional[List[Dict[str, Any]]],
    schema: Optional[Dict[str, Any]] = None,
) -> bool:
    """True if any chip uses 「示例：…」 or a schema description as a field value."""
    all_descs = _field_descriptions(schema) if schema else []
    flat = flatten_json_schema(schema) if schema else {}
    for e in examples or []:
        if not isinstance(e, dict):
            continue
        raw = e.get("content")
        obj: Any = raw if isinstance(raw, dict) else None
        if obj is None:
            try:
                obj = json.loads(str(raw or ""))
            except Exception:
                s = str(raw or "").strip()
                if _EXAMPLE_PREFIX_RE.match(s) or value_copies_field_description(s, None, all_descs):
                    return True
                continue
        if not isinstance(obj, dict):
            continue
        for k, v in obj.items():
            spec = flat.get(k) if isinstance(flat.get(k), dict) else None
            if value_copies_field_description(v, spec, all_descs):
                return True
            key_l = str(k).lower()
            typ = str((spec or {}).get("type") or "") if isinstance(spec, dict) else ""
            desc = str((spec or {}).get("description") or "") if isinstance(spec, dict) else ""
            if (
                _looks_like_byte_size(key_l, desc, typ)
                and isinstance(v, (int, float))
                and 0 < int(v) < 1024
            ):
                return True
    return False


def sanitize_execution_examples(
    examples: Optional[List[Dict[str, Any]]],
    schema: Optional[Dict[str, Any]] = None,
    *,
    skill_hint: str = "",
) -> List[Dict[str, str]]:
    """Rewrite persisted/LLM chips so field descriptions are never used as values."""
    out: List[Dict[str, str]] = []
    all_descs = _field_descriptions(schema)
    for e in examples or []:
        if not isinstance(e, dict):
            continue
        title = str(e.get("title") or "").strip()
        content = e.get("content")
        if content is None:
            continue
        obj: Any = content if isinstance(content, (dict, list)) else None
        if obj is None:
            try:
                obj = json.loads(str(content))
            except Exception:
                obj = None
        if isinstance(obj, dict):
            rewritten = rewrite_copied_description_values(obj, schema, skill_hint=skill_hint)
            content_s = json.dumps(rewritten, ensure_ascii=False, indent=2)
        else:
            content_s = str(content).strip()
            if value_copies_field_description(content_s, None, all_descs):
                continue
        if title and content_s:
            out.append({"title": title[:80], "content": content_s[:8000]})
    return out


def schema_from_io_list(items: Any) -> Dict[str, Any]:
    """Turn YAML ``input: [{name, type, ...}]`` into a flat schema map."""
    if not isinstance(items, list):
        return {}
    out: Dict[str, Any] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or it.get("id") or "").strip()
        if not name:
            continue
        spec = {k: v for k, v in it.items() if k not in ("name", "id")}
        spec.setdefault("type", "string")
        out[name] = spec
    return out


def resolve_skill_example_schema(
    *,
    live: Any = None,
    frontmatter: Any = None,
) -> Dict[str, Any]:
    """Prefer execution_input_schema, then input_schema dict, then YAML input list, then live."""
    fm = frontmatter if isinstance(frontmatter, dict) else {}
    candidates = (
        fm.get("execution_input_schema"),
        fm.get("input_schema") if isinstance(fm.get("input_schema"), dict) else None,
        schema_from_io_list(fm.get("input")),
        live if isinstance(live, dict) else None,
    )
    for cand in candidates:
        if isinstance(cand, dict) and cand:
            return dict(cand)
    return {}


def sop_excerpt_from_markdown(raw: str, *, limit: int = 2500) -> str:
    """SKILL.md / AGENT.md body only (strip YAML frontmatter), truncated for prompts."""
    text = str(raw or "").replace("\r\n", "\n")
    parts = text.split("---", 2)
    body = parts[2] if len(parts) >= 3 else text
    body = body.strip()
    if not body:
        return ""
    if len(body) > limit:
        return body[:limit].rstrip() + "\n…"
    return body


def example_covers_required_schema(content: Any, schema: Optional[Dict[str, Any]]) -> bool:
    """True when JSON content has required keys with typed (non-description) values."""
    flat = flatten_json_schema(schema)
    required = [
        k for k, spec in flat.items()
        if isinstance(spec, dict) and spec.get("required")
    ]
    if not required:
        return True
    obj: Any = content if isinstance(content, dict) else None
    if obj is None:
        try:
            obj = json.loads(str(content or ""))
        except Exception:
            return False
    if not isinstance(obj, dict):
        return False
    all_descs = _field_descriptions(schema)
    for k in required:
        if k not in obj:
            return False
        spec = flat.get(k) if isinstance(flat.get(k), dict) else {}
        val = obj.get(k)
        if value_copies_field_description(val, spec, all_descs):
            return False
        key_l = str(k).lower()
        typ = str((spec or {}).get("type") or "").lower()
        desc = str((spec or {}).get("description") or "")
        if _looks_like_file_ref(key_l, typ) and isinstance(val, str):
            s = val.strip()
            if not s or _EXAMPLE_PREFIX_RE.match(s):
                return False
            if not (_PATHISH_RE.match(s) or s.startswith("sample_")):
                return False
        if _looks_like_byte_size(key_l, desc, typ) and isinstance(val, (int, float)):
            n = int(val)
            # Tiny positives are leftover integer defaults (3), not file bytes.
            if 0 < n < 1024:
                return False
    return True


def llm_examples_pass_schema_gate(
    examples: Optional[List[Dict[str, Any]]],
    schema: Optional[Dict[str, Any]] = None,
) -> bool:
    """LLM chips count as success only with ≥2 items and required-schema coverage."""
    dicts = [e for e in (examples or []) if isinstance(e, dict) and e.get("content")]
    if len(dicts) < 2:
        return False
    if examples_copy_field_descriptions(dicts, schema):
        return False
    flat = flatten_json_schema(schema)
    required = [
        k for k, spec in flat.items()
        if isinstance(spec, dict) and spec.get("required")
    ]
    if not required:
        return True
    return any(example_covers_required_schema(e.get("content"), schema) for e in dicts)


def accept_llm_execution_examples(
    extracted: Optional[List[Dict[str, Any]]],
    schema: Optional[Dict[str, Any]] = None,
    *,
    skill_hint: str = "",
) -> List[Dict[str, str]]:
    """Keep LLM chips only if the *raw* payload already fits; empty → heuristic fallback.

    Sanitize must not run first: rewriting「示例：说明」into ``/tmp/sample.mp4`` would
    launder copied descriptions as ``source=llm`` and persist them.
    """
    chips: List[Dict[str, Any]] = [
        e for e in (extracted or [])
        if isinstance(e, dict) and str(e.get("title") or "").strip() and e.get("content") is not None
    ]
    if examples_copy_field_descriptions(chips, schema):
        return []
    flat = flatten_json_schema(schema)
    required = [
        k for k, spec in flat.items()
        if isinstance(spec, dict) and spec.get("required")
    ]
    if required and not any(example_covers_required_schema(e.get("content"), schema) for e in chips):
        return []
    if schema:
        chips = sanitize_execution_examples(chips, schema, skill_hint=skill_hint)
    rich = filter_rich_execution_examples(chips, min_keep=2)
    if not llm_examples_pass_schema_gate(rich, schema if schema else None):
        return []
    return rich


def build_sample_payload(
    schema: Optional[Dict[str, Any]],
    *,
    include_optional: bool = True,
    skill_hint: str = "",
) -> Dict[str, Any]:
    flat = flatten_json_schema(schema)
    if not flat:
        return {}
    payload: Dict[str, Any] = {}
    for k, v in flat.items():
        is_req = bool(isinstance(v, dict) and v.get("required"))
        if include_optional or is_req:
            payload[k] = sample_value_for_field(k, v, skill_hint=skill_hint)
    if not include_optional and not payload:
        # nothing marked required → fill all
        for k, v in flat.items():
            payload[k] = sample_value_for_field(k, v, skill_hint=skill_hint)
    return rewrite_copied_description_values(payload, schema, skill_hint=skill_hint)


def build_examples_from_input_schema(
    input_schema: Dict[str, Any],
    *,
    skill_id: str = "",
    skill_name: str = "",
) -> List[Dict[str, str]]:
    """Build one-click / auto-fill test cases from skill-style or JSON Schema."""
    flat = flatten_json_schema(input_schema)
    if not flat:
        return []

    skill_hint = f"{skill_id} {skill_name}".strip()

    text_field = None
    primary_text_keys = {
        "message",
        "prompt",
        "query",
        "topic",
        "markdown",
        "text",
        "content",
        "input",
    }
    for k, v in flat.items():
        sample = sample_value_for_field(k, v, skill_hint=skill_hint)
        if text_field is None and str(k).lower() in primary_text_keys and isinstance(sample, str):
            text_field = sample

    label = (skill_name or skill_id or "本能力").strip() or "本能力"
    skill_l = f"{skill_id} {skill_name}".strip().lower()

    # requirement_analysis / PRD：用领域场景，不要泛化「字段冒烟」模板
    if (
        "requirement_analysis" in skill_l
        or any(k in skill_l for k in ("prd", "需求分析", "需求文档", "requirement analysis"))
    ):
        primary = "user_requirement" if "user_requirement" in flat else (_pick_primary_text_field(flat) or "user_requirement")
        return [
            {
                "title": f"{label} - 简单示例（含边界）",
                "content": json.dumps({primary: _prd_requirement_simple()}, ensure_ascii=False, indent=2),
            },
            {
                "title": f"{label} - 复杂示例（多约束）",
                "content": json.dumps({primary: _prd_requirement_complex()}, ensure_ascii=False, indent=2),
            },
        ]

    # Generic: dominant free-text field → simple + complex pair (any skill)
    primary = _pick_primary_text_field(flat)
    narrative_keys = {
        "user_requirement", "requirement", "requirements", "prd_input", "需求",
        "message", "prompt", "query", "topic", "text", "content", "input", "instruction", "task", "brief",
    }
    if primary and str(primary).lower() in narrative_keys:
        spec = flat.get(primary) if isinstance(flat.get(primary), dict) else {"type": "string"}
        desc = str((spec or {}).get("description") or "")
        simple_val = _generic_scenario_simple(label=label, field_key=str(primary), field_desc=desc)
        complex_val = _generic_scenario_complex(
            label=label, field_key=str(primary), field_desc=desc, skill_desc=skill_hint,
        )
        # Reuse domain-specific rich samples when available (e.g. message→long article for summarize)
        sampled = sample_value_for_field(primary, spec, skill_hint=skill_hint)
        if isinstance(sampled, str) and not example_content_is_thin(sampled) and str(primary).lower() in {
            "message", "prompt", "text", "content", "input", "markdown", "query", "topic",
        }:
            simple_val = sampled if len(sampled) < 1200 else _generic_scenario_simple(
                label=label, field_key=str(primary), field_desc=desc,
            )
            complex_val = (
                sampled.rstrip()
                + "\n\n【加严验收】请同时覆盖：明确不做项、1 条未知待确认、输出须可对照契约检查；禁止空话。"
            )
        return [
            {
                "title": f"{label} - 简单示例",
                "content": json.dumps({primary: simple_val}, ensure_ascii=False, indent=2),
            },
            {
                "title": f"{label} - 复杂示例",
                "content": json.dumps({primary: complex_val}, ensure_ascii=False, indent=2),
            },
        ]

    # Parametric / Tool / MCP style: 主路径 + 边界 + 全量（覆盖可测点）
    return build_param_smoke_examples(
        input_schema,
        asset_id=skill_id,
        asset_name=skill_name or label,
        asset_kind="skill",
        text_field=text_field if isinstance(text_field, str) else None,
    )


def _boundary_value_for_field(name: str, spec: Any, happy: Any) -> Any:
    """Edge values that exercise validation / failure / empty-input paths."""
    key = str(name or "").strip().lower()
    typ = ""
    desc = ""
    enum_vals: List[Any] = []
    if isinstance(spec, dict):
        typ = str(spec.get("type") or "").lower()
        desc = str(spec.get("description") or "")
        if isinstance(spec.get("enum"), list) and spec["enum"]:
            enum_vals = list(spec["enum"])
    elif isinstance(spec, str):
        typ = spec.lower()

    if len(enum_vals) >= 2:
        return enum_vals[-1]
    if typ in ("boolean", "bool") or key.startswith("is_") or key.startswith("enable_"):
        return False if happy is True else True
    if _looks_like_byte_size(key, desc, typ):
        limit = _parse_size_limit_bytes(desc)
        if limit:
            return int(limit) + 1
        return 0
    if typ in ("integer", "int") or key.endswith("_count") or key.endswith("_limit"):
        return 0
    if typ in ("number", "float"):
        return -1.0
    if typ in ("array", "list"):
        return []
    if typ in ("object", "dict"):
        return {}
    if "url" in key or key in ("uri", "endpoint", "href"):
        return "http://127.0.0.1:9/should-be-unreachable"
    if _looks_like_file_ref(key, typ) or key in (
        "path", "file_path", "source_path", "template_path", "directory",
    ):
        return "/tmp/__aiplat_missing_path__.txt"
    if key in ("command", "cmd"):
        return "false"  # exits non-zero
    if isinstance(happy, str):
        if len(happy) > 40:
            return ""  # empty free-text → often rejects or returns thin
        return " "  # whitespace-only
    if happy is None:
        return ""
    return happy


def build_boundary_payload(
    flat: Dict[str, Any],
    *,
    skill_hint: str = "",
) -> Dict[str, Any]:
    """Required-field payload with edge values (boundary / negative smoke)."""
    happy = build_sample_payload(flat, include_optional=False, skill_hint=skill_hint)
    out: Dict[str, Any] = {}
    for k, v in happy.items():
        spec = flat.get(k) if isinstance(flat.get(k), dict) else flat.get(k)
        out[k] = _boundary_value_for_field(k, spec, v)
    if not out:
        for k, spec in flat.items():
            sample = sample_value_for_field(k, spec, skill_hint=skill_hint)
            out[k] = _boundary_value_for_field(k, spec, sample)
    return out


def build_param_smoke_examples(
    input_schema: Dict[str, Any],
    *,
    asset_id: str = "",
    asset_name: str = "",
    asset_kind: str = "tool",
    text_field: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Tool / MCP / schema-driven smoke chips: 主路径 + 边界 + 全量.

    Covers test points beyond「填个默认值」:
    - happy path (required)
    - boundary / negative (empty, 0, unreachable URL, flipped bool)
    - complex (optional + enriched narrative where applicable)
    """
    flat = flatten_json_schema(input_schema)
    if not flat:
        return []

    hint = f"{asset_id} {asset_name}".strip()
    label = (asset_name or asset_id or asset_kind or "本能力").strip() or "本能力"
    required_payload = build_sample_payload(flat, include_optional=False, skill_hint=hint)
    full_payload = build_sample_payload(flat, include_optional=True, skill_hint=hint)
    boundary_payload = build_boundary_payload(flat, skill_hint=hint)

    # Enrich long-text fields in complex payload when still thin
    narrative_keys = {
        "message", "prompt", "query", "topic", "text", "content", "input",
        "user_requirement", "requirement", "instruction", "task", "brief", "markdown",
    }
    complex_payload = dict(full_payload)
    for k, v in list(complex_payload.items()):
        if str(k).lower() in narrative_keys and isinstance(v, str) and example_content_is_thin(v):
            complex_payload[k] = _generic_scenario_complex(
                label=label, field_key=str(k), field_desc="", skill_desc=hint,
            )

    examples: List[Dict[str, str]] = [
        {
            "title": f"{label}（主路径·必填）",
            "content": json.dumps(required_payload, ensure_ascii=False, indent=2),
        },
        {
            "title": f"{label}（边界/异常）",
            "content": json.dumps(boundary_payload, ensure_ascii=False, indent=2),
        },
    ]
    if complex_payload != required_payload:
        examples.append(
            {
                "title": f"{label}（复杂·全量）",
                "content": json.dumps(complex_payload, ensure_ascii=False, indent=2),
            }
        )

    if text_field and isinstance(text_field, str) and not example_content_is_thin(text_field):
        examples.append({"title": f"{label}（纯文本）", "content": text_field})
    elif "outline" in flat:
        examples.append(
            {
                "title": f"{label}（大纲文本）",
                "content": (
                    "标题：aiPlat 产品介绍\n"
                    "\n"
                    "一、背景与目标\n"
                    "- 交付慢、知识难沉淀\n"
                    "- 目标：缩短交付周期、可治理执行\n"
                    "\n"
                    "二、方案概览\n"
                    "- 八层架构：本体底座 / 知识引擎 / 上下文总线\n"
                ),
            }
        )

    return examples


def build_workflow_start_examples(
    start_inputs: Optional[List[Dict[str, Any]]] = None,
    *,
    workflow_name: str = "",
) -> List[Dict[str, str]]:
    """Workflow start-node smoke: 主路径 / 边界 / 复杂（按变量名启发式填值）。"""
    rows = [r for r in (start_inputs or []) if isinstance(r, dict)]
    keys = [str(r.get("key") or r.get("name") or "").strip() for r in rows]
    keys = [k for k in keys if k]
    label = (workflow_name or "Workflow").strip() or "Workflow"

    if not keys:
        # No declared vars — still offer a portable message/query pair for agent/llm stages
        keys = ["message", "query"]

    def _value_for(key: str, *, mode: str) -> Any:
        spec = {"type": "string"}
        if mode == "boundary":
            happy = sample_value_for_field(key, spec, skill_hint=label)
            return _boundary_value_for_field(key, spec, happy)
        if mode == "complex":
            kl = key.lower()
            if kl in (
                "message", "prompt", "query", "topic", "text", "content", "input",
                "user_requirement", "requirement", "instruction", "task", "brief",
            ):
                return _generic_scenario_complex(label=label, field_key=key, field_desc="")
            return sample_value_for_field(key, spec, skill_hint=f"{label} complex")
        # happy
        return sample_value_for_field(key, spec, skill_hint=label)

    def _as_json(mode: str) -> str:
        payload = {k: _value_for(k, mode=mode) for k in keys}
        return json.dumps(payload, ensure_ascii=False, indent=2)

    return [
        {"title": f"{label}（主路径）", "content": _as_json("happy")},
        {"title": f"{label}（边界/异常）", "content": _as_json("boundary")},
        {"title": f"{label}（复杂·多约束）", "content": _as_json("complex")},
    ]


def workflow_example_to_start_inputs(example_content: str) -> List[Dict[str, str]]:
    """Parse example JSON content → [{key, value}] for start node."""
    try:
        obj = json.loads(example_content)
    except Exception:
        return [{"key": "message", "value": str(example_content or "")}]
    if isinstance(obj, dict):
        return [{"key": str(k), "value": "" if v is None else (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))} for k, v in obj.items()]
    return [{"key": "message", "value": str(obj)}]


def build_agent_task_examples(
    *,
    display_name: str,
    description: str = "",
    skill_ids: Optional[List[str]] = None,
    tool_ids: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Skill/tool-aware defaults when Agent has no execution_examples / schema."""
    label = (display_name or "Agent").strip() or "Agent"
    skills = {str(s).lower() for s in (skill_ids or [])}
    tools = {str(t).lower() for t in (tool_ids or [])}
    desc = (description or "").strip()
    task_hint = f"任务背景：{desc}\n" if desc else ""
    label_blob = f"{label} {desc}".lower()

    if any(s in skills for s in ("ppt_generation", "pptx_generation", "slide_generation")):
        outline_text = (
            f"{task_hint}"
            "请根据以下大纲生成 PPT（有默认模版也须先确认再生成）：\n"
            "标题：aiPlat 产品介绍\n"
            "一、背景与目标\n"
            "- 交付慢、知识难沉淀\n"
            "- 目标：缩短交付周期\n"
            "二、方案概览\n"
            "- 八层架构要点\n"
            "三、下一步\n"
            "- 试点范围与成功指标\n"
            "\n"
            "约束：不编造数据；输出 pptx 绝对路径；生成前列出将使用的模版路径请用户确认。"
        )
        return [
            {"title": f"{label}（PPT 大纲）", "content": outline_text},
            {
                "title": f"{label}（PPT JSON）",
                "content": json.dumps({"message": outline_text.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Research / multi-source survey — before browser, so webfetch+browser agents aren't misclassified.
    if (
        "last30days" in skills
        or "knowledge_multi_query" in skills
        or any(k in label_blob for k in ("调研", "research", "竞品", "paper_monitor", "competitor"))
    ):
        research_msg = (
            f"{task_hint}"
            "【调研任务】话题：企业级 Agent 平台的「技能上架审批」实践（最近 30 天）。\n"
            "\n"
            "请完成一次可验收的调研冒烟（不要只堆链接）：\n"
            "1. 从至少 3 类来源检索（如 HN / Reddit / 技术博客 / 文档站；没有某源就跳过并说明）；\n"
            "2. 输出结构化报告：共识观点 / 争议焦点 / 新兴趋势 / 可能偏见；\n"
            "3. 每个观点至少标注 1 个可点击来源（标题+URL）；\n"
            "4. 末尾给「对我们产品的 3 条可执行建议」。\n"
            "禁止编造未检索到的来源。"
        )
        narrow_msg = (
            f"{task_hint}"
            "只做开场规划：话题「本地 LLM 推理网关选型」。\n"
            "- 列出检索关键词（中英各 4 个）与计划访问的来源清单；\n"
            "- 说明成功标准（报告章节骨架）；\n"
            "- 暂不抓全文，等用户确认后再深挖。"
        )
        return [
            {"title": f"{label}（技能上架·调研报告）", "content": research_msg},
            {"title": f"{label}（选题·检索规划）", "content": narrow_msg},
            {
                "title": f"{label}（调研 JSON）",
                "content": json.dumps({"message": research_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Product / requirements / PRD agents.
    # Match on skill or *display name* only — descriptions often mention "PRD" (architect/coder)
    # and must not steal those roles' templates.
    name_l = label.lower()
    if "requirement_analysis" in skills or any(
        k in name_l for k in ("产品经理", "pm_agent", "product manager", "产品负责人")
    ):
        prd_msg = (
            f"{task_hint}"
            "【客户口述｜请按产品经理职责做草稿轮/冒烟，不要 PRD_READY】\n"
            "客户：江苏某制造企业，想做一个「现场巡检报障」小应用。\n"
            "- 一线工人用手机拍照上报设备异常；班组长审批后派维修。\n"
            "- 希望和现有钉钉账号打通，但暂时没有开放 API 文档。\n"
            "- 管理层要看「本周报障量 / 平均闭环时长」两个数。\n"
            "- 上线时间：希望 6 周内能试点 1 个车间；预算与编制未定。\n"
            "- 合规：照片可能含产线布局，不能传到公网。\n"
            "\n"
            "请完成一次可验收的需求分析草稿（不要只回「已验证」）：\n"
            "1. 列出至少 5 个必须向客户追问的澄清问题（按优先级，每题说明为什么问）；\n"
            "2. 基于已知信息起草结构化 PRD 草稿，至少包含：\n"
            "   - 背景与目标 / 用户与场景 / 功能需求(FR-001…) / 非功能需求 / 验收标准(AC) /\n"
            "     待确认问题 / 里程碑假设（分期切片，勿把开放问题当里程碑）；\n"
            "3. 每条 FR 给出可验证 AC（禁止「清晰可见/功能正常/实际操作测试」）；\n"
            "4. 信息不足一律标「待确认」；禁止编造多语言、具体 SLA、加密方案、\n"
            "   「已在钉钉应用内完成全流程」等未口述边界。\n"
            "\n"
            "【硬性自检——缺任一条视为失败】\n"
            "- 正文必须显式保留「照片不能传到公网 / 不上公网」（不得弱化成笼统合规）；\n"
            "- 正文必须显式保留「钉钉 API 文档未开放 / 集成方式待确认」；\n"
            "- 不要输出 <!-- PRD_READY -->；不要在文末再套一层 markdown 代码块复读全文。\n"
            "优先调用技能 requirement_analysis；输出一份中文 Markdown 即可。"
        )
        clarifying_msg = (
            f"{task_hint}"
            "用户只说了一句：「我们想做个智能客服，能回答知识库里的制度问题。」\n"
            "\n"
            "请以产品经理身份开场澄清（不要直接写完整 PRD）：\n"
            "- 用 6～8 个选择题/填空题把范围钉住（渠道、知识源、权限、幻觉处理、转人工、成功指标）；\n"
            "- 每题说明「为什么要问」；\n"
            "- 最后给一版「若用户全选默认值」的范围摘要（≤8 行），方便下一轮生成 PRD。\n"
        )
        return [
            {"title": f"{label}（巡检报障·PRD 草稿）", "content": prd_msg},
            {"title": f"{label}（智能客服·澄清开场）", "content": clarifying_msg},
            {
                "title": f"{label}（PRD JSON）",
                "content": json.dumps({"message": prd_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Architect — before generic keyword roles that might overlap descriptions
    if (
        "architecture_design" in skills
        or any(k in name_l for k in ("架构师", "architect"))
        or ("系统设计" in label_blob and "architecture_design" in skills)
    ):
        arch_msg = (
            f"{task_hint}"
            "【输入｜精简 PRD 摘要】\n"
            "目标：现场巡检报障小应用（拍照上报 → 班组长审批 → 派修 → 看板）。\n"
            "约束：照片不可上公网；希望对接钉钉但暂无 API 文档；6 周试点一个车间。\n"
            "\n"
            "请按架构师职责输出一版可评审的架构草稿：\n"
            "1. 上下文与假设（标明待确认）；\n"
            "2. 逻辑架构 + 关键组件职责；\n"
            "3. 数据流（上报/审批/派修/看板）与存储选型理由；\n"
            "4. 对外 API 契约草案（3～5 个端点：方法/路径/请求响应要点）；\n"
            "5. 安全与合规（照片落地、脱敏、内网边界）；\n"
            "6. 6 周试点的分期切片与风险。\n"
            "禁止编造未给定的第三方接口细节。"
        )
        review_msg = (
            f"{task_hint}"
            "已有一版架构说「全部用公有云对象存储存巡检照片」。\n"
            "请做架构评审：指出与「照片不可上公网」的冲突，给出 2 套可落地替代方案及取舍。"
        )
        return [
            {"title": f"{label}（巡检报障·架构草稿）", "content": arch_msg},
            {"title": f"{label}（合规冲突·架构评审）", "content": review_msg},
            {
                "title": f"{label}（架构 JSON）",
                "content": json.dumps({"message": arch_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Eval engineer: generate scoring code for a *target* Agent (not QA test design).
    # Must run before test_case_generation — eval_engineer also binds that skill.
    if "eval_code_generator" in skills or any(
        k in name_l for k in ("评估工程师", "eval_engineer")
    ):
        target = "qa_agent"
        eval_msg = (
            f"{task_hint}"
            f"请为已上架 Agent 生成评估代码（Amazon Eval Agent 方法）。\n"
            f"\n"
            f"target_agent_id: {target}\n"
            f"\n"
            f"要求：\n"
            f"1. 读取 `~/.aiplat/agents/{target}/AGENT.md` 与最近执行轨迹；\n"
            f"2. 调用技能 eval_code_generator，产出 ≤5 个任务质量指标；\n"
            f"3. 写入 `~/.aiplat/eval/{target}/eval_metric.py` 与 `eval_runner.py`；\n"
            f"4. scoring_dimensions 已有且合理则不要覆盖；引擎内置 Agent 可跳过；\n"
            f"5. 尽量跑通 `python eval_runner.py --agent_id={target}`（最多 3 轮修复）；\n"
            f"6. 输出：指标列表 + 文件路径 + 试跑结果摘要。\n"
            f"禁止编造不存在的轨迹或库 API。"
        )
        eval_json = {
            "message": (
                f"为 Agent 生成评估代码并试跑。"
                f"已有评分维度合理则勿覆盖。"
            ),
            "target_agent_id": target,
            "max_traces": 5,
        }
        skip_msg = (
            f"{task_hint}"
            "target_agent_id: programmer_agent\n"
            "该 Agent 若已有合理 scoring_dimensions，请说明并跳过生成；"
            "若只有维度没有评估代码，则只补 eval_metric.py / eval_runner.py。"
        )
        return [
            {
                "title": f"{label}（按 agent_id 评估·qa_agent）",
                "content": eval_msg,
            },
            {
                "title": f"{label}（target_agent_id JSON）",
                "content": json.dumps(eval_json, ensure_ascii=False, indent=2),
            },
            {
                "title": f"{label}（已有维度则跳过）",
                "content": skip_msg,
            },
        ]

    # QA / test design (exclude eval_engineer — it also binds test_case_generation)
    if (
        (
            "test_case_generation" in skills
            or any(k in name_l for k in ("测试经理", "qa_agent", "测试工程师"))
        )
        and "eval_code_generator" not in skills
        and not any(k in name_l for k in ("评估工程师", "eval_engineer"))
    ):
        qa_msg = (
            f"{task_hint}"
            "【被测对象｜巡检报障】能力：工人拍照上报、班组长审批、派修、周看板。\n"
            "\n"
            "请设计可执行的冒烟用例集（不要空话）：\n"
            "1. 至少 8 条用例：编号 / 前置 / 步骤 / 期望 / 优先级；\n"
            "2. 覆盖主路径 + 至少 3 条异常（无权限、照片超限、审批驳回）；\n"
            "3. 另附 3 条接口级用例（若契约未知则标「待契约确认」并写假设）；\n"
            "4. 给出首轮冒烟的执行顺序（≤15 分钟能跑完）。"
        )
        agent_qa = (
            f"{task_hint}"
            "被测 Agent：产品经理（输入自然语言需求 → 输出 PRD Markdown）。\n"
            "请设计 5 条「Agent 对话」用例，每条含：用户输入样例、期望结构检查点、失败判据。"
        )
        return [
            {"title": f"{label}（巡检报障·用例集）", "content": qa_msg},
            {"title": f"{label}（Agent 对话用例）", "content": agent_qa},
            {
                "title": f"{label}（用例 JSON）",
                "content": json.dumps({"message": qa_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Test runner: consume test_cases; do not invent a product brief.
    if "test_executor" in skills or any(
        k in name_l for k in ("测试执行器", "test_executor", "测试用例执行")
    ):
        cases = [
            {
                "id": "SMK-001",
                "title": "工人拍照上报主路径",
                "precondition": "工人已登录且有上报权限；网络正常",
                "steps": [
                    "进入上报页",
                    "选择 1 张 ≤10MB 的 jpg",
                    "填写故障描述与位置后提交",
                ],
                "expected": "返回工单号，状态为待审批",
                "priority": "P0",
                "category": "happy_path",
                "execution": "conversation",
                "ac_ref": "FR-上报",
                "min_expectation": "返回工单号且状态为待审批",
            },
            {
                "id": "SMK-005",
                "title": "无权限上报被拒绝",
                "precondition": "使用无报障权限账号登录",
                "steps": ["尝试进入上报页或直接提交上报"],
                "expected": "操作被拒绝，不产生工单，后端 403/401",
                "priority": "P0",
                "category": "exception",
                "execution": "conversation",
                "ac_ref": "FR-权限",
                "min_expectation": "无权限被拒绝且无数据变更",
            },
            {
                # Standalone-executable: platform_check needs no agent_app / business skill.
                "id": "PLT-001",
                "title": "平台 SSRF 防护冒烟（独立执行可验）",
                "precondition": "无；校验平台 URL 拦截",
                "steps": ["对内网 URL 执行 platform.ssrf_block 断言"],
                "expected": "http://127.0.0.1/x 被拦截",
                "priority": "P0",
                "category": "happy_path",
                "execution": "platform_check",
                "ac_ref": "平台安全",
                "min_expectation": "内网 URL 被 SSRF 防护拦截",
                "asserts": [
                    {
                        "type": "platform.ssrf_block",
                        "url": "http://127.0.0.1/x",
                        "expect_blocked": True,
                    }
                ],
            },
        ]
        run_payload = {
            "message": (
                "请执行下列 test_cases，按绑定 skill「test_executor」产出测试报告"
                "（header/meta/test_results，含通过/失败与原因）。"
                "conversation 用例需要 agent_app（被测 Agent）；独立执行时会 SKIP，不算产品缺陷。"
                "platform_check 可独立跑通以验证执行器本身。"
                "禁止自行编造新用例；禁止「功能正常」作为判定。"
            ),
            "test_cases": cases,
        }
        blocked_payload = {
            "message": "请执行测试并产出通过/失败报告。",
            "test_cases": [],
        }
        run_text = json.dumps(run_payload, ensure_ascii=False, indent=2)
        blocked_text = json.dumps(blocked_payload, ensure_ascii=False, indent=2)
        return [
            {"title": f"{label}（带 test_cases 执行）", "content": run_text},
            {
                "title": f"{label}（缺用例应阻断）",
                "content": blocked_text,
            },
            {
                "title": f"{label}（对话说明+用例）",
                "content": (
                    f"{task_hint}"
                    "上游测试经理已给出用例，请勿再设计需求。\n"
                    "直接执行下面 JSON 中的 test_cases，输出 IEEE 829 风格报告。\n\n"
                    + run_text
                ),
            },
        ]

    # Scaffold: startable FastAPI + Vite (before frontend_engineer, same code_generation skill)
    if any(
        k in name_l
        for k in ("scaffold_agent", "工程脚手架", "脚手架生成")
    ) or (
        "code_generation" in skills
        and any(k in name_l for k in ("scaffold", "脚手架"))
    ):
        scaf_msg = (
            f"{task_hint}"
            "请生成**可启动**的前后端工程骨架（不要写业务 CRUD）：\n"
            "1. FastAPI：`main.py` + `requirements.txt`，"
            "`uvicorn main:app --reload --port 8000` 可启动；含 CORS 与 GET /health。\n"
            "2. Vite+React+TS：`frontend/package.json`、`frontend/vite.config.ts`"
            "（`/api` 代理到 8000）、`frontend/index.html`、`frontend/src/main.tsx`、"
            "`frontend/src/App.tsx`、`frontend/tsconfig.json`。"
            "`.py` 三引号必须成对。禁止只交 frontend/README.md。\n"
            "3. 根 `README.md` 写清后端/前端两条启动命令。\n"
            "调用 code_generation → DONE。"
        )
        return [
            {"title": f"{label}（可启动前后端骨架）", "content": scaf_msg},
            {
                "title": f"{label}（脚手架 JSON）",
                "content": json.dumps({"message": scaf_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Frontend page / app_page OR frontend engineer coding (TS from api_contracts)
    if "app_page_generation" in skills or any(
        k in name_l
        for k in (
            "前端程序员",
            "frontend_developer",
            "前端工程师",
            "frontend_engineer",
        )
    ):
        # Coding FE agent: deliver TypeScript client — NOT FastAPI/Pydantic (that is backend).
        if "code_generation" in skills or any(
            k in name_l for k in ("前端工程师", "frontend_engineer")
        ):
            fe_code = (
                f"{task_hint}"
                "【单独测·可组装切片】本用例测业务模块，不是 Vite 工程。"
                "不要生成 package.json / vite.config；不要用能否 `npm run dev` 判断成败。\n"
                "\n"
                "【验收标准】\n"
                "- 至少 3 个页面：ReportFaultPage / ApproveFaultPage / DispatchRepairPage\n"
                "- apiClient 覆盖下方每一条 method+path；页面禁止裸 fetch\n"
                "- types.ts 覆盖契约模型；鉴权标 `// TODO: auth`\n"
                "- 使用 `## FILE:`；禁止重写 Vite；禁止 Python/FastAPI\n"
                "- 禁止交付 App.tsx / main.tsx / package.json（那是「有脚手架挂路由」或 scaffold）\n"
                "\n"
                "【输入摘要】\n"
                "- PRD：巡检报障（上报 / 审批 / 派修）\n"
                "- 无 project_scaffold（单独测 Agent，不跑研发团队）\n"
                "\n"
                "【api_contracts】\n"
                f"{_INSPECTION_API_CONTRACTS}"
                "\n"
                "\n"
                "请交付：\n"
                "1. `## FILE: frontend/src/types.ts`\n"
                "2. `## FILE: frontend/src/api/apiClient.ts`（上列每个 endpoint 一个函数）\n"
                "3. `## FILE: frontend/src/pages/ReportFaultPage.tsx` 上报\n"
                "4. `## FILE: frontend/src/pages/ApproveFaultPage.tsx` 审批列表/详情\n"
                "5. `## FILE: frontend/src/pages/DispatchRepairPage.tsx` 派修\n"
                "可加 components。缺接口标 BLOCKED，不要编造 path。附成功+失败示例。\n"
                "调用 code_generation → autoreview → DONE。"
            )
            fe_with_scaffold = (
                f"{task_hint}"
                "【单独测·有脚手架时挂路由】假定 Vite 骨架已存在"
                "（frontend/src/App.tsx + react-router）。不要重写 package.json。\n"
                "\n"
                "【验收标准】切片同「可组装切片」+ 必须改 App.tsx 挂三页路由。\n"
                "【api_contracts】\n"
                f"{_INSPECTION_API_CONTRACTS}"
                "\n"
                "\n"
                "交付 types.ts + apiClient.ts + 三页 + "
                "`## FILE: frontend/src/App.tsx`。\n"
                "调用 code_generation → autoreview → DONE。"
            )
            fe_review = (
                f"{task_hint}"
                "下面伪代码把照片 URL 直接拼到公网 CDN。"
                "请指出问题并用最小 diff 思路给出内网存储修正方案（文字即可）。"
            )
            return [
                {"title": f"{label}（单独测·可组装切片·无脚手架）", "content": fe_code},
                {"title": f"{label}（单独测·有脚手架挂路由）", "content": fe_with_scaffold},
                {"title": f"{label}（安全·代码评审）", "content": fe_review},
                {
                    "title": f"{label}（编码 JSON）",
                    "content": json.dumps(
                        {"message": fe_code.strip()}, ensure_ascii=False, indent=2
                    ),
                },
            ]
        page_msg = (
            f"{task_hint}"
            "【输入】为「巡检报障」Agent 应用生成使用页布局描述（app_page.json 风格）。\n"
            "角色：一线工人（上报）+ 班组长（审批列表）。\n"
            "\n"
            "请输出：\n"
            "1. 页面信息架构（路由/区块）；\n"
            "2. 关键组件与绑定的 Agent/Skill 动作；\n"
            "3. 一份可粘贴的 JSON 草稿（字段名清晰）；\n"
            "4. 列出 3 个需产品确认的交互问题。\n"
            "不要生成完整前端工程代码。"
        )
        return [
            {"title": f"{label}（巡检报障·页面草稿）", "content": page_msg},
            {
                "title": f"{label}（页面 JSON）",
                "content": json.dumps({"message": page_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Programmer / backend code generation (FastAPI etc.)
    if "code_generation" in skills or any(
        k in name_l for k in ("程序员", "programmer", "后端开发", "backend_developer", "后端工程师")
    ):
        code_msg = (
            f"{task_hint}"
            "【单独测·可组装切片】测 API 模块，不是完整 uvicorn 工程。"
            "不要用能否单独启动服务判断成败（工程骨架属 scaffold_agent）。\n"
            "\n"
            "【验收标准】\n"
            "- 四条契约各一路由：POST/GET /api/v1/inspection/reports，"
            "POST .../reports/{id}/approve，POST .../reports/{id}/dispatch\n"
            "- Pydantic 字段与契约一致；400/404；鉴权 TODO；禁止假对接钉钉\n"
            "- ## FILE: 切片（routes + schemas）；不要重写 Vite/package.json\n"
            "- 禁止交付 App.tsx / main.tsx / 完整 uvicorn 工程（属 scaffold_agent）\n"
            "\n"
            "【输入摘要】\n"
            "- PRD：巡检报障（上报/审批/派修）\n"
            "- 无 project_scaffold（单独测 Agent）\n"
            "\n"
            "【api_contracts】\n"
            f"{_INSPECTION_API_CONTRACTS}"
            "\n"
            "\n"
            "调用 code_generation → autoreview → DONE。"
        )
        review_msg = (
            f"{task_hint}"
            "下面伪代码把照片 URL 直接拼到公网 CDN。请指出问题并用最小 diff 思路给出内网存储修正方案（文字即可）。"
        )
        return [
            {"title": f"{label}（单独测·可组装切片·无脚手架）", "content": code_msg},
            {"title": f"{label}（安全·代码评审）", "content": review_msg},
            {
                "title": f"{label}（编码 JSON）",
                "content": json.dumps({"message": code_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    if "site_tester" in skills or (
        ("browser" in tools or any(s == "browser" or s.endswith("_browser") for s in skills))
        and "last30days" not in skills
    ):
        msg = (
            f"{task_hint}"
            "请对 https://example.com 做一次可验收冒烟巡检：\n"
            "1. 打开首页，记录标题与主 CTA 是否可见；\n"
            "2. 检查控制台是否有明显 JS error（有则摘录）；\n"
            "3. 输出：通过/失败 + 证据截图或 DOM 要点 + 阻塞项。\n"
            "不要声称访问了未打开的页面。"
        )
        return [
            {"title": f"{label}（站点冒烟）", "content": msg},
            {
                "title": f"{label}（JSON）",
                "content": json.dumps(
                    {"message": msg.strip(), "url": "https://example.com"},
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

    if "summarize" in skills or "summarization" in skills:
        msg = (
            f"{task_hint}"
            "请阅读以下材料并输出结构化摘要（3 条要点 + 1 条风险 + 1 条行动，勿编造原文没有的事实）：\n"
            "\n"
            + sample_value_for_field("message", {"type": "string"})
        )
        return [
            {"title": f"{label}（长文摘要）", "content": str(msg)},
            {
                "title": f"{label}（JSON）",
                "content": json.dumps({"message": str(msg).strip()}, ensure_ascii=False, indent=2),
            },
        ]

    if "file_operations" in tools:
        msg = f"{task_hint}请列出 /tmp 下最近修改的文件，并给出简要说明。"
        return [
            {"title": f"{label}（目录任务）", "content": msg},
            {
                "title": f"{label}（JSON）",
                "content": json.dumps(
                    {"message": msg.strip(), "directory": "/tmp"},
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

    simple_msg = (
        f"{task_hint}"
        f"【简单冒烟｜{label}】\n"
        f"角色：你是「{label}」。\n"
        "- 目标：按本 Agent 职责完成一次最小可交付输出；\n"
        "- 范围：只做核心路径；明确 1 件「本次不做」；\n"
        "- 约束：信息不足标「待确认」，禁止编造未提供的事实；\n"
        "- 验收：输出须含「步骤摘要 + 结果要点 + 1 个风险/阻塞」；禁止只回「已完成/已验证」。\n"
    )
    complex_msg = (
        f"{task_hint}"
        f"【复杂冒烟｜{label}】\n"
        f"角色/干系人：一线用户 + 审批/管理者（你以「{label}」身份服务）。\n"
        "- 场景：现场巡检报障小应用相关任务，需同时考虑主流程与边界；\n"
        "- 范围：主路径 + 至少 1 个异常分支；明确 2 件「本次不做」；\n"
        "- 约束：同时覆盖「依赖未就绪（如钉钉 API 未开放）」与「合规（照片不上公网）」；未知标待确认；\n"
        "- 验收：可复现步骤 + 可对照检查点；禁止「功能正常/清晰可见」；\n"
        "- 输出：结构化结果（标题/要点/待确认/下一步），勿空话。\n"
    )
    return [
        {"title": f"{label}（简单·可验收）", "content": simple_msg},
        {"title": f"{label}（复杂·多约束）", "content": complex_msg},
        {
            "title": f"{label}（复杂 JSON）",
            "content": json.dumps({"message": complex_msg.strip()}, ensure_ascii=False, indent=2),
        },
    ]


def examples_are_generic(
    examples: Optional[List[Dict[str, Any]]],
    schema: Optional[Dict[str, Any]] = None,
) -> bool:
    """True when examples are empty, legacy smoke chips, description-as-value, or too thin."""
    if not examples:
        return True
    dicts = [e for e in examples if isinstance(e, dict)]
    if not dicts:
        return True
    # Legacy chip titles were literally "通用…" placeholders — not display names like「通用助手」
    def _legacy_generic_title(t: str) -> bool:
        s = str(t or "").strip()
        if not s.startswith("通用"):
            return False
        # 「通用助手（…）」等真实 Agent 名：通用后紧跟非分隔符汉字/字母
        rest = s[2:]
        if not rest:
            return True
        if rest[0] in ("（", "(", "-", "—", " ", "示", "冒"):
            return True
        return False

    if all(_legacy_generic_title(e.get("title") or "") for e in dicts):
        return True
    if examples_copy_field_descriptions(dicts, schema):
        return True
    if any(
        "单独测" in f"{e.get('title') or ''}{e.get('content') or ''}" for e in dicts
    ):
        return False
    return all(example_content_is_thin(e.get("content")) for e in dicts)
