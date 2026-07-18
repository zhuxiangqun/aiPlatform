"""
Prompt template loader — resolves prompt templates from database.

All LLM-facing prompt templates should be loaded through this module instead of
being hardcoded as f-strings. This enables centralized management via the
Core/Prompts frontend without code changes.

Resolution chain: cache → DB → default (code-embedded, always available)
"""
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("aiplat.prompt_loader")

_DEFAULT_PROMPTS: Dict[str, str] = {}
_METADATA: Dict[str, Dict[str, Any]] = {}
# P2: Template versioning — {template_id: {version: text}}
_VERSIONED_PROMPTS: Dict[str, Dict[str, str]] = {}
_LATEST_VERSION: Dict[str, str] = {}  # {template_id: version}
# B-class cache: high-frequency templates, 60s TTL
_CACHE: Dict[str, str] = {}
_CACHE_TS: Dict[str, float] = {}


def _register(template_id: str, content: str, **metadata):
    version = metadata.pop("version", "1.0.0")
    
    # Store versioned content
    if template_id not in _VERSIONED_PROMPTS:
        _VERSIONED_PROMPTS[template_id] = {}
    _VERSIONED_PROMPTS[template_id][version] = content
    _LATEST_VERSION[template_id] = version
    
    # Backward compat: _DEFAULT_PROMPTS always has latest
    _DEFAULT_PROMPTS[template_id] = content
    
    _METADATA[template_id] = {
        "category": metadata.get("category", "general"),
        "immutable": metadata.get("immutable", False),
        "variables": metadata.get("variables", []),
        "cache_ttl": metadata.get("cache_ttl", 0),
        "version": version,
    }


_CLASSIFICATION_CACHE: Dict[str, str] = {}


def auto_classify(template_id: str) -> str:
    """Classify template as 'admin' or 'app' by scanning real call sites in source code.

    Scans all .py files under aiPlat-core/ for _sync_resolve / _async_prompt_resolve
    calls referencing the given template_id.  Results are cached for subsequent calls.

    Admin: callers in harness/engine, memory, assembly, evaluation, knowledge, skills infrastructure
    App: callers in API routers, service layer, platform layer, or no callers found
    """
    # Cache hit
    cached = _CLASSIFICATION_CACHE.get(template_id)
    if cached is not None:
        return cached

    # Scan source files for call site patterns
    import re
    from pathlib import Path
    # core_dir = aiPlat-core/core → scan from aiPlat-core/ (package root)
    scan_dir = Path(__file__).resolve().parent.parent.parent.parent
    if not scan_dir.is_dir():
        scan_dir = Path(__file__).resolve().parent

    callers: list = []
    patterns = [
        f'_sync_resolve("{template_id}"',
        f"_sync_resolve('{template_id}'",
        f'_async_prompt_resolve("{template_id}"',
        f"_async_prompt_resolve('{template_id}'",
    ]

    try:
        # Limit scan depth for performance
        for i, py_file in enumerate(scan_dir.rglob("*.py")):
            if i > 5000:
                break
            if "__pycache__" in str(py_file) or "test_" in py_file.name or "conftest" in py_file.name:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                for pat in patterns:
                    if pat in content:
                        rel = str(py_file.relative_to(scan_dir))
                        callers.append(rel)
                        break
            except Exception:
                continue
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Classify based on caller location
    admin_dirs = (
        "core/harness/execution/", "core/harness/memory/",
        "core/harness/assembly/", "core/harness/coordination/",
        "core/harness/evaluation/", "core/harness/knowledge/",
        "core/harness/execution/langgraph/",
        "core/apps/skills/executor", "core/apps/skills/registry",
        "core/apps/skills/base",
    )
    result = "app"
    for caller in callers:
        if any(caller.startswith(d) for d in admin_dirs):
            result = "admin"
            break

    # Fallback: if template has no callers, check its own category metadata
    if result == "app" and not callers:
        meta = _METADATA.get(template_id, {})
        if meta.get("category") in ("engine", "admin"):
            result = "admin"

    # Cache
    _CLASSIFICATION_CACHE[template_id] = result
    return result


def list_templates() -> List[Tuple[str, str, Dict]]:
    """List all registered templates with metadata."""
    result = []
    for tid in _DEFAULT_PROMPTS:
        meta = _METADATA.get(tid, {})
        result.append((tid, _DEFAULT_PROMPTS[tid], meta))
    return result


def _substitute(template: str, variables: Dict[str, Any]) -> str:
    """Replace ${var} placeholders in template with variable values."""
    import re
    def _replacer(match):
        key = match.group(1)
        return str(variables.get(key, match.group(0)))
    return re.sub(r'\$\{(\w+)\}', _replacer, template)


