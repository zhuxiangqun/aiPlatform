import logging

"""

Context Compression



Five-level context compression strategy with per-tool-type summaries and

iterative summary preservation. Includes async tool output summarization

to prevent context window exhaustion during tool-heavy tasks.

"""



from typing import List, Dict, Any, Optional, Tuple

from dataclasses import dataclass, field

from enum import Enum

from functools import lru_cache

import asyncio

import os





# ── P0-3: LRU-cached embedding for semantic relevance scoring ──



@lru_cache(maxsize=1024)

def get_cached_embedding(text: str) -> Optional[tuple]:

    """LRU 缓存的 embedding。同一段文本重复调用只计算一次。

    

    Public function — used by both compression.py and manager.py for

    cross-layer re-ranking (P0-4).

    """

    try:

        from core.harness.infrastructure.infra_embedding_adapter import get_embedding

        result = get_embedding(text[:500])

        if result is not None:

            if asyncio.iscoroutine(result):

                result = asyncio.run(result)

            return tuple(result)

        return None

    except Exception:

        return None





def score_semantic_relevance(messages: List[Dict], task: str) -> List[float]:

    """P0-3: 计算每条消息与当前任务的语义相似度 [0, 1]。

    

    使用 LRU 缓存的 embedding，同一段文本只计算一次。

    返回与 messages 等长的分数列表。

    """

    if not messages or not task:

        return [0.5] * len(messages)

    try:

        import numpy as np

        task_vec = get_cached_embedding(task)

        if task_vec is None:

            return [0.5] * len(messages)

        scores = []

        for msg in messages:

            key = str(msg.get("content", ""))[:200]

            msg_vec = get_cached_embedding(key)

            if msg_vec is not None:

                sim = np.dot(task_vec, msg_vec) / (

                    np.linalg.norm(task_vec) * np.linalg.norm(msg_vec) + 1e-8

                )

                scores.append(max(0.0, min(1.0, (sim + 1.0) / 2.0)))

            else:

                scores.append(0.5)

        return scores

    except Exception:

        return [0.5] * len(messages)





class CompressionLevel(Enum):

    """Compression level based on token usage"""

    NORMAL = (0, 0.85)

    WARNING = (0.85, 0.90)

    REPLACE = (0.90, 0.93)

    PRUNE = (0.93, 0.96)

    AGGRESSIVE = (0.96, 0.99)

    EMERGENCY = (0.99, 1.0)





@dataclass

class ContextState:

    """Current state of the context"""

    token_usage: int

    token_limit: int

    message_count: int



    @property

    def usage_ratio(self) -> float:

        if self.token_limit == 0:

            return 0

        return self.token_usage / self.token_limit





def get_model_context_length(model_name: str) -> int:

    """Read model context_window from infra llm_profile.yaml (core → infra, allowed direction).



    Returns context_window or 200000 (safe default). Used by compression to

    calculate accurate usage_ratio instead of a fixed token_limit.

    """

    try:

        import yaml as _yaml, os as _os

        from pathlib import Path as _Path

        config_path = _os.getenv("AIPLAT_LLM_CONFIG_PATH",

            str(_Path(__file__).resolve().parents[4] / "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"))

        with open(config_path) as f:

            profile = _yaml.safe_load(f)

        caps = (profile.get("model_capabilities") or {}).get(model_name, {})

        window = caps.get("context_window", 200000)

        return int(window)

    except Exception:

        return 200000  # safe default: assume 200K context window





