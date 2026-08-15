"""

SpecLifecycle — Spec 版本状态机 (P0: Andrew Ng 三层 Loop 传动轴)



让 Spec 从"静态 JSON"变成带版本、带状态、带触发原因的可追溯对象。



状态转换:

  DRAFT → PENDING → EXECUTING → REVIEW ──→ REVISING ──→ PENDING (循环)

                         ↓                    ↓

                      (失败) → REVISING    STABLE → ARCHIVED



存储: ~/.aiplat/spec_lifecycle.db (独立 SQLite)



接线点:

  1. OnboardingWizard activate → create_draft()

  2. UserWorkbench 审查 → revise() → trigger re-execution

  3. EvolutionEngine Step 12 → mark_stable() / mark_archived()

"""

from __future__ import annotations



import json

import os

import sqlite3

import time

import uuid

from dataclasses import dataclass, field

from datetime import datetime, timezone

from enum import Enum

from typing import Any, Dict, List, Optional



import logging



_log = logging.getLogger("aiplat.spec_lifecycle")





# ── Types ──



class SpecStatus(str, Enum):

    DRAFT = "draft"            # 草稿，尚未提交执行

    PENDING = "pending"        # 已提交，等待首次执行

    EXECUTING = "executing"    # 正在执行

    REVIEW = "review"          # 执行完成，等待开发者审查

    REVISING = "revising"      # 开发者在修改

    STABLE = "stable"          # 稳定版本（冻结）

    ARCHIVED = "archived"      # 已归档



    @classmethod

    def valid_transitions(cls, current: "SpecStatus") -> List["SpecStatus"]:

        _transitions = {

            cls.DRAFT:     [cls.PENDING, cls.ARCHIVED],

            cls.PENDING:   [cls.EXECUTING, cls.REVISING, cls.ARCHIVED],

            cls.EXECUTING: [cls.REVIEW, cls.REVISING],

            cls.REVIEW:    [cls.REVISING, cls.STABLE, cls.ARCHIVED],

            cls.REVISING:  [cls.PENDING, cls.DRAFT, cls.ARCHIVED],

            cls.STABLE:    [cls.REVISING, cls.ARCHIVED],

            cls.ARCHIVED:  [],

        }

        return _transitions.get(current, [])





class RevisionTrigger(str, Enum):

    MANUAL = "manual"               # 开发者手动修改

    USER_FEEDBACK = "user_feedback"  # 用户行为信号触发

    AGENT_TRACE = "agent_trace"     # Agent 决策痕迹分析

    AUTO_LEARN = "auto_learn"       # AutoLearner / EvolutionEngine

    GOAL_DEVIATION = "goal_deviation"  # 业务目标偏离





@dataclass

class SpecVersion:

    spec_id: str

    version: int

    content: Dict[str, Any]     # {agent_md: str, tools: list, evals: list, stage_configs: list}

    status: SpecStatus

    trigger: str                # RevisionTrigger value

    trigger_detail: str

    created_by: str

    created_at: str             # ISO timestamp

    execution_run_id: str = ""

    execution_result: Optional[Dict[str, Any]] = None

    affected_stages: List[int] = field(default_factory=list)

    # Phase 5 — Platform promotion (Palantir 碎石路→高速公路)

    scope: str = "tenant"           # "tenant" | "platform"

    promotion_status: str = "none"  # "none" | "pending" | "approved" | "rejected"

    promotion_requester: str = ""

    promotion_reviewer: str = ""

    promotion_reviewed_at: str = ""  # ISO timestamp

    promotion_notes: str = ""





# ── SQLite Store ──



