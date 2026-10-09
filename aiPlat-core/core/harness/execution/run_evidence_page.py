"""Oversight P1: discardable interactive evidence page (template + JSON, no LLM JS).

Facts come from stage topology / handoff / errors / structure diagram only.
Rendered HTML is template-injected; iframe must sandbox (no network / no deploy).
TTL default 24h; read-only — cannot trigger coding or deploy.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

STATE_EVIDENCE_KEY = "_evidence_page"
STATE_EVIDENCE_METRICS_KEY = "_evidence_metrics"
SCHEMA_VERSION = "evidence_page.v1"
METRICS_SCHEMA_VERSION = "evidence_metrics.v1"
TEMPLATE_ID = "oversight_verify_v1"
DEFAULT_TTL_HOURS = 24
_MAX_RECENT_EVENTS = 50

# Verification success metrics (postMessage → parent may record)
METRIC_EVENTS = (
    "source_click",
    "input_change",
    "inconsistency_found",
    "hitl_refine",
)
ALLOWED_METRIC_EVENTS = frozenset(METRIC_EVENTS)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_ttl_hours(source: Optional[Mapping[str, Any]] = None) -> int:
    """TTL hours from state/env; clamp 1..168 (7d). Default 24."""
    raw = None
    if source:
        raw = source.get("evidence_ttl_hours") or source.get("_evidence_ttl_hours")
    if raw in (None, ""):
        raw = os.getenv("AIPLAT_EVIDENCE_TTL_HOURS", "").strip() or DEFAULT_TTL_HOURS
    try:
        h = int(raw)
    except (TypeError, ValueError):
        h = DEFAULT_TTL_HOURS
    return max(1, min(168, h))


def is_evidence_expired(payload: Mapping[str, Any], *, now: Optional[datetime] = None) -> bool:
    exp = str(payload.get("expires_at") or "").strip()
    if not exp:
        return False
    try:
        # Accept Z suffix
        ts = exp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (now or _utc_now()) >= dt


def _stage_bits(st: Any) -> Dict[str, Any]:
    if isinstance(st, Mapping):
        return {
            "id": str(st.get("id") or "").strip(),
            "output_artifact": str(st.get("output_artifact") or "").strip(),
            "depends_on": list(st.get("depends_on") or []),
            "input_artifacts": list(st.get("input_artifacts") or []),
        }
    return {
        "id": str(getattr(st, "id", "") or "").strip(),
        "output_artifact": str(getattr(st, "output_artifact", "") or "").strip(),
        "depends_on": list(getattr(st, "depends_on", None) or []),
        "input_artifacts": list(getattr(st, "input_artifacts", None) or []),
    }


def collect_evidence_data(
    state: Optional[Mapping[str, Any]] = None,
    *,
    stages: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Build tool_result JSON for the fixed template (no LLM)."""
    st = state if isinstance(state, Mapping) else {}
    stage_seq: Sequence[Any] = stages or ()
    if not stage_seq:
        raw = st.get("stages")
        if isinstance(raw, list):
            stage_seq = raw

    inputs: List[Dict[str, Any]] = []
    conclusions: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    uncertainties: List[Dict[str, Any]] = []

    phase = str(st.get("phase") or "").strip() or "unknown"
    run_id = str(st.get("run_id") or st.get("_run_id") or "").strip()
    err = str(st.get("error_message") or "").strip()

    stage_list = list(stage_seq)
    last_idx = len(stage_list) - 1
    seen_in: set = set()
    for i, stage in enumerate(stage_list):
        bits = _stage_bits(stage)
        sid = bits["id"] or f"stage_{i}"
        art = bits["output_artifact"]
        for inp in bits["input_artifacts"]:
            key = str(inp).strip()
            if not key or key in seen_in:
                continue
            seen_in.add(key)
            present = key in st and st.get(key) not in (None, "", {}, [])
            inputs.append(
                {
                    "key": key,
                    "label": key,
                    "value": "present" if present else "missing",
                    "source_type": "tool_result",
                    "confidence": 1.0,
                }
            )
        if art:
            status = "failed" if (phase == "failed" and err and i == last_idx) else "ok"
            conclusions.append(
                {
                    "id": f"c_{sid}",
                    "stage_id": sid,
                    "text": f"{sid} → {art} ({status})",
                    "depends_on_inputs": [str(x).strip() for x in bits["input_artifacts"] if str(x).strip()],
                    "artifact": art,
                    "href": f"#artifact:{art}",
                    "source_type": "tool_result",
                    "confidence": 1.0,
                }
            )
            evidence.append(
                {
                    "label": f"artifact:{art}",
                    "href": f"#artifact:{art}",
                    "stage_id": sid,
                    "source_type": "tool_result",
                    "confidence": 1.0,
                }
            )

    # Handoff known issues → uncertainty annotations (still tool-derived text)
    handoff = st.get("_handoff")
    if isinstance(handoff, Mapping):
        for art_key, payload in handoff.items():
            if not isinstance(payload, Mapping):
                continue
            issues = payload.get("known_issues") or []
            if isinstance(issues, list):
                for issue in issues[:8]:
                    text = str(issue).strip()
                    if text:
                        uncertainties.append(
                            {
                                "text": text[:300],
                                "artifact": str(art_key),
                                "source_type": "tool_result",
                                "confidence": 0.8,
                            }
                        )
            summary = str(payload.get("summary") or "").strip()
            if summary:
                evidence.append(
                    {
                        "label": f"handoff:{art_key}",
                        "href": f"#artifact:{art_key}",
                        "snippet": summary[:200],
                        "source_type": "tool_result",
                        "confidence": 1.0,
                    }
                )

    if err:
        uncertainties.append(
            {
                "text": err[:400],
                "source_type": "tool_result",
                "confidence": 1.0,
                "kind": "error_message",
            }
        )

    structure = st.get("_structure_diagram")
    mermaid = ""
    if isinstance(structure, Mapping):
        mermaid = str(structure.get("mermaid") or "")

    gates = _collect_gate_facts(st)

    return {
        "run_id": run_id,
        "phase": phase,
        "inputs": inputs,
        "conclusions": conclusions,
        "evidence": evidence[:40],
        "uncertainties": uncertainties[:20],
        "gates": gates,
        "structure_mermaid": mermaid[:8000],
        "hint": (
            "Change an input value to mark dependent conclusions as stale. "
            "Click evidence to open artifact anchors. No coding/deploy actions."
        ),
    }


