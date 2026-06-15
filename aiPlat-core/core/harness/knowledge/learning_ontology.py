"""
Learning Domain Ontology — T-Box definitions for the AI Learning Coach.

Extends the core knowledge ontology with learning-specific classes:
  - LearningPath:     structured curriculum (ai_engineer / ai_product / ai_literacy)
  - SkillNode:        a teachable skill within a path
  - Chapter:          a chapter containing concepts + materials + exercises
  - Material:         study resources (readings, external links, videos)
  - Exercise:         assessment tasks (multiple_choice, open_ended, coding)
  - Assessment:       LLM evaluation result for an exercise submission
  - Milestone:        a checkpoint at which a learner demonstrates mastery
  - CapstoneProject:  final integrative project assembling all chapters

LearnerProfile: captures current level, target role, time budget, prior knowledge.

Design: T-Box in knowledge_ontology.py CLASSES, data models here.
AI-generated chapter content is stored as KnowledgeAtom + WikiPage.

callers: learning_paths.py, learning_assessment.py, core_facade.py, wiki.py
"""

from __future__ import annotations

import json as _json
import os as _os
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

AI = "http://aiplat.local/knowledge#"


# ══════════════════════════════════════════════════════════════
# Learner Profile
# ══════════════════════════════════════════════════════════════

class TargetRole(str, Enum):
    AI_ENGINEER = "ai_engineer"
    AI_DECISION_MAKER = "ai_decision_maker"
    AI_LITERATE = "ai_literate"


class CurrentLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


@dataclass
class LearnerProfile:
    learner_id: str
    current_level: CurrentLevel = CurrentLevel.BEGINNER
    target_role: TargetRole = TargetRole.AI_LITERATE
    weekly_hours: int = 3
    prior_knowledge: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    goals: str = ""

    active_path_id: str = ""
    current_chapter_id: str = ""
    completed_chapters: List[str] = field(default_factory=list)
    mastery_scores: Dict[str, float] = field(default_factory=dict)

    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "learner_id": self.learner_id,
            "current_level": self.current_level.value,
            "target_role": self.target_role.value,
            "weekly_hours": self.weekly_hours,
            "prior_knowledge": self.prior_knowledge,
            "interests": self.interests,
            "goals": self.goals,
            "active_path_id": self.active_path_id,
            "current_chapter_id": self.current_chapter_id,
            "completed_chapters": self.completed_chapters,
            "mastery_scores": self.mastery_scores,
            "created_at": self.created_at or _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "updated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LearnerProfile":
        return cls(
            learner_id=d.get("learner_id", ""),
            current_level=CurrentLevel(d.get("current_level", "beginner")),
            target_role=TargetRole(d.get("target_role", "ai_literate")),
            weekly_hours=int(d.get("weekly_hours", 3)),
            prior_knowledge=d.get("prior_knowledge", []),
            interests=d.get("interests", []),
            goals=d.get("goals", ""),
            active_path_id=d.get("active_path_id", ""),
            current_chapter_id=d.get("current_chapter_id", ""),
            completed_chapters=d.get("completed_chapters", []),
            mastery_scores=d.get("mastery_scores", {}),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


# ══════════════════════════════════════════════════════════════
# Chapter Data Model (content — A-Box population)
# ══════════════════════════════════════════════════════════════

@dataclass
class ChapterContent:
    chapter_id: str
    title: str                         # e.g. "第1章: Prompt 工程基础"
    path_id: str                       # which learning path this belongs to
    order: int = 0
    estimated_minutes: int = 60
    prerequisites: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)

    status: str = "draft"              # draft | published | deprecated

    materials: List[Dict[str, str]] = field(default_factory=list)
    exercises: List[Dict[str, Any]] = field(default_factory=list)
    mini_project: Dict[str, str] = field(default_factory=dict)

    ai_generated_body: str = ""        # LLM-compiled chapter text (cached)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "title": self.title,
            "path_id": self.path_id,
            "order": self.order,
            "estimated_minutes": self.estimated_minutes,
            "prerequisites": self.prerequisites,
            "concepts": self.concepts,
            "status": self.status,
            "materials": self.materials,
            "exercises": self.exercises,
            "mini_project": dict(self.mini_project),
            "ai_generated_body": self.ai_generated_body[:500] + "..." if len(self.ai_generated_body) > 500 else self.ai_generated_body,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChapterContent":
        return cls(
            chapter_id=d.get("chapter_id", ""),
            title=d.get("title", ""),
            path_id=d.get("path_id", ""),
            order=int(d.get("order", 0)),
            estimated_minutes=int(d.get("estimated_minutes", 60)),
            prerequisites=d.get("prerequisites", []),
            concepts=d.get("concepts", []),
            status=d.get("status", "draft"),
            materials=d.get("materials", []),
            exercises=d.get("exercises", []),
            mini_project=d.get("mini_project", {}),
            ai_generated_body=d.get("ai_generated_body", ""),
        )