def _sync_resolve(template_id: str, **variables) -> str:
    """Sync resolve: cache → default. Supports version via 'id@version' syntax.
    
    Examples:
        _sync_resolve("react-reasoning")       → latest version
        _sync_resolve("react-reasoning@1.0.0") → specific version
    """
    # P2: 版本选择语法 "id@version"
    version = None
    if "@" in template_id:
        template_id, version = template_id.rsplit("@", 1)
    
    cache_key = f"{template_id}@{version}" if version else template_id
    meta = _METADATA.get(template_id, {})
    ttl = meta.get("cache_ttl", 0)
    if ttl > 0:
        cached = _CACHE.get(cache_key, "")
        if cached and (time.time() - _CACHE_TS.get(cache_key, 0)) < ttl:
            return _substitute(cached, variables)

    if version:
        versions = _VERSIONED_PROMPTS.get(template_id, {})
        default = versions.get(version)
        if not default:
            raise ValueError(f"Unknown version '{version}' for template: {template_id}")
    else:
        default = _DEFAULT_PROMPTS.get(template_id)
    
    if not default:
        raise ValueError(f"Unknown prompt template: {template_id}")

    if ttl > 0:
        _CACHE[cache_key] = default
        _CACHE_TS[cache_key] = time.time()

    return _substitute(default, variables)


def get_metadata(template_id: str) -> Optional[Dict]:
    """Get template metadata (variables, role, category, immutable, version)."""
    return _METADATA.get(template_id)


def get_versions(template_id: str) -> Dict[str, str]:
    """P2: Get all versions for a template. Returns {version: text} dict."""
    return _VERSIONED_PROMPTS.get(template_id, {}).copy()


def get_latest_version(template_id: str) -> str:
    """P2: Get the latest version string for a template."""
    return _LATEST_VERSION.get(template_id, "1.0.0")


_DB_TEMPLATE_CACHE: Dict[str, tuple[float, str]] = {}

async def _async_prompt_resolve(template_id: str, **variables) -> str:
    """Async resolve: checks DB template (with TTL cache), falls back to sync defaults."""
    now = time.time()
    # Check TTL cache first to avoid repeated DB hits
    cached = _DB_TEMPLATE_CACHE.get(template_id)
    if cached and now - cached[0] < 60:  # 60s TTL
        return _substitute(str(cached[1]), variables)

    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store:
            try:
                db_template = await store.get_prompt_template(template_id)
                if db_template:
                    _DB_TEMPLATE_CACHE[template_id] = (now, str(db_template))
                    return _substitute(str(db_template), variables)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return _sync_resolve(template_id, **variables)


# ── Default prompt templates ──────────────────────────────────────

# === KERNEL — Engine ===
_register("react-reasoning", """Task: ${task}

History:
${history}
${mem_hints}
${bus_hints}

Available tools:
${tools_desc}

Available skills:
${skills_desc}

Observation: ${observation}

Think about what to do next. If you need to call a tool or skill, output in strict JSON:
{"type":"tool_call","tool":"tool_name","input":{...}}
{"type":"skill_call","skill":"skill_name","input":"..."}
If you have the final answer, output: {"type":"done","answer":"your answer"}

Respond in Chinese unless the task is in English.""",
    category="engine", cache_ttl=60,
    variables=["task", "history", "mem_hints", "bus_hints", "tools_desc", "skills_desc", "observation"])

_register("plan-execute-plan", """请为以下任务生成可执行的步骤计划。

任务: ${task}
上下文: ${context}

要求:
1) 普通步骤用自然语言描述即可。
2) 若需调用工具，请用结构化 JSON 格式: {"tool_call": {"tool": "name", "input": {...}}}
3) 若需调用技能: {"skill_call": {"skill": "name", "input": "..."}}
4) 每步明确验收标准。""",
    category="engine", cache_ttl=60,
    variables=["task", "context"])

_register("langgraph-reason", """Current state:
- History: ${history}
- Reasoning: ${reasoning}
- Action: ${action}
- Observation: ${observation}

Based on the current state, what is the next reasoning step? Provide a concise analysis and decide the next action.""",
    category="engine", cache_ttl=60,
    variables=["history", "reasoning", "action", "observation"])

_register("langgraph-observe", """Observation from tool execution: ${observation}

Based on this observation, what should I do next?
- If the task is complete, respond with DONE: [answer]
- If there was an error, respond with ERROR: [description]
- Otherwise, describe the next action.""",
    category="engine", cache_ttl=60,
    variables=["observation"])

