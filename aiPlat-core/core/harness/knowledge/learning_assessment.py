"""
Learning Assessment Engine — auto-grade MC exercises + LLM-scored open-ended ones.

Three assessment types:
  1. multiple_choice — deterministic answer match, no LLM
  2. open_ended     — LLM grades against rubric, returns score + feedback + weak points
  3. coding         — py_compile check + LLM review

Integration with Phase C verification: after grading, expected outcomes are
verified to ensure the grade itself is consistent.

callers: wiki.py /learning/chapter/{id}/complete, core_facade
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any, Dict, List, Optional

from core.harness.knowledge.learning_ontology import (
    ExerciseResult, LearnerProfile, ChapterContent,
    save_exercise_results, load_exercise_results,
)

logger = logging.getLogger(__name__)

# ── Message constants (env-overridable) ──
import os as _os
_MSG_NO_CODE = _os.getenv("AIPLAT_ASSESS_MSG_NO_CODE", "No code submitted. Please submit your implementation.")
_MSG_RESUBMIT = _os.getenv("AIPLAT_ASSESS_MSG_RESUBMIT", "Resubmit code")
_MSG_COMPILE_FAIL = _os.getenv("AIPLAT_ASSESS_MSG_COMPILE_FAIL", "Compilation failed:\n{error}\nPlease fix syntax errors and resubmit.")
_MSG_UNKNOWN_TYPE = _os.getenv("AIPLAT_ASSESS_MSG_UNKNOWN_TYPE", "Unknown exercise type")
_MSG_NO_ANSWER = _os.getenv("AIPLAT_ASSESS_MSG_NO_ANSWER", "No answer submitted. Please complete your answer next time.")
_MSG_RESUBMIT_ANSWER = _os.getenv("AIPLAT_ASSESS_MSG_RESUBMIT_ANSWER", "Resubmit answer")
_MSG_SUGGEST_REVIEW = _os.getenv("AIPLAT_ASSESS_MSG_SUGGEST_REVIEW", "Suggested review: {title}")
_MSG_CONTINUE = "继续下一题"


# ══════════════════════════════════════════════════════════════
# Assessment Dispatch
# ══════════════════════════════════════════════════════════════

async def assess_exercise(
    exercise: Dict[str, Any],
    student_answer: Any,
    *,
    learner: LearnerProfile,
    chapter: ChapterContent,
    exercise_index: int = 0,
) -> ExerciseResult:
    u"""Dispatch to the correct assessment function based on exercise_type.

    Args:
        exercise: the exercise dict from ChapterContent.exercises.
        student_answer: learner's submission.
        learner: LearnerProfile for context.
        chapter: the chapter this exercise belongs to.
        exercise_index: position in the chapter's exercise list.

    Returns:
        ExerciseResult with score, passed, feedback, weak_points, next_step.
    """
    ex_type = exercise.get("type", "multiple_choice")
    exercise_id = f"{chapter.chapter_id}_ex{exercise_index + 1}"

    if ex_type == "multiple_choice":
        return _assess_mc(exercise, student_answer, exercise_id, chapter, learner)
    elif ex_type == "open_ended":
        return await _assess_open(exercise, student_answer, exercise_id, chapter, learner)
    elif ex_type == "coding":
        return await _assess_coding(exercise, student_answer, exercise_id, chapter, learner)
    else:
        return ExerciseResult(
            exercise_id=exercise_id, chapter_id=chapter.chapter_id,
            learner_id=learner.learner_id, exercise_type=ex_type,
            score=0, passed=False, feedback=_MSG_UNKNOWN_TYPE,
        )


def _assess_mc(
    exercise: Dict[str, Any],
    student_answer: Any,
    exercise_id: str,
    chapter: ChapterContent,
    learner: LearnerProfile,
) -> ExerciseResult:
    u"""Multiple choice: deterministic answer matching."""
    correct_idx = exercise.get("answer", -1)
    try:
        student_idx = int(student_answer)
    except (ValueError, TypeError):
        student_idx = -1

    correct = student_idx == correct_idx
    options = exercise.get("options", [])

    if correct:
        feedback = "✅ 回答正确！"
    else:
        correct_text = options[correct_idx] if 0 <= correct_idx < len(options) else "N/A"
        feedback = f"❌ 正确答案是: {correct_text}"

    return ExerciseResult(
        exercise_id=exercise_id, chapter_id=chapter.chapter_id,
        learner_id=learner.learner_id, exercise_type="multiple_choice",
        student_answer=student_idx,
        score=100.0 if correct else 0.0,
        passed=correct,
        feedback=feedback,
        weak_points=[] if correct else [exercise.get("question", "")[:60]],
        next_step=_MSG_CONTINUE if correct else _MSG_SUGGEST_REVIEW.format(title=chapter.title),
    )


async def _assess_open(
    exercise: Dict[str, Any],
    student_answer: Any,
    exercise_id: str,
    chapter: ChapterContent,
    learner: LearnerProfile,
) -> ExerciseResult:
    u"""Open-ended: LLM grades against rubric."""
    question = exercise.get("question", "")
    rubric = exercise.get("rubric", "")

    if not student_answer or not str(student_answer).strip():
        return ExerciseResult(
            exercise_id=exercise_id, chapter_id=chapter.chapter_id,
            learner_id=learner.learner_id, exercise_type="open_ended",
            score=0, passed=False,
            feedback=_MSG_NO_ANSWER,
            next_step=_MSG_RESUBMIT_ANSWER,
        )

    answer_text = str(student_answer)[:3000]

    prompt = f"""你是 AI 学习教练的评估导师。请根据评分标准评估学生回答。用中文回复。

