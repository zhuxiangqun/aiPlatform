"""Security View Compiler (Phase A) — deterministic, no LLM.

Consumes the existing code_graph (file-level nodes/edges) and emits
``secview.v1`` JSON: entries / sinks / gates / scored hot_paths.

All risk labels are heuristic (call/import reachability ≠ taint).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_log = logging.getLogger("security_view")

SCHEMA_VERSION = "secview.v1"
DEFAULT_MAX_DEPTH = 8
DEFAULT_MAX_PATHS = 20
DEFAULT_DIGEST_MAX_CHARS = 4000

# Trust / sink severity weights for hot-path scoring
_TRUST_SCORE = {"external": 30, "internal": 10, "admin": 5}
_SINK_SCORE = {
    "subprocess": 40,
    "eval_exec": 45,
    "deserialize": 40,
    "sql": 35,
    "filesystem_write": 20,
    "network_egress": 30,
    "secret": 25,
    "other": 10,
}


@dataclass
class Entry:
    id: str
    kind: str
    file: str
    symbol: str = ""
    route: str = ""
    layer: str = "unknown"
    trust: str = "internal"  # external|internal|admin


@dataclass
class Sink:
    id: str
    kind: str
    file: str
    symbol: str = ""
    line: Optional[int] = None
    evidence_snippet: str = ""


@dataclass
class Gate:
    id: str
    kind: str
    file: str
    symbol: str = ""


@dataclass
class HotPath:
    id: str
    entry_id: str
    sink_id: str
    via: List[str] = field(default_factory=list)
    edge_kinds: List[str] = field(default_factory=list)
    gates_on_path: List[str] = field(default_factory=list)
    risk_hint: str = "unknown"
    layer: str = "unknown"
    score: float = 0.0
    heuristic: bool = True  # always true in Phase A


@dataclass
class LayerStats:
    file_count: int = 0
    entry_count: int = 0
    sink_count: int = 0
    gate_count: int = 0
    top_hubs: List[str] = field(default_factory=list)


@dataclass
class RepoSummary:
    trust_boundaries: List[str] = field(default_factory=list)
    priority_areas: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=lambda: [
        "hot_paths use call/import reachability, not taint; treat as heuristic",
    ])


@dataclass
class SecurityView:
    schema_version: str
    repo_id: str
    built_at: str
    graph_stats: Dict[str, int]
    layers: Dict[str, LayerStats]
    entries: List[Entry]
    sinks: List[Sink]
    gates: List[Gate]
    hot_paths: List[HotPath]
    repo_summary: RepoSummary
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repo_id": self.repo_id,
            "built_at": self.built_at,
            "graph_stats": self.graph_stats,
            "layers": {k: asdict(v) for k, v in self.layers.items()},
            "entries": [asdict(e) for e in self.entries],
            "sinks": [asdict(s) for s in self.sinks],
            "gates": [asdict(g) for g in self.gates],
            "hot_paths": [asdict(h) for h in self.hot_paths],
            "repo_summary": asdict(self.repo_summary),
            "metrics": self.metrics,
        }


def _default_rules() -> Dict[str, Any]:
    """Built-in Python-first rules; YAML may override/extend."""
    return {
        "entry": {
            "python": [
                {
                    "kind": "http_route",
                    "trust": "external",
                    "match": {
                        "path_contains": ["/api/", "/routers/", "routes.py"],
                        "text_regex": [r"@router\.(get|post|put|patch|delete)\b", r"@app\.(get|post)\b"],
                    },
                },
                {
                    "kind": "skill_handler",
                    "trust": "internal",
                    "match": {
                        "path_contains": ["media_skill_handlers.py", "/skills/"],
                        "symbol_contains": ["handle_", "HANDLERS"],
                    },
                },
            ],
        },
        "sink": {
            "python": [
                {"kind": "subprocess", "match": {"text_regex": [r"\bsubprocess\.(run|Popen|call)\b", r"\bos\.system\b"]}},
                {"kind": "eval_exec", "match": {"text_regex": [r"(?<![\w.])eval\s*\(\s*['\"\w(]", r"(?<![\w.])exec\s*\(\s*['\"\w(]"]}},
                {"kind": "deserialize", "match": {"text_regex": [r"\bpickle\.loads\b", r"\byaml\.load\s*\("]}},
                {"kind": "network_egress", "match": {"text_regex": [r"\brequests\.(get|post)\b", r"\bhttpx\.(get|post)\b", r"\burlopen\s*\("]}},
                {"kind": "filesystem_write", "match": {"text_regex": [r"open\s*\([^)]*['\"]w", r"\.write_text\s*\(", r"\.write_bytes\s*\("]}},
                {"kind": "sql", "match": {"text_regex": [r"execute\s*\(\s*[f\"'].*%", r"execute\s*\(\s*f[\"']"]}},
            ],
        },
        "gate": {
            "python": [
                {"kind": "policy", "match": {"text_regex": [r"\bPolicyGate\b", r"\bcheck_tool\b", r"\brequire_builder_access\b"]}},
                {"kind": "ssrf", "match": {"text_regex": [r"\bcheck_ssrf\b", r"\bvalidate_url\b", r"\bis_safe_url\b", r"SSRF"]}},
                {"kind": "sandbox", "match": {"text_regex": [r"\bStageSandbox\b", r"\bDockerSandbox\b", r"\bbuild_os_sandbox_cmd\b"]}},
                {"kind": "authz", "match": {"text_regex": [r"\bDepends\s*\(", r"\brequire_auth\b", r"\bmfa_required\b"]}},
            ],
        },
    }


def _rules_search_paths() -> List[Path]:
    paths: List[Path] = []
    try:
        from core.harness.utils.paths import get_aiplat_home

        paths.append(Path(get_aiplat_home()) / "security_view_rules.yaml")
    except Exception:
        paths.append(Path.home() / ".aiplat" / "security_view_rules.yaml")
    here = Path(__file__).resolve()
    # aiPlat-core/core/harness/knowledge → workspace_seeds
    for cand in (
        here.parents[2] / "workspace_seeds" / "security_view_rules.yaml",
        here.parents[3] / "workspace_seeds" / "security_view_rules.yaml",
        here.parents[3] / "core" / "workspace_seeds" / "security_view_rules.yaml",
    ):
        paths.append(cand)
    return paths


def load_rules(path: Optional[Path] = None) -> Dict[str, Any]:
    base = _default_rules()
    candidates = [path] if path else _rules_search_paths()
    for p in candidates:
        if not p or not p.is_file():
            continue
        try:
            import yaml

            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                # Shallow merge per section/lang
                for section in ("entry", "sink", "gate"):
                    if section not in data:
                        continue
                    base.setdefault(section, {})
                    for lang, rules in (data[section] or {}).items():
                        base[section].setdefault(lang, [])
                        if isinstance(rules, list):
                            base[section][lang].extend(rules)
                _log.debug("security_view rules loaded from %s", p)
                break
        except Exception as e:
            _log.debug("rules load failed %s: %s", p, e)
    return base


def _layer_of(file_path: str) -> str:
    from core.harness.knowledge.code_graph import _layer_bucket

    return _layer_bucket(file_path)


def _cache_path() -> Path:
    try:
        from core.harness.utils.paths import get_aiplat_home

        root = Path(get_aiplat_home())
    except Exception:
        root = Path.home() / ".aiplat"
    return root / "cache" / "security_view.json"


def _fingerprint(nodes: Dict[str, Any], edges: List[Any]) -> str:
    sample = ":".join(sorted(nodes.keys())[:80])
    raw = f"{len(nodes)}:{len(edges)}:{sample}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _compile_patterns(rules: Dict[str, Any], section: str) -> List[Tuple[str, str, Dict[str, Any], List[re.Pattern]]]:
    """Return list of (kind, trust_or_empty, match_dict, compiled_text_regexes)."""
    out: List[Tuple[str, str, Dict[str, Any], List[re.Pattern]]] = []
    for _lang, items in (rules.get(section) or {}).items():
        if not isinstance(items, list):
            continue
        for rule in items:
            if not isinstance(rule, dict):
                continue
            kind = str(rule.get("kind") or "other")
            trust = str(rule.get("trust") or "")
            match = rule.get("match") or {}
            regs: List[re.Pattern] = []
            for rx in match.get("text_regex") or []:
                try:
                    regs.append(re.compile(rx))
                except re.error:
                    continue
            out.append((kind, trust, match, regs))
    return out


def _path_matches(file_path: str, match: Dict[str, Any]) -> bool:
    needles = match.get("path_contains") or []
    if not needles:
        return False
    fp = file_path.replace("\\", "/")
    return any(n in fp for n in needles)


def _symbol_matches(symbols: List[Any], match: Dict[str, Any]) -> bool:
    needles = match.get("symbol_contains") or []
    if not needles:
        return False
    names: List[str] = []
    for s in symbols or []:
        if isinstance(s, (list, tuple)) and s:
            names.append(str(s[0]))
        else:
            names.append(str(s))
    blob = " ".join(names)
    return any(n in blob for n in needles)


def _read_file_text(repo_root: Path, rel: str) -> str:
    from core.harness.knowledge.code_graph import read_text

    return read_text(repo_root / rel, max_bytes=200_000)


def _detect_entities(
    repo_root: Path,
    nodes: Dict[str, Dict[str, Any]],
    rules: Dict[str, Any],
) -> Tuple[List[Entry], List[Sink], List[Gate]]:
    entry_rules = _compile_patterns(rules, "entry")
    sink_rules = _compile_patterns(rules, "sink")
    gate_rules = _compile_patterns(rules, "gate")

    entries: List[Entry] = []
    sinks: List[Sink] = []
    gates: List[Gate] = []
    seen_entry: Set[str] = set()
    seen_sink: Set[str] = set()
    seen_gate: Set[str] = set()

    for rel, node in nodes.items():
        if not str(rel).endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
            continue
        text = ""
        symbols = node.get("symbols") or []
        routes = node.get("routes") or []
        layer = _layer_of(rel)

        # --- entries ---
        # Graph-native routes always count as external HTTP entries.
        if routes:
            eid = f"entry:{rel}"
            if eid not in seen_entry:
                seen_entry.add(eid)
                r0 = routes[0]
                route_s = str(r0[0] if isinstance(r0, (list, tuple)) else r0)
                sym = ""
                if symbols:
                    s0 = symbols[0]
                    sym = str(s0[0] if isinstance(s0, (list, tuple)) else s0)
                entries.append(
                    Entry(
                        id=eid,
                        kind="http_route",
                        file=rel,
                        symbol=sym,
                        route=route_s,
                        layer=layer,
                        trust="external",
                    )
                )

        for kind, trust, match, regs in entry_rules:
            # AND all declared constraints (path / symbol / text_regex).
            constraints: List[bool] = []
            if match.get("path_contains"):
                constraints.append(_path_matches(rel, match))
            if match.get("symbol_contains"):
                constraints.append(_symbol_matches(symbols, match))
            if regs:
                if not text:
                    text = _read_file_text(repo_root, rel)
                constraints.append(bool(text) and any(r.search(text) for r in regs))
            hit = bool(constraints) and all(constraints)
            if hit:
                eid = f"entry:{rel}"
                if eid not in seen_entry:
                    seen_entry.add(eid)
                    route_s = ""
                    if routes:
                        r0 = routes[0]
                        route_s = str(r0[0] if isinstance(r0, (list, tuple)) else r0)
                    sym = ""
                    if symbols:
                        s0 = symbols[0]
                        sym = str(s0[0] if isinstance(s0, (list, tuple)) else s0)
                    entries.append(
                        Entry(
                            id=eid,
                            kind=kind,
                            file=rel,
                            symbol=sym,
                            route=route_s,
                            layer=layer,
                            trust=trust or ("external" if kind == "http_route" else "internal"),
                        )
                    )

        # --- sinks / gates need text ---
        need_text = bool(sink_rules or gate_rules)
        if need_text and not text:
            text = _read_file_text(repo_root, rel)
        if not text:
            continue

        for kind, _trust, match, regs in sink_rules:
            if any(r.search(text) for r in regs):
                sid = f"sink:{kind}:{rel}"
                if sid not in seen_sink:
                    seen_sink.add(sid)
                    # first matching line hint
                    line_no = None
                    snippet = ""
                    for i, line in enumerate(text.splitlines()[:400], 1):
                        if any(r.search(line) for r in regs):
                            line_no = i
                            snippet = line.strip()[:160]
                            break
                    sinks.append(
                        Sink(
                            id=sid,
                            kind=kind,
                            file=rel,
                            symbol="",
                            line=line_no,
                            evidence_snippet=snippet,
                        )
                    )

        for kind, _trust, match, regs in gate_rules:
            if any(r.search(text) for r in regs):
                gid = f"gate:{kind}:{rel}"
                if gid not in seen_gate:
                    seen_gate.add(gid)
                    gates.append(Gate(id=gid, kind=kind, file=rel, symbol=kind))

    return entries, sinks, gates


def _score_path(entry: Entry, sink: Sink, via: List[str], gates_on: List[str]) -> float:
    score = float(_TRUST_SCORE.get(entry.trust, 10))
    score += float(_SINK_SCORE.get(sink.kind, 10))
    score += max(0, 12 - len(via))  # shorter paths score higher
    if gates_on:
        score -= 15 * len(gates_on)
    else:
        score += 20
    # cross-layer bonus
    layers = {_layer_of(p) for p in [entry.file, sink.file, *via]}
    if len(layers) >= 2:
        score += 8
    return score


def _build_hot_paths(
    nodes: Dict[str, Dict[str, Any]],
    entries: List[Entry],
    sinks: List[Sink],
    gates: List[Gate],
    max_depth: int,
    max_paths: int,
) -> List[HotPath]:
    sink_by_file: Dict[str, List[Sink]] = {}
    for s in sinks:
        sink_by_file.setdefault(s.file, []).append(s)
    gate_files = {g.file for g in gates}
    gate_by_file = {g.file: g.id for g in gates}

    paths: List[HotPath] = []
    for entry in entries:
        start = entry.file
        if start not in nodes:
            continue
        # BFS on import outs
        queue: List[Tuple[str, List[str]]] = [(start, [start])]
        seen: Set[str] = {start}
        while queue:
            cur, path = queue.pop(0)
            if len(path) - 1 > max_depth:
                continue
            if cur in sink_by_file:
                for sink in sink_by_file[cur]:
                    # Same-file sink: via empty; still emit (entry hosts sink).
                    gates_on = [gate_by_file[p] for p in path if p in gate_files]
                    # Gate in same file as entry/sink also counts
                    if cur in gate_files and gate_by_file[cur] not in gates_on:
                        gates_on.append(gate_by_file[cur])
                    risk = "gate_present" if gates_on else "external→sink_without_gate"
                    if entry.trust != "external" and not gates_on:
                        risk = "internal→sink_without_gate"
                    via = path[1:-1] if cur != start else []
                    score = _score_path(entry, sink, via, gates_on)
                    paths.append(
                        HotPath(
                            id=f"path:{len(paths) + 1}",
                            entry_id=entry.id,
                            sink_id=sink.id,
                            via=via,
                            edge_kinds=["import"] * max(0, len(path) - 1),
                            gates_on_path=gates_on,
                            risk_hint=risk,
                            layer=entry.layer,
                            score=score,
                            heuristic=True,
                        )
                    )
            if cur in sink_by_file and cur == start:
                # Still expand outs so cross-file sinks are found too
                pass
            for nxt in nodes.get(cur, {}).get("out") or []:
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))

    paths.sort(key=lambda p: (-p.score, p.risk_hint))
    # re-id after sort
    for i, p in enumerate(paths[:max_paths], 1):
        p.id = f"path:{i}"
    return paths[:max_paths]


def _build_layers(
    nodes: Dict[str, Dict[str, Any]],
    entries: List[Entry],
    sinks: List[Sink],
    gates: List[Gate],
) -> Dict[str, LayerStats]:
    stats: Dict[str, LayerStats] = {}
    for rel, node in nodes.items():
        layer = _layer_of(rel)
        st = stats.setdefault(layer, LayerStats())
        st.file_count += 1
    for e in entries:
        stats.setdefault(e.layer, LayerStats()).entry_count += 1
    for s in sinks:
        stats.setdefault(_layer_of(s.file), LayerStats()).sink_count += 1
    for g in gates:
        stats.setdefault(_layer_of(g.file), LayerStats()).gate_count += 1
    # hubs: highest in-degree per layer
    by_layer: Dict[str, List[Tuple[int, str]]] = {}
    for rel, node in nodes.items():
        layer = _layer_of(rel)
        by_layer.setdefault(layer, []).append((int(node.get("in") or 0), rel))
    for layer, pairs in by_layer.items():
        pairs.sort(reverse=True)
        stats.setdefault(layer, LayerStats()).top_hubs = [p for _, p in pairs[:5]]
    return stats


def compact_security_digest(sv: SecurityView, max_chars: int = DEFAULT_DIGEST_MAX_CHARS) -> Dict[str, Any]:
    """Token-budgeted digest for Agent plan stage."""
    payload = {
        "schema_version": sv.schema_version,
        "repo_summary": asdict(sv.repo_summary),
        "graph_stats": sv.graph_stats,
        "layer_counts": {
            k: {"files": v.file_count, "entries": v.entry_count, "sinks": v.sink_count, "gates": v.gate_count}
            for k, v in sv.layers.items()
        },
        "top_hot_paths": [
            {
                "id": h.id,
                "entry": h.entry_id,
                "sink": h.sink_id,
                "risk_hint": h.risk_hint,
                "score": h.score,
                "heuristic": True,
                "via_len": len(h.via),
            }
            for h in sv.hot_paths[:8]
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False)
    if len(raw) > max_chars:
        payload["top_hot_paths"] = payload["top_hot_paths"][:3]
        raw = json.dumps(payload, ensure_ascii=False)[:max_chars]
    payload["_token_estimate"] = max(1, len(raw) // 4)
    payload["_chars"] = len(raw)
    return payload


def build_security_view(
    *,
    repo_id: str = "aiPlatform",
    nodes: Optional[Dict[str, Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
    rules: Optional[Dict[str, Any]] = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_paths: int = DEFAULT_MAX_PATHS,
    cache: bool = True,
    force: bool = False,
) -> SecurityView:
    """Compile secview.v1 from code_graph. Pure-deterministic (no LLM)."""
    t0 = time.time()
    from core.harness.knowledge.code_graph import (
        build_graph,
        count_cycles,
        default_roots,
        repo_root,
    )

    root = repo_root()
    if nodes is None or edges is None:
        abs_roots = [(root / r).resolve() for r in default_roots()]
        nodes, edges, _issues = build_graph(root, abs_roots)
    assert nodes is not None and edges is not None

    rules = rules or load_rules()
    fp = _fingerprint(nodes, edges)
    cpath = _cache_path()
    if cache and not force and cpath.is_file():
        try:
            cached = json.loads(cpath.read_text(encoding="utf-8"))
            if cached.get("_fingerprint") == fp and cached.get("schema_version") == SCHEMA_VERSION:
                cached.pop("_fingerprint", None)
                return _dict_to_view(cached)
        except Exception as e:
            _log.debug("cache miss: %s", e)

    entries, sinks, gates = _detect_entities(root, nodes, rules)
    layers = _build_layers(nodes, entries, sinks, gates)
    hot_paths = _build_hot_paths(nodes, entries, sinks, gates, max_depth, max_paths)
    try:
        cycles = count_cycles(nodes)
    except Exception:
        cycles = 0

    priority = [
        h.entry_id
        for h in hot_paths
        if "without_gate" in h.risk_hint
    ][:10]
    summary = RepoSummary(
        trust_boundaries=sorted({e.layer for e in entries} | set(layers.keys())),
        priority_areas=priority,
    )
    digest = compact_security_digest(
        SecurityView(
            schema_version=SCHEMA_VERSION,
            repo_id=repo_id,
            built_at="",
            graph_stats={},
            layers=layers,
            entries=entries,
            sinks=sinks,
            gates=gates,
            hot_paths=hot_paths,
            repo_summary=summary,
        )
    )
    sv = SecurityView(
        schema_version=SCHEMA_VERSION,
        repo_id=repo_id,
        built_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        graph_stats={
            "files": len(nodes),
            "edges": len(edges),
            "cycles": int(cycles),
            "entries": len(entries),
            "sinks": len(sinks),
            "gates": len(gates),
            "hot_paths": len(hot_paths),
        },
        layers=layers,
        entries=entries,
        sinks=sinks,
        gates=gates,
        hot_paths=hot_paths,
        repo_summary=summary,
        metrics={
            "build_ms": int((time.time() - t0) * 1000),
            "fingerprint": fp,
            "digest_token_estimate": digest.get("_token_estimate"),
            "digest_chars": digest.get("_chars"),
            "heuristic": True,
        },
    )
    if cache:
        try:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            payload = sv.to_dict()
            payload["_fingerprint"] = fp
            cpath.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            _log.debug("cache write failed: %s", e)
    return sv


def _dict_to_view(data: Dict[str, Any]) -> SecurityView:
    layers = {
        k: LayerStats(**v) if isinstance(v, dict) else LayerStats()
        for k, v in (data.get("layers") or {}).items()
    }
    return SecurityView(
        schema_version=str(data.get("schema_version") or SCHEMA_VERSION),
        repo_id=str(data.get("repo_id") or "aiPlatform"),
        built_at=str(data.get("built_at") or ""),
        graph_stats=dict(data.get("graph_stats") or {}),
        layers=layers,
        entries=[Entry(**e) for e in (data.get("entries") or []) if isinstance(e, dict)],
        sinks=[Sink(**s) for s in (data.get("sinks") or []) if isinstance(s, dict)],
        gates=[Gate(**g) for g in (data.get("gates") or []) if isinstance(g, dict)],
        hot_paths=[HotPath(**h) for h in (data.get("hot_paths") or []) if isinstance(h, dict)],
        repo_summary=RepoSummary(**(data.get("repo_summary") or {})),
        metrics=dict(data.get("metrics") or {}),
    )


def get_security_view(**kwargs: Any) -> SecurityView:
    return build_security_view(**kwargs)
