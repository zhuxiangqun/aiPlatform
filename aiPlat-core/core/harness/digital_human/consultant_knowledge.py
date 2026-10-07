"""Platform constitution card + on-demand CAPABILITIES / registry snippets for 小朱.

Not semantic RAG: keyword → short section extract. Live inventory stays in
``platform_status_brief``; this pack only adds stable "how the platform works"
when the user question looks conceptual.
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

logger = logging.getLogger("aiplat.consultant_knowledge")

_HERE = Path(__file__).resolve().parent
_CONSTITUTION_PATH = _HERE / "consultant_constitution.md"

# digital_human → harness → core → aiPlat-core → workspace root
_REPO_ROOT = _HERE.parents[3]

_MAX_CONSTITUTION_CHARS = 2200
_MAX_PACK_CHARS = 2800
_MAX_SECTION_CHARS = 1400
_MAX_REGISTRY_LINES = 24

# (keywords in question) → CAPABILITIES.md section title substring
_TOPIC_MAP: Sequence[Tuple[Tuple[str, ...], str]] = (
    (("选模", "模型管理", "unified_pipeline", "purpose", "chat llm", "哪个模型", "deepseek", "ollama"), "九、模型基础设施"),
    (("skill", "技能", "skill.md", "execution_type"), "六、Skill 系统"),
    (("agent", "智能体", "agent.md", "react"), "五、Agent 系统"),
    (("rag", "检索", "wiki", "材料问答", "kb"), "四、RAG 检索"),
    (("本体", "ontology", "知识图谱", "domain", "graphindex"), "三、知识引擎"),
    (("记忆", "episodic", "semantic", "memory"), "二、记忆子系统"),
    (("mcp", "model context"), "十四、MCP 协议"),
    (("工具", "tool", "tools"), "十六、工具生态"),
    (("微调", "sft", "lora", "finetune", "训练"), "十七、微调系统"),
    (("治理", "审批", "policy", "安全", "rbac", "mfa"), "七、安全与治理"),
    (("可观测", "trace", "审计", "observ"), "八、可观测性"),
    (("评估", "eval", "评测"), "十三、评估系统"),
    (("编排", "pipeline", "workflow", "阶段"), "二十四、编排系统"),
    (("工厂", "builder", "交付", "fde"), "二十一、平台治理"),
    (("gate", "门禁", "policygate"), "十二、Gate 系统"),
    (("harness", "syscall", "reactloop", "执行引擎"), "一、Harness 执行引擎"),
    (("infra", "部署", "端口", "节点"), "二十二、Infra 基础设施"),
    (("数字人", "小朱", "顾问", "platform_consultant"), "五、Agent 系统"),
)


def _repo_root() -> Path:
    env = (os.getenv("AIPLAT_REPO_ROOT") or "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
    return _REPO_ROOT


def _capabilities_path() -> Path:
    env = (os.getenv("AIPLAT_CAPABILITIES_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    return _repo_root() / "AIPLAT_CAPABILITIES.md"


def _registry_path() -> Path:
    return _repo_root() / "aiPlat-core" / "core" / "capability_registry.yaml"


def load_constitution_card(*, max_chars: int = _MAX_CONSTITUTION_CHARS) -> str:
    """Short stable mental model; facts still come from the live brief.

    mtime-aware (see consultant_reload) so editing consultant_constitution.md
    takes effect without restarting gunicorn.
    """
    from core.harness.digital_human.consultant_reload import load_constitution_fresh

    return load_constitution_fresh(max_chars=max_chars)


def _wants_concept_pack(question: str) -> bool:
    q = (question or "").strip().lower()
    if len(q) < 2:
        return False
    # Inventory / screen / audit → brief only
    skip = (
        "有哪些", "几个", "列表", "清单", "这个画面", "当前页", "本页",
        "审核", "精简", "再说一遍", "叫我", "记住",
    )
    if any(s in q for s in skip) and not any(
        k in q for k in ("是什么", "怎么", "为何", "区别", "选模", "架构", "边界")
    ):
        return False
    triggers = (
        "是什么", "怎么用", "怎么做", "如何", "区别", "架构", "边界", "原理",
        "选模", "链路", "为什么", "能否", "可不可以", "支持", "什么是",
        "what is", "how to", "difference",
    )
    if any(t in q for t in triggers):
        return True
    # Keyword hit against topic map
    for keys, _ in _TOPIC_MAP:
        if any(k.lower() in q for k in keys):
            return True
    return False


def _match_topics(question: str) -> List[str]:
    q = (question or "").lower()
    hits: List[str] = []
    for keys, section in _TOPIC_MAP:
        if any(k.lower() in q for k in keys):
            if section not in hits:
                hits.append(section)
    return hits[:3]


@lru_cache(maxsize=1)
def _capabilities_text() -> str:
    path = _capabilities_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _extract_section(md: str, title_substr: str, *, max_chars: int) -> str:
    if not md or not title_substr:
        return ""
    # Match ## … title …
    pattern = re.compile(
        rf"^##\s+[^\n]*{re.escape(title_substr)}[^\n]*$",
        re.MULTILINE,
    )
    m = pattern.search(md)
    if not m:
        # softer: any heading containing key tokens from title
        key = title_substr.split("、")[-1].strip() if "、" in title_substr else title_substr
        pattern = re.compile(rf"^##\s+[^\n]*{re.escape(key)}[^\n]*$", re.MULTILINE)
        m = pattern.search(md)
    if not m:
        return ""
    start = m.start()
    nxt = re.search(r"^##\s+", md[m.end() :], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(md)
    chunk = md[start:end].strip()
    # Drop dense tables beyond budget — keep heading + first bullets/paragraphs
    if len(chunk) > max_chars:
        chunk = chunk[:max_chars].rstrip() + "\n…（摘录截断；细节以代码与简报为准）"
    return chunk


def _registry_hits(question: str, *, limit: int = _MAX_REGISTRY_LINES) -> str:
    q = (question or "").strip().lower()
    tokens = [t for t in re.split(r"[\s,，、/]+", q) if len(t) >= 3]
    if not tokens:
        return ""
    path = _registry_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    hits: List[str] = []
    for i, line in enumerate(lines):
        low = line.lower()
        if "symbol:" not in low and "signature:" not in low:
            continue
        if any(t in low for t in tokens):
            # include symbol + following signature/module if present
            block = [line.strip()]
            for j in range(i + 1, min(i + 4, len(lines))):
                nxt = lines[j].strip()
                if nxt.startswith("- symbol:"):
                    break
                if nxt.startswith("type:") or nxt.startswith("signature:") or nxt.startswith("module:"):
                    block.append(nxt)
            hits.append(" | ".join(block))
            if len(hits) >= limit:
                break
    if not hits:
        return ""
    return "capability_registry 命中（符号级，非实时名单）:\n" + "\n".join(f"- {h}" for h in hits)


def build_on_demand_pack(
    question: str,
    *,
    max_chars: int = _MAX_PACK_CHARS,
    force: bool = False,
) -> str:
    """Keyword-selected CAPABILITIES / registry snippets. Empty if not needed."""
    if not force and not _wants_concept_pack(question):
        return ""
    topics = _match_topics(question)
    parts: List[str] = [
        "按需能力摘录（手册片段；若与简报冲突，以简报/当前页为准）:"
    ]
    md = _capabilities_text()
    used = 0
    for title in topics:
        sec = _extract_section(md, title, max_chars=_MAX_SECTION_CHARS)
        if not sec:
            continue
        parts.append(sec)
        used += len(sec)
        if used >= max_chars:
            break
    reg = _registry_hits(question)
    if reg and used < max_chars:
        parts.append(reg[: max_chars - used])
    if len(parts) <= 1:
        return ""
    blob = "\n\n".join(parts)
    if len(blob) > max_chars:
        blob = blob[:max_chars].rstrip() + "\n…"
    return blob


_GENERIC_DISCLAIMER = "通用说明，非 aiPlat 既有"

# High-precision external topics only — never Skill/Agent/选模 (those are platform).
_EXTERNAL_GENERIC_HINTS: Tuple[str, ...] = (
    "oss", "s3", "对象存储", "minio",
    "kubernetes", "k8s", "docker compose", "dockerfile",
    "pytorch", "tensorflow", "huggingface", "transformer架构", "注意力机制",
    "langchain", "llamaindex", "llama index",
    "向量数据库是什么", "什么是embedding", "什么是 embedding",
    "redis缓存", "kafka", "rabbitmq", "graphql",
    "微服务架构", "ci/cd", "devops", "敏捷开发",
    "rest api设计", "openapi设计", "jwt是什么", "oauth是什么",
    "prompt工程通用", "提示词工程通用",
)

_PLATFORM_ANSWER_MARKERS: Tuple[str, ...] = (
    "简报未见",
    "平台实况",
    "当前页",
    "工作区 Agent",
    "工作区 Skill",
    "unified_pipeline",
    "platform_consultant",
    "/app/",
    "/workspace/",
    "/core/",
    "/infra/",
    "/diagnostics/",
    "/governance",
    "/approval",
    "/ontology",
    "/knowledge/",
    "→ /",
)

_PLATFORM_QUESTION_MARKERS: Tuple[str, ...] = (
    "aiplat",
    "小朱",
    "工作区",
    "应用工厂",
    "本平台",
    "简报",
    "这个画面",
    "当前页",
    "有哪些",
    "选模",
    "/workspace",
    "/app/factory",
    "skill",
    "agent",
    "审核",
)


def looks_external_generic_question(question: str) -> bool:
    """True when the user asks industry/generic knowledge, not aiPlat inventory."""
    q = (question or "").strip().lower()
    if len(q) < 2:
        return False
    if any(m in q for m in _PLATFORM_QUESTION_MARKERS):
        return False
    return any(h in q for h in _EXTERNAL_GENERIC_HINTS)


def answer_cites_platform(answer: str) -> bool:
    a = answer or ""
    return any(m in a for m in _PLATFORM_ANSWER_MARKERS)


def ensure_generic_disclaimer(
    answer: str,
    question: str,
    *,
    page_only: bool = False,
) -> str:
    """Prepend 通用说明 when a generic answer forgot the required label.

    High precision: only external-topic questions; never inventory/page/platform how-to.
    """
    raw = (answer or "").strip()
    if not raw or page_only:
        return answer
    if _GENERIC_DISCLAIMER in raw:
        return answer
    if answer_cites_platform(raw):
        return answer
    if not looks_external_generic_question(question):
        return answer
    return f"（{_GENERIC_DISCLAIMER}）\n\n{raw}"


def clear_knowledge_caches(*, reset_reload: bool = True) -> None:
    """Drop CAPABILITIES/brief caches; optionally reset AGENT.md mtime tracker."""
    if reset_reload:
        try:
            from core.harness.digital_human.consultant_reload import clear_reload_cache

            clear_reload_cache()
        except Exception:
            logger.debug("clear reload cache failed", exc_info=True)
    _capabilities_text.cache_clear()
    try:
        from core.harness.digital_human.platform_status_brief import clear_brief_cache

        clear_brief_cache()
    except Exception:
        logger.debug("clear brief cache failed", exc_info=True)