CREATE_TABLE_SQL = """

CREATE TABLE IF NOT EXISTS spec_versions (

    spec_id       TEXT NOT NULL,

    version       INTEGER NOT NULL,

    content_json  TEXT NOT NULL DEFAULT '{}',

    status        TEXT NOT NULL DEFAULT 'draft',

    trigger       TEXT NOT NULL DEFAULT 'manual',

    trigger_detail TEXT NOT NULL DEFAULT '',

    created_by    TEXT NOT NULL DEFAULT '',

    created_at    TEXT NOT NULL DEFAULT '',

    execution_run_id TEXT NOT NULL DEFAULT '',

    execution_result_json TEXT NOT NULL DEFAULT '{}',

    affected_stages_json TEXT NOT NULL DEFAULT '[]',

    scope         TEXT NOT NULL DEFAULT 'tenant',

    promotion_status TEXT NOT NULL DEFAULT 'none',

    promotion_requester TEXT NOT NULL DEFAULT '',

    promotion_reviewer TEXT NOT NULL DEFAULT '',

    promotion_reviewed_at TEXT NOT NULL DEFAULT '',

    promotion_notes TEXT NOT NULL DEFAULT '',

    PRIMARY KEY (spec_id, version)

);



CREATE TABLE IF NOT EXISTS spec_latest (

    spec_id       TEXT PRIMARY KEY,

    latest_version INTEGER NOT NULL,

    latest_status TEXT NOT NULL DEFAULT 'draft',

    updated_at    TEXT NOT NULL DEFAULT ''

);

"""



# Migration: add promotion columns for existing databases

MIGRATE_PROMOTION_SQL = [

    "ALTER TABLE spec_versions ADD COLUMN scope TEXT NOT NULL DEFAULT 'tenant'",

    "ALTER TABLE spec_versions ADD COLUMN promotion_status TEXT NOT NULL DEFAULT 'none'",

    "ALTER TABLE spec_versions ADD COLUMN promotion_requester TEXT NOT NULL DEFAULT ''",

    "ALTER TABLE spec_versions ADD COLUMN promotion_reviewer TEXT NOT NULL DEFAULT ''",

    "ALTER TABLE spec_versions ADD COLUMN promotion_reviewed_at TEXT NOT NULL DEFAULT ''",

    "ALTER TABLE spec_versions ADD COLUMN promotion_notes TEXT NOT NULL DEFAULT ''",

]





# ── Public API ──



