"""Minimal SecureScan gate for third-party asset trees / zip imports.

Non-goals: full malware analysis, network reputation, or runtime sandboxing.
Rejects obvious path traversal, dangerous executable suffixes, and zip-bomb heuristics.
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Windows/script payloads — not Node/Python MCP server sources (.js/.py OK).
_BLOCKED_SUFFIXES = {
    ".exe",
    ".bat",
    ".cmd",
    ".com",
    ".msi",
    ".scr",
    ".ps1",
    ".vbs",
    ".dll",
}
_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MiB
_MAX_COMPRESSION_RATIO = 100.0
_MAX_ZIP_ENTRIES = 5000


class AssetSecureScanError(ValueError):
    """Raised when SecureScan blocks an import (no disk install)."""

    def __init__(self, issues: List[str]):
        """Preserve scan issue codes for callers (fail closed, no install).

        Args:
            issues: Human-readable issue codes from zip/tree SecureScan.
        """
        self.issues = list(issues or [])
        super().__init__(f"asset_secure_scan_failed:{';'.join(self.issues[:5])}")


def secure_scan_zip(zip_path: Path | str) -> Dict[str, Any]:
    """Scan zip members for traversal / bomb / blocked suffixes before extract.

    Args:
        zip_path: Path to zip archive.

    Returns:
        ``{ok, issues, stats}``.
    """
    zp = Path(zip_path)
    issues: List[str] = []
    stats = {"entries": 0, "uncompressed": 0, "compressed": 0}
    if not zp.is_file():
        return {"ok": False, "issues": ["zip_not_found"], "stats": stats}
    try:
        with zipfile.ZipFile(str(zp), "r") as zf:
            infos = zf.infolist()
            stats["entries"] = len(infos)
            if len(infos) > _MAX_ZIP_ENTRIES:
                issues.append(f"zip_too_many_entries:{len(infos)}")
            total_uncomp = 0
            total_comp = 0
            for info in infos:
                name = str(info.filename or "")
                issues.extend(_path_issues(name, zip_member=True))
                total_uncomp += int(info.file_size or 0)
                total_comp += int(info.compress_size or 0)
                suf = Path(name).suffix.lower()
                if suf in _BLOCKED_SUFFIXES:
                    issues.append(f"blocked_suffix:{name}")
            stats["uncompressed"] = total_uncomp
            stats["compressed"] = total_comp
            if total_uncomp > _MAX_UNCOMPRESSED_BYTES:
                issues.append(f"zip_uncompressed_too_large:{total_uncomp}")
            if total_comp > 0 and (total_uncomp / max(total_comp, 1)) > _MAX_COMPRESSION_RATIO:
                issues.append(
                    f"zip_bomb_ratio:{total_uncomp / max(total_comp, 1):.1f}"
                )
    except zipfile.BadZipFile:
        issues.append("zip_corrupt")
    except Exception as exc:
        issues.append(f"zip_scan_error:{type(exc).__name__}")
        logger.debug("secure_scan_zip failed: %s", exc, exc_info=True)
    return {"ok": not issues, "issues": issues, "stats": stats}


def secure_scan_asset_tree(root: Path | str) -> Dict[str, Any]:
    """Scan an extracted / local asset tree for traversal and blocked suffixes.

    Args:
        root: Directory root to scan.

    Returns:
        ``{ok, issues, files_scanned}``.
    """
    base = Path(root)
    issues: List[str] = []
    scanned = 0
    if not base.exists() or not base.is_dir():
        return {"ok": False, "issues": ["root_not_found"], "files_scanned": 0}
    try:
        base_res = base.resolve()
    except Exception:
        base_res = base
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        scanned += 1
        try:
            rel = p.relative_to(base)
        except Exception:
            issues.append(f"path_outside_root:{p}")
            continue
        issues.extend(_path_issues(str(rel), zip_member=False))
        try:
            resolved = p.resolve()
            if base_res not in resolved.parents and resolved != base_res:
                issues.append(f"symlink_escape:{rel}")
        except OSError:
            # broken symlink / resolve race — still flag for review
            issues.append(f"path_resolve_failed:{rel}")
        if p.suffix.lower() in _BLOCKED_SUFFIXES:
            issues.append(f"blocked_suffix:{rel}")
    return {"ok": not issues, "issues": issues, "files_scanned": scanned}


def enforce_secure_scan(
    root: Path | str,
    *,
    zip_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Run zip + tree SecureScan; raise AssetSecureScanError on failure.

    Args:
        root: Extracted or local asset root.
        zip_path: Optional zip to scan before/without relying solely on tree.

    Returns:
        Combined scan report.

    Raises:
        AssetSecureScanError: When any check fails (caller must not install).
    """
    issues: List[str] = []
    report: Dict[str, Any] = {"ok": True, "issues": [], "zip": None, "tree": None}
    if zip_path:
        zrep = secure_scan_zip(zip_path)
        report["zip"] = zrep
        if not zrep.get("ok"):
            issues.extend(list(zrep.get("issues") or []))
    trep = secure_scan_asset_tree(root)
    report["tree"] = trep
    if not trep.get("ok"):
        issues.extend(list(trep.get("issues") or []))
    # de-dupe preserve order
    seen = set()
    uniq: List[str] = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    report["issues"] = uniq
    report["ok"] = not uniq
    if uniq:
        raise AssetSecureScanError(uniq)
    return report


def _path_issues(name: str, *, zip_member: bool) -> List[str]:
    issues: List[str] = []
    n = str(name or "").replace("\\", "/")
    if not n or n.startswith("/") or n.startswith("~"):
        issues.append(f"absolute_path:{name}")
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        issues.append(f"path_traversal:{name}")
    if zip_member and n.endswith("/"):
        return issues
    return issues