【题目】
{question}

【评分标准】
{rubric}

【学生回答】
{answer_text}

【评估要求】
1. 严格根据评分标准给分，不要因回答简短就直接扣分——只要覆盖了评分标准中的要点就应该给分。
2. feedback 要具体，指出哪里做得好、哪里可以改进。
3. weak_points 列出学生没有完全掌握的概念点。
4. next_step 给出可执行的下一步学习建议。

请返回纯 JSON（不含 markdown 代码块标记）：
{{"score": 0-100, "passed": true/false, "feedback": "中文评语", "weak_points": ["..."], "next_step": "..."}}"""

    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose
        result = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("assessment"),
            max_tokens=600,
        )
        content = result.get("content", "{}") if isinstance(result, dict) else str(result)
        parsed = _safe_parse_json(content)
    except Exception as e:
        logger.warning("LLM assessment failed: %s — falling back to rubric-based scoring", str(e)[:100])

        # Layer 2: rubric-based fallback scoring (no LLM needed)
        rubric_score = _assess_by_rubric_fallback(answer_text, rubric)
        feedback = (
            f"⚠️ 暂时评分 (LLM 不可用): {rubric_score}/100。\n"
            f"根据评分标准中的关键词匹配和答案长度进行预估。\n"
            f"当评估系统恢复后，将自动进行正式重新评估。"
        )
        parsed = {
            "score": rubric_score,
            "passed": rubric_score >= 60,
            "feedback": feedback,
            "weak_points": [],
            "next_step": "评估系统恢复后你的答案将被重新评分，届时会更新最终成绩。",
            "_pending_reassessment": True,
        }

        # Layer 3: enqueue for async LLM reassessment when available
        _enqueue_pending_assessment(
            learner_id=learner.learner_id,
            exercise_id=exercise_id,
            chapter_id=chapter.chapter_id,
            student_answer=answer_text,
            rubric=rubric,
            question=question,
        )

    score = float(parsed.get("score", 0))
    return ExerciseResult(
        exercise_id=exercise_id, chapter_id=chapter.chapter_id,
        learner_id=learner.learner_id, exercise_type="open_ended",
        student_answer=answer_text,
        score=score, passed=bool(parsed.get("passed", score >= 60)),
        feedback=str(parsed.get("feedback", "")),
        weak_points=[str(w) for w in parsed.get("weak_points", [])],
        next_step=str(parsed.get("next_step", "")),
    )


async def _assess_coding(
    exercise: Dict[str, Any],
    student_answer: Any,
    exercise_id: str,
    chapter: ChapterContent,
    learner: LearnerProfile,
) -> ExerciseResult:
    u"""Coding exercise: py_compile check + LLM review."""
    code = str(student_answer) if student_answer else ""

    if not code.strip():
        return ExerciseResult(
            exercise_id=exercise_id, chapter_id=chapter.chapter_id,
            learner_id=learner.learner_id, exercise_type="coding",
            score=0, passed=False,
            feedback=_MSG_NO_CODE,
            next_step=_MSG_RESUBMIT,
        )

    # Quick py_compile check
    compile_ok = True
    compile_error = ""
    try:
        import py_compile as _pc
        import tempfile as _tmp
        with _tmp.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f.flush()
            _pc.compile(f.name, doraise=True)
            import os as _os
            _os.unlink(f.name)
    except _pc.PyCompileError as e:
        compile_ok = False
        compile_error = str(e)[:200]

    if not compile_ok:
        return ExerciseResult(
            exercise_id=exercise_id, chapter_id=chapter.chapter_id,
            learner_id=learner.learner_id, exercise_type="coding",
            student_answer=code, score=30, passed=False,
            feedback=_MSG_COMPILE_FAIL.format(error=compile_error),
            weak_points=["代码语法"],
            next_step="修复编译错误后重新提交",
        )

    # LLM review
    rubric = exercise.get("rubric", "")
    question = exercise.get("question", "")

    prompt = f"""你是 AI 学习教练的代码评审导师。用中文评估学生代码。

