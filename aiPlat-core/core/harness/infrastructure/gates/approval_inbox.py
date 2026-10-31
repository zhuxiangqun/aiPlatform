"""Unattended approval Inbox — OpenWorker-inspired durable wait queue.

Attendance is orthogonal to the autonomy ceiling (ApprovalGate / RiskClass):

* ``attended`` — prompts stay inline (visibility=inline); not listed in Inbox.
* ``inbox``    — nobody watching: park for cross-session Inbox; agent must wait.
* ``auto``     — fixed least-destructive answers; **hard floors are never self-approved**.

This module is the park/resolve store. PolicyGate calls ``park_if_unattended`` when
returning APPROVAL_REQUIRED. Daemon / cron paths should set attendance to ``inbox``
or ``auto`` and must call ``refuse_unattended_self_approve`` before any auto path.
"""
from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

ATTENDED = "attended"
INBOX = "inbox"
AUTO = "auto"
ATTENDANCE_VALUES = (ATTENDED, INBOX, AUTO)

VIS_INLINE = "inline"
VIS_INBOX = "inbox"

STATE_PENDING = "pending"
STATE_RESOLVED = "resolved"

KIND_APPROVAL = "approval"
KIND_QUESTION = "question"

# Fixed auto-mode replies (never model-authored).
AUTO_HARD_FLOOR_DENY = (
    "No operator available; hard-floor action refused. Restart attended to approve."
)
AUTO_QUESTION_ANSWER = (
    "No one is available. Choose the least destructive option that still satisfies "
    "the task as written."
)


def normalize_attendance(value: object) -> str:
    if isinstance(value, bool):
        return INBOX if value else ATTENDED
    text = str(value or "").strip().lower()
    if text in ("true", "on", "unattended"):
        return INBOX
    return text if text in ATTENDANCE_VALUES else ATTENDED


@dataclass
class InboxItem:
    id: str
    session_id: str
    kind: str
    title: str
    body: str = ""
    state: str = STATE_PENDING
    resolution: Optional[str] = None  # allow / deny / always / free text
    visibility: str = VIS_INBOX
    hard_floor: bool = False
    tool_name: str = ""
    tool_call_id: Optional[str] = None
    risk_class: Optional[str] = None
    approval_source: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolved_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "InboxItem":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        data = {k: v for k, v in raw.items() if k in known}
        return cls(**data)


def _default_store_path() -> Path:
    home = get_aiplat_home()
    override = os.environ.get("AIPLAT_APPROVAL_INBOX_FILE")
    if override:
        return Path(override).expanduser()
    return Path(home) / "approval_inbox.json"


