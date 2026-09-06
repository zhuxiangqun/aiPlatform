"""PRD quality gate — pack-driven checks + repairs (zero LLM).

Pack locations (later wins):
  - core/harness/execution/prd_gate_packs/  (kernel-only: _common)
  - core/workspace_seeds/prd_gates/        (vertical domains, e.g. media)
  - ~/.aiplat/prd_gates/                   (user overrides / extra domains)

Harness only interprets packs; do not hardcode vertical product rules here.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from core.harness.execution.prd_gate_loader import load_prd_gate_packs

# ── Text helpers ──────────────────────────────────────────────────────────────


def _prd_blob(prd: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("title", "description", "scope", "target_state"):
        v = prd.get(key)
        if v:
            parts.append(str(v))
    for fr in prd.get("functional_requirements") or []:
        if not isinstance(fr, dict):
            continue
        parts.append(str(fr.get("name") or ""))
        parts.append(str(fr.get("description") or ""))
        for ac in fr.get("acceptance_criteria") or []:
            parts.append(str(ac))
    for us in prd.get("user_stories") or []:
        if isinstance(us, dict):
            parts.append(str(us.get("story") or us.get("description") or us.get("name") or ""))
        else:
            parts.append(str(us))
    cons = prd.get("constraints")
    if isinstance(cons, dict):
        for v in cons.values():
            if isinstance(v, list):
                parts.extend(str(x) for x in v)
            elif v:
                parts.append(str(v))
    elif cons:
        parts.append(str(cons))
    dec = prd.get("decisions")
    if isinstance(dec, dict):
        for k, v in dec.items():
            parts.append(f"{k}={v}")
    oq = prd.get("open_questions")
    if isinstance(oq, list):
        parts.extend(str(x) for x in oq)
    return "\n".join(parts)


def _domain_blob(prd: Dict[str, Any]) -> str:
    """FR/US/title only — used for pack trigger matching (ignore auto constraints)."""
    parts: List[str] = []
    for key in ("title", "description", "scope"):
        v = prd.get(key)
        if v:
            parts.append(str(v))
    for fr in prd.get("functional_requirements") or []:
        if not isinstance(fr, dict):
            continue
        parts.append(str(fr.get("name") or ""))
        parts.append(str(fr.get("description") or ""))
        for ac in fr.get("acceptance_criteria") or []:
            parts.append(str(ac))
    for us in prd.get("user_stories") or []:
        if isinstance(us, dict):
            parts.append(str(us.get("story") or us.get("description") or us.get("name") or ""))
        else:
            parts.append(str(us))
    return "\n".join(parts)


def _issue(
    code: str,
    message: str,
    *,
    severity: str = "error",
    fr_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if fr_ids:
        out["fr_ids"] = fr_ids
    return out


def _decision_value(prd: Dict[str, Any], key: str) -> str:
    dec = prd.get("decisions")
    if isinstance(dec, dict) and dec.get(key) not in (None, ""):
        return str(dec.get(key)).strip()
    return ""


def _open_questions_list(prd: Dict[str, Any]) -> List[str]:
    oq = prd.get("open_questions")
    if isinstance(oq, list):
        return [str(x).strip() for x in oq if str(x).strip()]
    if isinstance(oq, str) and oq.strip():
        return [oq.strip()]
    return []


def _ensure_list_field(cons: Dict[str, Any], key: str) -> List[Any]:
    raw = cons.get(key)
    if isinstance(raw, list):
        return list(raw)
    if raw:
        return [raw]
    return []


# ── Constraint normalization ──────────────────────────────────────────────────

_SCOPE_LINE_RE = re.compile(
    r"^\s*[-*]?\s*(平台|性能|安全|其他|platform|performance|security|other)\s*[：:]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def normalize_constraints(prd: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure prd['constraints'] is a structured dict; lift bullets from scope when needed."""
    out = dict(prd)
    cons = out.get("constraints")
    if not isinstance(cons, dict):
        cons = {}
    else:
        cons = dict(cons)

    scope = str(out.get("scope") or "")
    if scope:
        key_map = {
            "平台": "platform", "platform": "platform",
            "性能": "performance", "performance": "performance",
            "安全": "security", "security": "security",
            "其他": "other", "other": "other",
        }
        for m in _SCOPE_LINE_RE.finditer(scope):
            raw_key, val = m.group(1), m.group(2).strip()
            canon = key_map.get(raw_key.lower() if raw_key.isascii() else raw_key, raw_key)
            if canon == "platform" and not cons.get("platform"):
                cons["platform"] = val
            elif canon in ("performance", "security", "other"):
                existing = cons.get(canon)
                items = list(existing) if isinstance(existing, list) else ([existing] if existing else [])
                if val and val not in items:
                    items.append(val)
                cons[canon] = items

    if "platform" not in cons and re.search(r"\bWeb\b|网页|前端", _prd_blob(out), re.I):
        cons.setdefault("platform", "Web")

    out["constraints"] = cons
    return out


# ── Pack matching / condition eval ────────────────────────────────────────────

_RE_CACHE: Dict[str, re.Pattern] = {}


def _re(pattern: str) -> re.Pattern:
    compiled = _RE_CACHE.get(pattern)
    if compiled is None:
        compiled = re.compile(pattern, re.IGNORECASE)
        _RE_CACHE[pattern] = compiled
    return compiled


