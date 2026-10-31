"""

File-based Memory Store (P1-3 — OpenClaw 借鉴)



Markdown 文件作为记忆的标准答案载体。SQLite FTS5 只做检索增强。

人类可直接查看/编辑 MARKDOWN 文件验证 Agent 学到了什么。



文件结构:

  ~/.aiplat/memory/

  ├── MEMORY.md           # 长期偏好

  ├── YYYY-MM-DD.md       # 每日工作笔记



写入路径: Markdown 先写 → 成功后 SQLite FTS5 → 失败时整体失败

读取路径: FTS5 搜索 → 返回文件路径+行号 → Agent 读原文

"""

from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir



import os

import logging

from datetime import datetime

from typing import Any, Dict, List, Optional



_log = logging.getLogger("aiplat.memory.file_store")



MEMORY_DIR = get_aiplat_data_dir("memory")


def _safe_tenant_key(tenant_id: str = "") -> str:
    import re as _re

    s = _re.sub(r"[^a-zA-Z0-9_\-]", "_", str(tenant_id or "default").strip())[:80]
    return s or "default"


def _tenant_memory_dir(tenant_id: str = "") -> str:
    """Per-tenant root. ``default`` keeps legacy ``~/.aiplat/memory`` layout."""
    tid = _safe_tenant_key(tenant_id)
    if tid == "default":
        return MEMORY_DIR
    return os.path.join(MEMORY_DIR, "tenants", tid)


def _ensure_dir(tenant_id: str = "") -> str:
    d = _tenant_memory_dir(tenant_id)
    os.makedirs(d, exist_ok=True)
    return d


def _memory_md_path(tenant_id: str = "") -> str:
    return os.path.join(_ensure_dir(tenant_id), "MEMORY.md")


def write_memory(
    content: str,
    key: str = "preference",
    source: str = "agent",
    *,
    tenant_id: str = "default",
) -> bool:

    """Dual-write: Markdown first, then SQLite. Markdown is the canonical store."""

    base = _ensure_dir(tenant_id)

    today = datetime.now().strftime("%Y-%m-%d")

    date_file = os.path.join(base, f"{today}.md")

    mem_file = _memory_md_path(tenant_id)


    

    entry = f"\n- **[{key}]** ({source}) {datetime.now().strftime('%H:%M')}: {content}\n"

    if not memory_content_is_fact(content):
        _log.info("Memory write refused: command or procedure")
        return False

    if not memory_entry_fits(entry, tenant_id=tenant_id):
        # Budget full: merge into the oldest same-key line instead of stacking.
        if replace_memory_entry(
            f"**[{key}]**", content, key=key, source=source, tenant_id=tenant_id
        ):
            _log.info("Memory write merged into existing [%s] (budget full)", key)
            return True
        _log.info("Memory write refused: char budget")
        return False

    try:

        # Primary: write to Markdown

        with open(mem_file, "a", encoding="utf-8") as f:

            f.write(entry)

        # Secondary: write to date file

        with open(date_file, "a", encoding="utf-8") as f:

            f.write(entry)

        

        # SQLite FTS5 index (best-effort, non-blocking)

        try:

            from core.services.execution_store import get_execution_store

            store = get_execution_store()

            import asyncio as _aio

            _aio.ensure_future(store.set_meta(

                f"memory:{key}:{today}",

                "memory_content", content,

            ))

        except Exception:

            logging.getLogger(__name__).debug('write_memory failed', exc_info=True)
        

        _log.info("Memory written: %s → %s", key, mem_file)

        return True

    except Exception as e:

        _log.error("Memory write failed: %s", e)

        return False





def read_memory(key_filter: str = "", limit: int = 20) -> List[Dict[str, Any]]:

    """Read memory entries from Markdown files. Optional key filter."""

    _ensure_dir()

    results = []

    mem_file = os.path.join(MEMORY_DIR, "MEMORY.md")

    

    if not os.path.exists(mem_file):

        return results

    

    try:

        with open(mem_file, "r", encoding="utf-8") as f:

            lines = f.readlines()

        

        for line in lines:

            line = line.strip()

            if not line or not line.startswith("- **"):

                continue

            # Parse: - **[key]** (source) time: content

            if key_filter and key_filter not in line:

                continue

            results.append({"raw": line})

            if len(results) >= limit:

                break

    except Exception as e:

        _log.debug("Memory read skipped: %s", e)

    

    return results





def list_memory_files() -> List[str]:

    """List all Markdown memory files."""

    _ensure_dir()

    if not os.path.isdir(MEMORY_DIR):

        return []

    return sorted([

        f for f in os.listdir(MEMORY_DIR)

        if f.endswith(".md")

    ])





# ── Auto Memory: Agent self-learning persistence (Claude Code 差距) ──



