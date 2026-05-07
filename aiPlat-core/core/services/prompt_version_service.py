"""
Simple prompt version manager — stores prompt versions for each agent role.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

_PROMPT_FILE = os.path.join(
    os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")),
    "prompt_versions.json",
)


class PromptVersionService:

    def __init__(self):
        self._versions: Dict[str, List[Dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(_PROMPT_FILE):
                with open(_PROMPT_FILE, "r", encoding="utf-8") as f:
                    self._versions = json.load(f)
        except Exception:
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_PROMPT_FILE), exist_ok=True)
            with open(_PROMPT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._versions, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_version(self, agent_id: str, prompt_text: str, description: str = "") -> Dict[str, Any]:
        versions = self._versions.setdefault(agent_id, [])
        version_num = len(versions) + 1
        entry = {
            "version": version_num,
            "prompt": prompt_text,
            "description": description,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "metrics": {},
        }
        versions.append(entry)
        self._save()
        return entry

    def get_latest(self, agent_id: str) -> Optional[str]:
        versions = self._versions.get(agent_id, [])
        if versions:
            return versions[-1]["prompt"]
        return None

    def get_version(self, agent_id: str, version: int) -> Optional[str]:
        versions = self._versions.get(agent_id, [])
        if 0 < version <= len(versions):
            return versions[version - 1]["prompt"]
        return None

    def list_versions(self, agent_id: str) -> List[Dict[str, Any]]:
        return self._versions.get(agent_id, [])

    def rollback(self, agent_id: str, version: int) -> Optional[str]:
        prompt = self.get_version(agent_id, version)
        if prompt:
            self.save_version(agent_id, prompt, f"Rollback to v{version}")
            return prompt
        return None

    def record_metric(self, agent_id: str, version: int, metric: Dict[str, Any]) -> None:
        versions = self._versions.get(agent_id, [])
        if 0 < version <= len(versions):
            versions[version - 1]["metrics"] = {**versions[version - 1].get("metrics", {}), **metric}
            self._save()