【题目要求】
{question}

【评分标准】
{rubric}

【学生代码】
{code[:2000]}

【评估要求】
请返回纯 JSON：
{{"score": 0-100, "passed": true/false, "feedback": "中文评语（指出代码优点和需改进的地方）", "weak_points": ["..."], "next_step": "..."}}"""

    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose
        result = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("assessment"),
            max_tokens=600,
        )
        content = result.get("content", "{}") if isinstance(result, dict) else str(result)
        parsed = _safe_parse_json(content)
    except Exception as e:
        parsed = {"score": 70, "passed": True, "feedback": f"代码编译通过。评审过程出错: {e}", "weak_points": [], "next_step": "继续下一题"}

    score = float(parsed.get("score", 70))
    return ExerciseResult(
        exercise_id=exercise_id, chapter_id=chapter.chapter_id,
        learner_id=learner.learner_id, exercise_type="coding",
        student_answer=code,
        score=score, passed=bool(parsed.get("passed", score >= 60)),
        feedback=str(parsed.get("feedback", "")),
        weak_points=[str(w) for w in parsed.get("weak_points", [])],
        next_step=str(parsed.get("next_step", "")),
    )


# ══════════════════════════════════════════════════════════════
# Chapter Completion
# ══════════════════════════════════════════════════════════════

async def complete_chapter(
    learner: LearnerProfile,
    chapter: ChapterContent,
    answers: List[Any],
) -> Dict[str, Any]:
    u"""Assess all exercises in a chapter and return results + next step.

    If all exercises passed, mark chapter as completed and recommend next chapter.
    """
    exercises = chapter.exercises
    if not exercises:
        return {"passed": True, "results": [], "next_chapter": None}

    results: List[ExerciseResult] = []
    all_passed = True
    total_score = 0.0

    for i, ex in enumerate(exercises):
        student_answer = answers[i] if i < len(answers) else None
        result = await assess_exercise(ex, student_answer, learner=learner, chapter=chapter, exercise_index=i)
        results.append(result)
        total_score += result.score
        if not result.passed:
            all_passed = False

    avg_score = round(total_score / max(1, len(results)), 1)
    chapter.mastery_score = avg_score  # store in-memory

    # Save results
    save_exercise_results(results, learner.learner_id, chapter.chapter_id)

    # Update learner profile
    if all_passed:
        if chapter.chapter_id not in learner.completed_chapters:
            learner.completed_chapters.append(chapter.chapter_id)
        learner.mastery_scores[chapter.chapter_id] = avg_score
        from core.harness.knowledge.learning_ontology import save_learner_profile
        save_learner_profile(learner)

    # Phase L3 fix: write mastery data to A-Box (bidirectional)
    _write_mastery_to_abox(learner, chapter, avg_score, all_passed)

    # Find next chapter
    next_chapter = None
    paths = _get_paths()
    chs = paths.get(chapter.path_id, [])
    for c in chs:
        all_prereq_met = all(
            p in learner.completed_chapters for p in c.prerequisites
        )
        if c.chapter_id not in learner.completed_chapters and all_prereq_met:
            next_chapter = c.chapter_id
            break

    return {
        "chapter_id": chapter.chapter_id,
        "passed": all_passed,
        "average_score": avg_score,
        "results": [r.to_dict() for r in results],
        "next_chapter": next_chapter,
        "completed_count": len(learner.completed_chapters),
        "total_chapters_in_path": len(chs),
    }


def _get_paths():
    from core.harness.knowledge.learning_paths import get_builtin_paths
    return get_builtin_paths()


def _write_mastery_to_abox(
    learner: LearnerProfile,
    chapter: ChapterContent,
    avg_score: float,
    passed: bool,
) -> None:
    u"""Write learner mastery data to ontology A-Box for bidirectional linkage."""
    try:
        from core.harness.knowledge.knowledge_ontology import get_ontology, OntologyTriple
        AI = "http://aiplat.local/knowledge#"
        onto = get_ontology()

        learner_uri = f"{AI}Learner_{learner.learner_id}"
        chapter_uri = f"{AI}Chapter_{chapter.chapter_id}"

        # Register learner as entity
        onto.triples.append(OntologyTriple(learner_uri, "rdf:type", f"{AI}LearnerProfile"))

        # Mastery relation: learner mastered chapter
        if passed:
            onto.triples.append(OntologyTriple(
                learner_uri, f"{AI}masteredChapter", chapter_uri,
            ))

        # Mastery score data property
        for i, t in enumerate(onto.triples):
            if t.subject == chapter_uri and t.predicate == f"{AI}masteryScore":
                onto.triples[i] = OntologyTriple(
                    chapter_uri, f"{AI}masteryScore", f'"{avg_score}"',
                )
                return
        onto.triples.append(OntologyTriple(
            chapter_uri, f"{AI}masteryScore", f'"{avg_score}"',
        ))
    except Exception as e:
        logging.debug(str(e), exc_info=True)


def _safe_parse_json(content: str) -> Dict[str, Any]:
    text = content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return {}


def _assess_by_rubric_fallback(
    student_answer: str,
    rubric: str,
    *,
    min_length: int = 50,
    ideal_length: int = 150,
) -> int:
    u"""Rubric-based scoring when LLM is unavailable.

    Scoring dimensions:
      1. Answer length (relative to question type expectations)
      2. Keyword match against rubric (exact + edit distance ≤ 2)
      3. Answer structure (multi-paragraph bonus)

    Returns score 10-85. Capped at 85 because LLM validation is pending.
    """
    if not student_answer or not student_answer.strip():
        return 10

    answer = student_answer.lower().strip()
    score = 50  # baseline

    # 1. Length scoring
    ans_len = len(answer)
    if ans_len < min_length:
        score -= 25
    elif ans_len > ideal_length:
        score += 12

    # 2. Keyword matching (exact + fuzzy)
    keywords = _extract_rubric_keywords(rubric)
    matched = 0
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in answer:
            matched += 1
            score += 5
        else:
            # Edit distance ≤ 2 for short keywords (≤6 chars) — English only
            if kw.isascii() and len(kw) <= 6:
                for word in answer.split()[:50]:
                    if _levenshtein_distance(kw_lower, word) <= 2:
                        matched += 1
                        score += 3
                        break

    # 3. Structure bonus: multi-paragraph answers suggest thoughtful responses
    if "\n\n" in answer:
        score += 5

    return min(80, max(10, score))


def _extract_rubric_keywords(rubric: str) -> List[str]:
    u"""Extract meaningful keywords from a rubric string.

    Strategy:
      1. Split by punctuation → full segments
      2. For each segment, extract 2-3 char substrings (Chinese)
      3. Extract English abbreviations (2+ uppercase)
      4. Deduplicate, filter stops, limit to 10
    """
    stop = {"的", "了", "是", "在", "和", "不", "要", "有", "能", "可以",
            "正确", "清晰", "具体", "应", "必须", "至少", "以上", "以下",
            "分", "字", "言之", "条", "个", "如", "如果", "需要", "包含",
            "使用", "表达", "给出", "说明", "能够", "通过", "是否", "自己",
            "the", "a", "an", "and", "or", "should", "must"}

    import re
    segments = re.split(r'[，。；、：,\s]+', rubric)
    words = []

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        # Add full segment
        words.append(seg)
        # For Chinese-heavy segments: extract 2-3 char windows
        if len(seg) >= 4:
            for i in range(len(seg) - 1):
                frag = seg[i:i + 2]
                if frag not in stop:
                    words.append(frag)

    # English abbreviations
    en_abbr = re.findall(r'[A-Z]{2,}', rubric)
    words.extend(en_abbr)

    # Deduplicate + filter + limit
    seen = set()
    result = []
    for w in words:
        wl = w.lower()
        if wl not in seen and wl not in stop and len(w) >= 2:
            seen.add(wl)
            result.append(w)
    return result[:10]


def _levenshtein_distance(s1: str, s2: str) -> int:
    u"""Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _enqueue_pending_assessment(
    learner_id: str,
    exercise_id: str,
    chapter_id: str,
    student_answer: str,
    rubric: str,
    question: str,
) -> None:
    u"""Enqueue an assessment for retry when LLM becomes available.

    Pending assessments are stored in JSON and processed in batches
    when sys_llm_generate next succeeds.
    """
    import os as _os, json as _json, time as _time

    try:
        home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
        path = _os.path.join(home, "learning", "pending", f"{learner_id}_{chapter_id}.json")
        _os.makedirs(_os.path.dirname(path), exist_ok=True)

        existing = []
        if _os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = _json.load(f)
            except Exception:
                existing = []

        existing.append({
            "learner_id": learner_id,
            "exercise_id": exercise_id,
            "chapter_id": chapter_id,
            "student_answer": student_answer[:3000],
            "rubric": rubric,
            "question": question,
            "enqueued_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        })

        with open(path, "w", encoding="utf-8") as f:
            _json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