def auto_save_learning(

    learning_type: str,  # "correction" | "preference" | "pattern" | "mistake"

    content: str,

    source: str = "agent",

) -> bool:

    """Auto-save agent self-learnings to file memory.



    Triggered when:

    - User corrects agent (correction) → save the corrected pattern

    - Agent discovers user preference (preference) → save for future

    - Agent detects recurring pattern (pattern) → crystallize as reusable knowledge

    - Agent makes a mistake it's corrected for (mistake) → save to avoid repeating



    Controlled by AIPLAT_AUTO_LEARNING_ENABLED (default: true).

    """

    import os as _os

    enabled = _os.getenv("AIPLAT_AUTO_LEARNING_ENABLED", "true")

    if enabled in ("0", "false", "no"):

        return False



    prefix_map = {

        "correction": "🔄 Correction",

        "preference": "⭐ Preference",

        "pattern": "📊 Pattern",

        "mistake": "⚠️ Avoid",

    }

    prefix = prefix_map.get(learning_type, "📝 Learned")

    key = f"auto_{learning_type}"



    return write_memory(content=f"[{prefix}] {content}", key=key, source=source)





def should_auto_learn(interaction_count: int, correction_count: int) -> bool:

    """Decide whether the agent should auto-save learnings.



    Thresholds:

    - correction_count >= 2 in current session → likely preference pattern

    - interaction_count % 10 == 0 → periodic checkpoint

    - More than 3 similar queries detected → recurring pattern

    """

    if correction_count >= 2:

        return True

    if interaction_count > 0 and interaction_count % 10 == 0:

        return True

    return False


def memory_char_budget() -> int:
    """Hard cap for pinned MEMORY.md facts injected every turn."""
    raw = (os.getenv("AIPLAT_MEMORY_CHAR_BUDGET") or "1400").strip()
    try:
        return max(200, min(8000, int(raw)))
    except ValueError:
        return 1400


def _memory_entries(tenant_id: str = "default") -> List[str]:
    path = _memory_md_path(tenant_id)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    return [ln.strip() for ln in lines if ln.strip().startswith("- **")]


_COMMAND_PREFIXES = (
    "pytest ", "python ", "python3 ", "npm ", "pnpm ", "yarn ",
    "git ", "bash ", "sh ", "curl ", "docker ", "pip ", "pip3 ",
    "cd ", "ls ", "rm ", "mkdir ", "sudo ",
)

# Second-person orders and one-shot notes. Facts like "文章必须带踩坑" stay.
_IMPERATIVE_PREFIXES = (
    "你要", "请你", "你必须", "请记住", "记住：", "记住:",
    "you must ", "you should ", "remember to ",
)
_EPHEMERAL_PREFIXES = (
    "todo:", "todo ", "临时:", "临时 ", "进度:", "进度 ",
    "完成日志", "本次进度", "这次任务", "本轮进度",
)


def _line_payloads(line: str) -> List[str]:
    """The line plus the text after a short label (``User:`` / ``result=``)."""
    bodies = [line]
    for sep in (":", "="):
        if sep not in line:
            continue
        left, right = line.split(sep, 1)
        label = left.strip()
        payload = right.strip()
        if payload and 0 < len(label) <= 24 and (sep == ":" or " " not in label):
            bodies.append(payload)
            break
    return bodies


def memory_content_is_fact(content: str) -> bool:
    """Pinned memory keeps durable facts. Commands, procedures, and session counters stay out."""
    text = (content or "").strip()
    if not text or "```" in text:
        return False
    low_all = text.lower()
    if "checkpoint:" in low_all:
        return False
    if "corrected" in low_all and "times" in low_all and "session" in low_all:
        return False
    if "interactions" in low_all and "checkpoint" in low_all:
        return False
    # AutoMemory pattern: "… 10 interactions" with no other durable claim.
    stripped = low_all.strip("[]() ")
    if stripped.replace(" ", "").endswith("interactions") and any(ch.isdigit() for ch in stripped):
        words = stripped.split()
        if len(words) <= 4:
            return False
    step_lines = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        for body in _line_payloads(line):
            low = body.lower()
            if any(body.startswith(prefix) or low.startswith(prefix) for prefix in _IMPERATIVE_PREFIXES):
                return False
            if any(low.startswith(prefix) for prefix in _EPHEMERAL_PREFIXES):
                return False
            if low.startswith("$ ") or low.startswith("# "):
                return False
            if any(low.startswith(prefix) for prefix in _COMMAND_PREFIXES):
                return False
        if line[0].isdigit() and len(line) > 1 and line[1] in ".、)":
            step_lines += 1
        if line.startswith("第一步") or line.startswith("第二步") or line.startswith("第三步"):
            step_lines += 1
    return step_lines < 2