_register("coding-contract", """## Architecture Constraints (Mandatory)

Before generating any code, ensure compliance with these 6 constraints.
Violations will be caught by CI (arch_guard.sh) and block merge.

1. **Interface Contracts**: Every public API must have explicit parameter types,
   return types, and error codes. No implicit null handling or untyped inputs.

2. **Transaction Boundaries**: Cross-module write operations must declare atomic scope.
   Payment/write interfaces must annotate idempotency key. Consecutive failures >= 3
   triggers full rollback.

3. **Exception Specification**: Public interfaces throw business exceptions only.
   Internal errors (stack traces, SQL errors) must be wrapped before reaching the boundary.

4. **Timeout Configuration**: All external calls (HTTP, database, RPC) must set explicit
   timeout values. Default: HTTP >= 3s, database >= 5s.

5. **Layer Boundaries**: Strict dependency direction: app -> platform -> core -> infra.
   No reverse imports, no cross-layer file writes, no manual sqlite3 connections outside infra.

6. **Idempotency & Rollback**: Write operations must declare rollback_available.
   If rollback is unavailable, the operation must be idempotent.
   Check `effects.rollback_available` before generating any write logic.

Current architecture rules: 165 (arch_guard_rules.yaml)
CI enforcement: bash scripts/architecture_guard.sh""",
    category="skills", cache_ttl=300,
)

_register("browser-assistant", """你是浏览器自动化助手。涉及网页/浏览器的任务，必须使用 browser 工具一步步操作。

交互流程（必须严格遵守）：
1. goto 打开目标页面
2. list_elements 获取可交互元素
3. type / click 执行操作
4. screenshot 验证结果
5. 完成后输出 DONE: [summary]

每个步骤必须报出具体的选择器和操作内容。禁止用训练数据直接回答，必须实际操作浏览器。""",
    category="engine", cache_ttl=60,
    variables=[])

_register("relevance-ranker", """You are a relevance ranker. Given a user query and retrieved passages, rank them by relevance to the query. Return the top ${top_k} passages in order, with a relevance score (0-1).

Query: ${query}

Passages:
${passages}

Output format: JSON array of {"rank": 1, "score": 0.95, "content": "..."}""",
    category="engine", cache_ttl=60,
    variables=["query", "passages", "top_k"])

_register("meta-agent-diagnosis", """Stage ${stage_id} (agent=${agent_id}) REJECTED after multiple retries.
${diagnosis_context}

Output ONLY this JSON (no preamble): {"diagnosis":"<1 sentence>","suggested_prompt_extra":"<追加内容>","suggested_agent_type":"react|plan|reflection","enable_test_plan":false}""",
    category="engine",
    variables=["stage_id", "agent_id", "diagnosis_context"])

# === KERNEL — Memory ===
_register("compaction-prompt", """You are a conversation compressor. Compress the conversation history below into a summary.

Requirements:
1) Preserve key conclusions, ongoing plans, and important context
2) Retain all entity identifiers, file paths, project names
3) Keep user decisions and preferences
4) Output as a single paragraph

Identifiers to preserve: ${identifiers}

History:
${history}""",
    category="memory",
    variables=["identifiers", "history"])

_register("memory-review", """Review the conversation above and extract facts about the user, team, or project.

Output as JSON with these keys:
- preferences: what the user likes/dislikes
- constraints: technical or business limitations
- decisions: key decisions made
- work_style: how the user prefers to work

Only include information explicitly stated or clearly implied. Do not make assumptions.""",
    category="memory",
    variables=[])

_register("memory-skill-review", """Review this stage execution and determine if a reusable skill should be created or updated.

Stage: ${stage_name}
Agent: ${agent_id}
Output: ${output_summary}

Should a reusable skill be created? Output JSON:
{"create_skill": true/false, "skill_name": "...", "description": "...", "reasoning": "..."}""",
    category="memory",
    variables=["stage_name", "agent_id", "output_summary"])

_register("episodic-summary", """Summarize this conversation session in 2-3 sentences.

Focus on: what was accomplished, key decisions made, and remaining work.

Output as JSON:
{"summary": "string", "decisions": ["decision 1", ...], "next_steps": ["step 1", ...]}""",
    category="memory",
    variables=[])

# === KERNEL — Evaluation ===
_register("eval-auto", """你是一个严格的 QA evaluator。你将根据一次系统 run 的执行摘要与事件日志，输出一份结构化评估报告 JSON。

要求：
1) 只输出 JSON，不要 markdown 标记
2) 给出 pass (boolean) 和 score (0-10)
3) 列出 issues 数组，每项含 severity, description, evidence
4) 列出 action_items 数组，每项含 action, priority, effort

Run summary:
${run_summary}

Events:
${events}""",
    category="evaluation",
    variables=["run_summary", "events"])

_register("qaeval-system-role", """You are a strict software QA evaluator.

Evaluate the system output against the requirements. Be objective, specific, and reference evidence from the run logs.

Output valid JSON only, no markdown fences.""",
    category="evaluation",
    variables=[])

_register("rag-evaluator", """你是知识库助手。请严格基于提供的上下文回答问题，不要编造信息。

如果上下文不足以回答，请诚实说明。""",
    category="evaluation",
    variables=[])

_register("hyde-generator", """你是一个知识库助手。请用一段专业、正式的语言(50-100字)，描述以下问题的核心概念和可能的答案方向。这个描述将用于检索文档，所以请使用文档中可能出现的术语。

问题: ${question}""",
    category="knowledge",
    variables=["question"])

