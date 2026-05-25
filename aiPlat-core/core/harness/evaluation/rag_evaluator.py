"""
RAG Evaluator — ragas-based evaluation engine for KB Q&A quality.

Evaluates RAG pipeline quality using Ragas metrics:
  - Faithfulness: is the answer grounded in retrieved contexts?
  - AnswerRelevancy: is the answer relevant to the question?
  - ContextPrecision: are retrieved contexts relevant?
  - ContextRecall: are all relevant contexts retrieved?

Architecture:
  - Core layer, uses sys_kb_retrieve + sys_llm_generate
  - Ragas library for metric computation (optional, graceful degradation)
  - Results stored in kb_eval_reports SQLite table
"""
from __future__ import annotations

import json as _json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ── Schemas ──

@dataclass
class EvalSample:
    id: str = ""
    question: str = ""
    ground_truth: str = ""
    doc_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0


@dataclass
class EvalMetrics:
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0


@dataclass
class EvalReport:
    sample_id: str = ""
    question: str = ""
    answer: str = ""
    contexts: List[str] = field(default_factory=list)
    ground_truth: str = ""
    metrics: EvalMetrics = field(default_factory=EvalMetrics)
    failure_type: str = ""  # retrieval / generation / ok
    duration_ms: float = 0.0


# ── DB helpers ──

def _db_path() -> str:
    base = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
    return os.path.join(base, "default", "kb.sqlite3")