class ContextCompression:

    """Five-level context compression with anti-thrashing and iterative summary."""



    def __init__(self, config: Optional[Dict] = None):

        self._config = config or {}

        self._thresholds = self._init_thresholds()

        self._compression_stats: List[Tuple[int, int]] = []  # (before, after) msg counts



    @property

    def compression_stats(self) -> List[Tuple[int, int]]:

        """公开只读访问最近3次压缩统计，供SystemDiagnostician使用。"""

        return list(self._compression_stats)

        self._prev_summary: Optional[str] = None

        # P0-2: temperature-aware pruning

        self._last_temperature: float = 0.3

    

    def set_temperature(self, temp: float):

        """P0-2: 设置当前推理温度，影响剪枝保留比例。"""

        self._last_temperature = temp



    def _init_thresholds(self) -> Dict[CompressionLevel, float]:

        # PR #2: 从 ControlProfile 读取压缩激进系数

        try:

            from core.harness.meta.profile_registry import get_active_profile

            strictness = get_active_profile().compression_strictness

        except Exception:

            strictness = 1.0

        return {

            CompressionLevel.NORMAL: 0.85 * strictness,

            CompressionLevel.WARNING: 0.90 * strictness,

            CompressionLevel.REPLACE: 0.93 * strictness,

            CompressionLevel.PRUNE: 0.96 * strictness,

            CompressionLevel.AGGRESSIVE: 0.99 * strictness,

            CompressionLevel.EMERGENCY: 1.0  # 紧急模式不调权

        }



    def get_level(self, usage_ratio: float) -> CompressionLevel:

        """Determine compression level based on usage"""

        for level, threshold in self._thresholds.items():

            if usage_ratio < threshold:

                return level

        return CompressionLevel.EMERGENCY



    async def compress(

        self,

        context: List[Dict],

        state: ContextState

    ) -> List[Dict]:

        """Compress context based on current level"""

        level = self.get_level(state.usage_ratio)



        if level == CompressionLevel.NORMAL:

            return context



        elif level == CompressionLevel.WARNING:

            return context  # Just monitor, don't compress yet



        elif level == CompressionLevel.REPLACE:

            result = await self._replace_old_outputs(context)



        elif level == CompressionLevel.PRUNE:

            result = await self._prune_old_messages(context, keep_last=5)



        elif level == CompressionLevel.AGGRESSIVE:

            result = await self._aggressive_compress(context)



        elif level == CompressionLevel.EMERGENCY:

            # PR #3: 紧急压缩 — 归因到 D5_memory

            try:

                from core.harness.meta.profile_registry import set_failure_domain

                set_failure_domain("D5_memory")

            except Exception:

                logging.getLogger(__name__).debug('compress failed', exc_info=True)
            result = await self._emergency_compress(context)

        else:

            return context



        # Anti-thrashing: track effectiveness, skip if consistently <10% savings

        self._compression_stats.append((len(context), len(result)))

        if len(self._compression_stats) > 3:

            self._compression_stats.pop(0)

        if len(self._compression_stats) >= 2:

            savings = [(b - a) / max(b, 1) for b, a in self._compression_stats[-2:]]

            if all(s < 0.10 for s in savings):

                return context  # skip — compression isn't helping



        return result



    @staticmethod

    def _priority_order(msg: Dict) -> int:

        """Return sort key: 0=high (keep), 1=medium, 2=low (delete first)."""

        p = str(msg.get("priority") or msg.get("metadata", {}).get("priority", "")).lower()

        if p == "high":

            return 0

        if p == "low":

            return 2

        return 1  # medium / unset



    @staticmethod

    def _summarize_tool_msg(msg: Dict, idx: int) -> str:

        """Generate a per-tool-type informed summary preserving actionable info."""

        import json as _json

        content = str(msg.get("content", ""))

        name = msg.get("name", "") or msg.get("tool_name", "") or msg.get("tool_call_id", "") or "tool"

        snippet = ""

        for line in content.split("\n"):

            stripped = line.strip()

            if stripped and not stripped.startswith(("#", "//", "<!--")):

                snippet = stripped[:100]

                break

        if not snippet:

            snippet = content[:100].replace("\n", " ").strip()

        if snippet:

            return _json.dumps({"tool": name, "snippet": snippet}, ensure_ascii=False)

        return f"[{name}] executed"



    async def _replace_old_outputs(self, context: List[Dict], protected_roles: Optional[List[str]] = None) -> List[Dict]:

        """Replace old tool outputs with informed per-tool-type summaries.



        Args:

            context: List of message dicts.

            protected_roles: Roles that must never be compressed (e.g. ["system_arch"]).

        """

        protected = set(protected_roles or [])

        result = []

        tool_output_count = 0



        for msg in context:

            role = msg.get("role", "")

            meta_role = msg.get("meta", {}).get("role", "") if isinstance(msg.get("meta"), dict) else ""



            # Never compress protected system-level messages (CLAUDE.md, Domain Prompt, etc.)

            if role == "system" and (meta_role in protected or "system_arch" in protected):

                result.append(msg)

                continue



            if role == "tool":

                tool_output_count += 1

                if tool_output_count <= 3 or tool_output_count % 2 == 0:

                    result.append(msg)

                else:

                    result.append({

                        "role": "system",

                        "content": self._summarize_tool_msg(msg, tool_output_count),

                    })

            else:

                result.append(msg)



        return result



    async def _prune_old_messages(

        self,

        context: List[Dict],

        keep_last: int = 5,

        task: str = "",

    ) -> List[Dict]:

        """P0-2+P0-3: 温度感知 + 语义相关性的智能剪枝。

        

        高温（>0.5，探索）→ 保留更多消息（Top 60%）

        低温（<0.3，决策）→ 激进剪枝（Top 15%）

        

        优先级：system(priority=high) 固定保留，其余按语义相关性降序排列。

        """

        # P0-2: temperature-aware keep ratio

        t = self._last_temperature

        if t >= 0.6:

            keep_ratio = 0.60

        elif t >= 0.3:

            keep_ratio = 0.40

        else:

            keep_ratio = 0.15



        system_msgs = [m for m in context if m.get("role") == "system"]

        non_system = [m for m in context if m.get("role") != "system"]

        high = [m for m in non_system if self._priority_order(m) == 0]

        rest = [m for m in non_system if self._priority_order(m) != 0]



        # P0-3: 语义相关性评分（替代旧的位置启发性规则）

        if task and rest:

            relevance = score_semantic_relevance(rest, task)

            # 按相关性降序排列

            rest = [m for _, m in sorted(

                zip(relevance, rest), key=lambda x: -x[0]

            )]



        keep_count = max(keep_last, int(len(context) * keep_ratio))

        kept_rest = rest[:max(1, keep_count - len(system_msgs) - len(high))]

        return system_msgs + high + kept_rest



    async def _aggressive_compress(self, context: List[Dict]) -> List[Dict]:

        """Aggressive compression — preserve summary + all high-priority + recent turns (§5.21)."""

        system_msgs = [m for m in context if m.get("role") == "system"]

        non_system = [m for m in context if m.get("role") != "system"]

        high = [m for m in non_system if self._priority_order(m) == 0]

        rest = [m for m in non_system if self._priority_order(m) != 0]



        # Detect and preserve previous summary for iterative update

        prev_summary_content = self._prev_summary

        if not prev_summary_content:

            for msg in context:

                c = str(msg.get("content", ""))

                if msg.get("role") in ("system", "assistant") and ("summarized" in c.lower() or "CONTEXT_SUMMARY" in c):

                    prev_summary_content = c

                    break



        recent = rest[-2:] if len(rest) > 2 else rest

        dropped = rest[:len(rest) - len(recent)]

        summarized_count = len(dropped)



        # P1-1: prefer a real LLM semantic summary over the mechanical placeholder.

        llm_summary = ""

        if summarized_count > 0 and _context_summary_enabled():

            llm_summary = await _llm_summarize_conversation(dropped, prev_summary_content or "")



        if llm_summary:

            summary_msg = {"role": "system", "content": llm_summary}

        elif prev_summary_content:

            summary_msg = {

                "role": "system",

                "content": (

                    f"CONTEXT_SUMMARY (updated):\n{prev_summary_content}\n\n"

                    f"[+{summarized_count} new turns incorporated]"

                ),

            }

        else:

            summary_msg = {

                "role": "system",

                "content": f"[Previous {summarized_count} messages summarized]",

            }



        self._prev_summary = str(summary_msg["content"])

        return system_msgs + high + [summary_msg] + recent



    async def _emergency_compress(self, context: List[Dict]) -> List[Dict]:

        """Emergency compression — keep system + all high-priority + last message (§5.21).



        P1-1: even at this extreme level, preserve conversational continuity via a

        compact LLM semantic summary of the dropped messages (falls back to nothing

        on timeout/no-model, so it is never worse than pure truncation).

        """

        system_msgs = [m for m in context if m.get("role") == "system"]

        non_system = [m for m in context if m.get("role") != "system"]

        high = [m for m in non_system if self._priority_order(m) == 0]

        rest = [m for m in non_system if self._priority_order(m) != 0]

        keep = rest[-1:] if rest else []

        dropped = rest[:len(rest) - len(keep)]



        summary_msgs: List[Dict] = []

        if dropped and _context_summary_enabled():

            llm_summary = await _llm_summarize_conversation(dropped, self._prev_summary or "")

            if llm_summary:

                self._prev_summary = llm_summary

                summary_msgs = [{"role": "system", "content": llm_summary}]



        return system_msgs + high + summary_msgs + keep



    def should_trigger_compression(self, state: ContextState) -> bool:

        """Check if compression should be triggered"""

        level = self.get_level(state.usage_ratio)

        return level != CompressionLevel.NORMAL





