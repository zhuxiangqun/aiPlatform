"""T0/T1a/T1b: team harness paths, schema, lock, FF-only pull, async autosync.

Git team repo = reviewable publish source.
Runtime = ~/.aiplat/team/ (pull-only) + ~/.aiplat/local/ (never overwritten by pull).
T1b: SESSION_START / factory entry fires background pull when AUTOSYNC=1; never blocks.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional

logger = logging.getLogger(__name__)

_autosync_lock = threading.Lock()
_autosync_inflight = False

SCHEMA_VERSION = "1"
_SEED_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "workspace_seeds"
    / "team_harness"
    / "team_harness.yaml"
)


def aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()


def load_team_harness_schema() -> Dict[str, Any]:
    """Load T0 contract (seed, then optional home override with same/newer schema)."""
    data = _read_yaml(_SEED_SCHEMA) or {}
    home_schema = aiplat_home() / "team_harness.yaml"
    if home_schema.is_file():
        overlay = _read_yaml(home_schema) or {}
        if overlay:
            # Home may add resources; keep seed schema_version floor
            seed_ver = str(data.get("schema_version") or SCHEMA_VERSION)
            home_ver = str(overlay.get("schema_version") or seed_ver)
            merged = {**data, **overlay}
            merged["schema_version"] = home_ver if home_ver >= seed_ver else seed_ver
            if isinstance(data.get("resources"), dict) and isinstance(
                overlay.get("resources"), dict
            ):
                merged["resources"] = {**data["resources"], **overlay["resources"]}
            data = merged
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("paths", {})
    data.setdefault("resources", {})
    return data


def materialize_team_harness_schema(*, overwrite: bool = False) -> Path:
    """Copy seed contract to ~/.aiplat/team_harness.yaml when missing."""
    home = aiplat_home()
    home.mkdir(parents=True, exist_ok=True)
    dst = home / "team_harness.yaml"
    if dst.exists() and not overwrite:
        return dst
    if _SEED_SCHEMA.is_file():
        shutil.copy2(_SEED_SCHEMA, dst)
    else:
        dst.write_text(
            f"schema_version: \"{SCHEMA_VERSION}\"\npaths: {{}}\nresources: {{}}\n",
            encoding="utf-8",
        )
    return dst


def team_dir(schema: Optional[Mapping[str, Any]] = None) -> Path:
    s = schema or load_team_harness_schema()
    sub = str((s.get("paths") or {}).get("team_subdir") or "team")
    return aiplat_home() / sub


def local_dir(schema: Optional[Mapping[str, Any]] = None) -> Path:
    s = schema or load_team_harness_schema()
    sub = str((s.get("paths") or {}).get("local_subdir") or "local")
    return aiplat_home() / sub


def lock_path(schema: Optional[Mapping[str, Any]] = None) -> Path:
    s = schema or load_team_harness_schema()
    name = str((s.get("paths") or {}).get("lock_file") or "team_harness.lock")
    return aiplat_home() / name


def backups_dir(schema: Optional[Mapping[str, Any]] = None) -> Path:
    s = schema or load_team_harness_schema()
    sub = str((s.get("paths") or {}).get("backups_subdir") or "team_backups")
    return aiplat_home() / sub


def meta_path(schema: Optional[Mapping[str, Any]] = None) -> Path:
    s = schema or load_team_harness_schema()
    rel = str(
        (s.get("paths") or {}).get("meta_file") or "team_harness_meta.json"
    )
    # Meta must live outside team/ git worktree so writes do not dirty the tree.
    return aiplat_home() / rel


def config_path(schema: Optional[Mapping[str, Any]] = None) -> Path:
    s = schema or load_team_harness_schema()
    name = str(
        (s.get("paths") or {}).get("config_file") or "team_harness_config.json"
    )
    return aiplat_home() / name


def ensure_team_local_dirs(schema: Optional[Mapping[str, Any]] = None) -> None:
    team_dir(schema).mkdir(parents=True, exist_ok=True)
    local_dir(schema).mkdir(parents=True, exist_ok=True)
    backups_dir(schema).mkdir(parents=True, exist_ok=True)


def resource_relpath(name: str, schema: Optional[Mapping[str, Any]] = None) -> str:
    s = schema or load_team_harness_schema()
    resources = s.get("resources") or {}
    entry = resources.get(name) if isinstance(resources, Mapping) else None
    if isinstance(entry, Mapping) and entry.get("path"):
        return str(entry["path"])
    return str(name)


def is_resource_locked(name: str, schema: Optional[Mapping[str, Any]] = None) -> bool:
    s = schema or load_team_harness_schema()
    resources = s.get("resources") or {}
    entry = resources.get(name) if isinstance(resources, Mapping) else None
    if isinstance(entry, Mapping):
        return bool(entry.get("locked", True))
    return True


def read_config() -> Dict[str, Any]:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_config(cfg: Mapping[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(cfg), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def configure_team_harness(repo_url: str, *, branch: str = "main") -> Dict[str, Any]:
    """Persist publish-source URL (does not pull)."""
    cfg = read_config()
    cfg["repo_url"] = str(repo_url or "").strip()
    cfg["branch"] = str(branch or "main").strip() or "main"
    cfg["updated_at"] = time.time()
    write_config(cfg)
    materialize_team_harness_schema()
    ensure_team_local_dirs()
    return dict(cfg)


def read_meta() -> Dict[str, Any]:
    path = meta_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_meta(meta: Mapping[str, Any]) -> Path:
    path = meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(meta), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _read_yaml(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        import yaml  # type: ignore
    except ImportError:
        logger.warning("PyYAML missing; cannot load %s", path)
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to load %s: %s", path, e)
        return None
    return data if isinstance(data, dict) else None


def _run_git(
    args: List[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def team_is_dirty(team: Optional[Path] = None) -> bool:
    """True when team/ has local modifications (blocks pull)."""
    root = team or team_dir()
    if not is_git_repo(root):
        return False
    try:
        proc = _run_git(["status", "--porcelain"], cwd=root, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool((proc.stdout or "").strip())


@contextmanager
def team_harness_lock(timeout_sec: float = 30.0) -> Iterator[None]:
    """Exclusive lock for manual pull vs future autosync."""
    ensure_team_local_dirs()
    path = lock_path()
    deadline = time.time() + max(1.0, float(timeout_sec))
    fh = None
    while True:
        try:
            fh = open(path, "a+", encoding="utf-8")
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fh.seek(0)
            fh.truncate()
            fh.write(f"pid={os.getpid()} ts={time.time()}\n")
            fh.flush()
            break
        except (OSError, BlockingIOError):
            if fh is not None:
                try:
                    fh.close()
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                fh = None
            if time.time() >= deadline:
                raise TimeoutError(f"team_harness lock timeout: {path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            if fh is not None:
                if os.name != "nt":
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                fh.close()
        except Exception:
            logger.debug("unlock team_harness failed", exc_info=True)


def backup_team_tree(*, label: str = "") -> Optional[Path]:
    """Copy current team/ (without .git) to backups/ for rollback."""
    root = team_dir()
    if not root.is_dir():
        return None
    backups_dir().mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    name = f"{stamp}_{label}".strip("_") if label else stamp
    dest = backups_dir() / name
    if dest.exists():
        dest = backups_dir() / f"{name}_{os.getpid()}"
    shutil.copytree(root, dest, ignore=shutil.ignore_patterns(".git"))
    return dest


def restore_team_backup(backup: Path) -> Dict[str, Any]:
    """Restore team/ content from a backup (preserves .git if present)."""
    root = team_dir()
    if not backup.is_dir():
        return {"ok": False, "error": f"backup missing: {backup}"}
    ensure_team_local_dirs()
    # Remove non-git children then copy backup files in
    for child in list(root.iterdir()):
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)
    for child in backup.iterdir():
        target = root / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)
    return {"ok": True, "restored_from": str(backup), "team": str(root)}


def pull_team_harness(
    repo_url: str = "",
    *,
    branch: str = "",
    dry_run: bool = False,
    discard_dirty: bool = False,
    lock_timeout_sec: float = 30.0,
) -> Dict[str, Any]:
    """T1a: FF-only pull into ~/.aiplat/team/. Never writes local/.

    Returns ``{ok, skipped, blocked, error, commit, backup, dry_run, ...}``.
    """
    materialize_team_harness_schema()
    schema = load_team_harness_schema()
    ensure_team_local_dirs(schema)
    local_snapshot = _snapshot_tree(local_dir(schema))

    cfg = read_config()
    url = str(repo_url or cfg.get("repo_url") or "").strip()
    br = str(branch or cfg.get("branch") or "main").strip() or "main"
    if not url:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_repo",
            "team": str(team_dir(schema)),
            "local": str(local_dir(schema)),
        }

    out: Dict[str, Any] = {
        "ok": False,
        "skipped": False,
        "blocked": False,
        "dry_run": bool(dry_run),
        "repo_url": url,
        "branch": br,
        "team": str(team_dir(schema)),
        "local": str(local_dir(schema)),
        "schema_version": str(schema.get("schema_version") or SCHEMA_VERSION),
    }

    try:
        with team_harness_lock(timeout_sec=lock_timeout_sec):
            root = team_dir(schema)
            if dry_run:
                out.update(
                    {
                        "ok": True,
                        "dry_run": True,
                        "would_pull": url,
                        "dirty": team_is_dirty(root) if is_git_repo(root) else False,
                        "is_clone": is_git_repo(root),
                    }
                )
                return out

            if not is_git_repo(root):
                # Fresh clone into team/
                if any(root.iterdir()):
                    # Non-empty non-git team/ — refuse to clobber
                    out["blocked"] = True
                    out["error"] = "team_dir_nonempty_not_git"
                    return out
                _clone_into(url, root, branch=br)
            else:
                if team_is_dirty(root) and not discard_dirty:
                    out["blocked"] = True
                    out["error"] = "dirty_team_blocks_pull"
                    out["hint"] = "stash/discard local team/ edits or pass discard_dirty"
                    return out
                if team_is_dirty(root) and discard_dirty:
                    _run_git(["reset", "--hard", "HEAD"], cwd=root, check=False)
                    _run_git(["clean", "-fd"], cwd=root, check=False)

                backup = backup_team_tree(label="pre_pull")
                out["backup"] = str(backup) if backup else ""
                try:
                    _ff_pull(root, url=url, branch=br)
                except Exception as e:
                    out["error"] = f"ff_failed:{e}"
                    if backup:
                        restore_team_backup(backup)
                        out["restored"] = True
                    return out

            # Ensure remote URL recorded
            try:
                _run_git(["remote", "set-url", "origin", url], cwd=root, check=False)
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            commit = ""
            try:
                commit = _run_git(
                    ["rev-parse", "HEAD"], cwd=root, check=False
                ).stdout.strip()
            except Exception:
                commit = ""

            write_meta(
                {
                    "repo_url": url,
                    "branch": br,
                    "commit": commit,
                    "pulled_at": time.time(),
                    "schema_version": str(schema.get("schema_version") or SCHEMA_VERSION),
                }
            )
            configure_team_harness(url, branch=br)

            # Invariant: local/ untouched
            if _snapshot_tree(local_dir(schema)) != local_snapshot:
                out["error"] = "local_dir_mutated"
                return out

            out.update({"ok": True, "commit": commit, "dirty": False})
            # F-T1: best-effort materialize factory seeds after successful pull
            try:
                from core.harness.team_factory_seeds import apply_team_factory_seeds

                seeds = apply_team_factory_seeds()
                out["factory_seeds"] = seeds
            except Exception as e:
                logger.debug("apply_team_factory_seeds after pull skipped: %s", e)
                out["factory_seeds"] = {"ok": False, "error": str(e)[:200]}
            return out
    except TimeoutError as e:
        out["error"] = str(e)
        out["blocked"] = True
        return out
    except Exception as e:
        logger.debug("pull_team_harness failed", exc_info=True)
        out["error"] = str(e)[:400]
        return out


def _truthy(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on", "y")


def is_autosync_enabled() -> bool:
    """T1b: default off. Env AIPLAT_TEAM_HARNESS_AUTOSYNC overrides schema default."""
    schema = load_team_harness_schema()
    defaults = schema.get("defaults") if isinstance(schema.get("defaults"), dict) else {}
    env_name = str(defaults.get("autosync_env") or "AIPLAT_TEAM_HARNESS_AUTOSYNC")
    env = os.getenv(env_name)
    if env is not None and str(env).strip() != "":
        return _truthy(env)
    return _truthy(str(defaults.get("autosync_default") or "0"))


def autosync_timeout_sec() -> float:
    schema = load_team_harness_schema()
    defaults = schema.get("defaults") if isinstance(schema.get("defaults"), dict) else {}
    env_name = str(
        defaults.get("autosync_timeout_env") or "AIPLAT_TEAM_HARNESS_AUTOSYNC_TIMEOUT"
    )
    raw = os.getenv(env_name)
    if raw and str(raw).strip():
        try:
            return max(3.0, float(raw))
        except ValueError:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    try:
        return max(3.0, float(defaults.get("autosync_timeout_sec") or 20))
    except (TypeError, ValueError):
        return 20.0


def autosync_interval_sec() -> float:
    schema = load_team_harness_schema()
    defaults = schema.get("defaults") if isinstance(schema.get("defaults"), dict) else {}
    env_name = str(
        defaults.get("autosync_interval_env") or "AIPLAT_TEAM_HARNESS_AUTOSYNC_INTERVAL"
    )
    raw = os.getenv(env_name)
    if raw and str(raw).strip():
        try:
            return max(0.0, float(raw))
        except ValueError:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    try:
        return max(0.0, float(defaults.get("autosync_interval_sec") or 300))
    except (TypeError, ValueError):
        return 300.0


def _within_autosync_cooldown() -> bool:
    interval = autosync_interval_sec()
    if interval <= 0:
        return False
    meta = read_meta()
    last = meta.get("last_autosync_at") or meta.get("pulled_at")
    try:
        last_f = float(last)
    except (TypeError, ValueError):
        return False
    return (time.time() - last_f) < interval


def _run_autosync(*, timeout_sec: Optional[float] = None) -> Dict[str, Any]:
    """Synchronous autosync body: pull with short lock; degrade on any failure."""
    global _autosync_inflight
    t0 = time.time()
    budget = float(timeout_sec if timeout_sec is not None else autosync_timeout_sec())
    out: Dict[str, Any] = {
        "ok": True,
        "autosync": True,
        "degraded": False,
        "timeout_sec": budget,
    }
    if not is_autosync_enabled():
        out.update({"skipped": True, "reason": "autosync_disabled"})
        return out
    if _within_autosync_cooldown():
        out.update({"skipped": True, "reason": "cooldown"})
        return out

    with _autosync_lock:
        if _autosync_inflight:
            out.update({"skipped": True, "reason": "inflight"})
            return out
        _autosync_inflight = True

    box: Dict[str, Any] = {}

    def _worker() -> None:
        global _autosync_inflight
        try:
            try:
                box["result"] = pull_team_harness(
                    lock_timeout_sec=min(10.0, max(2.0, budget * 0.4))
                )
            except Exception as e:
                box["result"] = {
                    "ok": False,
                    "degraded": True,
                    "error": str(e)[:400],
                }
        finally:
            with _autosync_lock:
                _autosync_inflight = False

    try:
        th = threading.Thread(target=_worker, name="team-harness-autosync", daemon=True)
        th.start()
        th.join(timeout=budget)
        if th.is_alive():
            # Worker continues under file lock; leave inflight until it finishes.
            out.update(
                {
                    "ok": True,
                    "degraded": True,
                    "skipped": True,
                    "reason": "timeout",
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }
            )
            return out

        result = box.get("result") or {"ok": False, "error": "no_result"}
        try:
            meta = read_meta()
            meta["last_autosync_at"] = time.time()
            if result.get("commit"):
                meta["commit"] = result.get("commit")
            write_meta(meta)
        except Exception:
            logger.debug("autosync meta write failed", exc_info=True)

        out.update(result if isinstance(result, dict) else {"ok": False})
        out["autosync"] = True
        if not out.get("ok") or out.get("blocked"):
            out["degraded"] = True
            out["ok"] = True  # degrade, never fail the session
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        return out
    except Exception as e:
        logger.debug("autosync degraded: %s", e, exc_info=True)
        with _autosync_lock:
            _autosync_inflight = False
        return {
            "ok": True,
            "autosync": True,
            "degraded": True,
            "error": str(e)[:400],
            "elapsed_ms": int((time.time() - t0) * 1000),
        }


def maybe_autosync_team_harness(
    *,
    background: bool = True,
    timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """T1b entry: schedule or run autosync. Never raises; never blocks chat when background.

    Default ``background=True`` returns immediately with ``{scheduled: true}``.
    """
    if not is_autosync_enabled():
        return {"ok": True, "skipped": True, "reason": "autosync_disabled"}
    if background:
        th = threading.Thread(
            target=_run_autosync,
            kwargs={"timeout_sec": timeout_sec},
            name="team-harness-autosync-bg",
            daemon=True,
        )
        th.start()
        return {
            "ok": True,
            "scheduled": True,
            "background": True,
            "timeout_sec": float(
                timeout_sec if timeout_sec is not None else autosync_timeout_sec()
            ),
        }
    return _run_autosync(timeout_sec=timeout_sec)


# ── T1c: push → feature branch + MR template ──────────────────────────────


def _branch_prefix() -> str:
    schema = load_team_harness_schema()
    defaults = schema.get("defaults") if isinstance(schema.get("defaults"), dict) else {}
    return str(defaults.get("push_branch_prefix") or "teamai/").strip() or "teamai/"


def render_mr_template(
    *,
    branch: str,
    base: str = "main",
    title: str = "",
    summary: str = "",
    files: Optional[List[str]] = None,
) -> str:
    """Git-reviewable MR body (markdown). No auto-open of forge UI required."""
    files = files or []
    title = title or f"team harness: {branch}"
    lines = [
        f"# {title}",
        "",
        f"**Branch:** `{branch}` → `{base}`",
        "",
        "## Summary",
        summary or "Contribute local team harness changes for review.",
        "",
        "## Files",
    ]
    if files:
        for f in files[:50]:
            lines.append(f"- `{f}`")
        if len(files) > 50:
            lines.append(f"- … +{len(files) - 50} more")
    else:
        lines.append("- _(none listed)_")
    lines.extend(
        [
            "",
            "## Checklist",
            "- [ ] No secrets in `env/`",
            "- [ ] Locked resources only changed via intentional MR",
            "- [ ] Learnings scrubbed (no raw prompts / tool logs)",
            "",
            "_Generated by aiPlat team harness T1c._",
        ]
    )
    return "\n".join(lines) + "\n"


def _is_permission_denied(stderr: str) -> bool:
    s = (stderr or "").lower()
    needles = (
        "permission denied",
        "access denied",
        "write access",
        "protected branch",
        "authentication failed",
        "could not read from remote",
        "403",
        "401",
    )
    return any(n in s for n in needles)


def push_team_harness(
    *,
    paths: Optional[List[str]] = None,
    branch: str = "",
    message: str = "",
    base: str = "",
    dry_run: bool = False,
    include_local_learnings: bool = False,
    lock_timeout_sec: float = 30.0,
) -> Dict[str, Any]:
    """T1c: commit staged contribute paths on a feature branch and push (never main).

    Without remote write permission → ``ok=False`` + ``hint`` + MR template for manual flow.
    """
    materialize_team_harness_schema()
    schema = load_team_harness_schema()
    ensure_team_local_dirs(schema)
    cfg = read_config()
    root = team_dir(schema)
    br_base = str(base or cfg.get("branch") or "main").strip() or "main"
    prefix = _branch_prefix()
    br = str(branch or "").strip() or f"{prefix}contribute-{time.strftime('%Y%m%d-%H%M%S')}"
    if br in ("main", "master") or br == br_base:
        return {
            "ok": False,
            "error": "refuse_push_to_base",
            "hint": "T1c only pushes feature branches; open an MR into main",
            "base": br_base,
        }

    out: Dict[str, Any] = {
        "ok": False,
        "branch": br,
        "base": br_base,
        "dry_run": bool(dry_run),
        "team": str(root),
    }

    if not is_git_repo(root):
        out["error"] = "team_not_git"
        out["hint"] = "pull_team_harness first to clone the publish source"
        out["mr_template"] = render_mr_template(branch=br, base=br_base)
        return out

    # Collect files to contribute
    rels: List[str] = []
    if paths:
        for p in paths:
            rel = str(p).lstrip("/")
            # Guard: never push locked primary unless explicitly listed under learnings/env
            top = rel.split("/", 1)[0]
            if top in ("skills", "rules", "hooks", "mcp", "teams", "factory_sanitize") and not rel.startswith(
                "sources/"
            ):
                # locked — allow only if caller insists via sources/ or explicit override flag
                if not rel.startswith("sources/"):
                    continue
            cand = root / rel
            if cand.is_file():
                rels.append(rel)
    if include_local_learnings:
        local_learn = local_dir(schema) / "learnings"
        dest_learn = root / "learnings"
        dest_learn.mkdir(parents=True, exist_ok=True)
        if local_learn.is_dir():
            for src in local_learn.glob("*.json"):
                dst = dest_learn / src.name
                if not dry_run:
                    shutil.copy2(src, dst)
                rels.append(f"learnings/{src.name}")

    # Also include already-dirty non-locked paths under learnings/env/sources if none given
    if not rels and team_is_dirty(root):
        try:
            proc = _run_git(["status", "--porcelain"], cwd=root, check=False)
            for line in (proc.stdout or "").splitlines():
                path = line[3:].strip() if len(line) > 3 else ""
                if not path:
                    continue
                top = path.split("/", 1)[0]
                if top in ("learnings", "env", "sources") or path == "culture.md":
                    # culture is locked — skip unless already in paths explicitly
                    if path == "culture.md":
                        continue
                    rels.append(path)
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    rels = sorted(set(rels))
    out["files"] = rels
    out["mr_template"] = render_mr_template(
        branch=br,
        base=br_base,
        title=message or f"team harness contribute ({len(rels)} files)",
        summary=message or "Opt-in contribute from local/learnings or non-locked team paths.",
        files=rels,
    )

    if not rels:
        out.update({"ok": True, "skipped": True, "reason": "nothing_to_push"})
        return out

    if dry_run:
        out["ok"] = True
        out["would_push"] = True
        return out

    try:
        with team_harness_lock(timeout_sec=lock_timeout_sec):
            # Create/switch branch from current HEAD
            _run_git(["checkout", "-B", br], cwd=root, check=False)
            for rel in rels:
                _run_git(["add", "--", rel], cwd=root, check=False)
            status = _run_git(["status", "--porcelain"], cwd=root, check=False)
            if not (status.stdout or "").strip():
                out.update({"ok": True, "skipped": True, "reason": "nothing_staged"})
                return out
            msg = message or f"team harness: contribute {len(rels)} file(s)"
            commit = _run_git(
                ["commit", "-m", msg],
                cwd=root,
                check=False,
            )
            if commit.returncode != 0:
                out["error"] = (commit.stderr or commit.stdout or "commit failed")[:400]
                return out
            sha = _run_git(["rev-parse", "HEAD"], cwd=root, check=False).stdout.strip()
            out["commit"] = sha
            push = _run_git(
                ["push", "-u", "origin", br],
                cwd=root,
                check=False,
                timeout=180,
            )
            if push.returncode != 0:
                err = (push.stderr or push.stdout or "push failed")[:400]
                out["error"] = err
                out["pushed"] = False
                if _is_permission_denied(err):
                    out["hint"] = (
                        "No write permission on remote. Keep the MR template and push "
                        "manually after obtaining Git write access (Git permission = truth)."
                    )
                    out["permission_denied"] = True
                else:
                    out["hint"] = "Push failed; branch may exist locally — use MR template manually."
                # Still ok-ish for workflow: template ready
                out["ok"] = False
                return out

            out.update({"ok": True, "pushed": True, "permission_denied": False})
            try:
                meta = read_meta()
                meta["last_push_branch"] = br
                meta["last_push_at"] = time.time()
                meta["last_push_commit"] = sha
                write_meta(meta)
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            return out
    except TimeoutError as e:
        out["error"] = str(e)
        return out
    except Exception as e:
        logger.debug("push_team_harness failed", exc_info=True)
        out["error"] = str(e)[:400]
        return out


def _snapshot_tree(path: Path) -> Dict[str, float]:
    """path → mtime map for change detection (local/ invariant)."""
    snap: Dict[str, float] = {}
    if not path.is_dir():
        return snap
    for p in path.rglob("*"):
        if p.is_file():
            try:
                snap[str(p.relative_to(path))] = p.stat().st_mtime
            except OSError:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return snap


def _clone_into(url: str, dest: Path, *, branch: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Clone into temp then move, so failed clone leaves team/ empty
    tmp = dest.parent / f".clone_{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp)
    cmd = ["git", "clone", "--branch", branch, "--single-branch", url, str(tmp)]
    # Local path repos may not need branch if missing — fall back
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        cmd2 = ["git", "clone", url, str(tmp)]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=180)
        if proc2.returncode != 0:
            raise RuntimeError(
                (proc2.stderr or proc.stderr or "clone failed")[:400]
            )
        # checkout branch if exists
        _run_git(["checkout", branch], cwd=tmp, check=False)
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)


def _ff_pull(root: Path, *, url: str, branch: str) -> None:
    _run_git(["remote", "set-url", "origin", url], cwd=root, check=False)
    fetch = _run_git(["fetch", "origin", branch], cwd=root, check=False)
    if fetch.returncode != 0:
        # try fetch default
        fetch = _run_git(["fetch", "origin"], cwd=root, check=False)
        if fetch.returncode != 0:
            raise RuntimeError((fetch.stderr or "fetch failed")[:400])
    # Prefer origin/branch
    target = f"origin/{branch}"
    rev = _run_git(["rev-parse", "--verify", target], cwd=root, check=False)
    if rev.returncode != 0:
        # fallback to FETCH_HEAD / origin/HEAD
        target = "FETCH_HEAD"
    merge = _run_git(["merge", "--ff-only", target], cwd=root, check=False)
    if merge.returncode != 0:
        raise RuntimeError((merge.stderr or merge.stdout or "ff-only failed")[:400])