class ApprovalInboxStore:
    """JSON-backed durable wait queue (daemon-safe, process-local lock)."""

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path else _default_store_path()
        self._lock = threading.RLock()
        self._attendance: Dict[str, str] = {}
        self._items: Dict[str, InboxItem] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            _log.warning("approval_inbox load failed: %s", e, exc_info=True)
            return
        if not isinstance(raw, dict):
            return
        for sid, mode in dict(raw.get("attendance") or {}).items():
            self._attendance[str(sid)] = normalize_attendance(mode)
        for row in list(raw.get("items") or []):
            if not isinstance(row, dict):
                continue
            try:
                item = InboxItem.from_dict(row)
                self._items[item.id] = item
            except Exception as e:
                _log.debug("skip corrupt inbox item: %s", e, exc_info=True)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "attendance": dict(self._attendance),
            "items": [it.to_dict() for it in self._items.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def set_attendance(self, session_id: str, mode: object) -> str:
        sid = str(session_id or "").strip() or "default"
        norm = normalize_attendance(mode)
        with self._lock:
            self._attendance[sid] = norm
            self._save()
        return norm

    def get_attendance(self, session_id: str) -> str:
        sid = str(session_id or "").strip() or "default"
        with self._lock:
            return normalize_attendance(self._attendance.get(sid, ATTENDED))

    def park(
        self,
        *,
        session_id: str,
        kind: str = KIND_APPROVAL,
        title: str,
        body: str = "",
        hard_floor: bool = False,
        tool_name: str = "",
        tool_call_id: Optional[str] = None,
        risk_class: Optional[str] = None,
        approval_source: Optional[str] = None,
        visibility: Optional[str] = None,
    ) -> InboxItem:
        sid = str(session_id or "").strip() or "default"
        attendance = self.get_attendance(sid)
        vis = visibility or (VIS_INBOX if attendance in (INBOX, AUTO) else VIS_INLINE)

        # Idempotent by (session_id, tool_call_id) while pending.
        with self._lock:
            if tool_call_id:
                for existing in self._items.values():
                    if (
                        existing.session_id == sid
                        and existing.tool_call_id == tool_call_id
                        and existing.state == STATE_PENDING
                    ):
                        return existing

            item = InboxItem(
                id=str(uuid.uuid4()),
                session_id=sid,
                kind=kind or KIND_APPROVAL,
                title=title or "Approval required",
                body=body or "",
                visibility=vis,
                hard_floor=bool(hard_floor),
                tool_name=tool_name or "",
                tool_call_id=tool_call_id,
                risk_class=risk_class,
                approval_source=approval_source,
            )
            self._items[item.id] = item

            # AUTO attendance: resolve immediately with fixed policy.
            if attendance == AUTO:
                self._auto_resolve_locked(item)

            self._save()
            return item

    def _auto_resolve_locked(self, item: InboxItem) -> None:
        if item.state != STATE_PENDING:
            return
        if item.kind == KIND_APPROVAL:
            # Hard floors + any approval card: refuse when nobody is present.
            item.resolution = "deny"
            item.body = (item.body + "\n" if item.body else "") + AUTO_HARD_FLOOR_DENY
        else:
            item.resolution = AUTO_QUESTION_ANSWER
        item.state = STATE_RESOLVED
        item.resolved_at = time.time()
        item.resolved_by = "auto"

    def resolve(
        self,
        item_id: str,
        resolution: str,
        *,
        resolved_by: str = "",
    ) -> Optional[InboxItem]:
        """First-responder wins; subsequent resolves are no-ops returning the same item."""
        with self._lock:
            item = self._items.get(str(item_id))
            if item is None:
                return None
            if item.state == STATE_RESOLVED:
                return item
            item.resolution = str(resolution or "")
            item.state = STATE_RESOLVED
            item.resolved_at = time.time()
            item.resolved_by = str(resolved_by or "")
            self._save()
            return item

    def get(self, item_id: str) -> Optional[InboxItem]:
        with self._lock:
            return self._items.get(str(item_id))

    def list_items(
        self,
        *,
        visibility: Optional[str] = VIS_INBOX,
        pending_only: bool = True,
        session_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            rows = list(self._items.values())
        if session_id:
            rows = [r for r in rows if r.session_id == session_id]
        if visibility:
            rows = [r for r in rows if r.visibility == visibility]
        if pending_only:
            rows = [r for r in rows if r.state == STATE_PENDING]
        rows.sort(key=lambda r: r.created_at)
        return [r.to_dict() for r in rows[: max(1, int(limit))]]


_store: Optional[ApprovalInboxStore] = None
_store_lock = threading.Lock()


def get_approval_inbox() -> ApprovalInboxStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = ApprovalInboxStore()
        return _store


def _reset_approval_inbox() -> None:
    """Test helper — drop singleton (does not delete file unless tests set path)."""
    global _store
    with _store_lock:
        _store = None


def refuse_unattended_self_approve(
    *,
    hard_floor: bool,
    attendance: object,
    auto_approve: bool = False,
) -> bool:
    """Return True when caller must NOT auto-approve (park / deny instead).

    Daemon and cron paths: pass attendance=inbox|auto. Hard floors always refuse
    self-approve under inbox/auto; auto_approve alone never clears a hard floor.
    """
    mode = normalize_attendance(attendance)
    if hard_floor and (mode in (INBOX, AUTO) or auto_approve):
        return True
    if mode == AUTO:
        # Auto mode never self-approves consequential actions.
        return True
    if mode == INBOX and auto_approve:
        return True
    return False


def park_if_unattended(
    *,
    session_id: str,
    title: str,
    body: str = "",
    hard_floor: bool = False,
    tool_name: str = "",
    tool_call_id: Optional[str] = None,
    risk_class: Optional[str] = None,
    approval_source: Optional[str] = None,
    attendance_override: Optional[object] = None,
) -> Optional[InboxItem]:
    """Park when session attendance is inbox/auto (or override). Attended → None."""
    store = get_approval_inbox()
    if attendance_override is not None:
        store.set_attendance(session_id, attendance_override)
    mode = store.get_attendance(session_id)
    if mode == ATTENDED:
        return None
    return store.park(
        session_id=session_id,
        kind=KIND_APPROVAL,
        title=title,
        body=body,
        hard_floor=hard_floor,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        risk_class=risk_class,
        approval_source=approval_source,
    )
