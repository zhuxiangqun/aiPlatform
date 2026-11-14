"""Generated-app Pi delivery smoke (eval-exam-runtime-tiers §6).

Offline: export/structural checks. Live: invoke `pi` CLI print token.
Does not change Agent workspace_execute path or process_split_authorized.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.utils.model_injection import get_default_model
from core.apps.eval.service.eval_plan import (
    attach_evaluation_plan,
    compile_plan_for_object,
)
from core.apps.eval.service.exam_runtime_tier import (
    annotate_generated_app_runtime,
    merge_runtime_fields,
)


def _with_generated_app_plan(out: Dict[str, Any], *, live: bool, object_id: str) -> Dict[str, Any]:
    try:
        plan = compile_plan_for_object(
            object_type="generated_app",
            object_id=object_id or "generated_app",
            set_ids=["generated_app/pi_smoke", "generated_app/runs_eval"],
            live=bool(live),
            source_refs=["generated_app_pi_ops"],
        )
        return attach_evaluation_plan(out, plan)
    except Exception:  # noqa: BLE001 — plan advisory must not fail pi smoke
        return out
from core.utils.paths import get_aiplat_data_dir

_log = logging.getLogger("aiplat.eval.generated_app_pi")

_PI_OK_TOKEN = "AIPLAT_PI_OK"
_DEFAULT_PROMPT = (
    f"Reply with exactly the token {_PI_OK_TOKEN} and nothing else."
)


def _workspace_root() -> Path:
    # …/aiPlatform/aiPlat-core/core/apps/eval/service → parents[5]=aiPlatform
    return Path(__file__).resolve().parents[5]


def _sample_app_home() -> Path:
    return (
        _workspace_root()
        / "packages"
        / "aiplat-pi-runtime"
        / "fixtures"
        / "sample-app"
    )


def _export_script() -> Path:
    return _workspace_root() / "scripts" / "export_pi_bundle.py"


def _load_export_bundle():
    script = _export_script()
    if not script.is_file():
        raise FileNotFoundError(f"export_pi_bundle.py missing: {script}")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "aiplat_export_pi_bundle_eval", script
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load export_pi_bundle.py")
    mod = sys.modules.get(spec.name)
    if mod is None:
        mod = importlib.util.module_from_spec(spec)
        ws = str(_workspace_root())
        if ws not in sys.path:
            sys.path.insert(0, ws)
        spec.loader.exec_module(mod)
    fn = getattr(mod, "export_bundle", None)
    if fn is None:
        raise RuntimeError("export_bundle() missing")
    return fn


def _structural_check(bundle: Path) -> Dict[str, Any]:
    errors: List[str] = []
    if not bundle.is_dir():
        return {"ok": False, "errors": [f"bundle missing: {bundle}"]}
    manifest = bundle / "agent_manifest.json"
    if not manifest.is_file():
        errors.append("missing agent_manifest.json")
    pkg = bundle / "package.json"
    if not pkg.is_file():
        errors.append("missing package.json")
    else:
        try:
            obj = json.loads(pkg.read_text(encoding="utf-8"))
            if "pi" not in obj:
                errors.append("package.json missing pi key")
        except Exception as e:
            errors.append(f"package.json unreadable: {e}")
    agents = bundle / "agents"
    if not agents.is_dir() and not (bundle / "AGENT.md").is_file():
        errors.append("missing agents/ or AGENT.md")
    skills = bundle / "skills"
    if not skills.is_dir():
        errors.append("missing skills/")
    ext = bundle / "extensions" / "aiplat-app.ts"
    if not ext.is_file():
        errors.append("missing extensions/aiplat-app.ts")
    return {"ok": not errors, "errors": errors}


def _resolve_app_home(
    *,
    source: str,
    project_id: str,
    app_home: str,
) -> Dict[str, Any]:
    src = (source or "sample").strip().lower()
    if src == "path":
        p = Path(app_home).expanduser()
        if not p.is_dir():
            return {"ok": False, "error": f"app_home missing: {p}"}
        return {"ok": True, "app_home": p, "source": "path", "project_id": ""}
    if src == "project":
        pid = (project_id or "").strip()
        if not pid:
            return {"ok": False, "error": "project_id required for source=project"}
        current = Path(get_aiplat_data_dir(f"apps/{pid}/current"))
        if not current.is_dir():
            return {
                "ok": False,
                "error": f"app current missing: {current}",
                "project_id": pid,
            }
        return {
            "ok": True,
            "app_home": current,
            "source": "project",
            "project_id": pid,
        }
    sample = _sample_app_home()
    if not sample.is_dir():
        return {"ok": False, "error": f"sample-app missing: {sample}"}
    return {
        "ok": True,
        "app_home": sample,
        "source": "sample",
        "project_id": "sample",
    }


def _ensure_export(*, app_home: Path, project_id: str) -> Dict[str, Any]:
    out = Path(get_aiplat_data_dir(f"eval/pi-smoke/{project_id or 'bundle'}"))
    try:
        export_fn = _load_export_bundle()
        written = export_fn(
            app_home=app_home,
            out=out,
            project_id=project_id or "pi-smoke",
        )
    except SystemExit as e:
        return {"ok": False, "error": f"export aborted: {e}", "app_home": str(app_home)}
    except Exception as e:
        _log.warning("pi export failed: %s", e, exc_info=True)
        return {"ok": False, "error": str(e), "app_home": str(app_home)}
    bundle = Path(written) if written else out
    check = _structural_check(bundle)
    return {
        "ok": bool(check.get("ok")),
        "app_home": str(app_home),
        "pi_bundle": str(bundle),
        "structural": check,
        "error": None if check.get("ok") else "; ".join(check.get("errors") or []),
    }


def _run_pi_cli(*, bundle: Path, model: str, timeout_s: float) -> Dict[str, Any]:
    pi_bin = shutil.which("pi")
    if not pi_bin:
        return {
            "ok": False,
            "error": "pi CLI not found on PATH",
            "pi_invoked": False,
        }
    env = os.environ.copy()
    env["AIPLAT_APP_HOME"] = str(bundle)
    cmd = [
        pi_bin,
        "-e",
        str(bundle),
        "-p",
        "--no-session",
        "--model",
        model,
        _DEFAULT_PROMPT,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"pi CLI timed out after {timeout_s}s",
            "pi_invoked": True,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "pi_invoked": True}
    body = (proc.stdout or "") + "\n" + (proc.stderr or "")
    token_ok = _PI_OK_TOKEN in body
    return {
        "ok": token_ok and proc.returncode == 0,
        "pi_invoked": True,
        "returncode": proc.returncode,
        "token_ok": token_ok,
        "output_tail": body[-1200:],
        "error": None
        if token_ok and proc.returncode == 0
        else (
            "token missing in pi output"
            if not token_ok
            else f"pi exit {proc.returncode}"
        ),
    }


def run_generated_app_pi_smoke(
    *,
    source: str = "sample",
    project_id: str = "",
    app_home: str = "",
    live: bool = False,
    model: str = "",
    timeout_s: float = 90.0,
) -> Dict[str, Any]:
    """Export + structural (always); optional live `pi` CLI print smoke.

    Args:
        source: source 参数。
        project_id: project 标识。
        app_home: app_home 参数。
        live: 是否 live（非 fixture）路径。
        model: 模型名。
        timeout_s: timeout_s 参数。
    """
    resolved = _resolve_app_home(
        source=source, project_id=project_id, app_home=app_home
    )
    if not resolved.get("ok"):
        out = {
            "ok": False,
            "error": resolved.get("error") or "resolve_failed",
            "source": source,
            "live": bool(live),
            "accuracy_claim": False,
        }
        return _with_generated_app_plan(
            merge_runtime_fields(
                out, annotate_generated_app_runtime(mode="pi_offline")
            ),
            live=False,
            object_id=str(project_id or source or "generated_app"),
        )

    exported = _ensure_export(
        app_home=resolved["app_home"],
        project_id=str(resolved.get("project_id") or "pi-smoke"),
    )
    oid = str(resolved.get("project_id") or project_id or source or "generated_app")
    base: Dict[str, Any] = {
        "ok": bool(exported.get("ok")),
        "source": resolved.get("source"),
        "project_id": resolved.get("project_id") or project_id or "",
        "app_home": exported.get("app_home"),
        "pi_bundle": exported.get("pi_bundle"),
        "structural": exported.get("structural"),
        "live": bool(live),
        "accuracy_claim": False,
        "honesty": (
            "Pi 交付态冒烟 · 目标 runtime_tier=pi · "
            "≠ workspace_execute · ≠ runs_eval 充分性"
        ),
    }
    if not exported.get("ok"):
        base["error"] = exported.get("error") or "export_or_structural_failed"
        return _with_generated_app_plan(
            merge_runtime_fields(
                base, annotate_generated_app_runtime(mode="pi_offline")
            ),
            live=False,
            object_id=oid,
        )

    if not live:
        base["msg"] = "offline export+structural ok; pi CLI not invoked"
        return _with_generated_app_plan(
            merge_runtime_fields(
                base, annotate_generated_app_runtime(mode="pi_offline")
            ),
            live=False,
            object_id=oid,
        )

    mdl = (model or get_default_model("pi") or "ollama/qwen2.5:3b").strip()
    cli = _run_pi_cli(
        bundle=Path(str(exported["pi_bundle"])),
        model=mdl,
        timeout_s=float(timeout_s or 90.0),
    )
    base["pi_cli"] = {
        k: cli.get(k)
        for k in ("pi_invoked", "returncode", "token_ok", "error", "output_tail")
        if k in cli
    }
    base["model"] = mdl
    if cli.get("ok") and cli.get("pi_invoked"):
        base["ok"] = True
        base["msg"] = "live pi CLI smoke ok"
        return _with_generated_app_plan(
            merge_runtime_fields(
                base, annotate_generated_app_runtime(mode="pi_live")
            ),
            live=True,
            object_id=oid,
        )

    # Live requested but Pi did not succeed — still tier=pi, claim=false
    base["ok"] = False
    base["error"] = cli.get("error") or "pi_live_failed"
    base["msg"] = "live requested but pi host did not confirm token"
    ann = annotate_generated_app_runtime(mode="pi_offline")
    if not cli.get("pi_invoked"):
        ann = {
            **ann,
            "runtime_claim_reason": "pi path not wired; pi CLI unavailable",
        }
    else:
        ann = {
            **ann,
            "runtime_claim_reason": (
                "pi CLI invoked but smoke failed; do not claim pi delivery"
            ),
        }
    return _with_generated_app_plan(
        merge_runtime_fields(base, ann), live=False, object_id=oid
    )