def _safe_int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _collect_gate_facts(st: Mapping[str, Any]) -> Dict[str, Any]:
    """Deterministic done_verify + bloat slices (tool_result only)."""
    out: Dict[str, Any] = {
        "done_verify": None,
        "bloat": None,
        "source_type": "tool_result",
        "confidence": 1.0,
    }
    dv = st.get("_done_verify")
    if isinstance(dv, Mapping):
        eo = dv.get("expected_outcomes")
        out["done_verify"] = {
            "enabled": bool(dv.get("enabled", True)),
            "min_output_length": max(0, _safe_int(dv.get("min_output_length"), 0)),
            "review_gate": str(dv.get("review_gate") or "").strip(),
            "require_keys": [str(k) for k in (dv.get("require_keys") or []) if str(k).strip()][
                :12
            ],
            "expected_outcomes": len(eo) if isinstance(eo, list) else 0,
            "veto_count": max(0, _safe_int(st.get("_done_verify_veto_count"), 0)),
            "exhausted": bool(st.get("_done_verify_exhausted")),
            "last_reason": str(st.get("_done_verify_last_reason") or "").strip()[:300],
            "source_type": "tool_result",
            "confidence": 1.0,
        }

    bloat = st.get("_bloat_metrics")
    if isinstance(bloat, Mapping):
        vs = bloat.get("vs_baseline") if isinstance(bloat.get("vs_baseline"), Mapping) else {}
        out["bloat"] = {
            "loc": max(0, _safe_int(bloat.get("loc"), 0)),
            "loc_non_import": max(0, _safe_int(bloat.get("loc_non_import"), 0)),
            "new_files": max(0, _safe_int(bloat.get("new_files"), 0)),
            "new_deps": max(0, _safe_int(bloat.get("new_deps"), 0)),
            "sources": [str(s) for s in (bloat.get("sources") or [])[:12]],
            "delta_loc": vs.get("delta_loc") if isinstance(vs, Mapping) else None,
            "delta_new_files": vs.get("delta_new_files") if isinstance(vs, Mapping) else None,
            "delta_new_deps": vs.get("delta_new_deps") if isinstance(vs, Mapping) else None,
            "has_baseline": bool(vs.get("has_baseline")) if isinstance(vs, Mapping) else False,
            "source_type": "tool_result",
            "confidence": 1.0,
        }
    return out


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Oversight evidence (discardable)</title>
<style>
  :root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
  body { margin: 0; padding: 12px; background: #0f172a; color: #e2e8f0; font-size: 13px; }
  h1 { font-size: 14px; margin: 0 0 8px; color: #94a3b8; font-weight: 600; }
  .banner { padding: 8px 10px; border-radius: 6px; margin-bottom: 10px; font-size: 11px; }
  .ok { background: #14532d55; border: 1px solid #22c55e55; color: #86efac; }
  .exp { background: #7f1d1d55; border: 1px solid #ef444455; color: #fca5a5; }
  .meta { color: #64748b; font-size: 10px; margin-bottom: 10px; }
  section { margin-bottom: 12px; }
  section h2 { font-size: 11px; color: #94a3b8; margin: 0 0 6px; text-transform: uppercase; letter-spacing: .04em; }
  .row { display: flex; gap: 8px; align-items: center; margin: 4px 0; flex-wrap: wrap; }
  label { color: #cbd5e1; min-width: 90px; }
  input { background: #1e293b; border: 1px solid #334155; color: #f1f5f9; border-radius: 4px; padding: 4px 6px; font-size: 12px; }
  .card { background: #1e293b88; border: 1px solid #334155; border-radius: 6px; padding: 8px; margin: 4px 0; }
  .stale { opacity: .55; border-color: #f59e0b88; }
  .stale::after { content: " stale — re-verify"; color: #fbbf24; font-size: 10px; margin-left: 6px; }
  a { color: #38bdf8; cursor: pointer; text-decoration: underline; }
  pre { background: #020617; padding: 8px; border-radius: 6px; overflow: auto; max-height: 160px; font-size: 10px; color: #94a3b8; }
  button.metric { background: #334155; border: 0; color: #e2e8f0; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer; }
  button.metric:hover { background: #475569; }
  .locked { color: #64748b; font-size: 10px; }
</style>
</head>
<body>
<h1>Interactive evidence (oversight · discardable)</h1>
<div id="banner" class="banner ok">Loading…</div>
<div class="meta" id="meta"></div>
<section>
  <h2>Inputs (what-if)</h2>
  <div id="inputs"></div>
  <p class="locked">Tweaking inputs only marks dependent conclusions stale — does not re-run the pipeline.</p>
</section>
<section>
  <h2>Conclusions</h2>
  <div id="conclusions"></div>
</section>
<section>
  <h2>Evidence links</h2>
  <div id="evidence"></div>
</section>
<section>
  <h2>Uncertainties</h2>
  <div id="uncertainties"></div>
</section>
<section>
  <h2>Gates (tool_result)</h2>
  <div id="gates"></div>
</section>
<section>
  <h2>Structure (Mermaid source)</h2>
  <pre id="mermaid"></pre>
</section>
<section>
  <h2>Verification signals</h2>
  <div class="row">
    <button type="button" class="metric" data-ev="inconsistency_found">Mark inconsistency found</button>
    <button type="button" class="metric" data-ev="hitl_refine">Mark HITL refine</button>
  </div>
  <p class="locked">Metrics: source_click · input_change · inconsistency_found · hitl_refine (postMessage only).</p>
</section>
<script>
(function(){
  var PAYLOAD = __EVIDENCE_JSON__;
  var data = (PAYLOAD && PAYLOAD.data) || {};
  var expired = !!PAYLOAD.expired;
  var banner = document.getElementById('banner');
  var meta = document.getElementById('meta');
  function emit(type, detail){
    try {
      parent.postMessage({
        type: 'aiplat_evidence_metric',
        event: type,
        detail: detail || {},
        run_id: data.run_id || '',
        schema_version: PAYLOAD.schema_version || ''
      }, '*');
    } catch (e) {}
  }
  if (expired) {
    banner.className = 'banner exp';
    banner.textContent = 'EXPIRED — TTL elapsed. Read-only archive; regenerate by re-running the pipeline.';
  } else {
    banner.className = 'banner ok';
    banner.textContent = 'Active until ' + (PAYLOAD.expires_at || '?') +
      ' · read_only · no coding/deploy triggers · source_type=' + (PAYLOAD.source_type || 'tool_result');
  }
  meta.textContent = 'template=' + (PAYLOAD.template_id || '') +
    ' · phase=' + (data.phase || '') +
    ' · run_id=' + (data.run_id || '(none)') +
    ' · confidence=' + (PAYLOAD.confidence != null ? PAYLOAD.confidence : '');

  var inputVals = {};
  var inputOrig = {};
  (data.inputs || []).forEach(function(inp){
    inputVals[inp.key] = String(inp.value == null ? '' : inp.value);
    inputOrig[inp.key] = inputVals[inp.key];
  });

  function isStale(c){
    var deps = c.depends_on_inputs || [];
    for (var i = 0; i < deps.length; i++){
      var k = deps[i];
      if (inputVals[k] !== undefined && inputVals[k] !== inputOrig[k]) return true;
    }
    return false;
  }

  function render(){
    var iroot = document.getElementById('inputs');
    iroot.innerHTML = '';
    (data.inputs || []).forEach(function(inp){
      var row = document.createElement('div');
      row.className = 'row';
      var lab = document.createElement('label');
      lab.textContent = inp.label || inp.key;
      var el = document.createElement('input');
      el.value = inputVals[inp.key] || '';
      el.disabled = expired;
      el.addEventListener('change', function(){
        inputVals[inp.key] = el.value;
        emit('input_change', { key: inp.key, value: el.value });
        renderConclusions();
      });
      row.appendChild(lab);
      row.appendChild(el);
      iroot.appendChild(row);
    });
    if (!(data.inputs || []).length){
      iroot.textContent = '(no input artifacts declared on stages)';
    }
    renderConclusions();
    var eroot = document.getElementById('evidence');
    eroot.innerHTML = '';
    (data.evidence || []).forEach(function(ev){
      var card = document.createElement('div');
      card.className = 'card';
      var a = document.createElement('a');
      a.textContent = ev.label || ev.href || 'evidence';
      a.href = ev.href || '#';
      a.addEventListener('click', function(e){
        e.preventDefault();
        emit('source_click', { href: ev.href || '', label: ev.label || '' });
        try { parent.postMessage({ type: 'aiplat_evidence_nav', href: ev.href || '' }, '*'); } catch (err) {}
      });
      card.appendChild(a);
      if (ev.snippet){
        var s = document.createElement('div');
        s.style.color = '#94a3b8';
        s.style.fontSize = '11px';
        s.style.marginTop = '4px';
        s.textContent = ev.snippet;
        card.appendChild(s);
      }
      eroot.appendChild(card);
    });
    if (!(data.evidence || []).length) eroot.textContent = '(no evidence links)';
    var uroot = document.getElementById('uncertainties');
    uroot.innerHTML = '';
    (data.uncertainties || []).forEach(function(u){
      var card = document.createElement('div');
      card.className = 'card';
      card.textContent = u.text || '';
      uroot.appendChild(card);
    });
    if (!(data.uncertainties || []).length) uroot.textContent = '(none)';
    var groot = document.getElementById('gates');
    groot.innerHTML = '';
    var gates = data.gates || {};
    var dv = gates.done_verify;
    var bl = gates.bloat;
    if (dv) {
      var dcard = document.createElement('div');
      dcard.className = 'card';
      dcard.textContent = 'done_verify: enabled=' + !!dv.enabled +
        ' · veto_count=' + (dv.veto_count || 0) +
        (dv.exhausted ? ' · exhausted' : '') +
        (dv.review_gate ? ' · review_gate=' + dv.review_gate : '') +
        (dv.last_reason ? ' · last_reason=' + dv.last_reason : '');
      groot.appendChild(dcard);
    }
    if (bl) {
      var bcard = document.createElement('div');
      bcard.className = 'card';
      var line = 'bloat: loc=' + (bl.loc || 0) +
        ' · files=' + (bl.new_files || 0) +
        ' · deps=' + (bl.new_deps || 0);
      if (bl.has_baseline) {
        line += ' · Δloc=' + (bl.delta_loc != null ? bl.delta_loc : '?') +
          ' · Δfiles=' + (bl.delta_new_files != null ? bl.delta_new_files : '?');
      }
      bcard.textContent = line;
      groot.appendChild(bcard);
    }
    if (!dv && !bl) groot.textContent = '(no gate metrics on this run)';
    document.getElementById('mermaid').textContent = data.structure_mermaid || '(no structure diagram)';
  }

  function renderConclusions(){
    var croot = document.getElementById('conclusions');
    croot.innerHTML = '';
    (data.conclusions || []).forEach(function(c){
      var card = document.createElement('div');
      card.className = 'card' + (isStale(c) ? ' stale' : '');
      var a = document.createElement('a');
      a.textContent = c.text || c.id;
      a.href = c.href || '#';
      a.addEventListener('click', function(e){
        e.preventDefault();
        emit('source_click', { href: c.href || '', id: c.id || '' });
        try { parent.postMessage({ type: 'aiplat_evidence_nav', href: c.href || '' }, '*'); } catch (err) {}
      });
      card.appendChild(a);
      croot.appendChild(card);
    });
    if (!(data.conclusions || []).length) croot.textContent = '(no stage conclusions)';
  }

  document.querySelectorAll('button.metric').forEach(function(btn){
    btn.addEventListener('click', function(){
      if (expired) return;
      emit(btn.getAttribute('data-ev') || 'unknown', {});
    });
  });

  render();
})();
</script>
</body>
</html>
"""


def render_evidence_html(payload: Mapping[str, Any]) -> str:
    """Inject JSON into fixed template. Never executes LLM-authored script."""
    safe = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Prevent breaking out of <script>
    safe = safe.replace("<", "\\u003c").replace(">", "\\u003e").replace("</", "<\\/")
    return _TEMPLATE.replace("__EVIDENCE_JSON__", safe)


def build_run_evidence_page(
    state: Optional[Mapping[str, Any]] = None,
    *,
    stages: Optional[Sequence[Any]] = None,
    ttl_hours: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return evidence page payload — deterministic, discardable oversight UI."""
    st = state if isinstance(state, Mapping) else {}
    hours = int(ttl_hours) if ttl_hours is not None else resolve_ttl_hours(st)
    hours = max(1, min(168, hours))
    created = now or _utc_now()
    expires = created + timedelta(hours=hours)
    data = collect_evidence_data(st, stages=stages)
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "template_id": TEMPLATE_ID,
        "source_type": "tool_result",
        "confidence": 1.0,
        "created_at": _iso(created),
        "expires_at": _iso(expires),
        "ttl_hours": hours,
        "read_only": True,
        "can_trigger_coding": False,
        "can_trigger_deploy": False,
        "expired": False,
        "data": data,
        "metrics_events": list(METRIC_EVENTS),
        "hint": (
            "Discardable oversight UI. Template + JSON only; iframe sandbox; "
            "TTL expires page; never triggers coding/deploy."
        ),
    }
    payload["expired"] = is_evidence_expired(payload, now=created)
    payload["html"] = render_evidence_html(payload)
    return payload


def write_evidence_page(
    state: MutableMapping[str, Any],
    *,
    stages: Optional[Sequence[Any]] = None,
    ttl_hours: Optional[int] = None,
) -> Dict[str, Any]:
    """Persist under state[_evidence_page] (best-effort like structure diagram)."""
    payload = build_run_evidence_page(state, stages=stages, ttl_hours=ttl_hours)
    state[STATE_EVIDENCE_KEY] = payload
    return payload


def empty_evidence_metrics() -> Dict[str, Any]:
    return {
        "schema_version": METRICS_SCHEMA_VERSION,
        "counts": {k: 0 for k in METRIC_EVENTS},
        "total": 0,
        "verified": False,
        "updated_at": "",
        "recent": [],
    }


def merge_evidence_metrics(
    store: MutableMapping[str, Any],
    *,
    events: Sequence[Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Accumulate oversight verification metrics (read-only; no coding/deploy).

    ``events`` items may be event name strings or ``{"event": name, ...}`` dicts.
    Unknown events are ignored. ``verified`` flips true when any allowed count > 0.
    """
    if not isinstance(store, MutableMapping):
        raise TypeError("store must be a mutable mapping")
    if store.get("schema_version") != METRICS_SCHEMA_VERSION:
        base = empty_evidence_metrics()
        # Preserve prior counts when upgrading a partial blob
        prev_counts = store.get("counts") if isinstance(store.get("counts"), Mapping) else {}
        for k in METRIC_EVENTS:
            try:
                base["counts"][k] = max(0, int(prev_counts.get(k) or 0))
            except (TypeError, ValueError):
                base["counts"][k] = 0
        store.clear()
        store.update(base)

    counts = store.setdefault("counts", {})
    if not isinstance(counts, dict):
        counts = {k: 0 for k in METRIC_EVENTS}
        store["counts"] = counts
    recent = store.setdefault("recent", [])
    if not isinstance(recent, list):
        recent = []
        store["recent"] = recent

    ts = _iso(now or _utc_now())
    accepted = 0
    for raw in events or ():
        name = ""
        detail: Dict[str, Any] = {}
        if isinstance(raw, str):
            name = raw.strip()
        elif isinstance(raw, Mapping):
            name = str(raw.get("event") or raw.get("name") or "").strip()
            detail = {k: v for k, v in raw.items() if k not in ("event", "name")}
        if name not in ALLOWED_METRIC_EVENTS:
            continue
        counts[name] = int(counts.get(name) or 0) + 1
        accepted += 1
        entry = {"event": name, "at": ts}
        if detail:
            entry["detail"] = detail
        recent.append(entry)

    if len(recent) > _MAX_RECENT_EVENTS:
        del recent[:-_MAX_RECENT_EVENTS]

    total = sum(int(counts.get(k) or 0) for k in METRIC_EVENTS)
    store["total"] = total
    store["verified"] = total > 0
    store["updated_at"] = ts
    store["schema_version"] = METRICS_SCHEMA_VERSION
    store["accepted"] = accepted
    return dict(store)


def verification_success(metrics: Optional[Mapping[str, Any]]) -> bool:
    """True when oversight UI recorded at least one verification signal."""
    if not isinstance(metrics, Mapping):
        return False
    if metrics.get("verified") is True:
        return True
    counts = metrics.get("counts")
    if isinstance(counts, Mapping):
        return any(int(counts.get(k) or 0) > 0 for k in METRIC_EVENTS)
    return int(metrics.get("total") or 0) > 0