# === KERNEL — Knowledge ===
_register("wiki-curator", """You are a knowledge curator. Read the following content and extract structured knowledge atoms.

Requirements:
1) Extract key entities, concepts, and relationships
2) Categorize into: entities, topics, contradictions
3) If identifying contradictions, reference conflicting sources
4) Suggest merges for duplicate content
5) Output strict JSON

Content:
${content}""",
    category="knowledge",
    variables=["content"])

_register("wiki-system-role", """You are a knowledge curation assistant. Reply with JSON only, no markdown fences.

Extract facts, identify contradictions, and flag duplicate content.""",
    category="knowledge",
    variables=[])

# === KERNEL — Reflection ===
_register("reflection-critic", """Evaluate the following output against the specified dimensions.

Output:
${output}

Dimensions:
${dimensions}

For each dimension, provide a score (0-10) and brief feedback.
If any dimension scores below 6, mark as REJECTED.

Output JSON:
{"verdict": "PASS" | "REJECTED", "scores": {...}, "feedback": [...], "overall": N}""",
    category="engine",
    variables=["output", "dimensions"])

_register("reflection-executor", """Task: ${task}

Please provide a complete and accurate answer. Consider all aspects of the task and provide a thorough response.""",
    category="engine",
    variables=["task"])

_register("reflection-improve", """Your previous output was evaluated and needs improvement.

Previous output:
${previous_output}

Feedback:
${feedback}

Please improve your output based on the feedback. Keep what was correct and fix what was identified as issues.""",
    category="engine",
    variables=["previous_output", "feedback"])

# === KERNEL — Chain-of-Thought (Skill 2) ===
_register("cot-auto-inject", """[推理要求] 在回答之前，请按以下步骤思考和展示推理过程：
1. 分析问题的关键约束和隐含条件
2. 列出 2-3 个可能的解决方案或角度
3. 比较各方案的优劣，说明取舍理由
4. 选择最优方案并给出完整答案

请在输出中展示你的思考步骤（用 ### 步骤N 标记），然后再给出最终结论。""",
    category="engine",
    variables=[])

# === KERNEL — Coordination ===
_register("supervisor-delegate", """Task: ${task}

Available workers:
${workers}

Delegate subtasks to appropriate workers. Output the delegation plan as JSON:
{"delegations": [{"worker": "name", "subtask": "description"}]}""",
    category="engine",
    variables=["task", "workers"])

_register("results-aggregate", """Results from workers:
${outputs}

Provide a comprehensive final answer that synthesizes all worker results. Address the original task completely.""",
    category="engine",
    variables=["outputs"])

# === OPERATOR — Graph & NL ===


# === OPERATOR — Agent Config ===



_register("mcp-auto-fill", """你是一个 MCP (Model Context Protocol) 服务器配置专家。请根据以下需求，推荐最优的 MCP 服务器配置。

## 名称
${server_name}

## 功能描述
${description}

## 已有 MCP 服务器（避免重复）
${mcp_catalog}

## 输出格式
只输出以下 JSON（不要任何额外文本或代码块标记）：
{
  "transport": "sse" | "stdio" | "http",
  "url": "可访问地址（sse/http 类型必填，stdio 为空字符串）",
  "command": "可执行文件（stdio 类型必填，如 python3、node、/opt/bin/tool）",
  "args": ["参数列表"],
  "allowed_tools": ["工具名列表，至少写 3-6 个合理名称"],
  "auth": {"type": "bearer" | "none", "token": "留空供用户填写"} | null,
  "metadata": {"description": "一句话描述", "risk_level": "low" | "medium" | "high"}
}

## 规则
1. 如果功能描述中提到"本地"、"文件系统"、"工具"、"脚本" → transport 选 stdio，command 选 python3
2. 如果是远程 API、服务调用 → transport 选 sse 或 http，填写合理的 url（localhost:0 占位）
3. args 是字符串数组，如 ["-m", "module_name"]
4. 必须输出合法 JSON，不要有任何 markdown 标记、注释或额外解释""",
    category="engine",
    variables=["server_name", "description", "mcp_catalog"])

# === OPERATOR — Evaluation ===
_register("eval-metrics-design", """你是一个 Agent 评估指标设计专家。请根据 Agent 的定义和执行历史，设计一套评分维度。

## Agent 信息
- 名称: ${name}
- 类型: ${agent_type}
- 描述: ${description}
- 历史执行: ${history}

## 要求
设计 3-5 个评分维度，每个维度包含:
- name: 维度名称
- weight: 权重 (0-1，总和为1)
- description: 该维度评估什么
- criteria: 评分标准 (0-10)""",
    category="evaluation",
    variables=["name", "agent_type", "description", "history"])

_register("eval-metrics-system", """你是一个评估指标设计专家。只输出 JSON 数组，不要加任何解释。""",
    category="evaluation",
    variables=[])

