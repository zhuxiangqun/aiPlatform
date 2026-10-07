"""Personal notes for 小朱 — user-editable file, not wiki/semantic RAG.

Tenant isolation (G9):
  non-default → ~/.aiplat/memory/tenants/{tenant_id}/xiaozhu.md
  default     → prefer tenants/default/…；若无文件则回退旧路径 memory/xiaozhu.md
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

_log = logging.getLogger("aiplat.digital_human.personal")
_SECRET = re.compile(r"(api[_-]?key|secret|password|token|sk-[a-z0-9]{8,})", re.I)
_SAFE_TENANT = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# 显式嘱咐（优先入库）。身份词勿放这里，否则「我在做什么」会被误存
_REMEMBER = (
    "记住",
    "请记住",
    "以后都",
    "下次都",
    "从今以后",
    "我希望你",
    "我喜欢你",
    "我习惯",
    "不要再",
    "别再",
    "我偏好",
    "帮我记住",
    "对我来说",
    "我更想",
)

# Bare「我是」易误存（我是想/我是说…）；身份句须无问句词才自动记
_IDENTITY = ("我叫", "请叫我", "我负责", "我们团队", "我司")
_QUESTION = (
    "怎么",
    "吗",
    "？",
    "?",
    "哪些",
    "什么",
    "为何",
    "为什么",
    "能否",
    "是否",
    "该不该",
    "有没有",
    "做成",
    "做一个",
)
_PAGE = ("这个画面", "这个页面", "审核结果", "当前页")
_FEEDBACK = ("讲得对", "不对", "应该是", "你说错", "纠正")
_SHORT_STYLE = ("精简", "太长", "太啰嗦", "简单点", "短一点", "少说两句")
_STYLE_LINE = "偏好：回答先结论、尽量短，不要套模板。"


def sanitize_tenant_id(tenant_id: Optional[str]) -> str:
    tid = str(tenant_id or "").strip() or "default"
    if not _SAFE_TENANT.match(tid):
        return "default"
    return tid


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _legacy_memory_path() -> Path:
    return _aiplat_home() / "memory" / "xiaozhu.md"


def _tenant_memory_path(tenant_id: str) -> Path:
    return _aiplat_home() / "memory" / "tenants" / tenant_id / "xiaozhu.md"


def memory_path(tenant_id: Optional[str] = None, *, for_write: bool = False) -> Path:
    """Resolve notes path for tenant.

    Read: default may fall back to legacy ``memory/xiaozhu.md``.
    Write: always ``memory/tenants/{tid}/xiaozhu.md``; first default write
    copies legacy content once so old notes are not stranded.
    """
    tid = sanitize_tenant_id(tenant_id)
    tenant_path = _tenant_memory_path(tid)
    if tid != "default":
        return tenant_path
    legacy = _legacy_memory_path()
    if for_write:
        if not tenant_path.is_file() and legacy.is_file():
            try:
                tenant_path.parent.mkdir(parents=True, exist_ok=True)
                tenant_path.write_text(
                    legacy.read_text(encoding="utf-8"), encoding="utf-8"
                )
            except OSError:
                _log.debug("xiaozhu memory migrate skipped", exc_info=True)
        return tenant_path
    if tenant_path.is_file() or not legacy.is_file():
        return tenant_path
    return legacy


def _contains_secret(text: str) -> bool:
    return bool(_SECRET.search(text or ""))


def looks_like_lasting_note(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 4 or len(t) > 400:
        return False
    if _contains_secret(t) or any(k in t for k in _PAGE):
        return False
    if any(k in t for k in _FEEDBACK):
        return False
    # 显式「记住」优先；身份句不含问句词才自动记（去掉易误触的「我是」）
    if any(k in t for k in _REMEMBER):
        return True
    if any(k in t for k in _QUESTION):
        return False
    if any(k in t for k in _IDENTITY):
        return True
    return False


def looks_like_short_style(text: str) -> bool:
    t = (text or "").strip()
    if not t or _contains_secret(t):
        return False
    return any(k in t for k in _SHORT_STYLE)


def load_personal_notes(
    *,
    tenant_id: Optional[str] = None,
    max_chars: int = 1800,
) -> str:
    path = memory_path(tenant_id)
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not raw:
        return ""
    if len(raw) > max_chars:
        raw = raw[-max_chars:]
        nl = raw.find("\n")
        if nl > 0:
            raw = raw[nl + 1 :]
    tid = sanitize_tenant_id(tenant_id)
    return (
        f"=== 关于你（个人笔记 tenant={tid}，可手改）===\n"
        "口吻、称呼、偏好、未竟事项用这里。平台有没有某资产仍以简报/当前页为准。\n"
        + raw
    )


def _append_line(line: str, *, tenant_id: Optional[str] = None) -> bool:
    path = memory_path(tenant_id, for_write=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = line.strip()
    if not body:
        return False
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if body in existing[-6000:]:
            return False
        with path.open("a", encoding="utf-8") as fh:
            if not existing:
                fh.write("# 小朱个人笔记（主人可直接编辑）\n\n")
            fh.write(body + "\n")
        return True
    except OSError:
        return False


def remember_from_user(text: str, *, tenant_id: Optional[str] = None) -> bool:
    t = (text or "").strip()
    if not looks_like_lasting_note(t):
        return False
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return _append_line(f"- ({stamp}) {t}", tenant_id=tenant_id)


def remember_style_pref(text: str, *, tenant_id: Optional[str] = None) -> bool:
    if not looks_like_short_style(text):
        return False
    path = memory_path(tenant_id)
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        existing = ""
    if _STYLE_LINE in existing:
        return False
    stamp = datetime.now().strftime("%Y-%m-%d")
    return _append_line(f"- ({stamp}) {_STYLE_LINE}", tenant_id=tenant_id)


def remember_from_turn(
    user_text: str,
    assistant_text: str = "",
    *,
    tenant_id: Optional[str] = None,
) -> bool:
    """Grow notes from explicit 记住, identity, and repeated style — not from page audit."""
    del assistant_text  # reserved; do not store model dumps as biography
    wrote = remember_from_user(user_text, tenant_id=tenant_id)
    wrote = remember_style_pref(user_text, tenant_id=tenant_id) or wrote
    return wrote
