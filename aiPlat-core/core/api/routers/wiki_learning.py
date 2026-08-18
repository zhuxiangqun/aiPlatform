"""
Learning Coach API (L6 — built-in AI Learning Coach).
"""

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

router = APIRouter(tags=["wiki-learning"])


class ProfileRequest(BaseModel):
    learner_id: str
    target_role: str = "ai_literate"
    current_level: str = "beginner"
    weekly_hours: int = 3
    prior_knowledge: List[str] = []
    interests: List[str] = []
    goals: str = ""


@router.post("/profile", response_model=Dict[str, Any])
async def create_learner_profile(req: ProfileRequest):
    """Create or update a learner profile."""
    from core.api.core_facade import (  # P0-A2: 经 CoreFacade
        LearnerProfile, TargetRole, CurrentLevel, save_learner_profile, load_learner_profile,
    )
    existing = load_learner_profile(req.learner_id)
    profile = LearnerProfile(
        learner_id=req.learner_id,
        current_level=CurrentLevel(req.current_level),
        target_role=TargetRole(req.target_role),
        weekly_hours=req.weekly_hours,
        prior_knowledge=req.prior_knowledge,
        interests=req.interests,
        goals=req.goals,
        created_at=existing.created_at if existing else "",
    )
    save_learner_profile(profile)
    return {"status": "ok", "profile": profile.to_dict()}


@router.get("/profile/{learner_id}", response_model=Dict[str, Any])
async def get_learner_profile(learner_id: str):
    """Get a learner profile."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")
    return profile.to_dict()


@router.get("/paths", response_model=Dict[str, Any])
async def list_learning_paths():
    """List all available learning paths with summaries."""
    from core.harness.knowledge.learning_paths import get_path_summary
    return {"paths": get_path_summary()}


@router.post("/start", response_model=Dict[str, Any])
async def start_learning_path(learner_id: str = Body(...), path_id: str = Body(...)):
    """Start a learning path. Returns the first chapter with content."""
    from core.harness.knowledge.learning_ontology import save_learner_profile
    from core.harness.knowledge.learning_ontology import load_learner_profile, save_learner_profile
    from core.harness.knowledge.learning_paths import get_path, get_chapter_body_sync

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    chapters = get_path(path_id)
    if not chapters:
        raise HTTPException(status_code=404, detail=f"Path '{path_id}' not found")

    profile.active_path_id = path_id
    profile.current_chapter_id = chapters[0].chapter_id
    save_learner_profile(profile)

    first = chapters[0]
    body = get_chapter_body_sync(first)
    return {
        "path_id": path_id, "chapter": first.to_dict(),
        "body": body, "total_chapters": len(chapters),
        "next": chapters[1].chapter_id if len(chapters) > 1 else None,
    }


@router.get("/chapter/{chapter_id}", response_model=Dict[str, Any])
async def get_chapter(chapter_id: str):
    """Get chapter content (cached body or skeleton)."""
    from core.harness.knowledge.learning_paths import get_chapter_body_sync
    from core.harness.knowledge.learning_paths import get_builtin_paths, get_chapter_body_sync
    paths = get_builtin_paths()
    for pid, chs in paths.items():
        for c in chs:
            if c.chapter_id == chapter_id:
                body = get_chapter_body_sync(c)
                return {"path_id": pid, "chapter": c.to_dict(), "body": body}
    raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")


@router.post("/chapter/{chapter_id}/compile", response_model=Dict[str, Any])
async def compile_chapter_body_endpoint(chapter_id: str):
    """Trigger AI compilation of chapter body text."""
    from core.harness.knowledge.learning_paths import compile_chapter_body
    from core.harness.knowledge.learning_paths import get_builtin_paths, compile_chapter_body
    paths = get_builtin_paths()
    for pid, chs in paths.items():
        for c in chs:
            if c.chapter_id == chapter_id:
                body = await compile_chapter_body(c, force=True)
                return {"chapter_id": chapter_id, "status": "compiled", "body_length": len(body)}
    raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")


@router.post("/chapter/{chapter_id}/complete", response_model=Dict[str, Any])
async def complete_chapter_endpoint(
    chapter_id: str,
    learner_id: str = Body(...),
    answers: List[Any] = Body(default=[]),
):
    """Submit answers for a chapter's exercises. Returns assessment results."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import get_builtin_paths
    from core.harness.knowledge.learning_assessment import complete_chapter

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    paths = get_builtin_paths()
    chapter = None
    for pid, chs in paths.items():
        for c in chs:
            if c.chapter_id == chapter_id:
                chapter = c
                break
    if not chapter:
        raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")

    result = await complete_chapter(profile, chapter, answers)
    return result