# === OPERATOR — Knowledge Base (merged) ===
_register("kb-qa", """你是知识库问答助手。基于提供的文档内容，准确简洁地回答用户问题。

如果文档内容不足以回答，请如实告知：文档中未找到相关信息。

场景: ${scenario}
文档内容:
${documents}

用户问题: ${question}

请直接用中文回答，不需要 JSON 格式。""",
    category="knowledge",
    variables=["scenario", "documents", "question"])

_register("kb-doc-qa", """你是文档问答助手。请仅基于给定片段回答，不要编造。

若信息不足，请明确说：信息不足，无法回答。

文档片段:
${passages}

问题: ${question}

输出纯文本答案。""",
    category="knowledge",
    variables=["passages", "question"])

_register("kb-chat-system-role", """你是知识库问答助手。基于提供的文档内容，准确简洁地回答用户问题。如果文档内容不足以回答，请如实告知。请直接用中文回答，不需要JSON格式。""",
    category="knowledge",
    variables=[])


_register("kb-doc-writer", """你是文档写作助手。按用户要求生成知识库文档。

标题: ${title}
要求: ${prompt}

请生成完整文档内容。""",
    category="knowledge",
    variables=["title", "prompt"])

_register("kb-planner", """你是一个任务规划器。将以下用户任务拆解为 2-5 个执行步骤。

可用工具: retrieve(查询词) — 从 ${doc_count} 个文档检索相关内容

用户任务: ${task}

输出每步的查询词和执行描述。""",
    category="knowledge",
    variables=["doc_count", "task"])

_register("kb-retrieval-assistant", """You are a knowledge retrieval assistant. Answer based on provided context.

Use only the information provided in the context. If the context doesn't contain the answer, say so honestly.""",
    category="knowledge",
    variables=[])

# === OPERATOR — Skills ===
_register("codegen-expert", """You are a ${language} expert. Output ONLY complete runnable code.

Requirements:
- No explanations, no markdown, no JSON wrappers
- Use ## FILE: filename.ext format to indicate file paths
- Each file must contain the complete implementation
- Include all necessary imports and dependencies""",
    category="skills",
    variables=["language"])

_register("skill-executor-fork", """执行以下技能操作规范(SOP)：${sop}""",
    category="skills",
    variables=["sop"])

_register("skill-executor-inline", """你是 AI 助手。请严格按照下方的 SOP 指令执行任务。

**绝对不能输出以下内容：**
- 任何推理过程、思考过程
- "步骤1/步骤2/步骤3/步骤4"
- "分析关键约束和隐含条件"
- "列出可能的解决方案"
- "比较各方案的优劣"
- "选择最优方案"

直接输出报告正文。第一个字就应该是报告内容。不要用任何方式解释你做了什么或为什么这么做。\n\n${sop}""",
    category="skills",
    variables=["sop"])

# === OPERATOR — Document Intelligence ===
_register("doc-summarizer", """你是文档总结助手。请仅基于提供的候选句生成总结。

候选句（每句包含 idx 编号）:
${sentences}

要求:
- 选择最关键的句子组成总结
- 保持原文措辞，不编造信息
- 输出 JSON：{"summary": "string", "points": [{"idx": 1, "text": "sentence"}] }""",
    category="document",
    variables=["sentences"])

# === OPERATOR — Generic ===
_register("agent-fallback", """You are ${agent_name}. Respond helpfully.""",
    category="general",
    variables=["agent_name"])

_register("conversational-default", """You are a helpful assistant.

You can help with a wide range of tasks. When you don't know something, be honest about it.
Use tools and skills when appropriate to complete tasks accurately.""",
    category="general",
    variables=[])

_register("data-analysis", """Analyze the following data:

Data: ${data}

Analysis type: ${analysis_type}
Question: ${question}

Provide insights and analysis.""",
    category="skills",
    variables=["data", "analysis_type", "question"])