# ── Tool output budget: background summarization ───────────────────



TOOL_OUTPUT_SUMMARY_THRESHOLD = 2000   # chars — trigger async summary above this

TOOL_OUTPUT_SUMMARY_TIMEOUT = 3.0       # seconds — fallback to truncation





async def _background_tool_summarize(

    tool_call_id: str,

    tool_name: str,

    raw_output: str,

    scratchpad: Dict[str, str],

) -> None:

    """Background task: generate LLM summary for large tool outputs.



    Must ALWAYS write a final state to scratchpad — even on timeout or error.

    This prevents "ghost placeholders" in the agent's context.

    """

    import time as _time

    _t0 = _time.time()

    try:

        from core.harness.memory.metrics import inc_tool_truncated

        inc_tool_truncated(tool_name)

    except Exception as e:

        logging.debug(str(e), exc_info=True)

    try:

        summary = await asyncio.wait_for(

            _llm_summarize_tool_output(tool_name, raw_output),

            timeout=TOOL_OUTPUT_SUMMARY_TIMEOUT,

        )

        scratchpad[tool_call_id] = summary

    except asyncio.TimeoutError:

        scratchpad[tool_call_id] = (

            f"[TIMEOUT] 工具摘要生成超时({TOOL_OUTPUT_SUMMARY_TIMEOUT}s)。"

            f"原始数据({len(raw_output)}chars)前1000字: {raw_output[:1000]}"

        )

    except Exception as e:

        scratchpad[tool_call_id] = (

            f"[ERROR] 工具摘要生成失败: {e}。"

            f"原始数据({len(raw_output)}chars)前1000字: {raw_output[:1000]}"

        )

    try:

        from core.harness.memory.metrics import observe_tool_summary

        observe_tool_summary(tool_name, _time.time() - _t0)

    except Exception as e:

        logging.debug(str(e), exc_info=True)





