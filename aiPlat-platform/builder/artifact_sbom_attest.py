"""P2-1: SBOM generation + attest chain + MCP/plugin allowlist publish gate.

Extends P0-3a ``artifact.security.json``:
  - CycloneDX-lite SBOM from lock/manifest files (no syft required for engineering)
  - SBOM digest attached into security manifest (hashed with canonical rules)
  - Optional Ed25519 over ``manifest_hash`` when key configured (else keep HMAC)
  - MCP / plugin allowlist check — undeclared entries block prodish publish

Honesty: never sets security_certification; missing SBOM in prodish → block.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

_log = logging.getLogger(__name__)

SBOM_NAME = "sbom.cdx.json"
ALLOWLIST_NAME = "mcp_plugin_allowlist.json"
SCHEMA_SBOM = "eval.security_p2_1_sbom.v1"
SCHEMA_ATTEST = "eval.security_p2_1_attest.v1"

_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".aiplat"}


def _profile() -> str:
    raw = (os.getenv("AIPLAT_PROFILE") or os.getenv("AIPLAT_ENV") or "").strip().lower()
    if raw in ("production", "prod"):
        return "production"
    if raw in ("staging", "stage", "preprod"):
        return "staging"
    return raw or "development"


def _prodish() -> bool:
    return _profile() in ("production", "staging")


def p2_1_sbom_required() -> bool:
    """p2_1_sbom_required。
    """
    flag = (os.getenv("AIPLAT_P2_1_SBOM") or "").strip().lower()
    if flag in ("0", "false", "off", "no"):
        return False
    if flag in ("1", "true", "yes", "enforce", "on"):
        return True
    return _prodish()


def default_allowlist_path() -> Path:
    """default_allowlist_path。
    """
    override = (os.getenv("AIPLAT_MCP_PLUGIN_ALLOWLIST") or "").strip()
    if override:
        return Path(override)
    return (
        Path(__file__).resolve().parents[2]
        / "security"
        / "keys"
        / "mcp_plugin_allowlist.json"
    )


def load_mcp_plugin_allowlist(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """load_mcp_plugin_allowlist。

    Args:
        path: 路径。
    """
    p = Path(path) if path else default_allowlist_path()
    if not p.is_file():
        return {
            "schema": "aiplat.mcp_plugin_allowlist.v1",
            "mcp_servers": [],
            "plugins": [],
            "missing": True,
            "path": str(p),
        }
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {"schema": "aiplat.mcp_plugin_allowlist.v1", "mcp_servers": [], "plugins": [], "invalid": True}
    raw.setdefault("mcp_servers", [])
    raw.setdefault("plugins", [])
    raw["path"] = str(p)
    raw["missing"] = False
    return raw


def _parse_requirements_txt(text: str) -> List[Dict[str, str]]:
    comps: List[Dict[str, str]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        # strip env markers / extras crudely
        s = s.split(";")[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*([=<>!~].+)?$", s)
        if not m:
            continue
        name = m.group(1)
        ver = (m.group(2) or "").lstrip("=<>!~ ").split(",")[0].strip() or "unknown"
        comps.append({"type": "library", "name": name, "version": ver, "purl": f"pkg:pypi/{name}@{ver}"})
    return comps


def _parse_package_json(data: Mapping[str, Any]) -> List[Dict[str, str]]:
    comps: List[Dict[str, str]] = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        block = data.get(section) if isinstance(data.get(section), Mapping) else {}
        for name, ver in (block or {}).items():
            v = str(ver).lstrip("^~>=< ")
            comps.append(
                {
                    "type": "library",
                    "name": str(name),
                    "version": v or "unknown",
                    "purl": f"pkg:npm/{name}@{v or 'unknown'}",
                }
            )
    return comps


def _parse_pyproject(text: str) -> List[Dict[str, str]]:
    # Minimal TOML-ish: dependencies = [ "foo==1.0", ... ]
    comps: List[Dict[str, str]] = []
    in_deps = False
    for line in text.splitlines():
        if re.match(r"^\s*dependencies\s*=\s*\[", line):
            in_deps = True
            # same-line entries
            for m in re.finditer(r'["\']([A-Za-z0-9_.\-]+)([=<>!~][^"\']*)?["\']', line):
                name = m.group(1)
                ver = (m.group(2) or "").lstrip("=<>!~ ") or "unknown"
                comps.append(
                    {
                        "type": "library",
                        "name": name,
                        "version": ver,
                        "purl": f"pkg:pypi/{name}@{ver}",
                    }
                )
            if "]" in line:
                in_deps = False
            continue
        if in_deps:
            if "]" in line:
                in_deps = False
            for m in re.finditer(r'["\']([A-Za-z0-9_.\-]+)([=<>!~][^"\']*)?["\']', line):
                name = m.group(1)
                ver = (m.group(2) or "").lstrip("=<>!~ ") or "unknown"
                comps.append(
                    {
                        "type": "library",
                        "name": name,
                        "version": ver,
                        "purl": f"pkg:pypi/{name}@{ver}",
                    }
                )
    return comps


def collect_components(root: Path) -> List[Dict[str, str]]:
    """collect_components。

    Args:
        root: root 参数。
    """
    root = Path(root)
    seen: Dict[str, Dict[str, str]] = {}
    # requirements*.txt
    for p in list(root.glob("requirements*.txt")) + list(root.rglob("requirements*.txt")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        try:
            for c in _parse_requirements_txt(p.read_text(encoding="utf-8", errors="ignore")):
                seen[c["purl"]] = c
        except OSError:
            continue
    # package.json
    for p in list(root.glob("package.json")) + list(root.rglob("package.json")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, Mapping):
                for c in _parse_package_json(data):
                    seen[c["purl"]] = c
        except (OSError, json.JSONDecodeError):
            continue
    # pyproject.toml
    for p in list(root.glob("pyproject.toml")) + list(root.rglob("pyproject.toml")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        try:
            for c in _parse_pyproject(p.read_text(encoding="utf-8", errors="ignore")):
                seen[c["purl"]] = c
        except OSError:
            continue
    return sorted(seen.values(), key=lambda x: x.get("purl") or "")


def generate_sbom_cyclonedx_lite(
    root: Path,
    *,
    artifact_id: str = "",
) -> Dict[str, Any]:
    """Engineering CycloneDX-lite SBOM (syft optional upgrade path).

    Args:
        root: root 参数。
        artifact_id: artifact 标识。
    """
    comps = collect_components(root)
    bom: Dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": artifact_id or Path(root).name,
                "version": "0.0.0-engineering",
            },
            "tools": [{"name": "aiplat.artifact_sbom_attest", "version": "p2-1"}],
            "aiplat": {
                "schema": SCHEMA_SBOM,
                "generator": "cyclonedx_lite",
                "syft_optional": True,
                "security_certification": False,
            },
        },
        "components": [
            {
                "type": c["type"],
                "name": c["name"],
                "version": c["version"],
                "purl": c["purl"],
            }
            for c in comps
        ],
    }
    return bom


def sbom_digest(bom: Mapping[str, Any]) -> str:
    """sbom_digest。

    Args:
        bom: bom 参数。
    """
    raw = json.dumps(bom, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_sbom(root: Path, bom: Mapping[str, Any], *, name: str = SBOM_NAME) -> Path:
    """write_sbom。

    Args:
        root: root 参数。
        bom: bom 参数。
        name: name 参数。
    """
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def discover_declared_mcp_plugins(root: Path) -> Dict[str, List[str]]:
    """Best-effort scan for MCP server / plugin ids in common manifest files.

    Args:
        root: root 参数。
    """
    root = Path(root)
    mcp: List[str] = []
    plugins: List[str] = []
    candidates = [
        "mcp.json",
        "mcp_servers.json",
        "plugins.json",
        "agent.json",
        "config/mcp.yaml",
        "config/plugins.yaml",
    ]
    for rel in candidates:
        p = root / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if p.suffix in {".json"}:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, Mapping):
                for key in ("mcpServers", "mcp_servers", "servers"):
                    block = data.get(key)
                    if isinstance(block, Mapping):
                        mcp.extend(str(k) for k in block.keys())
                    elif isinstance(block, list):
                        for item in block:
                            if isinstance(item, Mapping) and item.get("name"):
                                mcp.append(str(item["name"]))
                            elif isinstance(item, str):
                                mcp.append(item)
                for key in ("plugins", "plugin_ids"):
                    block = data.get(key)
                    if isinstance(block, Mapping):
                        plugins.extend(str(k) for k in block.keys())
                    elif isinstance(block, list):
                        for item in block:
                            if isinstance(item, Mapping) and item.get("id"):
                                plugins.append(str(item["id"]))
                            elif isinstance(item, str):
                                plugins.append(item)
        else:
            # yaml-ish: lines like "  name: foo"
            for m in re.finditer(r"(?m)^\s+(?:name|id|server)\s*:\s*([A-Za-z0-9_./\-]+)\s*$", text):
                mcp.append(m.group(1))
    # Also scan for mcpServers in any *.json under root (capped)
    n = 0
    for p in root.rglob("*.json"):
        if n >= 40:
            break
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        n += 1
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, Mapping) and isinstance(data.get("mcpServers"), Mapping):
            mcp.extend(str(k) for k in data["mcpServers"].keys())
    return {
        "mcp_servers": sorted(set(mcp)),
        "plugins": sorted(set(plugins)),
    }


def evaluate_mcp_plugin_allowlist(
    root: Path,
    *,
    allowlist: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """evaluate_mcp_plugin_allowlist。

    Args:
        root: root 参数。
        allowlist: allowlist 参数。
    """
    al = dict(allowlist) if allowlist is not None else load_mcp_plugin_allowlist()
    declared = discover_declared_mcp_plugins(root)
    allowed_mcp = {str(x) for x in (al.get("mcp_servers") or [])}
    allowed_plug = {str(x) for x in (al.get("plugins") or [])}
    # Empty allowlist file that exists with empty lists → deny all non-empty declarations
    # Missing allowlist → fail closed when declarations exist; pass when none declared
    missing_al = bool(al.get("missing"))
    undeclared_mcp = [x for x in declared["mcp_servers"] if x not in allowed_mcp]
    undeclared_plug = [x for x in declared["plugins"] if x not in allowed_plug]
    if not declared["mcp_servers"] and not declared["plugins"]:
        return {
            "ok": True,
            "status": "pass",
            "detail": "no_mcp_or_plugins_declared",
            "declared": declared,
            "allowlist_missing": missing_al,
            "security_certification": False,
        }
    if missing_al:
        return {
            "ok": False,
            "status": "fail",
            "detail": "allowlist_missing_but_mcp_or_plugins_declared",
            "declared": declared,
            "undeclared_mcp": declared["mcp_servers"],
            "undeclared_plugins": declared["plugins"],
            "security_certification": False,
        }
    blockers = []
    if undeclared_mcp:
        blockers.append(f"mcp_not_allowlisted:{','.join(undeclared_mcp[:8])}")
    if undeclared_plug:
        blockers.append(f"plugin_not_allowlisted:{','.join(undeclared_plug[:8])}")
    return {
        "ok": not blockers,
        "status": "pass" if not blockers else "fail",
        "detail": "ok" if not blockers else "allowlist_violations",
        "blockers": blockers,
        "declared": declared,
        "undeclared_mcp": undeclared_mcp,
        "undeclared_plugins": undeclared_plug,
        "security_certification": False,
    }


def try_ed25519_sign(manifest_hash: str) -> Optional[str]:
    """Optional Ed25519 over ``sha256:<hash>``. Returns ``ed25519:<b64>`` or None.

    Args:
        manifest_hash: manifest_hash 参数。
    """
    seed_hex = (os.getenv("AIPLAT_ARTIFACT_MANIFEST_ED25519_SEED") or "").strip()
    key_path = (os.getenv("AIPLAT_ARTIFACT_MANIFEST_ED25519_KEY") or "").strip()
    if not seed_hex and not key_path:
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64
    except ImportError:
        return None
    try:
        if seed_hex:
            seed = bytes.fromhex(seed_hex)
            if len(seed) != 32:
                return None
            key = Ed25519PrivateKey.from_private_bytes(seed)
        else:
            raw = Path(key_path).read_bytes()
            # raw 32-byte seed file
            if len(raw) == 32:
                key = Ed25519PrivateKey.from_private_bytes(raw)
            else:
                return None
        sig = key.sign(f"sha256:{manifest_hash}".encode("utf-8"))
        return f"ed25519:{base64.b64encode(sig).decode('ascii')}"
    except Exception:
        return None


def verify_ed25519_signature(manifest_hash: str, signature: str) -> Tuple[bool, str]:
    """verify_ed25519_signature。

    Args:
        manifest_hash: manifest_hash 参数。
        signature: signature 参数。
    """
    sig = (signature or "").strip()
    if not sig.startswith("ed25519:"):
        return False, "not_ed25519"
    pub_hex = (os.getenv("AIPLAT_ARTIFACT_MANIFEST_ED25519_PUB") or "").strip()
    pub_path = (os.getenv("AIPLAT_ARTIFACT_MANIFEST_ED25519_PUB_PATH") or "").strip()
    if not pub_hex and not pub_path:
        # Default repo pubkey path
        default = (
            Path(__file__).resolve().parents[2]
            / "security"
            / "keys"
            / "artifact-manifest-ci.pub"
        )
        if default.is_file():
            pub_path = str(default)
        else:
            return False, "no_ed25519_pubkey"
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        import base64
    except ImportError:
        return False, "cryptography_missing"
    try:
        if pub_hex:
            pub_bytes = bytes.fromhex(pub_hex)
        else:
            pub_bytes = Path(pub_path).read_bytes().strip()
            # allow hex text file
            try:
                if len(pub_bytes) != 32:
                    pub_bytes = bytes.fromhex(pub_bytes.decode("ascii").strip())
            except Exception:
                _log.debug("pubkey file is not hex text; keeping raw bytes", exc_info=True)
        if len(pub_bytes) != 32:
            return False, "bad_pubkey_len"
        key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        raw_sig = base64.b64decode(sig.split(":", 1)[1])
        key.verify(raw_sig, f"sha256:{manifest_hash}".encode("utf-8"))
        return True, "ok"
    except Exception as e:
        return False, f"ed25519_verify_fail:{type(e).__name__}"


def build_sbom_attest_bundle(
    root: Path,
    *,
    artifact_id: str,
    write: bool = True,
) -> Dict[str, Any]:
    """Generate SBOM + allowlist evaluation for a release tree.

    Args:
        root: root 参数。
        artifact_id: artifact 标识。
        write: write 参数。
    """
    root = Path(root)
    bom = generate_sbom_cyclonedx_lite(root, artifact_id=artifact_id)
    digest = sbom_digest(bom)
    sbom_path = write_sbom(root, bom) if write else root / SBOM_NAME
    allow = evaluate_mcp_plugin_allowlist(root)
    return {
        "schema": SCHEMA_ATTEST,
        "ok": bool(bom.get("components") is not None) and bool(allow.get("ok")),
        "sbom_path": str(sbom_path),
        "sbom_digest": digest,
        "component_count": len(bom.get("components") or []),
        "allowlist": allow,
        "sbom_required": p2_1_sbom_required(),
        "security_certification": False,
        "accuracy_claim": False,
        "honesty": (
            "P2-1 CycloneDX-lite SBOM + MCP/plugin allowlist. "
            "syft/cosign optional upgrade. ≠ certification."
        ),
    }


def evaluate_p2_1_gate(
    *,
    sbom_digest_value: str = "",
    component_count: int = 0,
    allowlist: Optional[Mapping[str, Any]] = None,
    require_sbom: Optional[bool] = None,
) -> Dict[str, Any]:
    """Publish blockers for P2-1.

    Args:
        sbom_digest_value: sbom_digest_value 参数。
        component_count: component_count 参数。
        allowlist: allowlist 参数。
        require_sbom: require_sbom 参数。
    """
    blockers: List[str] = []
    req = p2_1_sbom_required() if require_sbom is None else bool(require_sbom)
    if req:
        if not sbom_digest_value:
            blockers.append("sbom_missing")
        if component_count < 0:
            blockers.append("sbom_invalid")
        # Empty components allowed (stdlib-only / docs); digest still required
    al = dict(allowlist or {})
    if al and al.get("ok") is False:
        blockers.extend(list(al.get("blockers") or [al.get("detail") or "allowlist_fail"]))
    return {
        "ok": not blockers,
        "blockers": blockers,
        "require_sbom": req,
        "security_certification": False,
    }