def _ensure_eval_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS kb_eval_samples (
        id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        ground_truth TEXT NOT NULL,
        doc_ids TEXT NOT NULL,
        tags TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kb_eval_reports (
        sample_id TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        contexts TEXT NOT NULL,
        ground_truth TEXT NOT NULL,
        faithfulness REAL,
        answer_relevancy REAL,
        context_precision REAL,
        context_recall REAL,
        failure_type TEXT,
        duration_ms REAL,
        created_at REAL NOT NULL,
        PRIMARY KEY (sample_id, created_at)
    );
    """)
    conn.commit()


# ── Local embeddings cache ──

_embeddings_cache: Any = None


def _get_or_create_local_embeddings() -> Any:
    global _embeddings_cache
    if _embeddings_cache is not None:
        return _embeddings_cache
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper
        _model = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-zh-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        _embeddings_cache = LangchainEmbeddingsWrapper(_model)
    except Exception:
        _embeddings_cache = False
    return _embeddings_cache if _embeddings_cache is not False else None


# ── Evaluator ──

class _DeepSeekChatOpenAI:
    """Lazy-import ChatOpenAI wrapper that forces n=1 for DeepSeek compatibility."""

    _cls = None

    @classmethod
    def _get_cls(cls):
        if cls._cls is None:
            from langchain_openai import ChatOpenAI

            class _Forced(ChatOpenAI):
                def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                    kwargs.pop("n", None)
                    return super()._generate(messages, stop=stop, run_manager=run_manager, n=1, **kwargs)

                async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                    kwargs.pop("n", None)
                    return await super()._agenerate(messages, stop=stop, run_manager=run_manager, n=1, **kwargs)

            cls._cls = _Forced
        return cls._cls


class RagEvaluator:
    def __init__(self):
        self._ragas_available = False
        try:
            from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall  # noqa: F401
            self._ragas_available = True
        except ImportError:
            pass

    async def evaluate_sample(self, sample: EvalSample) -> EvalReport:
        """Evaluate a single sample: retrieve → generate → score."""
        t0 = time.time()

        # 1. Retrieve
        contexts = []
        try:
            from core.api.core_facade import kb_retrieve
            results = kb_retrieve(query=sample.question, doc_ids=sample.doc_ids, top_k=12)
            contexts = [r["text"] for r in results]
        except Exception:
            pass

        # Always include paragraph (full transcript) as additional context for LLM generation
        paragraph_context = None
        try:
            import os as _os, sqlite3 as _sqlite3
            _db = _os.path.expanduser(_os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
            _db = _os.path.join(_db, "default", "kb.sqlite3")
            _conn = _sqlite3.connect(_db)
            _row = _conn.execute(
                "SELECT text FROM kb_elements WHERE type='paragraph' AND text IS NOT NULL ORDER BY length(text) DESC LIMIT 1"
            ).fetchone()
            _conn.close()
            if _row:
                paragraph_context = _row[0]
                contexts.insert(0, paragraph_context[:4000])
        except Exception:
            pass

        # 2. Generate answer
        answer = "[no answer]"
        try:
            from core.harness.syscalls.llm import sys_llm_generate
            ctx_text = "\n\n---\n\n".join(contexts[:12]) if contexts else "(no context)"
            if paragraph_context:
                ctx_text = paragraph_context[:8000] + "\n\n---\n\n(以下为检索到的相关片段)\n" + ctx_text
            else:
                ctx_text = ctx_text[:8000]
            resp = await sys_llm_generate(
                None,
                [{"role": "system", "content": "你是知识库助手。请严格基于提供的上下文回答问题，不要编造信息。如果上下文不足以回答，请诚实说明。"},
                 {"role": "user", "content": f"上下文：\n{ctx_text[:8000]}\n\n问题：{sample.question}\n请基于上述上下文回答："}],
                model_name="deepseek-chat", temperature=0.1, max_tokens=2000,
            )
            answer = (getattr(resp, "content", "") or str(resp)).strip()
        except Exception:
            pass

        # 3. Score
        metrics = EvalMetrics()
        if contexts and answer:
            if self._ragas_available:
                try:
                    import os as _os
                    _api_key = _os.getenv("AIPLAT_LLM_API_KEY") or _os.getenv("DEEPSEEK_API_KEY", "")
                    if _api_key:
                        _os.environ.setdefault("OPENAI_API_KEY", _api_key)
                        _os.environ.setdefault("OPENAI_API_BASE", _os.getenv("AIPLAT_LLM_BASE_URL", "https://api.deepseek.com/v1"))
                    metrics = await self._ragas_score(sample.question, answer, contexts, sample.ground_truth)
                except Exception as _e:
                    import logging
                    logging.getLogger("aiplat.eval").warning("Ragas scoring failed: %s", _e)
                    metrics = self._simple_score(sample.question, answer, contexts, sample.ground_truth)
            else:
                metrics = self._simple_score(sample.question, answer, contexts, sample.ground_truth)

        # 4. Classify failure
        failure = _classify_failure(metrics, contexts)

        elapsed = (time.time() - t0) * 1000
        return EvalReport(
            sample_id=sample.id, question=sample.question, answer=answer,
            contexts=contexts, ground_truth=sample.ground_truth,
            metrics=metrics, failure_type=failure, duration_ms=elapsed,
        )

    async def evaluate_batch(self, samples: List[EvalSample]) -> List[EvalReport]:
        reports = []
        for sample in samples:
            try:
                reports.append(await self.evaluate_sample(sample))
            except Exception:
                pass
        return reports

    async def _ragas_score(self, question: str, answer: str, contexts: List[str], ground_truth: str) -> EvalMetrics:
        import os as _os

        from ragas import evaluate, EvaluationDataset
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from ragas.llms import LangchainLLMWrapper

        _api_key = _os.getenv("AIPLAT_LLM_API_KEY") or _os.getenv("DEEPSEEK_API_KEY", "")
        _base_url = _os.getenv("AIPLAT_LLM_BASE_URL", "https://api.deepseek.com/v1")
        _model = _os.getenv("AIPLAT_LLM_MODEL", "deepseek-chat")

        _wrapped_llm = None
        if _api_key:
            try:
                _llm = _DeepSeekChatOpenAI._get_cls()(model=_model, api_key=_api_key, base_url=_base_url, temperature=0.0, n=1)
                _wrapped_llm = LangchainLLMWrapper(_llm)
            except ImportError:
                pass

        # Use local sentence-transformers model for embeddings (avoids OpenAI API dependency)
        _embeddings = _get_or_create_local_embeddings()

        ds = EvaluationDataset.from_list([{
            "user_input": question,
            "response": answer,
            "retrieved_contexts": contexts,
            "reference": ground_truth,
        }])

        _metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
        if _wrapped_llm:
            for m in _metrics:
                if hasattr(m, 'llm'):
                    m.llm = _wrapped_llm

        _kwargs: dict = {"dataset": ds, "metrics": _metrics}
        if _embeddings:
            _kwargs["embeddings"] = _embeddings

        # Run evaluate in a thread to avoid uvloop incompatibility with nest_asyncio
        import concurrent.futures, functools
        _fn = functools.partial(evaluate, **{**_kwargs, "raise_exceptions": True})
        loop = __import__('asyncio').get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = await loop.run_in_executor(pool, _fn)
        df = result.to_pandas()
        return EvalMetrics(
            faithfulness=float(df.get("faithfulness", [0.0])[0] if "faithfulness" in df else 0),
            answer_relevancy=float(df.get("answer_relevancy", [0.0])[0] if "answer_relevancy" in df else 0),
            context_precision=float(df.get("context_precision", [0.0])[0] if "context_precision" in df else 0),
            context_recall=float(df.get("context_recall", [0.0])[0] if "context_recall" in df else 0),
        )

    def _simple_score(self, question: str, answer: str, contexts: List[str], ground_truth: str) -> EvalMetrics:
        """Simple token-overlap scoring when ragas is unavailable."""
        import re as _re
        q_tokens = set(_re.findall(r'[\u4e00-\u9fff]{2,4}', question.lower()))
        gt_tokens = set(_re.findall(r'[\u4e00-\u9fff]{2,4}', ground_truth.lower()))
        ans_tokens = set(_re.findall(r'[\u4e00-\u9fff]{2,4}', answer.lower()))
        ctx_text = " ".join(contexts).lower()
        return EvalMetrics(
            faithfulness=len(ans_tokens & set(ctx_text)) / max(1, len(ans_tokens)) if ans_tokens else 0.5,
            answer_relevancy=len(ans_tokens & q_tokens) / max(1, len(ans_tokens)) if ans_tokens else 0.5,
            context_precision=sum(1 for c in contexts if any(t in c.lower() for t in q_tokens)) / max(1, len(contexts)),
            context_recall=len(gt_tokens & set(ctx_text)) / max(1, len(gt_tokens)) if gt_tokens else 0.5,
        )


def _classify_failure(metrics: EvalMetrics, contexts: List[str]) -> str:
    if not contexts:
        return "检索为空"
    if metrics.context_precision < 0.4 or metrics.context_recall < 0.4:
        return "检索失效"
    if metrics.faithfulness < 0.5 and len(contexts) > 0:
        return "生成失效"
    if metrics.answer_relevancy < 0.3:
        return "答案无关"
    return "ok"


# ── Global singleton ──
_evaluator: Optional[RagEvaluator] = None


def get_rag_evaluator() -> RagEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = RagEvaluator()
    return _evaluator