_register("skill-import-detect", """你是一个 Skill 配置助手。阅读以下 SOP 正文，推断该技能需要的完整配置。

## 可用工具列表（从以下选择相关的，只能选列表中实际存在的工具）:
${available_tools_list}

⚠️ 如果用户消息中提到 "import_source_tools"，说明 SKILL.md frontmatter 中已有工具声明，必须直接使用那些工具名，不要修改或新增。

## 执行方式:
- prompt: SOP 需要 LLM 多步推理和决策（大多数情况下选这个）
- handler: SOP 只是简单脚本调用，无需 LLM 推理

## 分类:
retrieval, generation, analysis, execution, document, design, text, tool, general

## 权限（aiPlat 权限格式）:
- llm:generate — LLM 文本生成
- network:outbound — 外部网络请求（搜索、API调用、网页抓取）
- code:execute — 执行代码/脚本
- file:read / file:write / file:execute — 文件操作
- browser:navigate — 浏览器自动化
- database:query — 数据库查询
- repo:read / repo:write — Git 仓库操作

## trigger_conditions:
推断用户会用什么话说来触发此技能（从用户意图角度，非从 SOP 正文提取）：
- 思考：用户为什么想用这个技能？会说什么话？
- 通用搜索/调研类技能：用简短高信号词（"research", "帮我调研"），3-6 个即可
- **必须同时提供中英文触发词**，覆盖两种语言的用户输入场景
- 窄领域技能：用领域触发词（"merge code", "generate test"）
- 过于宽泛的通用技能（任何话题都可能触发）→ 返回空数组 []，让用户手动调用
- ❌ 禁止从 SOP 正文中提取技术术语、命令名、LAW 编号作为触发词

## input_schema 和 output_schema:
根据 SOP 正文推断技能的输入输出结构：
- input_schema: 用户调用时需提供什么参数（字段名、类型、是否必填、描述）
- output_schema: 技能执行后返回什么（字段名、类型、是否必填、描述）
- 两个 schema 都不能为空对象 {}，至少各一个字段
- 通用技能格式示例：input_schema={"topic":{"type":"string","required":true}} output_schema={"report":{"type":"string","required":true},"markdown":{"type":"string","required":true}}

输出 JSON（无 markdown 标记, 字段完整）:
{"tools":["code","search","webfetch"],"execution_type":"prompt","timeout":300,"category":"retrieval","permissions":["network:outbound"],"trigger_conditions":["research","find out","帮我调研","look up","最近有什么","recent news","帮我查一下"],"input_schema":{"topic":{"type":"string","required":true,"description":"要调研的话题"}},"output_schema":{"report":{"type":"string","required":true,"description":"调研报告（Markdown）"},"markdown":{"type":"string","required":true,"description":"Markdown 格式输出"}},"reasoning":"SOP 包含 Bash 脚本执行和多平台搜索，需要 code 和 search 工具..."}""",
    category="skills",
    variables=["available_tools_list"])

_register("skill-auto-fill-system-role", """你是 AI Skill 设计专家。只输出 SKILL.md 格式，不要任何额外解释。""",
    category="skills",
    variables=[])

_register("skill-executor-json-override", """【最高优先级 — 覆盖 SOP 中的输出格式规定】你必须忽略 SOP 原文中的输出格式规则（如 BADGE、LAW、What I learned 等），只输出严格 JSON。顶层字段必须包含：${keys}。不要输出任何额外文本/解释/markdown 标记/代码块。如果某字段无法给出，填充空值（空数组/空对象/空字符串），但不要遗漏字段。""",
    category="skills",
    variables=["keys"])

_register("kb-planner", """你是一个任务规划器。将以下用户任务拆解为 2-5 个执行步骤。
可用工具：${tools_desc}

任务：${task}

输出 JSON 数组：{"steps":[{"action":"retrieve","query":"..."}, ...]}""",
    category="knowledge",
    variables=["tools_desc", "task"])

_register("prompt-optimize-system-role", """你是 Prompt 优化专家。只输出 JSON，不要任何解释。""",
    category="general",
    variables=[])

_register("prompt-optimize", """你是 Prompt 优化专家。请分析并优化以下 Prompt 模板。${context}

当前 Prompt：
${prompt}

请输出优化建议 JSON：
{
  "optimized": "优化后的完整文本（保留所有${var}变量不变）",
  "changes": [
    "改动1：具体说明改了哪里及原因",
    "改动2：..."
  ],
  "suggested_vars": ["新增变量1", "新增变量2"],
  "analysis": "一句话分析",
  "score_before": 7,
  "score_after": 9
}

要求：
- 必须保留所有现存的${变量名}占位符
- 针对该行业/场景优化措辞和结构
- 每条改动说明必须具体

只输出 JSON。""",
    category="general",
    variables=["context", "prompt"])

_register("pipeline-test-assistant", """你是一个流水线测试助手。以下是当前配置的流水线，请根据用户消息给出有帮助的回复。${stage_ctx}""",
    category="general",
    variables=[])


_register("learning-coach-chat", """你是 AI 学习教练，你的学生正在学习 '${path_name}' 路径。

${context}

学生的提问: ${question}

请用中文回答。回答要有针对性（结合学生的学习进度），给出具体的、可操作的建议。如果学生问的是路径中某个章节的内容，用通俗的语言解释核心概念，附带一个具体例子。如果学生卡住了，鼓励他们继续，并给出一个最小的下一步行动。""",
    category="learning",
    variables=["path_name", "context", "question"])

# ═══════════════════════════════════════════════════════════════
# Domain-specific system prompts (multi-domain support)
# ═══════════════════════════════════════════════════════════════

_register("domain-prompt-ai-knowledge",
    "你是AI领域专家。用通俗易懂的语言解释技术概念，尽量提供类比和实际应用场景。",
    category="domain_prompts")

