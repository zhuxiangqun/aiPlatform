"""Code-review gold eval — ReviewBench-style Precision/Recall for autoreview.

Thin harness: YAML/JSON cases under ``~/.aiplat/eval/code_review_gold/``.
No parallel ReviewBench DB. Profiles map onto existing autoreview args.

Production callers: CoreFacade.run_code_review_gold_eval,
scripts/eval_code_review_gold.py, platform apps/eval code_review_gold router.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ReviewBench-style noise tiers → existing autoreview handler params
PROFILE_ARGS: Dict[str, Dict[str, Any]] = {
    "low_noise": {
        "panel": False,
        "focus": "comprehensive",
        "mode": "quick",
        "preset": "code_review",
        "auto_fix": False,
    },
    "balanced": {
        "panel": "auto",
        "focus": "comprehensive",
        "mode": "quick",
        "preset": "code_review",
        "auto_fix": False,
    },
    "high_coverage": {
        "panel": True,
        "focus": "security",
        "mode": "deep",
        "preset": "security",
        "auto_fix": False,
    },
}

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_\u4e00-\u9fff]{2,}")


def _safe_tenant(tenant_id: str = "") -> str:
    t = re.sub(r"[^a-zA-Z0-9_\-]", "_", (tenant_id or "default").strip())[:64]
    return t or "default"


def _safe_case_id(case_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]", "_", (case_id or "").strip())[:80]
    return s or "unnamed"


def default_gold_dir(tenant_id: str = "") -> Path:
    """Runtime gold cases dir. Tenant-scoped under eval/tenants/{id}/code_review_gold/.

    Empty tenant_id → legacy ``eval/code_review_gold`` (backward compatible).
    """
    from core.utils.paths import get_aiplat_data_dir

    if not (tenant_id or "").strip():
        return Path(get_aiplat_data_dir("eval/code_review_gold"))
    return Path(get_aiplat_data_dir(f"eval/tenants/{_safe_tenant(tenant_id)}/code_review_gold"))


def reports_dir(tenant_id: str = "") -> Path:
    """Append-only JSONL eval runs (ReviewBench regression history)."""
    from core.utils.paths import get_aiplat_data_dir

    tid = _safe_tenant(tenant_id) if (tenant_id or "").strip() else "default"
    return Path(get_aiplat_data_dir(f"eval/tenants/{tid}/code_review_gold_reports"))


def resolve_gold_dir(gold_dir: Optional[str] = None, tenant_id: str = "") -> Path:
    if gold_dir:
        return Path(gold_dir)
    return default_gold_dir(tenant_id)


def profile_to_autoreview_args(profile: str) -> Dict[str, Any]:
    """Map noise tier → autoreview execute() kwargs (copy)."""
    key = (profile or "balanced").strip().lower()
    if key not in PROFILE_ARGS:
        raise ValueError(f"unknown profile '{profile}'; choose {sorted(PROFILE_ARGS)}")
    return dict(PROFILE_ARGS[key])


def _tokenize(text: str) -> set:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _norm_path(p: str) -> str:
    return (p or "").replace("\\", "/").lstrip("./").lower()


@dataclass
class GoldFinding:
    file: str = ""
    line: int = 0
    severity: str = "P1"
    keywords: List[str] = field(default_factory=list)
    description: str = ""
    category: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GoldFinding":
        kws = d.get("keywords") or []
        if isinstance(kws, str):
            kws = [x.strip() for x in kws.split(",") if x.strip()]
        return cls(
            file=str(d.get("file") or ""),
            line=int(d.get("line") or 0),
            severity=str(d.get("severity") or "P1").upper(),
            keywords=[str(k) for k in kws][:24],
            description=str(d.get("description") or ""),
            category=str(d.get("category") or ""),
        )


@dataclass
class GoldCase:
    id: str
    gold_findings: List[GoldFinding]
    target: str = ""
    profile: str = ""
    description: str = ""
    # Offline / unit: skip live autoreview and score these predictions
    predicted: List[Dict[str, Any]] = field(default_factory=list)
    line_window: int = 5
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any], *, default_id: str = "") -> "GoldCase":
        findings = [
            GoldFinding.from_dict(x)
            for x in (d.get("gold_findings") or d.get("findings") or [])
            if isinstance(x, dict)
        ]
        pred = d.get("predicted") or d.get("predicted_fixture") or []
        if not isinstance(pred, list):
            pred = []
        return cls(
            id=str(d.get("id") or default_id or "unnamed"),
            gold_findings=findings,
            target=str(d.get("target") or ""),
            profile=str(d.get("profile") or ""),
            description=str(d.get("description") or ""),
            predicted=[x for x in pred if isinstance(x, dict)],
            line_window=max(0, int(d.get("line_window") or 5)),
            meta={k: v for k, v in d.items() if k not in (
                "id", "gold_findings", "findings", "target", "profile",
                "description", "predicted", "predicted_fixture", "line_window",
            )},
        )


def persist_eval_report(result: Dict[str, Any], *, tenant_id: str = "") -> Optional[str]:
    """Append one eval run as JSONL. Never mutates gold cases."""
    try:
        out_dir = reports_dir(tenant_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        path = out_dir / "runs.jsonl"
        slim = {k: v for k, v in result.items() if k != "cases"}
        slim["case_ids"] = [c.get("id") for c in (result.get("cases") or []) if isinstance(c, dict)]
        slim["written_at"] = ts
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")
        return str(path)
    except Exception as e:
        logger.debug("persist_eval_report skipped: %s", e, exc_info=True)
        return None


def list_eval_reports(*, tenant_id: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    path = reports_dir(tenant_id) / "runs.jsonl"
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows[-max(1, min(int(limit or 20), 100)):]


def novel_findings_from_case(scored: Dict[str, Any]) -> List[Dict[str, Any]]:
    """P0/P1 unmatched predictions — candidates, never auto-written into gold."""
    out: List[Dict[str, Any]] = []
    for fp in scored.get("false_positives") or []:
        if not isinstance(fp, dict):
            continue
        sev = str(fp.get("severity") or "P2").upper()
        if sev in ("P0", "P1"):
            out.append({**fp, "case_id": scored.get("id"), "kind": "novel_candidate"})
    return out


def _maybe_record_novel(novels: Sequence[Dict[str, Any]], *, source: str = "code_review_gold") -> List[Dict[str, Any]]:
    """shared_memory (medium) + optional experience_feedback pending; never rewrites gold.

    Promotion → Team Brain is handled by platform ExperienceStore on confirm.
    """
    recorded: List[Dict[str, Any]] = []
    if not novels:
        return recorded
    try:
        from core.harness.memory.shared_memory import record_learning
    except Exception:
        record_learning = None  # type: ignore
    for n in novels[:20]:
        desc = str(n.get("description") or "")[:240]
        key = f"team_solution:review_novel:{_safe_case_id(str(n.get('case_id') or ''))}:{_safe_case_id(str(n.get('file') or 'x'))}"
        if record_learning is None:
            continue
        try:
            rec = record_learning(
                key=key,
                value=desc or key,
                source_agent=source,
                confidence="medium",
            )
            recorded.append(rec.to_dict() if hasattr(rec, "to_dict") else {"key": key})
        except Exception as e:
            logger.debug("record novel skipped: %s", e, exc_info=True)
    # Experience L2 pending (P0 require_review); promote path already → Team Brain
    exp_on = (os.environ.get("AIPLAT_NOVEL_TO_EXPERIENCE") or "true").strip().lower() not in (
        "0", "false", "no", "off",
    )
    if exp_on:
        try:
            from core.harness.evaluation.novel_experience_bridge import register_novel_as_experience

            exp_rows = register_novel_as_experience(novels, source=source)
            for row in exp_rows:
                recorded.append({"channel": "experience_feedback", **row})
        except Exception as e:
            logger.debug("novel→experience skipped: %s", e, exc_info=True)
    return recorded


def load_gold_cases(gold_dir: Optional[str] = None, *, tenant_id: str = "") -> List[GoldCase]:
    """Load ``*.yaml`` / ``*.yml`` / ``*.json`` from gold directory."""
    root = resolve_gold_dir(gold_dir, tenant_id)
    if not root.is_dir():
        return []
    cases: List[GoldCase] = []
    for path in sorted(root.iterdir()):
        if path.suffix.lower() not in (".yaml", ".yml", ".json") or path.name.startswith("_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".json":
                data = json.loads(text)
            else:
                import yaml

                data = yaml.safe_load(text)
            if data is None:
                continue
            if isinstance(data, list):
                for i, item in enumerate(data):
                    if isinstance(item, dict):
                        cases.append(GoldCase.from_dict(item, default_id=f"{path.stem}_{i}"))
            elif isinstance(data, dict):
                # Allow {"cases": [...]} wrapper
                if isinstance(data.get("cases"), list):
                    for i, item in enumerate(data["cases"]):
                        if isinstance(item, dict):
                            cases.append(GoldCase.from_dict(item, default_id=f"{path.stem}_{i}"))
                else:
                    cases.append(GoldCase.from_dict(data, default_id=path.stem))
        except Exception as e:
            logger.warning("skip gold file %s: %s", path, e, exc_info=True)
    # Deduplicate by id (later files win) so singleton YAML + batch_* do not double-score.
    by_id: Dict[str, GoldCase] = {}
    for c in cases:
        cid = str(c.id or "").strip()
        if cid:
            by_id[cid] = c
    return list(by_id.values()) if by_id else cases


def _issue_blob(issue: Dict[str, Any]) -> str:
    return " ".join(
        str(issue.get(k) or "")
        for k in ("description", "title", "fix_suggestion", "suggested_fix", "category", "file")
    )


def finding_matches_issue(
    gold: GoldFinding,
    issue: Dict[str, Any],
    *,
    line_window: int = 5,
) -> bool:
    """True if predicted issue covers this gold finding (file + keywords + soft line)."""
    gfile = _norm_path(gold.file)
    ifile = _norm_path(str(issue.get("file") or ""))
    if gfile and ifile:
        if gfile != ifile and not ifile.endswith("/" + gfile) and not gfile.endswith("/" + ifile):
            # basename fallback
            if Path(gfile).name != Path(ifile).name:
                return False

    if gold.line and issue.get("line") and line_window >= 0:
        try:
            iline = int(issue.get("line") or 0)
        except (TypeError, ValueError):
            iline = 0
        if iline and abs(iline - gold.line) > line_window:
            return False

    keys = [k.lower() for k in gold.keywords if k]
    if not keys:
        keys = list(_tokenize(gold.description))[:8]
    if not keys:
        return bool(gfile and ifile)  # path-only soft match

    blob = _issue_blob(issue).lower()
    hits = sum(1 for k in keys if k.lower() in blob)
    need = 1 if len(keys) <= 2 else max(1, (len(keys) + 1) // 2)
    return hits >= need


def match_review_findings(
    predicted: Sequence[Dict[str, Any]],
    gold_findings: Sequence[GoldFinding],
    *,
    line_window: int = 5,
) -> Dict[str, Any]:
    """Greedy 1:1 match → precision / recall / P0 recall / comment_count."""
    preds = [dict(p) for p in predicted if isinstance(p, dict)]
    golds = list(gold_findings)
    matched_gold: set = set()
    matched_pred: set = set()
    pairs: List[Dict[str, Any]] = []

    # Prefer higher-severity gold first
    order = sorted(range(len(golds)), key=lambda i: (0 if golds[i].severity == "P0" else 1 if golds[i].severity == "P1" else 2, i))
    for gi in order:
        g = golds[gi]
        best_j = -1
        for j, p in enumerate(preds):
            if j in matched_pred:
                continue
            if finding_matches_issue(g, p, line_window=line_window):
                best_j = j
                break
        if best_j >= 0:
            matched_gold.add(gi)
            matched_pred.add(best_j)
            pairs.append({"gold_index": gi, "pred_index": best_j, "severity": g.severity})

    tp = len(matched_gold)
    fp = len(preds) - len(matched_pred)
    fn = len(golds) - tp
    precision = tp / (tp + fp) if (tp + fp) else (1.0 if not golds else 0.0)
    recall = tp / len(golds) if golds else (1.0 if not preds else 0.0)

    p0_golds = [i for i, g in enumerate(golds) if g.severity == "P0"]
    p0_hit = sum(1 for i in p0_golds if i in matched_gold)
    p0_recall = p0_hit / len(p0_golds) if p0_golds else None

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "p0_recall": round(p0_recall, 4) if p0_recall is not None else None,
        "comment_count": len(preds),
        "gold_count": len(golds),
        "matched_pairs": pairs,
        "unmatched_gold": [
            {"index": i, "file": golds[i].file, "severity": golds[i].severity, "description": golds[i].description[:120]}
            for i in range(len(golds))
            if i not in matched_gold
        ],
        "false_positives": [
            {"index": j, "file": preds[j].get("file"), "severity": preds[j].get("severity"),
             "description": str(preds[j].get("description") or "")[:120]}
            for j in range(len(preds))
            if j not in matched_pred
        ],
    }


def score_case(
    case: GoldCase,
    predicted: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    metrics = match_review_findings(
        predicted,
        case.gold_findings,
        line_window=case.line_window,
    )
    return {
        "id": case.id,
        "description": case.description,
        "target": case.target,
        **metrics,
    }


async def _default_execute(params: Dict[str, Any]) -> Dict[str, Any]:
    from core.engine.skills.autoreview.handler import execute

    return await execute(params)


async def run_code_review_gold_eval(
    *,
    profile: str = "balanced",
    gold_dir: Optional[str] = None,
    case_ids: Optional[Sequence[str]] = None,
    match_only: bool = False,
    execute_fn: Optional[Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]] = None,
    limit: int = 0,
    tenant_id: str = "",
    persist: bool = True,
    record_novel: bool = False,
) -> Dict[str, Any]:
    """Run gold eval: match_only uses embedded ``predicted``; else live autoreview.

    Returns aggregate precision/recall/p0_recall + per-case breakdown.
    Novel (unmatched P0/P1) findings are listed; gold files are never rewritten.
    """
    t0 = time.time()
    cases = load_gold_cases(gold_dir, tenant_id=tenant_id)
    if case_ids:
        want = {str(x) for x in case_ids}
        cases = [c for c in cases if c.id in want]
    if limit and limit > 0:
        cases = cases[: int(limit)]

    if not cases:
        return {
            "ok": False,
            "reason": "no_gold_cases",
            "gold_dir": str(resolve_gold_dir(gold_dir, tenant_id)),
            "profile": profile,
            "tenant_id": tenant_id or "",
            "cases": [],
        }

    base_args = profile_to_autoreview_args(profile)
    runner = execute_fn or _default_execute
    results: List[Dict[str, Any]] = []

    for case in cases:
        case_profile = case.profile or profile
        try:
            args = profile_to_autoreview_args(case_profile)
        except ValueError:
            args = dict(base_args)
            case_profile = profile

        use_fixture = match_only or bool(case.predicted and not case.target)
        if use_fixture:
            if not case.predicted:
                results.append({
                    "id": case.id,
                    "ok": False,
                    "reason": "missing_predicted_fixture",
                    "precision": 0.0,
                    "recall": 0.0,
                    "p0_recall": None,
                    "comment_count": 0,
                })
                continue
            predicted = list(case.predicted)
            exec_meta: Dict[str, Any] = {"mode": "match_only"}
        else:
            if not case.target:
                results.append({
                    "id": case.id,
                    "ok": False,
                    "reason": "missing_target",
                    "precision": 0.0,
                    "recall": 0.0,
                    "p0_recall": None,
                    "comment_count": 0,
                })
                continue
            params = {**args, "target": case.target}
            try:
                out = await runner(params)
                report = (out or {}).get("report") or {}
                predicted = list(report.get("issues") or [])
                exec_meta = {
                    "mode": "live",
                    "clean": (out or {}).get("clean"),
                    "routing": (out or {}).get("routing"),
                }
            except Exception as e:
                logger.warning("autoreview failed for gold case %s: %s", case.id, e, exc_info=True)
                results.append({
                    "id": case.id,
                    "ok": False,
                    "reason": str(e)[:200],
                    "precision": 0.0,
                    "recall": 0.0,
                    "p0_recall": None,
                    "comment_count": 0,
                })
                continue

        scored = score_case(case, predicted)
        scored["ok"] = True
        scored["profile"] = case_profile
        scored["exec"] = exec_meta
        results.append(scored)

    ok_rows = [r for r in results if r.get("ok")]
    def _avg(key: str) -> Optional[float]:
        vals = [float(r[key]) for r in ok_rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    p0_vals = [float(r["p0_recall"]) for r in ok_rows if r.get("p0_recall") is not None]
    novels: List[Dict[str, Any]] = []
    for r in ok_rows:
        novels.extend(novel_findings_from_case(r))
    recorded: List[Dict[str, Any]] = []
    if record_novel:
        recorded = _maybe_record_novel(novels)

    try:
        from core.harness.evaluation.harness_factors import collect_harness_factors

        factors = collect_harness_factors(extra={"noise_profile": profile})
    except Exception:
        factors = {"noise_profile": profile}

    payload = {
        "ok": True,
        "profile": profile,
        "tenant_id": tenant_id or "",
        "gold_dir": str(resolve_gold_dir(gold_dir, tenant_id)),
        "case_count": len(results),
        "scored_count": len(ok_rows),
        "precision": _avg("precision"),
        "recall": _avg("recall"),
        "p0_recall": round(sum(p0_vals) / len(p0_vals), 4) if p0_vals else None,
        "avg_comment_count": _avg("comment_count"),
        "elapsed_sec": round(time.time() - t0, 3),
        "profiles_available": sorted(PROFILE_ARGS.keys()),
        "novel_count": len(novels),
        "novel_findings": novels,
        "novel_recorded": recorded,
        "harness_factors": factors,
        "cases": results,
    }
    if persist:
        payload["report_path"] = persist_eval_report(payload, tenant_id=tenant_id)
    return payload


def list_profiles() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in PROFILE_ARGS.items()}
