"""
Prompt App Manager — directory-backed prompt app templates.

Stores templates as:
  ~/.aiplat/prompt-apps/<id>/
    template.json          ← name, category, prompts, variables
    TEMPLATE.manifest.json ← provenance, signature

Migrates from SQLite prompt_app_templates on first load (one-time).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import logging
import os

_logger = logging.getLogger(__name__)


@dataclass
class PromptAppTemplate:
    template_id: str
    name: str
    category: str = ""
    tags: List[str] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt: str = ""
    assistant_prompt: str = ""
    variables: List[str] = field(default_factory=list)
    status: str = "draft"  # draft | published
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0.0"


class PromptAppManager:
    """Directory-based prompt app template manager."""

    def __init__(self):
        self._templates: Dict[str, PromptAppTemplate] = {}
        self.reload()

    def _base_dir(self) -> Path:
        return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat"))) / "prompt-apps"

    # ==================== Load & Save ====================

    def reload(self) -> None:
        self._templates = {}
        base = self._base_dir()
        if not base.exists():
            self._migrate_from_sqlite()
            return

        for item in base.iterdir():
            if not item.is_dir() or item.name.startswith("."):
                continue
            tmpl_json = item / "template.json"
            if not tmpl_json.exists():
                continue
            try:
                data = json.loads(tmpl_json.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            tpl = self._dict_to_template(data)
            tpl.metadata.setdefault("filesystem", {})
            tpl.metadata["filesystem"]["template_dir"] = str(item)
            self._enrich_provenance_and_integrity(tpl.metadata, template_dir=item)
            self._templates[tpl.template_id] = tpl

        if not self._templates:
            self._migrate_from_sqlite()

    def _dict_to_template(self, data: dict) -> PromptAppTemplate:
        return PromptAppTemplate(
            template_id=data.get("template_id", ""),
            name=data.get("name", ""),
            category=data.get("category", ""),
            tags=data.get("tags", []) if isinstance(data.get("tags"), list) else [],
            system_prompt=data.get("system_prompt", ""),
            user_prompt=data.get("user_prompt", ""),
            assistant_prompt=data.get("assistant_prompt", ""),
            variables=data.get("variables", []) if isinstance(data.get("variables"), list) else [],
            status=data.get("status", "draft"),
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
            version=data.get("version", "1.0.0"),
        )

    def _migrate_from_sqlite(self) -> None:
        """One-time migration from SQLite to directory storage."""
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            if not store:
                return
            # Use internal query if available
            result = getattr(store, "list_prompt_app_templates", None)
            if not callable(result):
                return
            import concurrent.futures as _cf
            with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
                items = _pool.submit(asyncio.run, result(limit=10000, offset=0)).result(timeout=30)
        except Exception:
            return

        if not items or not items.get("templates"):
            return

        base = self._base_dir()
        base.mkdir(parents=True, exist_ok=True)
        migrated = 0
        for t in items.get("templates", []):
            if not isinstance(t, dict):
                continue
            tid = t.get("template_id") or t.get("id", "")
            if not tid:
                continue
            tpl_dir = base / tid
            if tpl_dir.exists():
                continue  # already migrated
            tpl_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "template_id": tid,
                "name": t.get("name", ""),
                "category": t.get("category", ""),
                "tags": t.get("tags", []) if isinstance(t.get("tags"), list) else [],
                "system_prompt": t.get("system_prompt", ""),
                "user_prompt": t.get("user_prompt", ""),
                "assistant_prompt": t.get("assistant_prompt", ""),
                "variables": t.get("variables", []) if isinstance(t.get("variables"), list) else [],
                "status": t.get("status", "draft"),
                "version": "1.0.0",
                "migrated_from_sqlite": True,
            }
            (tpl_dir / "template.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            migrated += 1
        if migrated:
            _logger.info(f"Migrated {migrated} prompt app templates from SQLite")

    def _write_template(self, tpl: PromptAppTemplate) -> None:
        tmpl_dir = Path(tpl.metadata.get("filesystem", {}).get("template_dir") or "")
        if not tmpl_dir or not tmpl_dir.exists():
            base = self._base_dir()
            tmpl_dir = base / tpl.template_id
            tmpl_dir.mkdir(parents=True, exist_ok=True)
            tpl.metadata.setdefault("filesystem", {})
            tpl.metadata["filesystem"]["template_dir"] = str(tmpl_dir)
        payload = {
            "template_id": tpl.template_id, "name": tpl.name, "category": tpl.category,
            "tags": tpl.tags,
            "system_prompt": tpl.system_prompt, "user_prompt": tpl.user_prompt,
            "assistant_prompt": tpl.assistant_prompt, "variables": tpl.variables,
            "status": tpl.status, "version": tpl.version,
        }
        (tmpl_dir / "template.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ==================== Provenance & Integrity ====================

    def _sha256_file(self, p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as f:
            while True:
                b = f.read(1024 * 1024)
                if not b: break
                h.update(b)
        return h.hexdigest()

    def _read_manifest_json(self, template_dir: Path) -> Dict[str, Any]:
        p = template_dir / "TEMPLATE.manifest.json"
        if not p.exists(): return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _compute_bundle_integrity(self, template_dir: Path) -> Dict[str, Any]:
        entries: list = []
        total_bytes, file_count = 0, 0
        files_sample: list = []
        try:
            for p in sorted(template_dir.rglob("*")):
                try:
                    if p.is_dir(): continue
                    rel = str(p.relative_to(template_dir))
                    if rel.startswith("__pycache__/") or rel.endswith(".pyc"): continue
                    if rel.startswith(".git/"): continue
                    size = int(p.stat().st_size)
                    sha = self._sha256_file(p)
                    entries.append(f"{rel}\t{size}\t{sha}")
                    total_bytes += size; file_count += 1
                    if len(files_sample) < 20: files_sample.append(rel)
                except Exception:
                    _logger.warning("计算 bundle 文件失败: %s", p, exc_info=True)
                    continue
        except Exception:
            _logger.warning("计算 bundle 完整性失败: %s", template_dir, exc_info=True)
        bundle_sha256 = hashlib.sha256(("\n".join(entries)).encode("utf-8")).hexdigest()
        return {"bundle_sha256": bundle_sha256, "file_count": file_count, "total_bytes": total_bytes, "files_sample": files_sample}

    def _enrich_provenance_and_integrity(self, metadata: Dict[str, Any], *, template_dir: Path) -> None:
        if not isinstance(metadata, dict): return
        prov = metadata.get("provenance", {}) if isinstance(metadata.get("provenance"), dict) else {}
        prov.setdefault("source_type", "filesystem")
        prov.setdefault("template_dir", str(template_dir))
        manifest = self._read_manifest_json(template_dir)
        if not manifest:
            manifest = {"version": "1.0.0"}
            try:
                (template_dir / "TEMPLATE.manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if manifest:
            for k in ("publisher", "source", "version", "signature"):
                if manifest.get(k) is not None: prov.setdefault(k, manifest.get(k))
        metadata["provenance"] = prov
        integ = metadata.get("integrity", {}) if isinstance(metadata.get("integrity"), dict) else {}
        try: integ.update(self._compute_bundle_integrity(template_dir))
        except Exception:
            _logger.debug("无法计算完整性哈希: %s", template_dir, exc_info=True)
        metadata["integrity"] = integ

    def compute_signature_verification(self, tpl: PromptAppTemplate, trusted_keys: Dict[str, str]) -> Dict[str, Any]:
        if not isinstance(getattr(tpl, "metadata", None), dict): return {}
        prov = dict(tpl.metadata.get("provenance", {})) if isinstance(tpl.metadata.get("provenance"), dict) else {}
        integ = tpl.metadata.get("integrity", {}) if isinstance(tpl.metadata, dict) else {}
        sig = prov.get("signature")
        bundle_sha = integ.get("bundle_sha256") if isinstance(integ, dict) else None
        if not sig or not bundle_sha: return prov
        prov = dict(prov)
        prov["signature_verified"] = False
        try:
            from core.harness.infrastructure.crypto.signature import verify_skill_signature
            r = verify_skill_signature(skill_id=tpl.template_id, version=tpl.version, bundle_sha256=str(bundle_sha), signature=str(sig), trusted_keys=trusted_keys)
            prov["signature_verified"] = bool(r.get("verified"))
            prov["signature_verified_key_id"] = r.get("key_id") or ""
            prov["signature_verified_reason"] = (r.get("error") or "") if not r.get("verified") else ""
        except Exception as e:
            prov["signature_verified_reason"] = str(e)
        return prov

    # ==================== CRUD ====================

    def list(self) -> List[PromptAppTemplate]:
        return list(self._templates.values())

    def get(self, template_id: str) -> Optional[PromptAppTemplate]:
        return self._templates.get(template_id)

    def upsert(self, template_id: str, name: str, category: str, tags: list, system_prompt: str, user_prompt: str, assistant_prompt: str, variables: list) -> PromptAppTemplate:
        existing = self._templates.get(template_id)
        if existing:
            existing.name = name; existing.category = category; existing.tags = tags
            existing.system_prompt = system_prompt; existing.user_prompt = user_prompt
            existing.assistant_prompt = assistant_prompt; existing.variables = variables
            existing.updated_at = datetime.now(timezone.utc)
            self._write_template(existing)
            tmpl_dir = Path(existing.metadata.get("filesystem", {}).get("template_dir") or "")
            if tmpl_dir.exists():
                self._enrich_provenance_and_integrity(existing.metadata, template_dir=tmpl_dir)
            return existing
        tpl = PromptAppTemplate(template_id=template_id, name=name, category=category, tags=tags,
                                 system_prompt=system_prompt, user_prompt=user_prompt,
                                 assistant_prompt=assistant_prompt, variables=variables)
        self._templates[template_id] = tpl
        base = self._base_dir()
        tmpl_dir = base / template_id
        tmpl_dir.mkdir(parents=True, exist_ok=True)
        self._write_template(tpl)
        self._enrich_provenance_and_integrity(tpl.metadata, template_dir=tmpl_dir)
        return tpl

    def delete(self, template_id: str) -> bool:
        tpl = self._templates.pop(template_id, None)
        if not tpl: return False
        tmpl_dir = Path(tpl.metadata.get("filesystem", {}).get("template_dir") or "")
        if tmpl_dir.exists():
            import shutil
            shutil.rmtree(tmpl_dir, ignore_errors=True)
        return True