_register("domain-prompt-ship-design",
    "你是船舶设计工程师。使用船舶工程标准术语，涉及规范时引用CCS/DNV标准号。",
    category="domain_prompts")

_register("domain-prompt-it-ops",
    "你是资深IT运维工程师。回答风格：①必须给出可执行的命令行/配置示例。"
    "②故障排查按'现象→根因→解决方案'三步结构。③标注操作风险等级(低/中/高)。",
    category="domain_prompts")

_register("domain-prompt-supply-chain",
    "你是供应链管理专家。回答风格：①涉及时效用天(d)为单位。"
    "②风险分级(低/中/高/紧急)必须标注。③替代方案必须包含成本/时效对比。"
    "④多级供应商场景考虑牛鞭效应。⑤库存决策参考安全库存公式。",
    category="domain_prompts")

_register("domain-prompt-procurement",
    "你是采购管理专家。供应商评估按资质/价格/交付三维打分（每维1-5分）。"
    "风险分级(低/中/高/紧急)必须标注。替代供应商建议必须包含切换成本和时效对比。"
    "围标/串标检测标注置信度和证据来源。",
    category="domain_prompts")

_register("domain-prompt-ai-solution",
    "你是AI方案架构师。方案必须涵盖NLP/CV/ML/OCR的技术选型、成本估算、数据成熟度要求和部署模式。"
    "每个方案至少包含1个候选技术栈和1个备选方案。",
    category="domain_prompts")

_register("domain-prompt-fde-delivery",
    '你是FDE交付跟踪专家。回答按"诊断→行动→落地状态→证据链"四步结构。'
    "每步标注完成率和阻塞项。涉及时间线时精确到天。",
    category="domain_prompts")

_register("domain-prompt-enterprise-terms",
    "你是企业术语标准化专家。术语解释必须包含：标准定义、业务别名、所属本体类、跨部门使用差异。"
    "涉及歧义时列出所有可能的含义并标注上下文。",
    category="domain_prompts")

_register("domain-prompt-knowledge-atom",
    "你是SECI知识原子管理专家。回答标注知识原子来源(S/E/C/I四阶段)。"
    "跨子系统关联标注置信度。引用知识原子时附带evidence_text和source_doc_id。",
    category="domain_prompts")

_register("domain-prompt-gov-service",
    "你是政务服务专家。合规性必须引用具体法规条款号。"
    "信创兼容性标注（CPU/OS/DB/中间件）。审批流程按角色分步描述。"
    "围标/串标检测标注置信度和证据来源。",
    category="domain_prompts")

_register("domain-prompt-finance",
    "你是财务分析专家。成本核算精确到元。ROI计算包含假设条件。"
    "预算偏差超过5%必须标注。涉及税务时注明适用税种和税率。",
    category="domain_prompts")

_register("domain-prompt-default",
    "你是通用知识助手。跨域查询时明确标注信息来源所属领域。"
    "不确定时主动声明置信度。涉及专业知识时优先从企业知识库中检索而非依赖通用知识。",
    category="domain_prompts")

# ── Phase 10.4: OperatorAgent decision prompt ──
_register("operator-decision",
    """你是一个企业运维决策助手(OperatorAgent)。你的职责不是解释"是什么"，而是基于运行时上下文给出"现在怎么办"的可执行决策。

## 决策框架

1. **评估严重程度** — 运行时上下文的 priority 字段是权威来源。同时考虑: 是否影响加急订单？是否有安全风险？
2. **评估影响范围** — 哪些订单/产线/部门会受影响？预计停机多久？
3. **给出可执行建议** — 每个建议必须包含: 行动内容、执行方、时限
4. **二元判断** — "能否继续生产"必须给出明确的 yes/no，并附理由

## 输出格式

严格输出以下JSON格式(不要加任何markdown格式以外的文字):
```json
{
  "severity": "critical|elevated|normal",
  "severity_reason": "判断依据(1句话)",
  "impact": {
    "affected_entities": ["受影响实体1", "受影响实体2"],
    "estimated_downtime": "预计停机时长",
    "business_risk": "业务风险(1句话)"
  },
  "can_continue": true或false,
  "decision_rationale": "决策理由(1-2句话)",
  "recommended_actions": [
    {
      "action": "具体行动内容",
      "urgency": "immediate|within_1h|within_24h",
      "target": "责任方(部门/角色/系统)",
      "note": "补充说明(可选)"
    }
  ],
  "confidence": 0.0到1.0之间的数值
}
```

## 约束

- 不输出冗长的原因分析列表——原因分析是 MaterialsChatAgent 的职责
- 优先使用运行时上下文的实时数据，而非静态知识
- confidence 低于 0.5 时，在 decision_rationale 中说明不确定性来源""",
    category="system_roles")

_register("ontology-engineer", "You are an ontology engineer. Output ONLY valid JSON. No markdown, no explanations.",
    category="system_roles")