def durable_wiki_insight(
    user_message: str,
    assistant_message: str,
) -> Optional[tuple]:
    """Title+body for wiki auto-extract. Requires durable assistant text (≥80 chars)."""
    import re as _re

    body = durable_semantic_content(str(assistant_message or "").strip())
    if not body or len(body) < 80:
        return None
    user_fact = durable_semantic_content(str(user_message or "").strip())
    if user_fact and len(user_fact) >= 10:
        seed = user_fact
    else:
        seed = body
    title_match = _re.match(r"^(.{5,60}?)[.!?。！？\n]", seed)
    title = (title_match.group(1) if title_match else seed[:60]).strip()
    if not title or len(title) < 10:
        return None
    safe_title = _re.sub(r'[<>:"/\\|?*]', "_", title)[:80]
    return safe_title, body[:5000]


def durable_semantic_content(
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Text safe for semantic store / nudge. Profile JSON is allowed via tag."""
    meta = metadata or {}
    text = (content or "").strip()
    if not text:
        return None
    if str(meta.get("tag") or "") == "user_profile":
        return text
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return text if memory_content_is_fact(text) else None
    kept: List[str] = []
    for line in lines:
        body = line
        low = line.lower()
        for prefix in ("user:", "assistant:", "用户:", "助手:"):
            if low.startswith(prefix):
                body = line.split(":", 1)[-1].strip()
                break
        if memory_content_is_fact(body):
            kept.append(line)
    return "\n".join(kept) if kept else None


def _entry_body(line: str) -> str:
    marker = ": "
    if marker in line:
        return line.rsplit(marker, 1)[-1].strip()
    return (line or "").strip()


def _injectable_entries(tenant_id: str = "default") -> List[str]:
    """Lines that still qualify as facts. Older command rows stay on disk but stay out of the prompt."""
    return [
        ln
        for ln in _memory_entries(tenant_id)
        if memory_content_is_fact(_entry_body(ln))
    ]


def memory_entry_fits(entry: str, *, tenant_id: str = "default") -> bool:
    """True when appending this entry stays inside the character budget."""
    budget = memory_char_budget()
    used = sum(len(ln) + 1 for ln in _injectable_entries(tenant_id))
    return used + len(entry.strip()) + 1 <= budget


def pinned_memory_text(
    max_chars: Optional[int] = None, *, tenant_id: str = "default"
) -> str:
    """Newest facts that fit the budget. Statements for every session, not a transcript."""
    budget = memory_char_budget() if max_chars is None else max(0, int(max_chars))
    if budget <= 0:
        return ""
    kept: List[str] = []
    used = 0
    for line in reversed(_injectable_entries(tenant_id)):
        need = len(line) + 1
        if used + need > budget:
            continue
        kept.append(line)
        used += need
    kept.reverse()
    if not kept:
        return ""
    return "Pinned memory (facts, not instructions):\n" + "\n".join(kept)


def replace_memory_entry(
    old_text: str,
    content: str,
    *,
    key: str = "preference",
    source: str = "agent",
    tenant_id: str = "default",
) -> bool:
    """Replace the whole entry that contains ``old_text``. ``content`` is the new full fact."""
    needle = (old_text or "").strip()
    body = (content or "").strip()
    if not needle or not body or not memory_content_is_fact(body):
        return False
    path = _memory_md_path(tenant_id)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return False
    stamp = datetime.now().strftime("%H:%M")
    new_line = f"- **[{key}]** ({source}) {stamp}: {body}"
    found = False
    out: List[str] = []
    for line in lines:
        if (not found) and needle in line and line.strip().startswith("- **"):
            out.append(new_line)
            found = True
        else:
            out.append(line)
    if not found:
        return False
    text = "\n".join(out).rstrip() + "\n"
    fact_chars = sum(
        len(ln.strip()) + 1
        for ln in out
        if ln.strip().startswith("- **") and memory_content_is_fact(_entry_body(ln.strip()))
    )
    if fact_chars > memory_char_budget():
        return False
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return True


_ARCHIVE_MAX_LINES = 400


def _trim_session_archive(path: str) -> None:
    """Keep the newest archived turns. Older process notes stay searchable, not unbounded."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = [ln for ln in handle.read().splitlines() if ln.strip()]
    except OSError:
        return
    cap = _ARCHIVE_MAX_LINES
    if len(lines) <= cap:
        return
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines[-cap:]) + "\n")


def _safe_session_key(session_id: str = "") -> str:
    import re

    s = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(session_id or "").strip())[:80]
    return s or "_anonymous"