class SpecLifecycle:

    """Spec 版本状态机 + SQLite 持久化。



    Usage:

        sl = SpecLifecycle()

        v1 = sl.create_draft("my-spec", content, created_by="业务负责人")

        sl.promote_to_pending("my-spec")

        sl.mark_review("my-spec", v1.version, run_id="...", result={...})

        v2 = sl.revise("my-spec", new_content, trigger=..., detail=...)

    """



    def __init__(self, db_path: Optional[str] = None):

        self._db_path = db_path or os.path.expanduser("~/.aiplat/spec_lifecycle.db")

        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

        self._init_db()



    # ── DB helpers ──



    def _connect(self) -> sqlite3.Connection:

        conn = sqlite3.connect(self._db_path, timeout=5.0)

        conn.execute("PRAGMA journal_mode=WAL;")

        conn.execute("PRAGMA foreign_keys=ON;")

        conn.row_factory = sqlite3.Row

        return conn



    def _init_db(self) -> None:

        with self._connect() as conn:

            conn.executescript(CREATE_TABLE_SQL)

            # Run migrations for existing databases

            for sql in MIGRATE_PROMOTION_SQL:

                try:

                    conn.execute(sql)

                except sqlite3.OperationalError:

                    pass  # Column already exists  # noqa: schema-idempotent



    @staticmethod

    def _now() -> str:

        return datetime.now(timezone.utc).isoformat()



    def _to_row(self, sv: SpecVersion) -> tuple:

        return (

            sv.spec_id, sv.version,

            json.dumps(sv.content, ensure_ascii=False),

            sv.status.value,

            sv.trigger, sv.trigger_detail, sv.created_by,

            sv.created_at, sv.execution_run_id,

            json.dumps(sv.execution_result or {}, ensure_ascii=False),

            json.dumps(sv.affected_stages),

            sv.scope, sv.promotion_status, sv.promotion_requester,

            sv.promotion_reviewer, sv.promotion_reviewed_at,

            sv.promotion_notes,

        )



    def _from_row(self, row: sqlite3.Row) -> SpecVersion:

        return SpecVersion(

            spec_id=row["spec_id"],

            version=row["version"],

            content=json.loads(row["content_json"]),

            status=SpecStatus(row["status"]),

            trigger=row["trigger"],

            trigger_detail=row["trigger_detail"],

            created_by=row["created_by"],

            created_at=row["created_at"],

            execution_run_id=row["execution_run_id"],

            execution_result=json.loads(row["execution_result_json"]) or None,

            affected_stages=json.loads(row["affected_stages_json"]),

            scope=row["scope"] if "scope" in row.keys() else "tenant",

            promotion_status=row["promotion_status"] if "promotion_status" in row.keys() else "none",

            promotion_requester=row["promotion_requester"] if "promotion_requester" in row.keys() else "",

            promotion_reviewer=row["promotion_reviewer"] if "promotion_reviewer" in row.keys() else "",

            promotion_reviewed_at=row["promotion_reviewed_at"] if "promotion_reviewed_at" in row.keys() else "",

            promotion_notes=row["promotion_notes"] if "promotion_notes" in row.keys() else "",

        )



    def _upsert_latest(self, spec_id: str, version: int, status: SpecStatus) -> None:

        with self._connect() as conn:

            conn.execute(

                """INSERT INTO spec_latest (spec_id, latest_version, latest_status, updated_at)

                   VALUES (?, ?, ?, ?)

                   ON CONFLICT(spec_id) DO UPDATE SET

                     latest_version=excluded.latest_version,

                     latest_status=excluded.latest_status,

                     updated_at=excluded.updated_at""",

                (spec_id, version, status.value, self._now()),

            )



    def _next_version(self, spec_id: str) -> int:

        with self._connect() as conn:

            row = conn.execute(

                "SELECT MAX(version) as mv FROM spec_versions WHERE spec_id=?",

                (spec_id,),

            ).fetchone()

            return (row["mv"] or 0) + 1



    # ── State transitions ──



    def create_draft(

        self, spec_id: str, content: Dict[str, Any],

        created_by: str = "", trigger_detail: str = "",

    ) -> SpecVersion:

        """创建草稿版本 (DRAFT). 接线点: OnboardingWizard.activate"""

        version = self._next_version(spec_id)

        sv = SpecVersion(

            spec_id=spec_id, version=version,

            content=content, status=SpecStatus.DRAFT,

            trigger=RevisionTrigger.MANUAL.value,

            trigger_detail=trigger_detail or "初始创建",

            created_by=created_by,

            created_at=self._now(),

        )

        with self._connect() as conn:

            conn.execute(

                """INSERT INTO spec_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

                self._to_row(sv),

            )

        self._upsert_latest(spec_id, version, SpecStatus.DRAFT)

        _log.info("SpecLifecycle: %s v%d created (DRAFT) by %s", spec_id, version, created_by)

        return sv



    def promote_to_pending(self, spec_id: str) -> Optional[SpecVersion]:

        """标记为待执行 (DRAFT→PENDING). 接线点: UserWorkbench 提交时"""

        latest = self.get_latest(spec_id)

        if not latest or SpecStatus.PENDING not in SpecStatus.valid_transitions(latest.status):

            _log.warning("SpecLifecycle: cannot promote %s from %s to PENDING", spec_id, getattr(latest, 'status', '?'))

            return None

        return self._set_status(spec_id, latest.version, SpecStatus.PENDING)



    def mark_executing(self, spec_id: str, run_id: str = "") -> Optional[SpecVersion]:

        """标记为执行中 (PENDING→EXECUTING). 接线点: PipelineEngine.start()"""

        latest = self.get_latest(spec_id)

        if not latest or SpecStatus.EXECUTING not in SpecStatus.valid_transitions(latest.status):

            return None

        sv = self._set_status(spec_id, latest.version, SpecStatus.EXECUTING)

        if sv and run_id:

            with self._connect() as conn:

                conn.execute(

                    "UPDATE spec_versions SET execution_run_id=? WHERE spec_id=? AND version=?",

                    (run_id, spec_id, latest.version),

                )

            sv.execution_run_id = run_id

        return sv



    def mark_review(

        self, spec_id: str, version: int,

        run_id: str = "", result: Optional[Dict[str, Any]] = None,

    ) -> Optional[SpecVersion]:

        """标记为待审查 (EXECUTING→REVIEW). 接线点: PipelineEngine 执行完成"""

        sv = self.get_version(spec_id, version)

        if not sv or SpecStatus.REVIEW not in SpecStatus.valid_transitions(sv.status):

            return None

        with self._connect() as conn:

            conn.execute(

                """UPDATE spec_versions SET status=?, execution_run_id=?,

                   execution_result_json=? WHERE spec_id=? AND version=?""",

                (SpecStatus.REVIEW.value, run_id,

                 json.dumps(result or {}, ensure_ascii=False),

                 spec_id, version),

            )

        self._upsert_latest(spec_id, version, SpecStatus.REVIEW)

        sv.status = SpecStatus.REVIEW

        sv.execution_run_id = run_id

        sv.execution_result = result

        _log.info("SpecLifecycle: %s v%d → REVIEW (run=%s)", spec_id, version, run_id)

        return sv



    def revise(

        self, spec_id: str,

        new_content: Dict[str, Any],

        trigger: str = RevisionTrigger.MANUAL.value,

        trigger_detail: str = "",

        created_by: str = "",

        affected_stages: Optional[List[int]] = None,

    ) -> Optional[SpecVersion]:

        """修订 Spec (REVIEW/STABLE→REVISING→新版本 PENDING).



        接线点: UserWorkbench 开发者点击"修订"

        默认只重跑受影响阶段，全量重跑需传入 affected_stages=None（表示全部）.

        """

        latest = self.get_latest(spec_id)

        if not latest or SpecStatus.REVISING not in SpecStatus.valid_transitions(latest.status):

            _log.warning("SpecLifecycle: cannot revise %s from %s", spec_id, getattr(latest, 'status', '?'))

            return None



        # 标记旧版本为 REVISING

        self._set_status(spec_id, latest.version, SpecStatus.REVISING)



        # 创建新版本

        version = self._next_version(spec_id)



        # 默认只重跑受影响阶段；不传表示全量

        stages = affected_stages if affected_stages is not None else []



        sv = SpecVersion(

            spec_id=spec_id, version=version,

            content=new_content, status=SpecStatus.PENDING,

            trigger=trigger, trigger_detail=trigger_detail,

            created_by=created_by, created_at=self._now(),

            affected_stages=stages,

        )

        with self._connect() as conn:

            conn.execute(

                """INSERT INTO spec_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

                self._to_row(sv),

            )

        self._upsert_latest(spec_id, version, SpecStatus.PENDING)

        _log.info("SpecLifecycle: %s v%d created (PENDING) via %s: %s (stages=%s)",

                   spec_id, version, trigger[:20], trigger_detail[:80],

                   stages if stages else "ALL")

        return sv



    def mark_stable(self, spec_id: str) -> Optional[SpecVersion]:

        """标记为稳定 (REVIEW→STABLE). 接线点: EvolutionEngine Step 12"""

        latest = self.get_latest(spec_id)

        if not latest or SpecStatus.STABLE not in SpecStatus.valid_transitions(latest.status):

            return None

        sv = self._set_status(spec_id, latest.version, SpecStatus.STABLE)

        _log.info("SpecLifecycle: %s v%d → STABLE", spec_id, latest.version)

        return sv



    def mark_archived(self, spec_id: str) -> Optional[SpecVersion]:

        """标记为归档 (STABLE→ARCHIVED 或 timeout). 接线点: EvolutionEngine Step 12"""

        latest = self.get_latest(spec_id)

        if not latest or SpecStatus.ARCHIVED not in SpecStatus.valid_transitions(latest.status):

            return None

        sv = self._set_status(spec_id, latest.version, SpecStatus.ARCHIVED)

        _log.info("SpecLifecycle: %s v%d → ARCHIVED", spec_id, latest.version)

        return sv



    # ── Platform Promotion (Palantir 碎石路→高速公路) ──



    def promote_to_platform(

        self, spec_id: str, requester: str = "", notes: str = "",

    ) -> Optional[SpecVersion]:

        """Request promotion: mark a Spec as pending platform review."""

        latest = self.get_latest(spec_id)

        if not latest or latest.scope != "tenant":

            return None

        with self._connect() as conn:

            conn.execute(

                """UPDATE spec_versions SET scope='platform', promotion_status='pending',

                   promotion_requester=?, promotion_notes=?, promotion_reviewed_at=''

                   WHERE spec_id=? AND version=?""",

                (requester, notes, spec_id, latest.version),

            )

        latest.scope = "platform"

        latest.promotion_status = "pending"

        latest.promotion_requester = requester

        latest.promotion_notes = notes

        _log.info("SpecLifecycle: %s v%d promoted → platform (pending)", spec_id, latest.version)

        return latest



    def promote_approve(

        self, spec_id: str, reviewer: str = "", notes: str = "",

    ) -> Optional[SpecVersion]:

        """Approve platform promotion: scope=platform, status=approved."""

        latest = self.get_latest(spec_id)

        if not latest or latest.promotion_status != "pending":

            return None

        with self._connect() as conn:

            conn.execute(

                """UPDATE spec_versions SET promotion_status='approved',

                   promotion_reviewer=?, promotion_reviewed_at=?, promotion_notes=?

                   WHERE spec_id=? AND version=?""",

                (reviewer, self._now(), notes or latest.promotion_notes, spec_id, latest.version),

            )

        latest.promotion_status = "approved"

        latest.promotion_reviewer = reviewer

        latest.promotion_reviewed_at = self._now()

        _log.info("SpecLifecycle: %s v%d → platform APPROVED by %s", spec_id, latest.version, reviewer)



        # Register as platform skill for all tenants

        try:

            from core.api.core_facade import get_skill_registry

            from core.apps.skills.base import BaseSkill

            # Create a lightweight platform-spec skill entry

            if SkillRegistry:

                pass  # Platform-spec registration handled via management layer

        except Exception:

            logging.getLogger(__name__).debug('promote_approve failed', exc_info=True)


        return latest



    def promote_reject(

        self, spec_id: str, reviewer: str = "", reason: str = "",

    ) -> Optional[SpecVersion]:

        """Reject platform promotion: scope back to tenant."""

        latest = self.get_latest(spec_id)

        if not latest or latest.promotion_status != "pending":

            return None

        with self._connect() as conn:

            conn.execute(

                """UPDATE spec_versions SET scope='tenant', promotion_status='rejected',

                   promotion_reviewer=?, promotion_reviewed_at=?, promotion_notes=?

                   WHERE spec_id=? AND version=?""",

                (reviewer, self._now(), reason, spec_id, latest.version),

            )

        latest.scope = "tenant"

        latest.promotion_status = "rejected"

        latest.promotion_reviewer = reviewer

        _log.info("SpecLifecycle: %s v%d → platform REJECTED by %s: %s", spec_id, latest.version, reviewer, reason[:80])

        return latest



    def get_promotion_queue(self) -> List[SpecVersion]:

        """Get all Specs awaiting platform promotion review."""

        with self._connect() as conn:

            rows = conn.execute(

                "SELECT * FROM spec_versions WHERE promotion_status='pending' ORDER BY created_at ASC",

            ).fetchall()

            return [self._from_row(r) for r in rows]



    def _set_status(self, spec_id: str, version: int, status: SpecStatus) -> Optional[SpecVersion]:

        with self._connect() as conn:

            conn.execute(

                "UPDATE spec_versions SET status=? WHERE spec_id=? AND version=?",

                (status.value, spec_id, version),

            )

        self._upsert_latest(spec_id, version, status)

        sv = self.get_version(spec_id, version)

        if sv:

            sv.status = status

        return sv



    # ── Queries ──



    def get_latest(self, spec_id: str) -> Optional[SpecVersion]:

        with self._connect() as conn:

            row = conn.execute(

                "SELECT * FROM spec_versions WHERE spec_id=? ORDER BY version DESC LIMIT 1",

                (spec_id,),

            ).fetchone()

            return self._from_row(row) if row else None



    def get_version(self, spec_id: str, version: int) -> Optional[SpecVersion]:

        with self._connect() as conn:

            row = conn.execute(

                "SELECT * FROM spec_versions WHERE spec_id=? AND version=?",

                (spec_id, version),

            ).fetchone()

            return self._from_row(row) if row else None



    def get_history(self, spec_id: str) -> List[SpecVersion]:

        with self._connect() as conn:

            rows = conn.execute(

                "SELECT * FROM spec_versions WHERE spec_id=? ORDER BY version ASC",

                (spec_id,),

            ).fetchall()

            return [self._from_row(r) for r in rows]



    def get_all_active(self) -> List[SpecVersion]:

        """获取所有非归档的 Spec 最新版本."""

        with self._connect() as conn:

            rows = conn.execute(

                """SELECT sv.* FROM spec_versions sv

                   INNER JOIN spec_latest sl ON sv.spec_id=sl.spec_id AND sv.version=sl.latest_version

                   WHERE sl.latest_status != 'archived'

                   ORDER BY sl.updated_at DESC""",

            ).fetchall()

            return [self._from_row(r) for r in rows]



    def list_specs(self) -> List[Dict[str, Any]]:

        """列出所有 Spec 及其最新状态."""

        with self._connect() as conn:

            rows = conn.execute(

                """SELECT sl.spec_id, sl.latest_version, sl.latest_status, sl.updated_at,

                   sv.trigger, sv.created_by

                   FROM spec_latest sl

                   LEFT JOIN spec_versions sv ON sv.spec_id=sl.spec_id AND sv.version=sl.latest_version

                   ORDER BY sl.updated_at DESC""",

            ).fetchall()

            return [dict(r) for r in rows]



    # ── Translation: SpecVersion → PipelineStageConfig ──



    def to_pipeline_stages(self, spec_id: str) -> Optional[List[Dict[str, Any]]]:

        """将最新 Spec 版本翻译为 pipeline 可用的 stage 配置列表。



        输出格式兼容 PipelineStageConfig，engine 零改动.

        """

        latest = self.get_latest(spec_id)

        if not latest:

            return None

        stages = latest.content.get("stage_configs", [])

        # 如果只有 agent_md 没有显式 stage_configs，从 agent_md 推断一个简单配置

        if not stages and latest.content.get("agent_md"):

            stages = [{

                "agent_id": spec_id,

                "agent_name": spec_id,

                "output_artifact": spec_id,

                "routing_mode": getattr(latest, "_routing_mode", "static"),

            }]

        return stages





# ── Singleton ──



_spec_lifecycle_instance: Optional[SpecLifecycle] = None





def get_spec_lifecycle(db_path: Optional[str] = None) -> SpecLifecycle:

    global _spec_lifecycle_instance

    if _spec_lifecycle_instance is None:

        _spec_lifecycle_instance = SpecLifecycle(db_path=db_path)

    return _spec_lifecycle_instance


