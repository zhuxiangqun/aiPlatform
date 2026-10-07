"""Deterministic platform status brief for the digital-human consultant.

Scans live workspace assets + menu catalog. No LLM. Answers must cite this brief.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.digital_human.brief")

_BRIEF_CACHE: Optional[str] = None
_BRIEF_CACHE_TS: float = 0.0
_BRIEF_TTL_SEC = 60.0


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _page_manifest_path() -> Path:
    env_root = os.getenv("AIPLAT_REPO_ROOT") or os.getenv("AIPLAT_PROJECT_ROOT") or ""
    candidates = []
    if env_root:
        candidates.append(
            Path(env_root) / "aiPlat-management/frontend/src/pageManifest.ts"
        )
    # digital_human → harness → core → aiPlat-core → workspace
    try:
        candidates.append(
            Path(__file__).resolve().parents[4]
            / "aiPlat-management/frontend/src/pageManifest.ts"
        )
    except IndexError:
        logger.debug("pageManifest path parents[4] missing", exc_info=True)
    for p in candidates:
        if p.is_file():
            return p
    return Path()


def _parse_page_manifest_entries(src: Path) -> List[Dict[str, str]]:
    """Parse sidebar keys from pageManifest.ts (single source of menu truth)."""
    text = src.read_text(encoding="utf-8")
    start = text.find("export const menuItems")
    end = text.find("];", start)
    if start < 0 or end < 0:
        return []
    entries: List[Dict[str, str]] = []
    group = ""
    for line in text[start:end].splitlines():
        gm = re.search(r"group:\s*'([^']+)',\s*label:\s*'([^']+)'", line)
        if gm:
            group = re.sub(r"^[^\s]+\s", "", gm.group(2))
            continue
        km = re.search(r"key:\s*'(/[^']+)'", line)
        lm = re.search(r"label:\s*'([^']+)'", line)
        if km and lm:
            entries.append({"route": km.group(1), "label": lm.group(1), "group": group})
    return entries


def _parse_page_purposes(src: Path) -> Dict[str, str]:
    text = src.read_text(encoding="utf-8")
    start = text.find("export const PAGE_PURPOSE")
    if start < 0:
        return {}
    brace = text.find("{", start)
    end = text.find("\n};", brace)
    if brace < 0 or end < 0:
        return {}
    block = text[brace : end + 1]
    out: Dict[str, str] = {}
    for km, pm in re.findall(r"'(/[^']+)':\s*'([^']*)'", block):
        out[km] = pm
    return out


def _load_menu_catalog() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "menu_catalog.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("menu_catalog load failed", exc_info=True)
        catalog = {"entries": [], "build_paths": []}
    manifest = _page_manifest_path()
    if manifest.is_file():
        try:
            live = _parse_page_manifest_entries(manifest)
            if live:
                catalog["entries"] = live
            purposes = _parse_page_purposes(manifest)
            if purposes:
                catalog["purposes"] = purposes
        except Exception:
            logger.debug("pageManifest parse failed", exc_info=True)
    return catalog


def _summarize_names(names: List[str], *, limit: int = 12, more: str = "问「有哪些 Agent」可看全量") -> str:
    if not names:
        return "(空)"
    if limit <= 0 or len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f" …共{len(names)}个（{more}）"


def _format_menu_lines(entries: List[Any]) -> List[str]:
    grouped: Dict[str, List[str]] = {}
    order: List[str] = []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        g = str(e.get("group") or "其他")
        if g not in grouped:
            grouped[g] = []
            order.append(g)
        grouped[g].append(f"{e.get('route')} {e.get('label')}")
    lines = [f"管理端菜单（与侧栏一致，共 {sum(len(v) for v in grouped.values())}）:"]
    for g in order:
        items = grouped[g]
        if len(items) > 5:
            shown = "; ".join(items[:5]) + f" …等{len(items)}项"
        else:
            shown = "; ".join(items)
        lines.append(f"  [{g}] {shown}")
    return lines


def _list_workspace_dirs(subdir: str, markers: List[str]) -> List[str]:
    root = _aiplat_home() / subdir
    if not root.is_dir():
        return []
    names: List[str] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name in ("catalog", "TEMPLATE", "__pycache__"):
            continue
        if any((d / m).exists() for m in markers):
            names.append(d.name)
        elif subdir == "mcps" and any(d.iterdir()):
            names.append(d.name)
        elif subdir == "workflows" and any(d.iterdir()):
            names.append(d.name)
    return names


def _list_workspace_tools() -> List[str]:
    root = _aiplat_home() / "tools"
    if not root.is_dir():
        return []
    names: List[str] = []
    for p in sorted(root.iterdir()):
        if p.name.startswith(".") or p.name == "__pycache__":
            continue
        if p.is_file() and p.suffix == ".py":
            names.append(p.stem)
        elif p.is_dir() and (p / f"{p.name}.py").exists():
            names.append(p.name)
    return names


def _list_deployed_apps() -> List[str]:
    root = _aiplat_home() / "apps"
    if not root.is_dir():
        return []
    names: List[str] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if d.name in ("catalog", "TEMPLATE", "__pycache__"):
            continue
        if (d / "current").is_dir() or (d / "agent_manifest.json").is_file():
            names.append(d.name)
        elif any(d.iterdir()):
            names.append(d.name)
    return names


def _list_domain_ids() -> List[str]:
    path = _aiplat_home() / "ontologies" / "registry.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    domains = data.get("domains") if isinstance(data, dict) else None
    if not isinstance(domains, dict):
        return []
    return sorted(str(k) for k in domains.keys() if str(k).strip())


def _list_factory_projects() -> List[str]:
    path = _aiplat_home() / "projects.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    rows = data.get("projects") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    names: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("project_id") or row.get("id") or "").strip()
        name = str(row.get("name") or "").strip()
        if pid and name and name != pid:
            names.append(f"{pid}({name})")
        elif pid or name:
            names.append(pid or name)
    return names


def _list_team_files() -> List[str]:
    root = _aiplat_home() / "teams"
    if not root.is_dir():
        return []
    names: List[str] = []
    for p in sorted(root.iterdir()):
        if p.suffix.lower() in (".yaml", ".yml") and p.is_file():
            names.append(p.stem)
    return names


def _wiki_page_count() -> int:
    root = _aiplat_home() / "wiki" / "collections"
    if not root.is_dir():
        return 0
    n = 0
    try:
        for p in root.rglob("*.md"):
            if p.name.startswith("."):
                continue
            n += 1
            if n >= 5000:
                break
    except OSError:
        return 0
    return n


def _list_wiki_collections() -> List[str]:
    root = _aiplat_home() / "wiki" / "collections"
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _execution_db_path() -> Path:
    env = os.getenv("AIPLAT_EXECUTION_DB_PATH", "").strip()
    if env:
        return Path(env)
    return _aiplat_home() / "aiplat_executions.sqlite3"


def _sqlite_has_table(path: Path, table: str) -> bool:
    if not re.match(r"^[A-Za-z0-9_]+$", table):
        return False
    rows = _sqlite_rows(
        path,
        f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table}' LIMIT 1",
    )
    return bool(rows)


def _platform_db_path() -> Path:
    env = os.getenv("AIPLAT_PLATFORM_DB_PATH", "").strip()
    if env:
        return Path(env)
    candidates = [
        _aiplat_home() / "data" / "aiplat_platform.sqlite3",
        _aiplat_home() / "platform.sqlite3",
        _repo_root() / "aiPlat-platform" / "data" / "aiplat_platform.sqlite3",
        _repo_root() / "aiPlat-core" / "data" / "aiplat_platform.sqlite3",
    ]
    for p in candidates:
        if not p.is_file() or p.stat().st_size < 64:
            continue
        if _sqlite_has_table(p, "auth_users") or _sqlite_has_table(p, "apps") or _sqlite_has_table(
            p, "gateway_routes"
        ):
            return p
    return candidates[0]


def _sqlite_rows(path: Path, sql: str) -> List[tuple]:
    if not path.is_file() or path.stat().st_size < 64:
        return []
    try:
        import sqlite3

        conn = sqlite3.connect(str(path), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            return list(conn.execute(sql).fetchall())
        finally:
            conn.close()
    except Exception:
        logger.debug("sqlite query failed %s", path, exc_info=True)
        return []


def _list_platform_tenants() -> List[str]:
    names: List[str] = []
    for row in _sqlite_rows(
        _platform_db_path(),
        "SELECT name, COALESCE(status,'') FROM tenants LIMIT 40",
    ):
        name = str(row[0] or "").strip()
        if not name:
            continue
        st = str(row[1] or "").strip()
        names.append(f"{name}({st})" if st else name)
    return names


def _list_gateway_routes() -> List[str]:
    names: List[str] = []
    for row in _sqlite_rows(
        _platform_db_path(),
        "SELECT name, path, COALESCE(enabled,1) FROM gateway_routes LIMIT 40",
    ):
        name = str(row[0] or "").strip() or str(row[1] or "").strip()
        if not name:
            continue
        path = str(row[1] or "").strip()
        on = "on" if row[2] in (1, True, "1") else "off"
        names.append(f"{name} {path} {on}".strip())
    return names


def _list_platform_apps() -> List[str]:
    names: List[str] = []
    for row in _sqlite_rows(
        _platform_db_path(),
        "SELECT name, COALESCE(mode,''), COALESCE(enabled,1) FROM apps LIMIT 40",
    ):
        name = str(row[0] or "").strip()
        if not name:
            continue
        mode = str(row[1] or "").strip()
        on = "on" if row[2] in (1, True, "1") else "off"
        names.append(f"{name}/{mode} {on}" if mode else f"{name} {on}")
    return names


def _list_auth_users() -> List[str]:
    """username + role + status. Never data_json."""
    names: List[str] = []
    for row in _sqlite_rows(
        _platform_db_path(),
        "SELECT username, COALESCE(role,''), COALESCE(status,'') FROM auth_users LIMIT 40",
    ):
        u = str(row[0] or "").strip()
        if not u:
            continue
        role = str(row[1] or "").strip()
        st = str(row[2] or "").strip()
        extra = "/".join(x for x in (role, st) if x)
        names.append(f"{u}({extra})" if extra else u)
    return names


def _list_gateway_token_names() -> List[str]:
    """Token names only. Never token/sha."""
    names: List[str] = []
    for row in _sqlite_rows(
        _execution_db_path(),
        "SELECT name, COALESCE(enabled,1) FROM gateway_tokens LIMIT 40",
    ):
        n = str(row[0] or "").strip()
        if n:
            on = "on" if row[1] in (1, True, "1") else "off"
            names.append(f"{n} {on}")
    return names


def _list_gateway_channels() -> List[str]:
    names: List[str] = []
    for row in _sqlite_rows(
        _execution_db_path(),
        "SELECT channel, COUNT(*) FROM gateway_pairings GROUP BY channel LIMIT 20",
    ):
        ch = str(row[0] or "").strip() or "(unknown)"
        names.append(f"{ch}×{int(row[1])}")
    return names


def _list_plugins() -> List[str]:
    """plugin_id/name/version/enabled. Never manifest_json."""
    names: List[str] = []
    for row in _sqlite_rows(
        _execution_db_path(),
        "SELECT plugin_id, COALESCE(name,''), COALESCE(version,''), COALESCE(enabled,1) "
        "FROM plugins LIMIT 40",
    ):
        pid = str(row[0] or "").strip()
        if not pid:
            continue
        name = str(row[1] or "").strip()
        ver = str(row[2] or "").strip()
        on = "on" if row[3] in (1, True, "1") else "off"
        label = pid
        if name and name != pid:
            label += f"({name})"
        if ver:
            label += f"@{ver}"
        names.append(f"{label} {on}")
    return names


def _list_platform_workflows() -> List[str]:
    names: List[str] = []
    for row in _sqlite_rows(
        _platform_db_path(),
        "SELECT name FROM workflows LIMIT 40",
    ):
        n = str(row[0] or "").strip()
        if n:
            names.append(n)
    return names


def _list_session_queue_summary() -> List[str]:
    """kind/status counts. Never payload_json."""
    names: List[str] = []
    for row in _sqlite_rows(
        _execution_db_path(),
        "SELECT kind, status, COUNT(*) FROM session_queue GROUP BY kind, status LIMIT 20",
    ):
        kind = str(row[0] or "?").strip() or "?"
        st = str(row[1] or "?").strip() or "?"
        names.append(f"{kind}/{st}×{int(row[2])}")
    return names


def _list_api_key_prefixes() -> List[str]:
    """key_prefix + active only. Never key_hash / permissions JSON."""
    names: List[str] = []
    for row in _sqlite_rows(
        _platform_db_path(),
        "SELECT key_prefix, COALESCE(active,1) FROM api_keys LIMIT 40",
    ):
        prefix = str(row[0] or "").strip()
        if not prefix:
            continue
        shown = prefix if len(prefix) <= 12 else (prefix[:8] + "…")
        on = "on" if row[1] in (1, True, "1") else "off"
        names.append(f"{shown} {on}")
    return names


def _port_service_lines() -> List[str]:
    raw = os.getenv("AIPLAT_PORT_SERVICES", "").strip()
    if not raw:
        return []
    names: List[str] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        port, rest = entry.split("=", 1)
        names.append(f"{port.strip()}={rest.strip()}")
    return names


def _listen_ports() -> List[str]:
    try:
        import subprocess

        out = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return []
    ports: List[str] = []
    seen = set()
    for line in (out.stdout or "").splitlines()[1:]:
        m = re.search(r":(\d+)\s+\(LISTEN\)", line)
        if not m:
            continue
        port = m.group(1)
        if port in seen:
            continue
        seen.add(port)
        cmd = (line.split() or ["?"])[0][:18]
        ports.append(f"{port}({cmd})")
        if len(ports) >= 24:
            break
    wanted = {"5173", "8001", "8002", "8003", "8004", "8005", "8080", "11434", "1234"}
    for entry in os.getenv("AIPLAT_PORT_SERVICES", "").split(","):
        entry = entry.strip()
        if "=" in entry:
            wanted.add(entry.split("=", 1)[0].strip())
    filtered = [p for p in ports if p.split("(", 1)[0] in wanted]
    return filtered or ports[:8]


def _list_registered_models() -> Dict[str, List[str]]:
    """Unique model names from adapters table. No API keys. Not a pin for selection."""
    empty: Dict[str, List[str]] = {"local": [], "api": []}
    db = _execution_db_path()
    if not db.is_file() or db.stat().st_size < 64:
        return empty
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            cols = {
                str(r[1])
                for r in conn.execute("PRAGMA table_info(adapters)").fetchall()
            }
            if not {"adapter_id", "models_json"} <= cols:
                return empty
            rows = conn.execute(
                "SELECT adapter_id, provider, models_json FROM adapters "
                "WHERE COALESCE(status,'active')='active'"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        logger.debug("adapters model list failed", exc_info=True)
        return empty
    local: List[str] = []
    api: List[str] = []
    seen = set()
    for adapter_id, provider, models_json in rows:
        try:
            parsed = json.loads(models_json) if models_json else []
        except Exception:
            parsed = []
        if not isinstance(parsed, list):
            parsed = []
        names: List[str] = []
        for entry in parsed:
            if isinstance(entry, dict):
                if entry.get("enabled") is False:
                    continue
                name = str(entry.get("name") or "").strip()
            else:
                name = str(entry).strip()
            if name:
                names.append(name)
        aid = str(adapter_id or "")
        prov = str(provider or "").strip()
        for name in names:
            key = name.lower()
            if key in seen or "," in name:
                continue
            seen.add(key)
            if aid.startswith("local-scan:"):
                local.append(name)
            else:
                api.append(f"{name}({prov})" if prov else name)
            if len(seen) >= 80:
                return {"local": sorted(local), "api": sorted(api)}
    return {"local": sorted(local), "api": sorted(api)}


def _list_prompt_template_ids() -> List[str]:
    """template_id only. Never read prompt body."""
    db = _execution_db_path()
    if not db.is_file() or db.stat().st_size < 64:
        return []
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            cols = {
                str(r[1])
                for r in conn.execute("PRAGMA table_info(prompt_templates)").fetchall()
            }
            if "template_id" not in cols:
                return []
            name_col = "name" if "name" in cols else None
            sql = (
                "SELECT template_id, name FROM prompt_templates LIMIT 80"
                if name_col
                else "SELECT template_id FROM prompt_templates LIMIT 80"
            )
            rows = conn.execute(sql).fetchall()
        finally:
            conn.close()
    except Exception:
        logger.debug("prompt_templates list failed", exc_info=True)
        return []
    names: List[str] = []
    for row in rows:
        tid = str(row[0] or "").strip()
        if not tid:
            continue
        nm = str(row[1] or "").strip() if len(row) > 1 else ""
        names.append(f"{tid}({nm})" if nm and nm != tid else tid)
    return names


def _list_jobs() -> List[str]:
    """Job names only. Never payload/options/delivery JSON."""
    db = _execution_db_path()
    if not db.is_file() or db.stat().st_size < 64:
        return []
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            cols = {
                str(r[1])
                for r in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "name" not in cols:
                return []
            want = [c for c in ("name", "kind", "enabled", "cron", "target_id") if c in cols]
            rows = conn.execute(
                f"SELECT {', '.join(want)} FROM jobs LIMIT 40"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        logger.debug("jobs list failed", exc_info=True)
        return []
    names: List[str] = []
    for row in rows:
        rec = dict(zip(want, row))
        name = str(rec.get("name") or "").strip()
        if not name:
            continue
        kind = str(rec.get("kind") or "").strip()
        cron = str(rec.get("cron") or "").strip()
        tgt = str(rec.get("target_id") or "").strip()
        en = rec.get("enabled")
        flag = "on" if en in (1, True, "1", "true") else "off"
        bit = name
        if kind:
            bit += f"/{kind}"
        if tgt:
            bit += f"→{tgt}"
        bit += f" {flag}"
        if cron:
            bit += f" {cron}"
        names.append(bit)
    return names


def _count_table_rows(table: str) -> int:
    db = _execution_db_path()
    if not db.is_file() or db.stat().st_size < 64:
        return 0
    if not re.match(r"^[A-Za-z0-9_]+$", table):
        return 0
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(n[0]) if n else 0
        finally:
            conn.close()
    except Exception:
        return 0


def _count_table_rows_at(db: Path, table: str) -> int:
    if not db.is_file() or db.stat().st_size < 64:
        return 0
    if not re.match(r"^[A-Za-z0-9_]+$", table):
        return 0
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(n[0]) if n else 0
        finally:
            conn.close()
    except Exception:
        return 0


def _code_graph_line() -> str:
    db = _aiplat_home() / "code_graph.db"
    files = _count_table_rows_at(db, "files")
    symbols = _count_table_rows_at(db, "symbols")
    edges = _count_table_rows_at(db, "edges")
    return (
        f"代码图谱: files {files}, symbols {symbols}, edges {edges}"
        " → /diagnostics/code-intel（只计数量，不列路径）"
    )


def _cap_index_line() -> str:
    db = _aiplat_home() / "cap_graph.db"
    nodes = _count_table_rows_at(db, "cap_nodes")
    edges = _count_table_rows_at(db, "cap_edges")
    return (
        f"能力关系图: nodes {nodes}, edges {edges}"
        " → /diagnostics/capability-graph（只计数量，不列节点名）"
    )


def _ontology_triple_n() -> int:
    return _count_table_rows_at(_aiplat_home() / "ontology_triples.sqlite3", "triples")


def _wiki_quality_line() -> str:
    db = _aiplat_home() / "wiki_quality.sqlite3"
    n = _count_table_rows_at(db, "wiki_quality_alerts")
    return (
        f"Wiki 质量告警: {n} 条"
        " → /platform/kb/health（只计条数，不含 explanation）"
    )


def _count_json_in_dir(subdir: str) -> int:
    root = _aiplat_home() / subdir
    if not root.is_dir():
        return 0
    n = 0
    try:
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() == ".json" and not p.name.startswith("."):
                n += 1
    except OSError:
        return 0
    return n


def _governance_cycle_line() -> str:
    """Count governance_cycles; sample domain prefixes only. Never open JSON bodies."""
    root = _aiplat_home() / "governance_cycles"
    if not root.is_dir():
        return "治理循环: 0 → /governance"
    n = 0
    domains: Dict[str, int] = {}
    try:
        for p in root.iterdir():
            if not p.is_file() or p.suffix.lower() != ".json" or p.name.startswith("."):
                continue
            n += 1
            # gov-cycle-{domain}-{ts}.json
            stem = p.stem
            if stem.startswith("gov-cycle-"):
                rest = stem[len("gov-cycle-") :]
                # strip trailing timestamp digits
                parts = rest.rsplit("-", 1)
                dom = parts[0] if parts else rest
            else:
                dom = stem.split("-", 1)[0]
            if dom:
                domains[dom] = domains.get(dom, 0) + 1
            if n >= 20000:
                break
    except OSError:
        return "治理循环: (简报未见) → /governance"
    top = sorted(domains.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    shown = ", ".join(f"{k}×{v}" for k, v in top)
    extra = f"；域样本 {shown}" if shown else ""
    return f"治理循环: {n} 份{extra} → /governance（只计文件/域名，不含正文）"


def _awareness_log_line() -> str:
    root = _aiplat_home() / "awareness_logs"
    if not root.is_dir():
        return "觉察日志: 0 天 → /governance"
    days = sorted(
        p.stem.replace("awareness_log_", "")
        for p in root.iterdir()
        if p.is_file() and p.name.startswith("awareness_log_") and p.suffix == ".jsonl"
    )
    if not days:
        return "觉察日志: 0 天 → /governance"
    span = f"{days[0]}…{days[-1]}" if len(days) > 1 else days[0]
    return f"觉察日志: {len(days)} 天（{span}）→ /governance（只列日期，不含 jsonl 正文）"


def _evolution_line() -> str:
    path = _aiplat_home() / "evolution" / "last_run.json"
    if not path.is_file():
        return "自演进上次运行: (无) → /governance"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return "自演进上次运行: (简报未见) → /governance"
    if not isinstance(data, dict):
        return "自演进上次运行: (简报未见) → /governance"
    date = str(data.get("date") or "").strip()
    status = str(data.get("status") or "").strip()
    steps = data.get("step_count")
    bit = " / ".join(x for x in (date, status) if x) or "(简报未见)"
    if isinstance(steps, int):
        bit += f", steps={steps}"
    return f"自演进上次运行: {bit} → /governance（不含步骤正文）"


def _experience_feedback_line() -> str:
    """rule_id + status counts only. Never content body."""
    path = _aiplat_home() / "experience_feedback.json"
    if not path.is_file():
        return "经验回写: 0 → /governance"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or []
    except Exception:
        return "经验回写: (简报未见) → /governance"
    if not isinstance(data, list):
        return "经验回写: (简报未见) → /governance"
    by_status: Dict[str, int] = {}
    rules: List[str] = []
    seen = set()
    for row in data[:200]:
        if not isinstance(row, dict):
            continue
        st = str(row.get("status") or "?").strip() or "?"
        by_status[st] = by_status.get(st, 0) + 1
        rid = str(row.get("rule_id") or "").strip()
        if rid and rid not in seen:
            seen.add(rid)
            rules.append(rid)
    st_bits = ", ".join(f"{k}×{v}" for k, v in sorted(by_status.items()))
    rule_bits = _summarize_names(rules, limit=8, more="问「有哪些经验」可看全量")
    return (
        f"经验回写: {len(data)} 条"
        + (f"；{st_bits}" if st_bits else "")
        + (f"；规则 {rule_bits}" if rules else "")
        + " → /governance（只列 rule_id/status，不含 content）"
    )


def _sqlite_status_summary(table: str, *, col: str = "status") -> str:
    db = _execution_db_path()
    if not db.is_file() or db.stat().st_size < 64:
        return ""
    if not re.match(r"^[A-Za-z0-9_]+$", table) or not re.match(r"^[A-Za-z0-9_]+$", col):
        return ""
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            rows = conn.execute(
                f"SELECT {col}, COUNT(*) FROM {table} GROUP BY {col} ORDER BY COUNT(*) DESC LIMIT 12"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return ""
    parts = []
    for st, n in rows:
        parts.append(f"{st or '?'}×{int(n)}")
    return ", ".join(parts)


def _model_manager_brief_line(*, name_limit: int = 12) -> str:
    """Enabled Chat models from cached ModelManager (sync read). Not a pin for selection."""
    skip_types = {"embedding", "rerank", "reranker", "audio", "ocr", "whisper", "stt", "tts"}
    try:
        from core.harness.utils.model_injection import _model_manager_cache

        mgr = _model_manager_cache
        if mgr is None:
            return (
                "ModelManager 启用摘要: (进程内尚未加载目录，见上方 Adapters 清单)"
                " → /infra/models（只读盘点，不是指定选哪个）"
            )
        models = list(getattr(mgr, "_models", {}) or {}).values()
    except Exception:
        logger.debug("model manager brief failed", exc_info=True)
        return (
            "ModelManager 启用摘要: (简报未见)"
            " → /infra/models（只读盘点，不是指定选哪个）"
        )
    enabled_chat: List[str] = []
    disabled_n = 0
    by_status: Dict[str, int] = {}
    for m in models:
        try:
            mtype = str(
                getattr(getattr(m, "type", None), "value", None)
                or getattr(m, "type", "")
                or "chat"
            ).lower()
            if mtype in skip_types:
                continue
            if not bool(getattr(m, "enabled", True)):
                disabled_n += 1
                continue
            name = str(getattr(m, "name", "") or "").strip()
            if not name or "," in name:
                continue
            st = str(
                getattr(getattr(m, "status", None), "value", None)
                or getattr(m, "status", "")
                or "?"
            )
            by_status[st] = by_status.get(st, 0) + 1
            enabled_chat.append(name)
        except Exception:
            continue
    seen = set()
    uniq: List[str] = []
    for n in enabled_chat:
        k = n.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(n)
    st_bits = ", ".join(f"{k}×{v}" for k, v in sorted(by_status.items()))
    return (
        f"ModelManager 已启用 Chat ({len(uniq)}): "
        + _summarize_names(uniq, limit=name_limit, more="问「有哪些模型」可看全量")
        + (f"；状态 {st_bits}" if st_bits else "")
        + (f"；已禁用 {disabled_n}" if disabled_n else "")
        + " → /infra/models（目录只读摘要，选模仍走 purpose→unified_pipeline）"
    )


def _recent_failed_runs(*, limit: int = 5) -> str:
    """Last failed agent/skill runs: id + status + short error_code. Never I/O bodies."""
    db = _execution_db_path()
    if not db.is_file() or db.stat().st_size < 64:
        return ""
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            bits: List[str] = []
            for table, id_col in (
                ("agent_executions", "agent_id"),
                ("skill_executions", "skill_id"),
            ):
                cols = {
                    str(r[1])
                    for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if not {id_col, "status"} <= cols:
                    continue
                err_sel = "COALESCE(error_code,'')" if "error_code" in cols else "''"
                order = "created_at" if "created_at" in cols else "rowid"
                rows = conn.execute(
                    f"SELECT {id_col}, status, {err_sel} FROM {table} "
                    f"WHERE lower(COALESCE(status,'')) IN ('failed','error','timeout') "
                    f"ORDER BY {order} DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                kind = "Agent" if id_col == "agent_id" else "Skill"
                for rid, st, code in rows:
                    label = str(rid or "?").strip() or "?"
                    code_s = str(code or "").strip()
                    if len(code_s) > 48:
                        code_s = code_s[:45] + "…"
                    extra = f"/{code_s}" if code_s else ""
                    bits.append(f"{kind}:{label}({st or '?'}{extra})")
        finally:
            conn.close()
    except Exception:
        logger.debug("recent failed runs brief failed", exc_info=True)
        return ""
    if not bits:
        return "最近失败运行: (无) → /diagnostics/runs（只列 id/status/error_code，不含 input/output）"
    return (
        "最近失败运行: "
        + _summarize_names(bits, limit=limit)
        + " → /diagnostics/runs（只列 id/status/error_code，不含 input/output）"
    )


def _list_pending_approvals() -> List[str]:
    """operation + status only. Never details JSON."""
    db = _execution_db_path()
    if not db.is_file() or db.stat().st_size < 64:
        return []
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            cols = {
                str(r[1])
                for r in conn.execute("PRAGMA table_info(approval_requests)").fetchall()
            }
            if "operation" not in cols:
                return []
            rows = conn.execute(
                "SELECT operation, COALESCE(status,'') AS st, COUNT(*) "
                "FROM approval_requests GROUP BY operation, st "
                "ORDER BY COUNT(*) DESC LIMIT 20"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        logger.debug("approval_requests list failed", exc_info=True)
        return []
    names: List[str] = []
    for op, st, n in rows:
        label = str(op or "").strip() or "(unknown)"
        flag = str(st or "").strip() or "?"
        names.append(f"{label} {flag}×{int(n)}")
    return names


def _list_sqlite_labels(
    table: str, id_col: str, extra_col: str = ""
) -> List[str]:
    db = _execution_db_path()
    if not db.is_file() or db.stat().st_size < 64:
        return []
    if not re.match(r"^[A-Za-z0-9_]+$", table) or not re.match(r"^[A-Za-z0-9_]+$", id_col):
        return []
    if extra_col and not re.match(r"^[A-Za-z0-9_]+$", extra_col):
        return []
    try:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            cols = {
                str(r[1])
                for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if id_col not in cols:
                return []
            if extra_col and extra_col in cols:
                rows = conn.execute(
                    f"SELECT {id_col}, {extra_col} FROM {table} LIMIT 40"
                ).fetchall()
            else:
                rows = conn.execute(f"SELECT {id_col} FROM {table} LIMIT 40").fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    names: List[str] = []
    for row in rows:
        a = str(row[0] or "").strip()
        if not a:
            continue
        b = str(row[1] or "").strip() if len(row) > 1 else ""
        names.append(f"{a}({b})" if b and b != a else a)
    return names


def _list_llm_providers() -> List[str]:
    """Provider ids from repo YAML. Never env values / API keys."""
    path = _repo_root() / "aiPlat-infra" / "config" / "providers.yaml"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    names: List[str] = []
    for block in re.split(r"\n\s*-\s+id:\s*", text)[1:]:
        m = re.match(r"([A-Za-z0-9_\-]+)", block)
        if not m:
            continue
        ident = m.group(1)
        enabled = True
        em = re.search(r"(?m)^(?:\s*)enabled:\s*(true|false)", block)
        if em and em.group(1) == "false":
            enabled = False
        typ = ""
        tm = re.search(r"(?m)^(?:\s*)type:\s*(\w+)", block)
        if tm:
            typ = tm.group(1)
        flag = "on" if enabled else "off"
        names.append(f"{ident}/{typ} {flag}" if typ else f"{ident} {flag}")
        if len(names) >= 40:
            break
    return names


def _list_dir_names(subdir: str) -> List[str]:
    root = _aiplat_home() / subdir
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _list_file_stems(subdir: str, suffixes: tuple) -> List[str]:
    root = _aiplat_home() / subdir
    if not root.is_dir():
        return []
    names: List[str] = []
    want = {s.lower() for s in suffixes}
    try:
        for p in sorted(root.iterdir()):
            if not p.is_file() or p.name.startswith("."):
                continue
            if p.suffix.lower() in want:
                names.append(p.stem)
    except OSError:
        return []
    return names


def _list_json_asset_labels(
    filename: str, *, name_keys: tuple = ("name", "id"), extra_keys: tuple = ()
) -> List[str]:
    """Labels from a JSON array file. Never include key/value/secret fields."""
    path = _aiplat_home() / filename
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("items") or data.get("credentials") or data.get("variables") or []
    if not isinstance(data, list):
        return []
    forbid = {"key", "value", "secret", "password", "token", "api_key"}
    names: List[str] = []
    for row in data[:80]:
        if not isinstance(row, dict):
            continue
        label = ""
        for k in name_keys:
            v = str(row.get(k) or "").strip()
            if v:
                label = v
                break
        extras = []
        for k in extra_keys:
            if k.lower() in forbid:
                continue
            v = str(row.get(k) or "").strip()
            if v and v != label:
                extras.append(v)
        if label:
            names.append(f"{label}({','.join(extras)})" if extras else label)
    return names


def _memory_note_count() -> int:
    root = _aiplat_home() / "memory"
    if not root.is_dir():
        return 0
    n = 0
    try:
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() == ".md" and not p.name.startswith("."):
                n += 1
    except OSError:
        return 0
    return n


def _repo_root() -> Path:
    env = os.getenv("AIPLAT_REPO_ROOT") or os.getenv("AIPLAT_PROJECT_ROOT") or ""
    if env:
        return Path(env)
    try:
        return Path(__file__).resolve().parents[4]
    except IndexError:
        return Path()


def _list_engine_ids(subdir: str, marker: str) -> List[str]:
    root = _repo_root() / "aiPlat-core" / "core" / "engine" / subdir
    if not root.is_dir():
        return []
    names: List[str] = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and (d / marker).is_file():
            names.append(d.name)
    return names


def _list_action_ids() -> List[str]:
    root = _aiplat_home() / "actions"
    if not root.is_dir():
        return []
    ids: List[str] = []
    seen = set()
    for p in sorted(root.iterdir()):
        if p.suffix.lower() not in (".yaml", ".yml") or p.name.startswith("."):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[:80000]
        except OSError:
            continue
        for m in re.finditer(r"action_id:\s*[\"']?([A-Za-z0-9_\-]+)", text):
            aid = m.group(1)
            if aid not in seen:
                seen.add(aid)
                ids.append(aid)
    return ids


def _list_yaml_stems(subdir: str) -> List[str]:
    root = _aiplat_home() / subdir
    if not root.is_dir():
        return []
    names: List[str] = []
    for p in sorted(root.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix.lower() in (".yaml", ".yml"):
            names.append(p.stem)
    return names


def _list_mcp_assets() -> List[str]:
    dirs = _list_workspace_dirs("mcps", ["server.yaml", "mcp.json", "mcp.yaml"])
    yamls = _list_yaml_stems("mcp")
    return sorted(set(dirs) | set(yamls))


def _list_package_ids() -> List[str]:
    root = _aiplat_home() / "packages" / "registry"
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _list_auto_pipelines() -> List[str]:
    root = _aiplat_home() / "auto_pipelines"
    if not root.is_dir():
        return []
    names: List[str] = []
    for p in sorted(root.glob("*.json")):
        label = p.stem[:12]
        try:
            data = json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        if isinstance(data, dict):
            kws = data.get("keywords") or []
            seq = data.get("agent_sequence") or []
            if isinstance(kws, list) and kws:
                label = ",".join(str(x) for x in kws[:3])
            elif isinstance(seq, list) and seq:
                label = "-".join(str(x) for x in seq[:4])
        names.append(str(label))
    return names


def _list_eval_sets() -> List[str]:
    root = _aiplat_home() / "eval_sets"
    if not root.is_dir():
        return []
    names: List[str] = []
    for sub in sorted(root.iterdir()):
        if sub.name.startswith("."):
            continue
        if sub.is_dir():
            for f in sorted(sub.glob("*.json")):
                names.append(f"{sub.name}/{f.stem}")
        elif sub.suffix.lower() == ".json":
            names.append(sub.stem)
    return names


def _list_kb_tenants() -> List[str]:
    root = _aiplat_home() / "kb" / "tenants"
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _count_json_files(subdir: str) -> int:
    root = _aiplat_home() / subdir
    if not root.is_dir():
        return 0
    n = 0
    try:
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() == ".json" and not p.name.startswith("."):
                n += 1
    except OSError:
        return 0
    return n


def _fde_manual_line() -> str:
    root = _aiplat_home() / "fde-manuals"
    if not root.is_dir():
        return "FDE 手册 (0) → /diagnostics/fde"
    names = [
        p.name
        for p in sorted(root.iterdir())
        if p.is_file() and p.suffix.lower() == ".md" and not p.name.startswith(".")
    ]
    prefixes: List[str] = []
    seen = set()
    for n in names:
        pre = n.split("_", 1)[0]
        if pre and pre not in seen:
            seen.add(pre)
            prefixes.append(pre)
    shown = ", ".join(prefixes[:12])
    extra = " …" if len(prefixes) > 12 else ""
    return f"FDE 手册 ({len(names)}): 行业 {shown or '(无)'}{extra} → /diagnostics/fde"


def _org_line() -> str:
    org = _aiplat_home() / "org"
    bits: List[str] = []
    goals = org / "goals.json"
    if goals.is_file():
        try:
            data = json.loads(goals.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        titles: List[str] = []
        rows = data.get("goals") if isinstance(data, dict) else None
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                t = str(row.get("title") or row.get("goal_id") or "").strip()
                if t:
                    titles.append(t)
        if titles:
            bits.append(
                f"目标 {len(titles)}: " + _summarize_names(titles, limit=8, more="问组织目标可看全量")
            )
        keys = [str(k) for k in (data.keys() if isinstance(data, dict) else [])][:8]
        bits.append("goals.json" + (f"({','.join(keys)})" if keys else ""))
    if (org / "approval_rules.yaml").is_file():
        bits.append("approval_rules.yaml")
    return "组织配置: " + (", ".join(bits) or "(空)") + " → /org/pilot"


def _agent_display(agent_id: str) -> str:
    md = _aiplat_home() / "agents" / agent_id / "AGENT.md"
    if not md.exists():
        return agent_id
    try:
        text = md.read_text(encoding="utf-8", errors="ignore")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].splitlines():
                    line = line.strip()
                    if line.startswith("display_name:"):
                        return line.split(":", 1)[1].strip().strip("'\"") or agent_id
                    if line.startswith("name:") and "display_name" not in text[:200]:
                        pass
    except Exception:
        logger.debug("agent display parse failed for %s", agent_id, exc_info=True)
    return agent_id


def _team_stages_summary() -> str:
    team = _aiplat_home() / "teams" / "default.yaml"
    if not team.exists():
        return "(无 ~/.aiplat/teams/default.yaml)"
    try:
        import yaml

        data = yaml.safe_load(team.read_text(encoding="utf-8")) or {}
        stages = data.get("stages") or []
        bits = []
        for s in stages:
            if not isinstance(s, dict):
                continue
            aid = s.get("agent_id") or "?"
            order = s.get("order", "?")
            bits.append(f"{order}:{aid}")
        title = data.get("team_name") or "default"
        return f"{title} → {' → '.join(bits)}" if bits else f"{title} (无 stages)"
    except Exception:
        logger.debug("team yaml parse failed", exc_info=True)
        return "(团队配置解析失败)"


def refers_to_current_screen(text: str) -> bool:
    """User is pointing at the open page; omit workspace-wide inventory from the brief."""
    t = (text or "").strip()
    return any(
        k in t
        for k in ("这个画面", "这个页面", "当前画面", "当前页", "本页", "这页")
    )


def asks_app_vs_agent(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    path = ("应用" in t or "工厂" in t) and ("agent" in low or "助手" in t)
    return path and any(k in t for k in ("还是", "区别", "该做", "应该做", "选"))


def page_data_has_live_facts(page_data: str) -> bool:
    fields = _parse_page_data_fields(page_data)
    keys = {k.strip().lower() for k in fields}
    return bool(keys & {"issue0", "skillid", "toolid", "mcpid", "agentid", "auditsummary"})


def is_page_followup(text: str) -> bool:
    t = (text or "").strip()
    return any(
        k in t
        for k in ("精简", "再说一遍", "简单点", "通俗", "短一点", "然后呢", "接着说", "刚才那个", "刚才的")
    )


def asks_open_item_audit(text: str) -> bool:
    t = (text or "").strip()
    if not t or asks_app_vs_agent(t):
        return False
    return any(k in t for k in ("审核结果", "审核", "issue0", "这条 skill", "这条skill", "这条 Skill"))


def use_page_only_brief(question: str, page_data: str = "") -> bool:
    """Omit workspace inventory only when the question is about the open page/item."""
    if refers_to_current_screen(question):
        return True
    if page_data_has_live_facts(page_data) and (
        is_page_followup(question) or asks_open_item_audit(question)
    ):
        return True
    return False


def is_inventory_question(text: str) -> bool:
    """True when the user wants the full workspace asset list."""
    t = (text or "").strip()
    if not t:
        return False
    keys = (
        "有哪些 agent",
        "有哪些agent",
        "有哪些技能",
        "有哪些 skill",
        "有哪些skill",
        "有哪些工具",
        "列出 agent",
        "列出agent",
        "工作区有哪些",
        "有哪些应用",
        "有哪些域",
        "有哪些项目",
        "有哪些团队",
        "有哪些 wiki",
        "有哪些模型",
        "有哪些数据源",
        "有哪些画像",
        "有哪些 mcp",
        "有哪些mcp",
        "有哪些评测",
        "有哪些动作",
        "有哪些包",
        "有哪些流水线",
        "有哪些手册",
        "有哪些引擎",
        "有哪些目标",
        "有哪些 action",
        "有哪些提示词",
        "有哪些 prompt",
        "有哪些任务",
        "有哪些 job",
        "有哪些凭证",
        "有哪些变量",
        "有哪些审批",
        "有哪些产出",
        "有哪些 checkpoint",
        "有哪些 provider",
        "有哪些租户",
        "有哪些渠道",
        "有哪些服务",
        "有哪些节点",
        "有哪些用户",
        "有哪些账号",
        "有哪些端口",
        "有哪些路由",
        "有哪些插件",
        "有哪些策略",
        "有哪些审计",
        "有哪些微调",
        "有哪些质量",
        "有哪些代码",
        "有哪些发布",
        "有哪些图谱",
        "有哪些引导",
        "有哪些关系图",
        "有哪些三元组",
        "有哪些 wiki 质量",
        "有哪些治理",
        "有哪些经验",
        "有哪些图示",
        "有哪些 diagram",
        "有哪些门禁",
        "有哪些优化",
    )
    low = t.lower()
    return any(k in low for k in keys)


_SCREEN_DATA_DROP = {
    "totalagents",
    "totalskills",
    "totaltools",
    "totalmcps",
    "statuscount",
    "running",
    "ready",
    "error",
    "failed",
    "listed",
    "purpose",
    "pagetitle",
    "page_title",
}


def _parse_page_data_fields(page_data: str) -> Dict[str, str]:
    """Split pageDataToText `k: v；k: v` into fields."""
    raw = str(page_data or "").strip()
    if not raw:
        return {}
    fields: Dict[str, str] = {}
    for part in raw.replace("\n", "；").split("；"):
        chunk = part.strip()
        if ":" not in chunk:
            continue
        key, val = chunk.split(":", 1)
        k = key.strip()
        v = val.strip()
        if k and v:
            fields[k] = v
    return fields


_EN_AUDIT_NOISE = re.compile(
    r"SIDE_EFFECT_UNREALIZED:?\s*|"
    r"skill declares mutating effects/permissions \[[^\]]*\] but execution_type=prompt has no handler\.py,?\s*registe\w*\s*",
    re.I,
)


def scrub_audit_english(text: str) -> str:
    t = _EN_AUDIT_NOISE.sub("", text or "")
    return re.sub(r"\s+", " ", t).strip()


def _page_live_data_line(page_data: str) -> str:
    """Keep audit issues / actions; drop inventory counters."""
    fields = _parse_page_data_fields(page_data)
    parts = []
    for k, v in fields.items():
        if k.strip().lower() in _SCREEN_DATA_DROP:
            continue
        cleaned = scrub_audit_english(v) if k.lower().startswith("issue") else v
        if cleaned:
            parts.append(f"{k}: {cleaned}")
    if not parts:
        return ""
    return "页面实时数据: " + "；".join(parts)[:1200]


def _chat_llm_brief_lines() -> List[str]:
    """Live purpose registry for 选模问答. No model name pins."""
    fallback = [
        "Chat LLM: 唯一入口 purpose → infra unified_pipeline；业务代码禁止点名模型。界面 /infra/models。",
    ]
    try:
        from core.harness.utils.model_injection import _load_llm_profile

        data = _load_llm_profile() or {}
    except Exception:
        return fallback
    if not isinstance(data, dict):
        return fallback
    profiles = [
        str(k)
        for k in (data.get("purpose_profiles") or {}).keys()
        if str(k) != "intent_route"
    ]
    routing = data.get("purpose_routing") or {}
    open_qa = [str(x) for x in (routing.get("open_qa_purposes") or [])]
    default_p = str(routing.get("default") or "chat")
    shown = ", ".join(profiles[:24])
    if len(profiles) > 24:
        shown += f" …共{len(profiles)}个"
    return [
        "Chat LLM: 任务明确时用已登记 purpose；开放问答 purpose=auto"
        "（intent_route 只输出 purpose 名）再 unified_pipeline 打分。"
        "禁止业务代码点名模型。界面 /infra/models。",
        f"已登记 purpose: {shown or '(简报未见)'}",
        f"开放问答枚举: {', '.join(open_qa) or default_p}；默认 {default_p}",
    ]


def build_platform_status_brief(
    *,
    page_context: Any = None,
    page_data: str = "",
    force_refresh: bool = False,
    include_inventory: bool = True,
    name_limit: int = 12,
) -> str:
    """Build a short Chinese brief of live platform inventory + menus + team.

    Cached ~60s unless force_refresh (still re-reads page context each call).
    When include_inventory is False (user pointing at the open page), skip the
    workspace-wide asset list so the model sees page chrome + live fields only.
    """
    import time

    # Append ephemeral page context (not cached). Built first so slim questions
    # never wait on disk inventory / capability graph.
    page_bits: List[str] = []
    purposes = {}
    purpose = ""
    try:
        purposes = (_load_menu_catalog() or {}).get("purposes") or {}
    except Exception:
        purposes = {}
    if isinstance(page_context, dict):
        route = page_context.get("route") or ""
        label = page_context.get("label") or ""
        group = page_context.get("groupLabel") or page_context.get("group") or ""
        purpose = str(page_context.get("purpose") or purposes.get(route) or "").strip()
        if route or label:
            page_bits.append(f"当前页: {label or route} ({route}) 分组={group}")
        if purpose:
            page_bits.append(f"当前页功能: {purpose}")
    elif page_context:
        page_bits.append(f"当前页: {page_context}")
    live = _page_live_data_line(page_data) if page_data else ""
    if live:
        page_bits.append(live)
    page_block = "\n".join(page_bits)
    if not include_inventory:
        slim = [
            "=== 当前页 ===",
            page_block or "（无当前页上下文）",
            "「这个画面」指上面这些事实。问审核/按钮/怎么做必须用「页面实时数据」。",
            "本轮优先当前页事实。用户若说精简/再说一遍，接本会话刚才，把本页审核压成最多5句。",
            "禁止改答「做应用还是 Agent」，除非用户本句在问构建路径。",
            "不要列举工作区全量 Agent/Skill。用户若问有哪些资产，再列名单。",
            "若问的是通用知识而非本页，可答并标明「通用说明，非 aiPlat 既有」。",
        ]
        return "\n".join(slim)

    global _BRIEF_CACHE, _BRIEF_CACHE_TS
    now = time.time()
    use_short_cache = name_limit == 12
    base = _BRIEF_CACHE if use_short_cache else ""
    if force_refresh or not base or (now - _BRIEF_CACHE_TS) > _BRIEF_TTL_SEC:
        agents = _list_workspace_dirs("agents", ["AGENT.md"])
        agents = [a for a in agents if a not in ("apps", "builder_outputs")]
        skills = _list_workspace_dirs("skills", ["SKILL.md"])
        mcps = _list_mcp_assets()
        workflows = _list_workspace_dirs(
            "workflows", ["workflow.yaml", "workflow.json"]
        )
        tools = _list_workspace_tools()
        apps = _list_deployed_apps()
        domains = _list_domain_ids()
        factory_projects = _list_factory_projects()
        team_files = _list_team_files()
        wiki_n = _wiki_page_count()
        wiki_cols = _list_wiki_collections()
        models = _list_registered_models()
        datasources = _list_yaml_stems("datasources")
        profiles = _list_yaml_stems("profiles")
        packages = _list_package_ids()
        auto_pipes = _list_auto_pipelines()
        eval_sets = _list_eval_sets()
        actions = _list_yaml_stems("actions")
        action_ids = _list_action_ids()
        engine_agents = _list_engine_ids("agents", "AGENT.md")
        engine_skills = _list_engine_ids("skills", "SKILL.md")
        kb_tenants = _list_kb_tenants()
        eval_n = _count_json_files("eval_results")
        prompt_ids = _list_prompt_template_ids()
        mem_n = _memory_note_count()
        jobs = _list_jobs()
        job_runs_n = _count_table_rows("job_runs")
        creds = _list_json_asset_labels(
            "credentials.json", name_keys=("name", "id"), extra_keys=("provider", "tool_name")
        )
        var_names = _list_json_asset_labels(
            "variables.json", name_keys=("name", "id"), extra_keys=("scope",)
        )
        approvals = _list_pending_approvals()
        agent_exec = _sqlite_status_summary("agent_executions")
        skill_exec = _sqlite_status_summary("skill_executions")
        mem_sess_n = _count_table_rows("memory_sessions")
        ltm_n = _count_table_rows("long_term_memories")
        ckpts = _list_dir_names("file_checkpoints")
        learn_results = _list_dir_names("learning/results")
        providers = _list_llm_providers()
        plat_tenants = _list_platform_tenants() or _list_sqlite_labels("tenants", "tenant_id", "name")
        gw_channels = _list_gateway_channels() or _list_sqlite_labels("gateway_pairings", "channel")
        traces_n = _count_table_rows("traces")
        trace_st = _sqlite_status_summary("traces")
        plat_apps = _list_platform_apps()
        plat_wfs = _list_platform_workflows()
        plugins = _list_plugins()
        pol_n = _count_table_rows("tenant_policies")
        auth_users = _list_auth_users()
        gw_routes = _list_gateway_routes()
        gw_tokens = _list_gateway_token_names()
        port_svcs = _port_service_lines()
        listen = _listen_ports()
        ft_jobs = _list_dir_names("finetune_jobs")
        ft_data = _list_file_stems("finetune_data", (".jsonl", ".json"))
        quality = _list_file_stems("model_quality", (".json",))
        syscall_kinds = _sqlite_status_summary("syscall_events", col="kind")
        audit_n = _count_table_rows("audit_logs")
        audit_actions = _sqlite_status_summary("audit_logs", col="action")
        queue = _list_session_queue_summary()
        key_prefixes = _list_api_key_prefixes()
        graph_runs_n = _count_table_rows("graph_runs")
        graph_run_st = _sqlite_status_summary("graph_runs")
        onboard_n = _count_table_rows("onboarding_evidence")
        rollouts_n = _count_table_rows("release_rollouts")
        diagrams = _list_file_stems("diagrams", (".xml", ".svg", ".json", ".drawio"))
        prd_gates = _list_yaml_stems("prd_gates")
        ontology_gen = _list_dir_names("ontology_gen")
        opts = _list_yaml_stems("optimizations")
        accept_n = _count_json_in_dir("acceptance")
        team = _team_stages_summary()
        catalog = _load_menu_catalog()

        lines: List[str] = [
            "=== 平台实况简报（磁盘扫描，非手册）===",
            f"AIPLAT_HOME: {_aiplat_home()}",
            f"工作区 Agent ({len(agents)}): "
            + _summarize_names(
                [f"{a}({_agent_display(a)})" for a in agents],
                limit=name_limit,
            ),
            f"工作区 Skill ({len(skills)}): "
            + _summarize_names(skills, limit=name_limit),
            f"工作区 Tool ({len(tools)}): "
            + _summarize_names(tools, limit=name_limit),
            f"工作区 MCP ({len(mcps)}): "
            + _summarize_names(mcps, limit=name_limit),
            f"工作区 Workflow ({len(workflows)}): "
            + _summarize_names(workflows, limit=name_limit),
            f"已部署应用 ({len(apps)}): "
            + _summarize_names(apps, limit=name_limit)
            + " → 菜单 /app/apps；新建走 /app/factory",
            f"业务域 ({len(domains)}): "
            + _summarize_names(domains, limit=name_limit),
            f"应用工厂项目 ({len(factory_projects)}): "
            + _summarize_names(factory_projects, limit=name_limit)
            + " → /app/factory（名单来自 projects.json）",
            f"工作区团队 ({len(team_files)}): "
            + _summarize_names(team_files, limit=name_limit),
            f"Wiki: {wiki_n} 页 / {len(wiki_cols)} 集合"
            + (("：" + _summarize_names(wiki_cols, limit=64)) if wiki_cols else "")
            + "（~/.aiplat/wiki/collections）",
            f"数据源 ({len(datasources)}): "
            + _summarize_names(datasources, limit=name_limit),
            f"控制画像 ({len(profiles)}): "
            + _summarize_names(profiles, limit=name_limit),
            f"Adapters 本地模型 ({len(models['local'])}): "
            + _summarize_names(models["local"], limit=name_limit, more="问「有哪些模型」可看全量")
            + " → /infra/models（adapters 去重清单，不是指定选哪个）",
            f"Adapters API 模型 ({len(models['api'])}): "
            + _summarize_names(models["api"], limit=name_limit, more="问「有哪些模型」可看全量")
            + " → /infra/models",
            _model_manager_brief_line(name_limit=name_limit),
            f"登记 Provider ({len(providers)}): "
            + _summarize_names(providers, limit=name_limit, more="问「有哪些 provider」可看全量")
            + " → /infra/models（providers.yaml 的 id，不含 API key）",
            f"平台租户 ({len(plat_tenants)}): "
            + _summarize_names(plat_tenants, limit=name_limit)
            + " → /platform/tenant",
            f"网关渠道绑定 ({len(gw_channels)}): "
            + _summarize_names(gw_channels, limit=name_limit)
            + " → /platform/gateway、/app/channels",
            f"Traces: {traces_n} 条"
            + (f"；{trace_st}" if trace_st else "")
            + " → /diagnostics/traces（只计状态，不含 attributes）",
            f"平台应用表 ({len(plat_apps)}): "
            + _summarize_names(plat_apps, limit=name_limit)
            + " → /app/apps（platform.apps，不含密钥）",
            f"平台 Workflow ({len(plat_wfs)}): "
            + _summarize_names(plat_wfs, limit=name_limit)
            + " → /core/workflows",
            f"插件 ({len(plugins)}): "
            + _summarize_names(plugins, limit=name_limit)
            + " → /core/plugins（不含 manifest）",
            f"租户策略记录: {pol_n} → /diagnostics/policies（不含 policy JSON）",
            f"认证用户 ({len(auth_users)}): "
            + _summarize_names(auth_users, limit=name_limit)
            + " → /platform/auth（只列用户名/角色/状态，不含密码和 data_json）",
            f"网关路由 ({len(gw_routes)}): "
            + _summarize_names(gw_routes, limit=name_limit)
            + " → /platform/gateway",
            f"网关 Token 名 ({len(gw_tokens)}): "
            + _summarize_names(gw_tokens, limit=name_limit)
            + "（只列名称，不含 token/sha）",
            f"端口服务配置: "
            + (_summarize_names(port_svcs, limit=name_limit) if port_svcs else "(未设 AIPLAT_PORT_SERVICES)"),
            f"本机监听口: "
            + (_summarize_names(listen, limit=name_limit) if listen else "(简报未见)"),
            f"微调任务目录 ({len(ft_jobs)}): "
            + _summarize_names(ft_jobs, limit=name_limit)
            + " → /infra/finetune（finetune_jobs，不含样本正文）",
            f"微调数据集文件 ({len(ft_data)}): "
            + _summarize_names(ft_data, limit=name_limit)
            + " → /infra/finetune（只列文件名）",
            f"模型质量探针 ({len(quality)}): "
            + _summarize_names(quality, limit=name_limit)
            + " → /infra/llm-stats（model_quality 文件名，不是指定选模）",
            _code_graph_line(),
            _cap_index_line(),
            f"本体三元组: {_ontology_triple_n()} 条 → /ontology-editor（只计数量）",
            _wiki_quality_line(),
            f"决策轨迹: {_count_json_in_dir('decision_traces')} 份 → /diagnostics/routing-replay（只计文件数，不含正文）",
            _governance_cycle_line(),
            _awareness_log_line(),
            _evolution_line(),
            _experience_feedback_line(),
            f"图示文件 ({len(diagrams)}): "
            + _summarize_names(diagrams, limit=name_limit)
            + " → /app/factory（diagrams，不含 xml 正文）",
            f"PRD 门禁 ({len(prd_gates)}): "
            + _summarize_names(prd_gates, limit=name_limit)
            + " → /app/factory（prd_gates yaml 名）",
            f"本体生成草稿 ({len(ontology_gen)}): "
            + _summarize_names(ontology_gen, limit=name_limit)
            + " → /ontology-editor（ontology_gen 目录名）",
            f"优化配置 ({len(opts)}): "
            + _summarize_names(opts, limit=name_limit)
            + " → /diagnostics（optimizations yaml 名）",
            f"验收包: {accept_n} 份 → /diagnostics/fde（acceptance，不含正文）",
            f"Graph 运行: {graph_runs_n} 条"
            + (f"；{graph_run_st}" if graph_run_st else "")
            + " → /diagnostics/graphs（只计状态，不含图数据）",
            f"引导证据: {onboard_n} 条 → /onboarding",
            f"发布灰度: {rollouts_n} 条 → /core/skills-rollouts（release_rollouts）",
            "Syscall 种类: "
            + (syscall_kinds or "(无)")
            + " → /diagnostics/syscalls（只计 kind，不含 args/result）",
            f"审计日志: {audit_n} 条"
            + (f"；动作 {audit_actions}" if audit_actions else "")
            + " → /diagnostics/audit（只计 action/status，不含 detail_json）",
            f"会话队列 ({len(queue)} 组): "
            + _summarize_names(queue, limit=name_limit)
            + " → /app/sessions（不含 payload）",
            f"API Key 前缀 ({len(key_prefixes)}): "
            + _summarize_names(key_prefixes, limit=name_limit)
            + " → /platform/auth（只列 prefix，不含 hash）",
            f"技能包 ({len(packages)}): "
            + _summarize_names(packages, limit=name_limit)
            + " → /core/skill-packs（packages/registry）",
            f"自动流水线 ({len(auto_pipes)}): "
            + _summarize_names(auto_pipes, limit=name_limit),
            f"评测集 ({len(eval_sets)}): "
            + _summarize_names(eval_sets, limit=name_limit)
            + f"；eval_results {eval_n} 份 → /diagnostics/eval",
            f"Action 契约文件 ({len(actions)}): "
            + _summarize_names(actions, limit=name_limit)
            + (
                "；id: " + _summarize_names(action_ids, limit=name_limit, more="问「有哪些动作」可看全量")
                if action_ids
                else ""
            ),
            f"引擎 Agent ({len(engine_agents)}): "
            + _summarize_names(engine_agents, limit=name_limit)
            + " → /core/agents（仓库 core/engine，不是工作区 ~/.aiplat/agents）",
            f"引擎 Skill ({len(engine_skills)}): "
            + _summarize_names(engine_skills, limit=name_limit)
            + " → /core/skills",
            f"KB 租户 ({len(kb_tenants)}): "
            + _summarize_names(kb_tenants, limit=name_limit)
            + " → /knowledge/library",
            f"提示词模板 ({len(prompt_ids)}): "
            + _summarize_names(prompt_ids, limit=name_limit, more="问「有哪些提示词」可看全量")
            + " → /core/prompts（只列 id，不含正文）",
            f"工作区记忆笔记: {mem_n} 个 md（~/.aiplat/memory，简报不注入正文）",
            f"定时任务 ({len(jobs)}): "
            + _summarize_names(jobs, limit=name_limit, more="问「有哪些任务」可看全量")
            + f"；job_runs {job_runs_n} 条 → /core/jobs（不含 payload）",
            f"凭证名 ({len(creds)}): "
            + _summarize_names(creds, limit=name_limit)
            + " → /core/credentials（只列名称，不含密钥）",
            f"变量名 ({len(var_names)}): "
            + _summarize_names(var_names, limit=name_limit)
            + " → /core/variables（只列名称/scope，不含取值）",
            f"待审/审批单 ({len(approvals)} 组): "
            + _summarize_names(approvals, limit=name_limit, more="问「有哪些审批」可看全量")
            + " → /approval（只列 operation/status，不含 details）",
            "Agent 执行: "
            + (agent_exec or "(无)")
            + " → /diagnostics/runs（只计状态，不含 input/output）",
            "Skill 执行: "
            + (skill_exec or "(无)")
            + "（只计状态，不含 input/output）",
            _recent_failed_runs(limit=12 if name_limit == 0 else 5),
            f"Memory 会话: {mem_sess_n}；长期记忆条数 {ltm_n}（正文不注入）→ /core/memory",
            f"文件 Checkpoint 会话 ({len(ckpts)}): "
            + _summarize_names(ckpts, limit=name_limit)
            + " → /core/checkpoints（不注入文件内容）",
            f"学习产出目录 ({len(learn_results)}): "
            + _summarize_names(learn_results, limit=name_limit)
            + " → /core/learning/artifacts（~/.aiplat/learning/results）",
            _fde_manual_line(),
            _org_line(),
            f"默认团队流水线: {team}",
        ]
        lines.extend(_chat_llm_brief_lines())
        lines.extend(_format_menu_lines(catalog.get("entries") or []))
        lines.append("构建路径索引:")
        for bp in catalog.get("build_paths") or []:
            agent = bp.get("agent")
            extra = f", agent={agent}" if agent else ""
            lines.append(
                f"  - [{bp.get('id')}] {bp.get('title')} → {bp.get('menu')}{extra}"
                f" | 何时: {bp.get('when')}"
            )
        lines.append(
            "规则: 平台事实只引用本简报出现的资产名；简报没有的写「简报未见」，不要编造。"
            "通用知识可用模型能力回答，必须标明「通用说明，非 aiPlat 既有」，且不得把它说成工作区已有同名 Skill/Agent。"
            "手册仅解释操作步骤；与简报冲突时以简报为准。"
            "「做一个应用/产品」→ /app/factory；「只要平台内角色」→ /workspace/agents。"
            "简报里的 Agent 是工作区资产/样例，可参考可试跑，不等于用户的应用已经交付。"
            "禁止用「工作区有 N 个 Agent」劝用户不要走工厂。"
            "可以建议去应用工厂，但不要替用户创建项目或 pipeline.start。"
            "「这个画面」只是指代当前页：用途看「当前页功能」，审核/按钮看「页面实时数据」。"
            "禁止因用户说了「这个画面」就只复述菜单简介。"
            "禁止把简报里的全量 Agent/Skill 名单当成本页内容（除非用户问有哪些资产）。"
        )
        base = "\n".join(lines)
        if use_short_cache:
            _BRIEF_CACHE = base
            _BRIEF_CACHE_TS = now

    if page_block:
        return (
            "=== 当前页 ===\n"
            + page_block
            + "\n"
            + base
        )
    return base


def clear_brief_cache() -> None:
    global _BRIEF_CACHE, _BRIEF_CACHE_TS
    _BRIEF_CACHE = None
    _BRIEF_CACHE_TS = 0.0