async def _llm_summarize_tool_output(tool_name: str, raw_output: str) -> str:

    """Call LLM to generate structured summary of tool output."""

    try:

        from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter

        from core.adapters.llm.base import LLMConfig

        model_name = best_model_for_purpose("doc_llm") or ""

        adapter = create_selected_adapter(model_name=model_name) if model_name else None

        if adapter is None:

            raise RuntimeError("no LLM model configured for tool summarization")



        prompt = (

            f"工具 [{tool_name}] 返回了以下输出。请输出 JSON：\n"

            '{{"summary":"<50字摘要>",'

            '"completed":["已完成事项"],'

            '"pending":["待办/未确认事项"],'

            '"user_preference":"从输出中提练的用户偏好(无则空)",'

            '"numbers":{{"key":"value"}},'

            '"actionable":true/false}}\n\n'

            f"输出({len(raw_output)}字符):\n{raw_output[:3000]}"

        )

        result = await adapter.generate(

            [{"role": "user", "content": prompt}],

            LLMConfig(model=model_name, temperature=0.0, max_tokens=500),

        )

        content = getattr(result, "content", "") or ""

        content_str = content.strip() if content else ""

        # Parse JSON; fallback to free text if parsing fails

        try:

            import json as _json

            parsed = _json.loads(content_str)

            lines = [f"[摘要] {parsed.get('summary', '')}"]

            if parsed.get('completed'):

                lines.append(f"✅ {'; '.join(parsed['completed'][:3])}")

            if parsed.get('pending'):

                lines.append(f"⏳ {'; '.join(parsed['pending'][:3])}")

            if parsed.get('user_preference'):

                lines.append(f"💡 {parsed['user_preference']}")

            return " | ".join(lines)

        except (json.JSONDecodeError, KeyError, TypeError):

            return f"[摘要] {content_str}" if content_str else raw_output[:1000]

    except Exception:

        raise