@dataclass
class ExerciseResult:
    exercise_id: str
    chapter_id: str
    learner_id: str
    exercise_type: str                # multiple_choice | open_ended | coding
    student_answer: Any = None
    score: float = 0.0
    passed: bool = False
    feedback: str = ""
    weak_points: List[str] = field(default_factory=list)
    next_step: str = ""
    submitted_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exercise_id": self.exercise_id,
            "chapter_id": self.chapter_id,
            "learner_id": self.learner_id,
            "exercise_type": self.exercise_type,
            "student_answer": self.student_answer,
            "score": round(self.score, 1),
            "passed": self.passed,
            "feedback": self.feedback,
            "weak_points": self.weak_points,
            "next_step": self.next_step,
            "submitted_at": self.submitted_at or _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        }


# ══════════════════════════════════════════════════════════════
# Storage Helpers
# ══════════════════════════════════════════════════════════════

def _learning_dir() -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "learning")


def _profile_path(learner_id: str) -> str:
    return _os.path.join(_learning_dir(), "profiles", f"{learner_id}.json")


def _chapter_content_path(chapter_id: str) -> str:
    return _os.path.join(_learning_dir(), "chapters", "generated", f"{chapter_id}.json")


def _exercise_results_path(learner_id: str, chapter_id: str) -> str:
    return _os.path.join(_learning_dir(), "results", learner_id, f"{chapter_id}.json")


def save_learner_profile(profile: LearnerProfile) -> None:
    path = _profile_path(profile.learner_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))


def load_learner_profile(learner_id: str) -> Optional[LearnerProfile]:
    path = _profile_path(learner_id)
    if not _os.path.exists(path):
        return None
    try:
        return LearnerProfile.from_dict(_json.load(open(path, "r", encoding="utf-8")))
    except Exception:
        return None


def save_chapter_content(chapter: ChapterContent) -> None:
    path = _chapter_content_path(chapter.chapter_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_json.dumps(chapter.to_dict(), ensure_ascii=False, indent=2))


def load_chapter_content(chapter_id: str) -> Optional[ChapterContent]:
    path = _chapter_content_path(chapter_id)
    if not _os.path.exists(path):
        return None
    try:
        return ChapterContent.from_dict(_json.load(open(path, "r", encoding="utf-8")))
    except Exception:
        return None


def save_exercise_results(results: List[ExerciseResult], learner_id: str, chapter_id: str) -> None:
    path = _exercise_results_path(learner_id, chapter_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump([r.to_dict() for r in results], f, ensure_ascii=False, indent=2)


def load_exercise_results(learner_id: str, chapter_id: str) -> List[ExerciseResult]:
    path = _exercise_results_path(learner_id, chapter_id)
    if not _os.path.exists(path):
        return []
    try:
        data = _json.load(open(path, "r", encoding="utf-8"))
        return [ExerciseResult(**r) for r in data]
    except Exception:
        return []
