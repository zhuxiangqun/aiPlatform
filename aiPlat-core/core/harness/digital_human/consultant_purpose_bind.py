"""小朱 purpose 绑定回执（第二道人批之后）。

默认只落盘、简报可见；仅当 ``AIPLAT_DH_PURPOSE_BIND=1`` 时顾问热路径才读取模型名。
非目标：不改全局 ``best_model_for_purpose`` / infra ModelManager；不宣称 E5。
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from core.utils.paths import get_aiplat_home

logger = logging.getLogger("aiplat.digital_human.purpose_bind")


def purpose_bind_enabled() -> bool:
    """顾问是否允许读取已批准的 purpose 绑定。"""
    return (os.getenv("AIPLAT_DH_PURPOSE_BIND") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _bind_path() -> Path:
    return Path(get_aiplat_home()) / "digital_human" / "purpose_bind.json"


def _clear_purpose_bind_for_tests() -> None:
    """单测清理绑定文件。"""
    path = _bind_path()
    if path.is_file():
        path.unlink()


def write_purpose_bind(
    *,
    model: str = "",
    purpose: str = "auto",
    job_id: str = "",
    proposal_id: str = "",
    actor: str = "user",
    note: str = "",
) -> Dict[str, Any]:
    """写入（覆盖）当前生效的绑定回执。

    Args:
        model: 建议模型名（可空=仅回执）。
        purpose: purpose 名，默认 auto。
        job_id: 来源微调任务。
        proposal_id: 来源提案。
        actor: 批准人。
        note: 备注。
    """
    path = _bind_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": "aiplat.dh_purpose_bind.v1",
        "model": (model or "").strip(),
        "purpose": (purpose or "auto").strip() or "auto",
        "job_id": (job_id or "").strip(),
        "proposal_id": (proposal_id or "").strip(),
        "actor": (actor or "user").strip(),
        "note": (note or "").strip()[:300],
        "updated_at": int(time.time()),
        "production_model_changed": False,
        "feeds_global_routing": False,
        "consultant_override_requires_env": "AIPLAT_DH_PURPOSE_BIND=1",
    }
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(path), "bind": row, "production_model_changed": False}


def load_purpose_bind() -> Optional[Dict[str, Any]]:
    """读取绑定回执；无文件返回 None。"""
    path = _bind_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("load purpose bind failed", exc_info=True)
        return None


def active_consultant_bind_meta() -> Dict[str, Any]:
    """若开关打开且有模型名，返回顾问可覆盖的 meta；否则空。

    Returns:
        可能含 model / model_purpose / bind_active；默认不覆盖。
    """
    out: Dict[str, Any] = {
        "bind_active": False,
        "production_model_changed": False,
        "feeds_global_routing": False,
    }
    if not purpose_bind_enabled():
        out["reason"] = "env_off"
        bind = load_purpose_bind()
        if bind:
            out["receipt"] = {
                "model": bind.get("model"),
                "purpose": bind.get("purpose"),
                "job_id": bind.get("job_id"),
            }
        return out
    bind = load_purpose_bind()
    if not bind:
        out["reason"] = "no_bind_file"
        return out
    model = str(bind.get("model") or "").strip()
    if not model:
        out["reason"] = "no_model_in_bind"
        out["receipt"] = bind
        return out
    out.update(
        {
            "bind_active": True,
            "model": model,
            "model_purpose": str(bind.get("purpose") or "auto").strip() or "auto",
            "job_id": bind.get("job_id"),
            "proposal_id": bind.get("proposal_id"),
            "reason": "ok",
        }
    )
    return out


def purpose_bind_brief_line() -> str:
    """简报一行。"""
    bind = load_purpose_bind()
    if not bind:
        return "顾问 purpose 绑定: 无（须 sft_promote 后另批 purpose_bind；默认不改选模）"
    model = str(bind.get("model") or "").strip() or "(仅回执无模型名)"
    purpose = str(bind.get("purpose") or "auto")
    env_on = purpose_bind_enabled()
    state = "热路径可读" if env_on and model and model != "(仅回执无模型名)" else "仅回执"
    return (
        f"顾问 purpose 绑定: {state} purpose={purpose} model={model} "
        f"（env AIPLAT_DH_PURPOSE_BIND={'1' if env_on else '0'}；不改全局选模）"
    )
