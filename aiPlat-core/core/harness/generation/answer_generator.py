"""Answer generation — unified LLM call + answer extraction for RAG pipelines.

Extracts the 3 duplicated answer-generation blocks from MaterialsChatAgent:
  - Streaming: sys_llm_generate_stream + chunk collection
  - Non-streaming: sys_llm_generate + answer validation
  - Cost tracking: model + estimated tokens

Any agent with a RAG pipeline (docs + context → LLM → answer) can use these.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.answer_generator")


async def generate_answer(
    system_msgs: List[Dict[str, str]],
    user_content: str,
    *,
    model_name: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> Tuple[str, Dict[str, Any]]:
    """Non-streaming answer generation via sys_llm_generate.

    Returns (answer_text, trace_info_dict) where trace_info contains
    model_name, input_tok_est, max_tokens for cost tracking.
    """
    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose

        mdl = model_name or best_model_for_purpose("chat")
        resp = await sys_llm_generate(
            None,
            system_msgs + [{"role": "user", "content": user_content}],
            model_name=mdl,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = getattr(resp, "content", "") or str(resp)
        answer = text.strip() if text and len(text) > 5 else ""

        trace = {
            "model_name": mdl,
            "input_tok_est": len(user_content) // 4,
            "max_tokens": max_tokens,
            "stream": False,
        }
        return answer, trace
    except Exception as e:
        logger.debug("generate_answer failed: %s", e)
        return "", {"error": str(e)}


async def generate_stream_answer(
    system_msgs: List[Dict[str, str]],
    user_content: str,
    stream_queue: Any,
    *,
    model_name: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> Tuple[str, Dict[str, Any]]:
    """Streaming answer generation via sys_llm_generate_stream.

    Returns (answer_text, trace_info_dict).
    """
    try:
        from core.harness.syscalls.llm import sys_llm_generate_stream
        from core.harness.utils.model_injection import best_model_for_purpose

        mdl = model_name or best_model_for_purpose("chat")
        answer_parts: List[str] = []
        async for chunk in sys_llm_generate_stream(
            None,
            system_msgs + [{"role": "user", "content": user_content}],
            model_name=mdl,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk:
                answer_parts.append(chunk)
                try:
                    stream_queue.append(chunk)
                except Exception as e:
                    logger.debug("stream queue push failed: %s", e)

        answer = "".join(answer_parts).strip()

        trace = {
            "model_name": mdl,
            "input_tok_est": len(user_content) // 4,
            "max_tokens": max_tokens,
            "stream": True,
        }
        return answer, trace
    except Exception as e:
        logger.debug("generate_stream_answer failed: %s", e)
        return "", {"error": str(e)}


def build_rag_user_message(
    docs: str,
    question: str,
    *,
    graph_context: str = "",
    template: str = "",
) -> str:
    """Build the user message for RAG answer generation.

    Default template uses Chinese format matching MaterialsChatAgent.
    Other agents can pass a custom template with {docs}, {question}, {graph_context}.
    """
    if template:
        return template.format(docs=docs, question=question, graph_context=graph_context)

    parts = [f"文档内容：\n{docs}"]
    if graph_context:
        parts.append(f"\n{graph_context}")
    parts.append(f"\n用户问题：{question}\n\n请回答：")
    return "".join(parts)