@router.get("/progress/{learner_id}", response_model=Dict[str, Any])
async def get_learning_progress(learner_id: str):
    """Get learning progress: completed chapters, scores, radar data."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import get_builtin_paths

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    paths = get_builtin_paths()
    path_chapters = paths.get(profile.active_path_id, [])

    total = len(path_chapters)
    completed = [c for c in profile.completed_chapters if c in {ch.chapter_id for ch in path_chapters}]

    radar = [
        {"chapter_id": c.chapter_id, "title": c.title,
         "mastery": profile.mastery_scores.get(c.chapter_id, 0),
         "completed": c.chapter_id in profile.completed_chapters}
        for c in path_chapters
    ]

    return {
        "learner_id": learner_id,
        "path_id": profile.active_path_id,
        "progress": f"{len(completed)}/{total}",
        "completion_pct": round(len(completed) / max(1, total) * 100, 1),
        "completed_chapters": completed,
        "current_chapter": profile.current_chapter_id,
        "radar": radar,
        "mastery_average": round(sum(profile.mastery_scores.values()) / max(1, len(profile.mastery_scores)), 1),
    }


@router.post("/ask", response_model=Dict[str, Any])
async def ask_learning_coach(
    learner_id: str = Body(...),
    question: str = Body(...),
):
    """Ask the AI Learning Coach a question, with learning context injected."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import _path_name
    from core.harness.knowledge.learning_paths import get_builtin_paths, _path_name

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    paths = get_builtin_paths()
    path_chapters = paths.get(profile.active_path_id, [])
    path_name = _path_name(profile.active_path_id) if profile.active_path_id else "未知路径"
    completed_names = [
        next((c.title for c in path_chapters if c.chapter_id == ch_id), ch_id)
        for ch_id in profile.completed_chapters
    ]

    context = (
        f"学生信息: 目标={profile.target_role.value}, 当前水平={profile.current_level.value}, "
        f"每周投入={profile.weekly_hours}小时。"
        f"正在学: {path_name}。"
        f"已完成: {len(completed_names)}/{len(path_chapters)} 章"
        + (f" ({', '.join(completed_names[-5:])})" if completed_names else "")
    )

    try:
        from core.api.core_facade import sys_llm_generate  # P0-A2: 经 CoreFacade
        from core.api.core_facade import _sync_resolve  # P0-A2: 经 CoreFacade
        prompt = _sync_resolve("learning-coach-chat",
            path_name=path_name, context=context, question=question)
        result = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        reply = result.get("content", "") if isinstance(result, dict) else str(result)
        return {"learner_id": learner_id, "reply": reply, "context": context}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendation/{learner_id}", response_model=Dict[str, Any])
async def get_learning_recommendation(learner_id: str):
    """Get recommended next learning action based on profile + gaps."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import get_builtin_paths

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    paths = get_builtin_paths()
    path_chapters = paths.get(profile.active_path_id, [])

    next_chapter = None
    recommendations = []
    for c in path_chapters:
        if c.chapter_id in profile.completed_chapters:
            continue
        prereq_met = all(p in profile.completed_chapters for p in c.prerequisites)
        if prereq_met and not next_chapter:
            next_chapter = c.chapter_id
        blocked = [p for p in c.prerequisites if p not in profile.completed_chapters]
        if blocked:
            rec = f"学习 '{c.title}' 之前，需要先完成: {', '.join(blocked[:3])}"
            recommendations.append(rec)

    return {
        "learner_id": learner_id,
        "next_chapter": next_chapter,
        "blocked_recommendations": recommendations,
        "weakest_areas": sorted(profile.mastery_scores.items(), key=lambda x: x[1])[:3],
    }