# ── P1-1: Conversation-level LLM semantic summary (Hermes Layer 4) ──

# Replaces the mechanical "[Previous N messages summarized]" placeholder at

# AGGRESSIVE/EMERGENCY levels with a real LLM summary that preserves 4 key

# categories: current goal / key conclusions / recent tool calls / todos.



CONTEXT_SUMMARY_TIMEOUT = 3.0  # seconds — fallback to mechanical placeholder





def _context_summary_enabled() -> bool:

    return os.getenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "true").lower() not in ("0", "false", "no")





async def _llm_summarize_conversation(messages: List[Dict], prev_summary: str = "") -> str:

    """LLM 语义摘要：把将被丢弃的对话历史压缩为保留 4 类关键信息的结构化摘要。



    保留类别（Hermes Layer 4）：当前目标 / 关键结论 / 近期工具调用及结果 / 待办事项。

    超时/无模型/异常时返回空串，调用方回退到机械占位符——保证行为绝不劣于原实现。

    """

    if not messages:

        return ""

    try:

        return await asyncio.wait_for(

            _do_llm_conversation_summary(messages, prev_summary),

            timeout=CONTEXT_SUMMARY_TIMEOUT,

        )

    except Exception:

        return ""





async def _do_llm_conversation_summary(messages: List[Dict], prev_summary: str) -> str:

    from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter

    from core.adapters.llm.base import LLMConfig



    model_name = best_model_for_purpose("doc_llm") or ""

    if not model_name:

        return ""

    adapter = create_selected_adapter(model_name=model_name)

    if adapter is None:

        return ""



    convo_lines = []

    for m in messages[-40:]:

        role = str(m.get("role", "?"))

        content = str(m.get("content", ""))[:800]

        if content:

            convo_lines.append(f"{role}: {content}")

    convo_text = "\n".join(convo_lines)[:6000]

    if not convo_text:

        return ""

    prev = f"\n已有摘要(需合并保留其信息):\n{prev_summary[:1000]}\n" if prev_summary else ""



    prompt = (

        "将以下对话历史压缩为结构化摘要，严格保留 4 类关键信息，用 JSON 输出：\n"

        '{"current_goal":"<当前任务目标>",'

        '"key_conclusions":["关键中间结论"],'

        '"recent_tools":["近期工具调用及结果"],'

        '"todos":["待办/未完成事项"]}\n'

        f"{prev}\n对话历史:\n{convo_text}"

    )

    result = await adapter.generate(

        [{"role": "user", "content": prompt}],

        LLMConfig(model=model_name, temperature=0.0, max_tokens=600),

    )

    content = getattr(result, "content", "") or ""

    content_str = content.strip() if content else ""

    if not content_str:

        return ""

    try:

        import json as _json

        s = content_str

        start = s.find("{")

        end = s.rfind("}")

        if start < 0 or end <= start:

            return f"CONTEXT_SUMMARY:\n{content_str[:800]}"

        parsed = _json.loads(s[start:end + 1])

        lines = ["CONTEXT_SUMMARY (LLM semantic):"]

        if parsed.get("current_goal"):

            lines.append(f"🎯 目标: {parsed['current_goal']}")

        if parsed.get("key_conclusions"):

            lines.append(f"📌 结论: {'; '.join(str(x) for x in parsed['key_conclusions'][:5])}")

        if parsed.get("recent_tools"):

            lines.append(f"🔧 工具: {'; '.join(str(x) for x in parsed['recent_tools'][:5])}")

        if parsed.get("todos"):

            lines.append(f"⏳ 待办: {'; '.join(str(x) for x in parsed['todos'][:5])}")

        return "\n".join(lines) if len(lines) > 1 else f"CONTEXT_SUMMARY:\n{content_str[:800]}"

    except Exception:

        return f"CONTEXT_SUMMARY:\n{content_str[:800]}"





__all__ = [

    "CompressionLevel", "ContextState", "ContextCompression",

    "TOOL_OUTPUT_SUMMARY_THRESHOLD", "_background_tool_summarize",

]





__all__ = ["ContextCompression", "CompressionLevel", "ContextState"]

