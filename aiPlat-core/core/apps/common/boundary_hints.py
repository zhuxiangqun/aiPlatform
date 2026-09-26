"""Lightweight boundary hints for conversational create-dialogs.

Not a classifier: keyword / structure heuristics that surface UX tips.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


_TOOL_LIKE = (
    "读写文件",
    "读文件",
    "写文件",
    "http请求",
    "发http",
    "调用api",
    "数学计算",
    "计算器",
    "抓取网页",
    "执行命令",
    "shell",
    "sqlite",
    "查数据库",
)
_AGENT_ORCH = ("多步", "编排", "数字员工", "流水线", "协调", "多个技能", "绑定")
# Concrete integrations only — bare「外部」matches「不引入外部内容」false positives.
_EXTERNAL = (
    "外部系统",
    "外部对接",
    "对接外部",
    "系统对接",
    "飞书",
    "企微",
    "钉钉",
    "第三方系统",
    "第三方服务",
    "webhook",
    "mcp server",
)
_EXTERNAL_NEGATION = (
    "不引入外部",
    "不补充外部",
    "禁止外部",
    "无外部",
    "不要外部",
    "外部内容",
    "外部素材",
    "外部信息",
)
_EXTERNAL_STRONG = ("飞书", "企微", "钉钉", "webhook", "第三方系统", "第三方服务")
_NO_NETWORK = (
    "不联网",
    "禁止联网",
    "无需联网",
    "不要联网",
    "禁止访问网络",
    "不访问网络",
    "离线",
    "no network",
    "offline only",
)
_YES_NETWORK = (
    "需要联网",
    "允许联网",
    "可以联网",
    "联网搜索",
    "webfetch",
    "web_search",
    "抓取网页",
    "访问外网",
)
_NET_TOOLS = frozenset({"search", "web_search", "webfetch", "http", "browser"})


def _blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def mentions_external_system(*parts: Any) -> bool:
    """True for real SaaS/API integration intent — not「外部内容」negations."""
    text = _blob(*parts)
    if not text:
        return False
    if any(k in text for k in _EXTERNAL_NEGATION) and not any(k in text for k in _EXTERNAL_STRONG):
        return False
    return any(k in text for k in _EXTERNAL)


def wants_outbound_network(*, tools: Optional[List[str]] = None, text: str = "") -> bool:
    """Least-privilege network:「不联网」wins over substring「联网」; bare「搜索」不算。"""
    tool_ids = [str(t) for t in (tools or []) if str(t).strip()]
    blob = _blob(text)
    if any(t in _NET_TOOLS for t in tool_ids):
        return True
    if any(k in blob for k in _NO_NETWORK):
        return False
    return any(k in blob for k in _YES_NETWORK)


def hints_for_agent_draft(draft: Optional[Dict[str, Any]] = None, *, description: str = "") -> List[str]:
    d = draft if isinstance(draft, dict) else {}
    skills = d.get("skills") if isinstance(d.get("skills"), list) else []
    tools = d.get("tools") if isinstance(d.get("tools"), list) else []
    mcps = d.get("mcp_ids") if isinstance(d.get("mcp_ids"), list) else []
    sop = str(d.get("sop_text") or d.get("sop") or "")
    text = _blob(description, d.get("description"), sop)
    out: List[str] = []

    if len(skills) <= 1 and len(tools) == 0 and len(mcps) == 0 and len(sop) < 200:
        out.append("绑定偏少：若只是单能力流程，可先建 Skill，再由 Agent 组装；若确需数字员工，请补 Tool/MCP 或加厚 SOP。")
    if mentions_external_system(text) and not mcps:
        out.append("描述像外部系统对接，但未绑定 MCP：可在 MCP 库创建后重填，或在 SOP 中写 `mcp_server_name` / [[need:mcp:名称]]。")
    if ("文件" in text or "http" in text or "api" in text) and not tools:
        out.append("描述含文件/HTTP/API 类原子操作，但未绑 Tool：可在 SOP 引用 `file_operations` / `http` 等白名单工具。")
    if not skills and not tools and not mcps:
        out.append("当前 Skill/Tool/MCP 均为空：确认创建前请核对绑定，否则 Agent 只能空转对话。")
    return out[:4]


def hints_for_skill_draft(draft: Optional[Dict[str, Any]] = None, *, description: str = "") -> List[str]:
    d = draft if isinstance(draft, dict) else {}
    text = _blob(description, d.get("description"), d.get("sop"), d.get("display_name"))
    out: List[str] = []
    if any(k in text for k in _TOOL_LIKE) and len(str(d.get("sop") or "")) < 120:
        out.append("更像原子 Tool（单次读写/HTTP/计算）。若无多步 SOP，建议改建成 Tool，而不是 Skill。")
    if any(k in text for k in _AGENT_ORCH) and "编排" in text:
        out.append("含编排/多 Agent 语义：编排应放在 Agent；Skill 只做单一可复用能力。")
    perms = d.get("permissions") if isinstance(d.get("permissions"), list) else []
    sop = str(d.get("sop") or "")
    if any("tool:" in str(p) for p in perms) and "`" not in sop and "tool" not in sop.lower():
        out.append("permissions 声明了 tool:*，但 SOP 未提及具体工具：建议在步骤中写明将调用的 Tool，或去掉多余权限。")
    return out[:4]


def hints_for_tool_draft(draft: Optional[Dict[str, Any]] = None, *, description: str = "") -> List[str]:
    d = draft if isinstance(draft, dict) else {}
    text = _blob(description, d.get("description"), d.get("display_name"))
    out: List[str] = []
    if any(k in text for k in ("多步", "流水线", "数字员工", "编排", "若干技能")):
        out.append("描述像编排/数字员工：应建 Agent（或 Skill 流程），Tool 只保留原子操作。")
    if any(k in text for k in ("飞书", "企微", "钉钉", "第三方服务", "第三方系统", "webhook")):
        out.append("外部 SaaS/另一进程能力：优先建 MCP Server，本进程 Tool 只做薄封装或不要建。")
    return out[:4]


def hints_for_mcp_draft(draft: Optional[Dict[str, Any]] = None, *, description: str = "") -> List[str]:
    d = draft if isinstance(draft, dict) else {}
    text = _blob(description, d.get("description"), d.get("display_name"))
    out: List[str] = []
    if any(k in text for k in ("本地文件", "读写本地", "计算器", "沙箱执行")) and not any(
        k in text for k in ("外部", "远程", "服务", "sse", "stdio", "http")
    ):
        out.append("更像本机原子能力：优先建 Tool；MCP 用于外部/独立进程服务。")
    transport = str(d.get("transport") or "").lower()
    if transport == "stdio" and not d.get("command"):
        out.append("transport=stdio 但未填 command：确认前请补启动命令，否则无法启用。")
    if transport in ("sse", "http") and not d.get("url"):
        out.append("transport 为网络类但未填 url：确认前请补服务地址。")
    return out[:4]