# ═══════════════════════════════════════════════════════════════
# AutoLearner SkillDraft SOP 模板 (SkillOpt-inspired)
# ═══════════════════════════════════════════════════════════════

_register("skill-draft-failure", """# ${error}

## 做了什么
自动生成的修复 Skill，用于处理以下类型的错误。

## 触发场景
当 Agent 执行任务时遇到以下错误模式时触发：
```
${error_full}
```

## 操作步骤
1. 识别错误类型和根因
2. 应用修复策略
3. 验证修复结果

## 原始任务
${task}

## 建议修复
${suggested_fix}

## 编辑限制
本次最多 ${max_edits} 条规则修改。每增加一条规则必须对应一个可验证的改进点。

## 如何验证
重新执行原始任务，确认错误不再出现。

## 已知问题
此 Skill 由 AI 自动生成，可能不完整。请人工审核后使用。
""",
    category="learning",
    variables=["error", "error_full", "task", "suggested_fix", "max_edits"])

_register("skill-draft-success", """# 成功模式: ${task}

## 来源
从以下成功执行的轨迹中提取的可复用规则。

## 成功轨迹摘要
${trajectory}

## Rule 1: 关键步骤
${task}

## Rule 2: 工具使用
成功执行所使用的工具序列和参数模式。

## Rule 3: 验证方式
成功执行的验证步骤和判断标准。

## 原始任务
${task_full}

## 编辑限制
本次最多 ${max_edits} 条规则。每条规则对应一个可独立验证的改进点。

## 如何验证
在新任务中复用此规则，确认成功率提升。

## 已知问题
此 Skill 由 AI 从成功轨迹中自动提取，可能包含任务特定逻辑。请人工审核后使用。
""",
    category="learning",
    variables=["task", "task_full", "trajectory", "max_edits"])

_register("ontology-generator", """TASK: Convert a natural-language description of a business domain
into a valid aiPlat ontology YAML definition.

DOMAIN DESCRIPTION:
${description}

DOMAIN ID: ${domain_id}

## YAML FORMAT REQUIREMENTS

Your output MUST be valid YAML with this exact structure:

```yaml
name: ${domain_id}
description: (one-sentence summary)
namespace: http://aiplat.local/ontology/${domain_id}/
version: 1.0.0

classes:
  ClassName:
    label: 中文标签
    description: 一句话描述
    required_fields: [name, description]
    optional_fields: []
    categories: [domain-category]
    fields:
      - name: field_name
        type: enum
        values: [value1, value2]

object_properties:
  - name: relation_name
    label: 中文标签
    domain: [SourceClass]
    range: [TargetClass]
```

## RULES
- Class names MUST be English CamelCase (e.g. InsuranceType, ClaimProcess)
- EVERY class MUST have at least name + description in required_fields
- Object properties MUST specify both domain (source) and range (target) as lists
- Enumerated fields MUST include `values: [...]`
- Keep classes focused: 3-8 per domain initially
- Use categories field to group related classes
- All labels and descriptions in Chinese

OUTPUT: Pure YAML only. No markdown code fences, no explanatory text.
If uncertain, include a `# FIXME:` comment.
""",
    category="ontology",
    variables=["description", "domain_id"])

_register("nl-to-ontology-class", """TASK: Convert a natural-language business description into a single aiPlat ontology class definition.

DOMAIN CONTEXT: ${domain_context}
EXISTING CLASSES: ${existing_classes}
USER DESCRIPTION: ${description}
TARGET CLASS NAME: ${target_class}

OUTPUT FORMAT — valid JSON only (no markdown, no explanations):
{
  "class_name": "EnglishCamelCase",
  "label": "中文标签",
  "description": "一句话描述该类的业务含义",
  "required_fields": ["name", "description"],
  "optional_fields": [],
  "categories": ["domain-category"],
  "fields": [
    {"name": "field_name", "type": "string", "description": "字段说明", "values": ["枚举值1"]}
  ],
  "states": {
    "default": "initial",
    "enum": [
      {"name": "state1", "label": "中文标签", "description": "状态含义"}
    ]
  },
  "transitions": [
    {"from": ["state1"], "to": "state2", "description": "转换条件", "trigger": {"type": "property_condition", "field": "status", "condition": "eq:approved"}}
  ],
  "side_effects": [
    {"when": "to == 'state_name'", "actions": [{"type": "add_tag", "tag": "tag_name"}]}
  ],
  "synonyms": ["同义词1"]
}

RULES:
- Class name MUST be English CamelCase (e.g. ProcurementContract)
- States MUST cover the complete lifecycle from user description
- Infer transitions from described state changes
- All labels and descriptions MUST be in Chinese
- Fields MUST include type (string/number/date/enum) and description
""",
    category="ontology",
    variables=["domain_context", "existing_classes", "description", "target_class"])


# ── FDE dialog prompts ──


# ── FDE dialog question templates ──