def _pack_matches(pack: Dict[str, Any], domain_text: str) -> bool:
    if pack.get("always"):
        return True
    triggers = pack.get("triggers") or []
    if not triggers:
        return False
    for t in triggers:
        try:
            if _re(str(t)).search(domain_text):
                return True
        except re.error:
            if str(t).lower() in domain_text.lower():
                return True
    return False


def matched_domain_packs(prd: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = _domain_blob(prd)
    return [p for p in load_prd_gate_packs() if _pack_matches(p, text)]


def matched_packs_for_text(text: str) -> List[Dict[str, Any]]:
    """Match gate packs against free text (chat history / user requirement)."""
    blob = str(text or "")
    if not blob.strip():
        return [p for p in load_prd_gate_packs() if p.get("always")]
    return [p for p in load_prd_gate_packs() if _pack_matches(p, blob)]


def format_pm_gate_guidance(text: str, *, max_hints: int = 20) -> str:
    """Build generation-time constraints from matched packs' ``pm_hints``.

    Injected into PM chat *before* the model writes PRD_READY so drafts avoid
    domain contradictions, instead of relying only on post-hoc finalize wash.
    Domain-agnostic: hints live in YAML packs, not in Agent markdown.
    """
    packs = matched_packs_for_text(text)
    if not packs:
        return ""
    lines: List[str] = [
        "## PRD 域质量约束（生成前必须遵守）",
        "以下规则来自平台 PRD 质量门禁 pack；输出 Markdown PRD / `<!-- PRD_READY -->` 前必须满足。",
        "禁止输出会违反下列禁令的验收标准；相关产品边界写入「决策」节（英文 snake_case）。",
        "标记为 `block_finalize_wash` 的语义矛盾：事后洗绿**不会**放行，必须首稿写对。",
    ]
    seen: set = set()
    count = 0
    for pack in packs:
        hints = pack.get("pm_hints") or []
        if not isinstance(hints, list) or not hints:
            continue
        did = str(pack.get("domain_id") or "pack")
        lines.append(f"### {did}")
        for h in hints:
            tip = str(h or "").strip()
            if not tip or tip in seen:
                continue
            seen.add(tip)
            lines.append(f"- {tip}")
            count += 1
            if count >= max_hints:
                lines.append(
                    "**重要**：违反上述禁令时，`factory_finalize` 洗绿不可替代首稿；须按 GOOD 口径重写后再 `PRD_READY`。"
                )
                return "\n".join(lines)
    if count == 0:
        return ""
    lines.append(
        "**重要**：违反上述禁令时，`factory_finalize` 洗绿不可替代首稿；须按 GOOD 口径重写后再 `PRD_READY`。"
    )
    return "\n".join(lines)


def is_media_prd(prd: Dict[str, Any]) -> bool:
    """True when the workspace-seeded ``media`` pack triggers (not a core builtin)."""
    return any(p.get("domain_id") == "media" for p in matched_domain_packs(prd))


def _eval_cond(cond: Any, *, prd: Dict[str, Any], blob: str) -> bool:
    if cond is True or cond == {"always": True} or (isinstance(cond, dict) and cond.get("always") is True):
        return True
    if not isinstance(cond, dict):
        return False

    if "all" in cond:
        return all(_eval_cond(c, prd=prd, blob=blob) for c in (cond.get("all") or []))
    if "any" in cond:
        return any(_eval_cond(c, prd=prd, blob=blob) for c in (cond.get("any") or []))

    if "blob_match" in cond:
        return bool(_re(str(cond["blob_match"])).search(blob))
    if "not_blob_match" in cond:
        return not bool(_re(str(cond["not_blob_match"])).search(blob))
    if "not_decision" in cond:
        return not bool(_decision_value(prd, str(cond["not_decision"])))
    if "decision_in" in cond:
        spec = cond["decision_in"] or {}
        val = _decision_value(prd, str(spec.get("key") or "")).lower()
        values = [str(x).lower() for x in (spec.get("values") or [])]
        return val in values
    if "not_decision_in" in cond:
        spec = cond["not_decision_in"] or {}
        val = _decision_value(prd, str(spec.get("key") or "")).lower()
        values = [str(x).lower() for x in (spec.get("values") or [])]
        return val not in values
    if "not_constraint" in cond:
        cons = prd.get("constraints") if isinstance(prd.get("constraints"), dict) else {}
        key = str(cond["not_constraint"])
        return not bool(cons.get(key))
    return False


# ── AC mutation helpers ───────────────────────────────────────────────────────


def _annotate_fr_acs(prd: Dict[str, Any], match_re: re.Pattern, note: str) -> int:
    n = 0
    frs = prd.get("functional_requirements")
    if not isinstance(frs, list):
        return 0
    for fr in frs:
        if not isinstance(fr, dict):
            continue
        acs = fr.get("acceptance_criteria")
        if not isinstance(acs, list):
            continue
        new_acs = []
        for ac in acs:
            s = str(ac)
            if match_re.search(s) and note not in s:
                new_acs.append(s.rstrip("。.;；") + note)
                n += 1
            else:
                new_acs.append(ac)
        fr["acceptance_criteria"] = new_acs
    return n


def _replace_fr_acs(prd: Dict[str, Any], match_re: re.Pattern, replacement: str) -> int:
    """Replace matching acceptance-criteria lines; de-dupe. Prose is `scrub_prose`."""
    n = 0
    frs = prd.get("functional_requirements")
    if not isinstance(frs, list):
        return 0
    for fr in frs:
        if not isinstance(fr, dict):
            continue
        acs = fr.get("acceptance_criteria")
        if not isinstance(acs, list):
            continue
        clean: List[str] = []
        seen: set = set()
        for ac in acs:
            s = str(ac)
            if match_re.search(s) and s.strip() != replacement:
                s = replacement
                n += 1
            key = s.strip()
            if key in seen:
                continue
            seen.add(key)
            clean.append(s)
        fr["acceptance_criteria"] = clean
    return n


def _scrub_prose_fields(prd: Dict[str, Any], match_re: re.Pattern, replacement: str) -> int:
    """Token-replace in title/description/FR prose/user stories; do not rewrite ACs."""
    n = 0

    def _one(obj: Dict[str, Any], key: str) -> None:
        nonlocal n
        val = obj.get(key)
        if not isinstance(val, str) or not val:
            return
        new = match_re.sub(replacement, val)
        if new != val:
            obj[key] = new
            n += 1

    for key in ("title", "description", "background", "scope"):
        _one(prd, key)
    for fr in prd.get("functional_requirements") or []:
        if isinstance(fr, dict):
            for key in ("name", "description"):
                _one(fr, key)
    for us in prd.get("user_stories") or []:
        if isinstance(us, dict):
            for key in ("story", "description", "name"):
                _one(us, key)
    return n


def _ensure_ac_on_fr(prd: Dict[str, Any], fr_name_re: re.Pattern, ac_text: str) -> bool:
    frs = prd.get("functional_requirements")
    if not isinstance(frs, list):
        return False
    for fr in frs:
        if not isinstance(fr, dict):
            continue
        hay = f"{fr.get('name') or ''} {fr.get('description') or ''} " + " ".join(
            str(x) for x in (fr.get("acceptance_criteria") or [])
        )
        if not fr_name_re.search(hay):
            continue
        acs = list(fr.get("acceptance_criteria") or [])
        if any(ac_text[:24] in str(a) for a in acs):
            return False
        acs.append(ac_text)
        fr["acceptance_criteria"] = acs
        return True
    return False


def _ensure_ac_anywhere(
    prd: Dict[str, Any], ac_text: str, prefer_fr_re: Optional[re.Pattern],
) -> bool:
    blob = _prd_blob(prd)
    if ac_text[:20] in blob:
        return False
    if prefer_fr_re and _ensure_ac_on_fr(prd, prefer_fr_re, ac_text):
        return True
    frs = prd.get("functional_requirements")
    if isinstance(frs, list) and frs and isinstance(frs[0], dict):
        acs = list(frs[0].get("acceptance_criteria") or [])
        acs.append(ac_text)
        frs[0]["acceptance_criteria"] = acs
        return True
    return False


def _apply_action(
    action: Dict[str, Any],
    *,
    out: Dict[str, Any],
    decisions: Dict[str, Any],
    cons: Dict[str, Any],
    notes: List[str],
    pack_id: str,
) -> None:
    if not isinstance(action, dict) or not action:
        return
    kind, payload = next(iter(action.items()))

    if kind == "set_decision" and isinstance(payload, dict):
        key = str(payload.get("key") or "")
        if key and not decisions.get(key):
            decisions[key] = payload.get("value")
            notes.append(f"auto:{pack_id}:set_decision:{key}")

    elif kind == "replace_ac" and isinstance(payload, dict):
        c = _replace_fr_acs(out, _re(str(payload.get("match") or "")), str(payload.get("text") or ""))
        if c:
            notes.append(f"auto:{pack_id}:replace_ac×{c}")

    elif kind == "scrub_prose" and isinstance(payload, dict):
        c = _scrub_prose_fields(
            out,
            _re(str(payload.get("match") or "")),
            str(payload.get("text") or ""),
        )
        if c:
            notes.append(f"auto:{pack_id}:scrub_prose×{c}")

    elif kind == "annotate_ac" and isinstance(payload, dict):
        c = _annotate_fr_acs(out, _re(str(payload.get("match") or "")), str(payload.get("note") or ""))
        if c:
            notes.append(f"auto:{pack_id}:annotate_ac×{c}")

    elif kind == "append_ac" and isinstance(payload, dict):
        prefer = str(payload.get("prefer_fr_match") or "")
        text = str(payload.get("text") or "")
        pref_re = _re(prefer) if prefer else None
        if text and _ensure_ac_anywhere(out, text, pref_re):
            notes.append(f"auto:{pack_id}:append_ac")

    elif kind == "append_constraint" and isinstance(payload, dict):
        key = str(payload.get("key") or "")
        val = str(payload.get("value") or "")
        if key and val:
            items = _ensure_list_field(cons, key)
            if val not in items and not any(val[:16] in str(x) for x in items):
                items.append(val)
                cons[key] = items
                notes.append(f"auto:{pack_id}:append_constraint:{key}")

    elif kind == "ensure_constraint_platform":
        if not cons.get("platform"):
            cons["platform"] = str(payload or "Web")
            notes.append(f"auto:{pack_id}:platform")

    elif kind == "ensure_constraint_performance_generic":
        if not _ensure_list_field(cons, "performance"):
            cons["performance"] = [str(payload or "P95 response within product-acceptable latency")]
            notes.append(f"auto:{pack_id}:performance_generic")

    elif kind == "ensure_constraint_security_generic":
        if not _ensure_list_field(cons, "security"):
            cons["security"] = [str(payload or "HTTPS + authentication")]
            notes.append(f"auto:{pack_id}:security_generic")

    elif kind == "ensure_constraint_performance_from_decision" and isinstance(payload, dict):
        key = str(payload.get("key") or "analysis_sla")
        fallback = str(payload.get("fallback") or "")
        sla = str(decisions.get(key) or fallback)
        perf = _ensure_list_field(cons, "performance")
        if not perf:
            cons["performance"] = [sla]
            notes.append(f"auto:{pack_id}:performance_from_decision")
        elif sla and sla not in perf and not any("P95" in str(x) for x in perf):
            perf.append(sla)
            cons["performance"] = perf
            notes.append(f"auto:{pack_id}:performance+=sla")

    elif kind == "ensure_constraint_security_ssrf":
        sec = _ensure_list_field(cons, "security")
        marker = "SSRF: reject private IPs and file:// on URL import"
        if not any("SSRF" in str(x) or "内网" in str(x) for x in sec):
            if not sec:
                cons["security"] = [marker]
            else:
                sec.append(marker)
                cons["security"] = sec
            notes.append(f"auto:{pack_id}:security_ssrf")

    elif kind == "infer_url_scope":
        if decisions.get("url_source_scope"):
            return
        blob = _prd_blob(out)
        has_direct = bool(_re(
            r"直链|http/?/?https|媒体文件\s*URL|直接下载|粘贴\s*URL|URL\s*(?:导入|粘贴)"
        ).search(blob))
        has_plat = bool(_re(
            r"YouTube|Bilibili|B站|Vimeo|平台(?:页|链接)|解析(?:链接|页面)"
        ).search(blob))
        if has_direct and has_plat:
            decisions["url_source_scope"] = "both"
        elif has_plat:
            decisions["url_source_scope"] = "platform_page"
        else:
            decisions["url_source_scope"] = "direct_media_url"
        notes.append(f"auto:{pack_id}:infer_url_scope={decisions['url_source_scope']}")

    elif kind == "infer_speech_pipeline":
        if decisions.get("speech_pipeline"):
            return
        blob = _prd_blob(out)
        # Negation first — cover 「不包含语音转写」「不进行语音到文字的转写」etc.
        # so substring 「语音转写」cannot flip the product to ASR.
        _no_asr = (
            r"不(?:做|进行|支持|生成|执行|包含|含)?\s*(?:语音到文字的?|语音|逐字)?转写|"
            r"不转写|无转写|非转写|不做\s*ASR|不生成逐字|不进行语音到文字"
        )
        if _re(_no_asr).search(blob):
            decisions["speech_pipeline"] = "audio_features_only"
            notes.append(f"auto:{pack_id}:infer_speech_pipeline=audio_features_only")
        else:
            _stripped = _re(_no_asr).sub("", blob)
            if _re(r"\bASR\b|Whisper|语音转写|逐字转写").search(_stripped):
                decisions["speech_pipeline"] = "asr"
                notes.append(f"auto:{pack_id}:infer_speech_pipeline=asr")
            elif _re(r"语种|说话人|情绪|语速|静音").search(blob):
                decisions["speech_pipeline"] = "audio_features_only"
                notes.append(f"auto:{pack_id}:infer_speech_pipeline=audio_features_only(inferred)")

    elif kind == "upsert_fr" and isinstance(payload, dict):
        _upsert_fr(out, payload, notes=notes, pack_id=pack_id)

    elif kind == "upsert_us" and isinstance(payload, dict):
        _upsert_us(out, payload, notes=notes, pack_id=pack_id)


def _upsert_fr(
    out: Dict[str, Any],
    payload: Dict[str, Any],
    *,
    notes: List[str],
    pack_id: str,
) -> None:
    """Replace or append a functional requirement from a pack template."""
    match_re = _re(str(payload.get("match") or "语音|音轨|转写|说话"))
    fr_tpl = payload.get("fr") if isinstance(payload.get("fr"), dict) else {}
    if not fr_tpl:
        return
    frs = out.get("functional_requirements")
    if not isinstance(frs, list):
        frs = []
        out["functional_requirements"] = frs
    target = None
    for fr in frs:
        if not isinstance(fr, dict):
            continue
        blob = f"{fr.get('id','')} {fr.get('name','')} {fr.get('description','')}"
        if match_re.search(blob):
            target = fr
            break
    if target is None:
        target = {"id": str(fr_tpl.get("id") or f"FR-S{len(frs)+1}")}
        frs.append(target)
    for key in ("id", "name", "description", "priority"):
        if key in fr_tpl and fr_tpl[key] is not None:
            target[key] = fr_tpl[key]
    if isinstance(fr_tpl.get("acceptance_criteria"), list):
        new_acs = list(fr_tpl["acceptance_criteria"])
        preserve_re = _re(str(payload.get("preserve_ac_match") or ""))
        if preserve_re.pattern and isinstance(target.get("acceptance_criteria"), list):
            for old in target["acceptance_criteria"]:
                s = str(old)
                if preserve_re.search(s) and not any(s[:24] in str(n) for n in new_acs):
                    new_acs.append(old)
        target["acceptance_criteria"] = new_acs
    notes.append(f"auto:{pack_id}:upsert_fr:{target.get('id')}")


def _upsert_us(
    out: Dict[str, Any],
    payload: Dict[str, Any],
    *,
    notes: List[str],
    pack_id: str,
) -> None:
    """Replace or append a user story from a pack template."""
    match_re = _re(str(payload.get("match") or "语音|主题|说话人|情感"))
    story = str(payload.get("story") or "")
    if not story:
        return
    related = payload.get("related_fr")
    us_id = str(payload.get("id") or "")
    stories = out.get("user_stories")
    if not isinstance(stories, list):
        stories = []
        out["user_stories"] = stories
    target = None
    for us in stories:
        if not isinstance(us, dict):
            continue
        rel = us.get("related_fr") or []
        rel_s = " ".join(str(x) for x in rel) if isinstance(rel, list) else str(rel)
        blob = f"{us.get('id','')} {us.get('story','')} {rel_s}"
        if match_re.search(blob):
            target = us
            break
    if target is None:
        target = {"id": us_id or f"US-S{len(stories)+1}"}
        stories.append(target)
    if us_id:
        target["id"] = us_id
    target["story"] = story
    if isinstance(related, list):
        target["related_fr"] = list(related)
    if payload.get("priority"):
        target["priority"] = payload["priority"]
    notes.append(f"auto:{pack_id}:upsert_us:{target.get('id')}")


def _apply_structural_repairs(
    prd: Dict[str, Any],
    wash_blocked_codes: List[str],
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Apply pack ``structural_repairs`` for wash-blocked codes (full FR/US rewrite).

    Unlike scrub enrich, a successful structural repair may clear wash blocks after
    re-assess verifies the contradiction codes no longer fire.

    Returns (prd, repair_notes, cleared_code_candidates).
    """
    out = dict(prd) if isinstance(prd, dict) else {}
    codes = {str(c) for c in wash_blocked_codes if c}
    if not codes:
        return out, [], []
    notes: List[str] = []
    cleared: List[str] = []
    decisions = dict(out.get("decisions") or {}) if isinstance(out.get("decisions"), dict) else {}
    cons = dict(out.get("constraints") or {}) if isinstance(out.get("constraints"), dict) else {}
    out["decisions"] = decisions
    out["constraints"] = cons

    for pack in matched_domain_packs(out):
        pack_id = str(pack.get("domain_id") or "pack")
        for repair in pack.get("structural_repairs") or []:
            if not isinstance(repair, dict):
                continue
            clears = [str(x) for x in (repair.get("clears_codes") or []) if x]
            if not clears or not codes.intersection(clears):
                continue
            when = repair.get("when")
            if when is not None and not _eval_cond(when, prd=out, blob=_prd_blob(out)):
                continue
            before = len(notes)
            for action in repair.get("actions") or []:
                if isinstance(action, dict):
                    _apply_action(
                        action, out=out, decisions=decisions, cons=cons, notes=notes, pack_id=pack_id
                    )
            if len(notes) > before:
                for c in clears:
                    if c not in cleared:
                        cleared.append(c)
                notes.append(f"structural:{pack_id}:{repair.get('id') or 'repair'}")
    out["decisions"] = decisions
    out["constraints"] = cons
    return out, notes, cleared


# ── Public API ────────────────────────────────────────────────────────────────


def assess_prd(prd: Dict[str, Any]) -> Dict[str, Any]:
    """Assess PRD via matched gate packs. Does not mutate input."""
    if not isinstance(prd, dict):
        return {
            "ok": False,
            "issues": [_issue("invalid_prd", "PRD 必须是 JSON 对象")],
            "domain_flags": [],
            "open_decisions": [],
            "normalized_prd": {},
            "scores": {"consistency": 0.0, "open_questions_closed": 0.0, "constraints_structured": 0.0},
        }

    normalized = normalize_constraints(prd)
    blob = _prd_blob(normalized)
    packs = matched_domain_packs(normalized)
    domain_flags = [str(p.get("domain_id")) for p in packs if p.get("domain_id") and p.get("domain_id") != "_common"]
    issues: List[Dict[str, Any]] = []
    open_decisions: List[str] = []

    # Universal structural checks (not domain-specific)
    cons = normalized.get("constraints") if isinstance(normalized.get("constraints"), dict) else {}
    has_perf = bool(cons.get("performance"))
    has_sec = bool(cons.get("security"))
    media_like = bool(domain_flags)
    if not has_perf and not has_sec:
        issues.append(_issue(
            "constraints_thin",
            "constraints 缺少 performance/security；请写入结构化非功能约束，勿只写功能 AC",
            severity="warning" if not media_like else "error",
        ))
    elif not has_perf or not has_sec:
        issues.append(_issue(
            "constraints_partial",
            "constraints 仅部分填充（需要 performance 与 security）",
            severity="warning",
        ))

    oqs = _open_questions_list(normalized)
    if oqs:
        issues.append(_issue(
            "open_questions_present",
            f"仍有 {len(oqs)} 个未关闭的 open_questions，确认前必须关闭或移入 decisions",
            severity="error",
        ))

    for pack in packs:
        for check in pack.get("checks") or []:
            if not isinstance(check, dict):
                continue
            when = check.get("when") or {}
            if not _eval_cond(when, prd=normalized, blob=blob):
                continue
            code = str(check.get("id") or "pack_check")
            issues.append(_issue(
                code,
                str(check.get("message") or code),
                severity=str(check.get("severity") or "error"),
            ))
            # Track missing decision keys mentioned in message/code
            if "open" in code or code.endswith("_open"):
                # best-effort: extract decision key from id prefixes like media_url_scope_open
                for key in ("url_source_scope", "speech_pipeline", "analysis_sla",
                            "encryption_key_mgmt", "vision_tag_granularity", "confidence_empty_policy"):
                    if key.replace("_", "") in code.replace("_", "") or key in code:
                        if key not in open_decisions and not _decision_value(normalized, key):
                            open_decisions.append(key)

    error_n = sum(1 for i in issues if i.get("severity") == "error")
    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    consistency = max(0.0, 10.0 - error_n * 3.5 - warn_n * 1.0)
    open_n = len(oqs) + len(open_decisions)
    open_closed = 10.0 if open_n == 0 else max(0.0, 10.0 - open_n * 2.5)
    cons_score = 10.0 if (has_perf and has_sec) else (6.0 if (has_perf or has_sec) else 2.0)
    if media_like and open_decisions:
        open_closed = min(open_closed, 4.0)

    return {
        "ok": error_n == 0,
        "issues": issues,
        "domain_flags": domain_flags,
        "open_decisions": open_decisions,
        "normalized_prd": normalized,
        "scores": {
            "consistency": round(consistency, 1),
            "open_questions_closed": round(open_closed, 1),
            "constraints_structured": round(cons_score, 1),
        },
    }


def enrich_prd(prd: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Apply matched pack repairs deterministically."""
    if not isinstance(prd, dict):
        return {}, ["invalid_prd"]

    out = normalize_constraints(dict(prd))
    if isinstance(out.get("functional_requirements"), list):
        out["functional_requirements"] = [
            dict(fr) if isinstance(fr, dict) else fr
            for fr in out["functional_requirements"]
        ]
        for fr in out["functional_requirements"]:
            if isinstance(fr, dict) and isinstance(fr.get("acceptance_criteria"), list):
                fr["acceptance_criteria"] = list(fr["acceptance_criteria"])

    notes: List[str] = []
    decisions = dict(out["decisions"]) if isinstance(out.get("decisions"), dict) else {}
    cons = dict(out["constraints"]) if isinstance(out.get("constraints"), dict) else {}
    out["decisions"] = decisions
    out["constraints"] = cons

    packs = matched_domain_packs(out)
    for pack in packs:
        pack_id = str(pack.get("domain_id") or "pack")
        for repair in pack.get("repairs") or []:
            if not isinstance(repair, dict):
                continue
            when = repair.get("when") or {"always": True}
            # Evaluate against live blob after prior repairs
            blob = _prd_blob(out)
            if not _eval_cond(when, prd=out, blob=blob):
                continue
            repair_id = str(repair.get("id") or "repair")
            n_before = len(notes)
            for action in repair.get("actions") or []:
                if isinstance(action, dict):
                    _apply_action(
                        action, out=out, decisions=decisions, cons=cons,
                        notes=notes, pack_id=pack_id,
                    )
            if len(notes) > n_before:
                notes.insert(n_before, f"auto:{pack_id}:{repair_id}")
            # keep decisions/constraints synced on out for next when-eval
            out["decisions"] = decisions
            out["constraints"] = cons

    # If encryption claimed and key mgmt set, mirror into security list
    blob = _prd_blob(out)
    key_mgmt = str(decisions.get("encryption_key_mgmt") or "")
    key_is_na = key_mgmt.upper() in ("N/A", "NA", "NONE", "")
    if key_mgmt and not key_is_na:
        sec = _ensure_list_field(cons, "security")
        if not any("KMS" in str(x) or key_mgmt[:20] in str(x) for x in sec):
            if re.search(r"AES-?256|加密存储", blob, re.I):
                sec.append(f"AES-256; {key_mgmt}")
                cons["security"] = sec
                notes.append("auto:mirror_key_mgmt_to_security")

    if not isinstance(out.get("open_questions"), list):
        out["open_questions"] = []
    out["_prd_enrichment"] = {"repairs": notes, "packs": [p.get("domain_id") for p in packs]}
    return out, notes


def _wash_blocked_issues_from_raw(
    prd: Dict[str, Any],
    raw_report: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Raw error issues whose pack check has ``block_finalize_wash: true``.

    Config-driven: packs declare which contradictions must not be green-washed
    by enrich/scrub alone — PM must rewrite the first draft.
    """
    fired = {
        str(i.get("code") or ""): i
        for i in (raw_report.get("issues") or [])
        if isinstance(i, dict) and i.get("severity") == "error" and i.get("code")
    }
    if not fired:
        return []
    blocked: List[Dict[str, Any]] = []
    seen: set = set()
    for pack in matched_domain_packs(prd if isinstance(prd, dict) else {}):
        for check in pack.get("checks") or []:
            if not isinstance(check, dict) or not check.get("block_finalize_wash"):
                continue
            code = str(check.get("id") or "")
            if not code or code not in fired or code in seen:
                continue
            seen.add(code)
            blocked.append(dict(fired[code]))
    return blocked


def _reapply_wash_blocks(
    report: Dict[str, Any],
    wash_blocked: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Force ok=False and keep wash-blocked codes even if scrub cleared blob matches."""
    if not wash_blocked:
        return report
    issues = [dict(i) for i in (report.get("issues") or []) if isinstance(i, dict)]
    by_code = {str(i.get("code") or ""): i for i in issues}
    wash_codes: List[str] = []
    for bi in wash_blocked:
        code = str(bi.get("code") or "")
        if not code:
            continue
        wash_codes.append(code)
        base_msg = str(bi.get("message") or code)
        wash_msg = (
            f"{base_msg}（首稿语义矛盾：门禁洗绿不可放行，请按域约束 GOOD 口径重写首稿后再 PRD_READY）"
        )
        if code in by_code:
            by_code[code]["message"] = wash_msg
            by_code[code]["wash_blocked"] = True
            by_code[code]["severity"] = "error"
        else:
            ni = _issue(code, wash_msg, severity="error")
            ni["wash_blocked"] = True
            issues.append(ni)
            by_code[code] = ni
    return {
        **report,
        "ok": False,
        "issues": issues,
        "wash_blocked": wash_codes,
    }


def factory_finalize_prd(prd: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Factory generation post-process: enrich → optional structural repair → assess.

    ``block_finalize_wash`` codes: word scrub alone must not green-pass. Packs may
    declare ``structural_repairs`` (full FR/US template rewrite); after those run,
    codes that no longer fire on re-assess are cleared so the factory can READY.
    """
    raw_src = prd if isinstance(prd, dict) else {}
    raw_report = assess_prd(raw_src)
    wash_blocked = _wash_blocked_issues_from_raw(raw_src, raw_report)
    wash_codes = [str(i.get("code") or "") for i in wash_blocked if i.get("code")]

    enriched, repairs = enrich_prd(prd)
    structural_notes: List[str] = []
    cleared_candidates: List[str] = []
    if wash_codes:
        enriched, structural_notes, cleared_candidates = _apply_structural_repairs(
            enriched, wash_codes
        )
        repairs = list(repairs or []) + list(structural_notes)

    report = assess_prd(enriched)
    out = dict(report["normalized_prd"])
    out["decisions"] = enriched.get("decisions") or out.get("decisions") or {}
    out["constraints"] = enriched.get("constraints") or out.get("constraints") or {}
    if isinstance(enriched.get("functional_requirements"), list):
        out["functional_requirements"] = enriched["functional_requirements"]
    if isinstance(enriched.get("user_stories"), list):
        out["user_stories"] = enriched["user_stories"]
    out["open_questions"] = (
        enriched.get("open_questions")
        if isinstance(enriched.get("open_questions"), list)
        else []
    )
    report = assess_prd(out)

    fired_errors = {
        str(i.get("code") or "")
        for i in (report.get("issues") or [])
        if isinstance(i, dict) and i.get("severity") == "error" and i.get("code")
    }
    cleared_set = set(cleared_candidates)
    # Structurally cleared + no longer firing → drop; scrub-only clear still blocked
    still_blocked = [
        bi
        for bi in wash_blocked
        if not (
            str(bi.get("code") or "") in cleared_set
            and str(bi.get("code") or "") not in fired_errors
        )
    ]
    report = _reapply_wash_blocks(report, still_blocked)
    out = dict(report["normalized_prd"])
    out["decisions"] = enriched.get("decisions") or out.get("decisions") or {}
    out["constraints"] = enriched.get("constraints") or out.get("constraints") or {}
    if isinstance(enriched.get("functional_requirements"), list):
        out["functional_requirements"] = enriched["functional_requirements"]
    if isinstance(enriched.get("user_stories"), list):
        out["user_stories"] = enriched["user_stories"]
    out.setdefault("open_questions", [])
    enrich_meta = dict(enriched.get("_prd_enrichment") or {"repairs": repairs})
    enrich_meta["repairs"] = repairs
    if structural_notes:
        enrich_meta["structural_repairs"] = structural_notes
        enrich_meta["structural_cleared"] = [
            c for c in cleared_candidates if c not in fired_errors
        ]
    out["_prd_enrichment"] = enrich_meta
    out["_prd_gate"] = {
        "ok": report["ok"],
        "issues": report["issues"],
        "domain_flags": report["domain_flags"],
        "open_decisions": report["open_decisions"],
        "scores": report["scores"],
        "forced": False,
        "factory_finalized": True,
        "wash_blocked": list(report.get("wash_blocked") or []),
        "structural_cleared": list(enrich_meta.get("structural_cleared") or []),
    }
    report = {**report, "normalized_prd": out, "repairs": repairs}
    return out, report


def looks_like_prd(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    frs = obj.get("functional_requirements")
    return isinstance(frs, list) and len(frs) > 0


def apply_gate_to_prd(
    prd: Dict[str, Any],
    *,
    force: bool = False,
    enrich: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Enrich (factory default) then assess. Raises ValueError if still failing."""
    if enrich:
        normalized, report = factory_finalize_prd(prd if isinstance(prd, dict) else {})
    else:
        report = assess_prd(prd)
        normalized = dict(report["normalized_prd"])
        normalized["_prd_gate"] = {
            "ok": report["ok"],
            "issues": report["issues"],
            "domain_flags": report["domain_flags"],
            "open_decisions": report["open_decisions"],
            "scores": report["scores"],
            "forced": bool(force),
        }
    gate_meta = dict(normalized.get("_prd_gate") or {})
    gate_meta["forced"] = bool(force)
    normalized["_prd_gate"] = gate_meta
    if report["ok"] and not _open_questions_list(normalized):
        normalized.setdefault("open_questions", [])
    if not report["ok"] and not force:
        msgs = [i["message"] for i in report["issues"] if i.get("severity") == "error"]
        raise ValueError(
            "PRD 质量门禁未通过：\n- " + "\n- ".join(msgs[:8])
            + ("\n(传入 force_confirm=true 可强制确认并保留风险标记)" if msgs else "")
        )
    return normalized, report


def followup_questions_from_report(report: Dict[str, Any]) -> str:
    """Render remaining gate errors as PM follow-up questions."""
    errs = [i for i in (report.get("issues") or []) if i.get("severity") == "error"]
    if not errs:
        return ""
    lines = [
        "",
        "---",
        "PRD 尚未闭合，请先确认以下决策（确认后我将重新生成完整 PRD）：",
    ]
    for i, issue in enumerate(errs[:6], 1):
        lines.append(f"{i}. {issue.get('message', '')}")
    return "\n".join(lines)


def render_prd_markdown(prd: Dict[str, Any], *, include_ready_marker: bool = True) -> str:
    """Render a structured PRD dict as Markdown matching pm_agent output format.

    Used after factory_finalize so chat reply shows the repaired PRD, not the
    contradictory LLM draft.
    """
    if not isinstance(prd, dict):
        return ""

    lines: List[str] = []
    title = str(prd.get("title") or "未命名项目").strip()
    lines.append(f"## 项目名称：{title}")
    lines.append("")

    bg = str(prd.get("description") or prd.get("background") or "").strip()
    if bg:
        lines.append("## 项目背景")
        lines.append(bg)
        lines.append("")

    frs = prd.get("functional_requirements") or []
    if isinstance(frs, list) and frs:
        lines.append("## 功能需求")
        for i, fr in enumerate(frs, 1):
            if not isinstance(fr, dict):
                continue
            fr_id = str(fr.get("id") or f"FR-{i:02d}").strip()
            name = str(fr.get("name") or fr_id).strip()
            lines.append(f"### {fr_id}: {name}")
            desc = str(fr.get("description") or "").strip()
            if desc:
                lines.append(f"- **描述**: {desc}")
            pri = str(fr.get("priority") or "").strip()
            if pri:
                lines.append(f"- **优先级**: {pri}")
            acs = fr.get("acceptance_criteria") or []
            if isinstance(acs, list) and acs:
                lines.append("- **验收标准**:")
                for j, ac in enumerate(acs, 1):
                    lines.append(f"  - AC{j}: {ac}")
            lines.append("")

    stories = prd.get("user_stories") or []
    if isinstance(stories, list) and stories:
        # Skip if identical to FRs (markdown parser sometimes aliases them)
        same_as_fr = (
            isinstance(frs, list)
            and len(stories) == len(frs)
            and all(
                isinstance(a, dict) and isinstance(b, dict) and a.get("id") == b.get("id")
                for a, b in zip(stories, frs)
            )
        )
        if not same_as_fr:
            lines.append("## 用户故事")
            for i, us in enumerate(stories, 1):
                if isinstance(us, dict):
                    us_id = str(us.get("id") or f"US-{i:02d}").strip()
                    text = str(
                        us.get("story") or us.get("description") or us.get("name") or ""
                    ).strip()
                    lines.append(f"### {us_id}: {text}")
                    rel = us.get("related_fr") or us.get("related_frs") or us.get("fr")
                    if rel:
                        if isinstance(rel, list):
                            rel = ", ".join(str(x) for x in rel)
                        lines.append(f"- **关联需求**: {rel}")
                    pri = str(us.get("priority") or "").strip()
                    if pri:
                        lines.append(f"- **优先级**: {pri}")
                else:
                    lines.append(f"### US-{i:02d}: {us}")
                lines.append("")

    decisions = prd.get("decisions")
    if isinstance(decisions, dict) and decisions:
        lines.append("## 决策")
        for k, v in decisions.items():
            if str(k).startswith("_"):
                continue
            lines.append(f"- {k}: {v}")
        lines.append("")

    oqs = _open_questions_list(prd)
    lines.append("## 待确认问题")
    if oqs:
        for q in oqs:
            lines.append(f"- {q}")
    else:
        lines.append("（无）")
    lines.append("")

    cons = prd.get("constraints")
    scope = str(prd.get("scope") or "").strip()
    lines.append("## 范围")
    if scope:
        lines.append(scope)
    elif isinstance(cons, dict) and cons:
        plat = cons.get("platform") or "Web"
        lines.append(f"- 平台: {plat}")
        perf = cons.get("performance")
        if isinstance(perf, list) and perf:
            lines.append("- 性能: " + str(perf[0]))
        elif perf:
            lines.append("- 性能: " + str(perf))
        sec = cons.get("security")
        if isinstance(sec, list) and sec:
            lines.append("- 安全: " + "; ".join(str(x) for x in sec))
        elif sec:
            lines.append("- 安全: " + str(sec))
    else:
        lines.append("- 平台: Web")
    lines.append("")

    repairs = []
    enrich = prd.get("_prd_enrichment")
    if isinstance(enrich, dict):
        repairs = list(enrich.get("repairs") or [])
    gate = prd.get("_prd_gate")
    if isinstance(gate, dict) and gate.get("factory_finalized") and repairs:
        lines.append("---")
        lines.append(f"（已由 PRD 质量门禁自动改写 {len(repairs)} 项矛盾/缺口）")
        lines.append("")

    body = "\n".join(lines).rstrip() + "\n"
    if include_ready_marker and not oqs:
        body = body + "\n<!-- PRD_READY -->\n"
    return body