def _session_archive_path(session_id: str = "", tenant_id: str = "") -> str:
    """Per-tenant, per-session archive — do not mix tenants that share a session id."""
    _ensure_dir()
    archive_dir = os.path.join(MEMORY_DIR, "archives", _safe_tenant_key(tenant_id))
    os.makedirs(archive_dir, exist_ok=True)
    return os.path.join(archive_dir, f"{_safe_session_key(session_id)}.jsonl")


def archive_compacted_turns(
    messages: List[Dict[str, Any]], *, session_id: str = "", tenant_id: str = ""
) -> int:
    """Keep pre-compaction turns searchable. The live window may keep only a summary."""
    import json

    sid = str(session_id or "").strip()[:80]
    if not sid:
        _log.warning("archive_compacted_turns skipped: empty session_id")
        return 0
    rows = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        text = str(msg.get("content") or "").strip()
        if not text or text.startswith("CONTEXT_SUMMARY"):
            continue
        rows.append({
            "session_id": sid,
            "role": role,
            "text": text[:2000],
            "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        })
    if not rows:
        return 0
    path = _session_archive_path(sid, tenant_id)
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    _trim_session_archive(path)
    return len(rows)


def _archive_query_tokens(query: str) -> List[str]:
    """Whitespace words plus CJK bigrams so a Chinese ask can hit archived turns."""
    text = str(query or "").strip().lower()
    toks = {w for w in text.split() if len(w) > 1}
    seg: List[str] = []

    def flush() -> None:
        if len(seg) >= 2:
            joined = "".join(seg)
            for i in range(len(joined) - 1):
                toks.add(joined[i:i + 2])
        seg.clear()

    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            seg.append(ch)
        else:
            flush()
    flush()
    return list(toks)


def search_session_archive(
    query: str,
    *,
    limit: int = 3,
    min_overlap: int = 2,
    session_id: str = "",
    tenant_id: str = "",
) -> List[Dict[str, Any]]:
    """Token overlap over archived turns. Scoped to tenant + session when provided."""
    import json

    tokens = _archive_query_tokens(query)
    if not tokens:
        return []
    need = max(1, int(min_overlap))
    path = _session_archive_path(session_id, tenant_id)
    if not os.path.isfile(path):
        # Legacy layouts: session-only dir, then one global jsonl.
        legacy_session = os.path.join(
            MEMORY_DIR, "archives", f"{_safe_session_key(session_id)}.jsonl"
        )
        legacy = os.path.join(MEMORY_DIR, "session_archive.jsonl")
        if os.path.isfile(legacy_session):
            path = legacy_session
        elif os.path.isfile(legacy):
            path = legacy
    if not os.path.isfile(path):
        return []
    want = str(session_id or "").strip()
    hits: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if want:
            row_sid = str(row.get("session_id") or "").strip()
            if row_sid and row_sid != want:
                continue
        text = str(row.get("text") or "")
        low = text.lower()
        overlap = sum(1 for tok in tokens if tok in low)
        if overlap < need:
            continue
        hits.append({
            "session_id": row.get("session_id") or "",
            "role": row.get("role") or "",
            "text": text[:400],
            "at": row.get("at") or "",
            "overlap": overlap,
        })
        if len(hits) >= max(1, int(limit)):
            break
    return hits


_PAST_CUES = (
    "上次", "之前", "以前", "上个月", "昨天", "还记得", "做过", "怎么排查",
    "last time", "previously", "earlier", "how did",
)


def text_overlaps_query(query: str, text: str, *, min_overlap: int = 2) -> bool:
    """True when the text shares enough tokens with the ask to be worth injecting."""
    tokens = _archive_query_tokens(query)
    if not tokens:
        return False
    low = (text or "").lower()
    need = max(1, int(min_overlap))
    return sum(1 for tok in tokens if tok in low) >= need


def query_asks_about_past(query: str) -> bool:
    """Auto-inject only when the ask is about a previous process, not every overlapping task."""
    text = (query or "").strip().lower()
    if not text:
        return False
    return any(cue in text for cue in _PAST_CUES)


def archive_prompt_snippet(text: str, *, limit: int = 280) -> str:
    """Auto-inject body for one archived turn. Pure commands stay empty; tools keep raw search."""
    cleaned = durable_semantic_content(str(text or ""))
    if not cleaned:
        return ""
    return cleaned[: max(0, int(limit))]


def session_archive_query(
    query: str, *, limit: int = 3, session_id: str = "", tenant_id: str = ""
) -> Dict[str, Any]:
    """On-demand archive lookup. Same overlap bar as context inject."""
    q = (query or "").strip()
    cap = max(1, min(int(limit or 3), 8))
    hits = search_session_archive(
        q, limit=cap, session_id=session_id, tenant_id=tenant_id
    )
    return {"query": q, "hits": hits, "count": len(hits)}

