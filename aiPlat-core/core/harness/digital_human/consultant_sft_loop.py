"""小朱策展样本 → 达标后自动提交微调任务（不切换顾问生产路由）。

非目标：不在线改 best_model_for_purpose；不把未评测 adapter 挂进咨询热路径。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import get_aiplat_data_dir, get_aiplat_home

logger = logging.getLogger("aiplat.digital_human.sft_loop")

_DATASET_NAME = "digital_human_curated"
_STATE_NAME = "dh_sft_auto_state.json"


def _min_samples() -> int:
    raw = (os.getenv("AIPLAT_DH_SFT_MIN_SAMPLES") or "10").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 10
    return max(1, n)


def _auto_submit_enabled() -> bool:
    return (os.getenv("AIPLAT_DH_SFT_AUTO_SUBMIT") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _state_path() -> Path:
    return Path(get_aiplat_data_dir("training")) / _STATE_NAME


def _read_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state: Dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def sharegpt_to_messages_jsonl(sharegpt_jsonl: str) -> str:
    """ShareGPT conversations → OpenAI-style messages JSONL（DatasetManager 校验格式）。

    Args:
        sharegpt_jsonl: 策展导出的 ShareGPT JSONL 正文。
    """
    out_lines: List[str] = []
    for line in (sharegpt_jsonl or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        conv = obj.get("conversations") or obj.get("messages")
        if not isinstance(conv, list) or len(conv) < 2:
            continue
        messages: List[Dict[str, str]] = []
        for turn in conv:
            if not isinstance(turn, dict):
                continue
            if "role" in turn and "content" in turn:
                role = str(turn.get("role") or "")
                content = str(turn.get("content") or "").strip()
            else:
                frm = str(turn.get("from") or "").lower()
                content = str(turn.get("value") or "").strip()
                if frm in ("human", "user"):
                    role = "user"
                elif frm in ("gpt", "assistant"):
                    role = "assistant"
                else:
                    continue
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        roles = {m["role"] for m in messages}
        if "user" in roles and "assistant" in roles and len(messages) >= 2:
            out_lines.append(json.dumps({"messages": messages}, ensure_ascii=False))
    return "\n".join(out_lines) + ("\n" if out_lines else "")


def count_curated_in_export(export_path: str) -> int:
    """统计策展导出文件样本数。

    Args:
        export_path: JSONL 路径。
    """
    path = Path(export_path or "")
    if not path.is_file():
        return 0
    n = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                n += 1
    except OSError:
        return 0
    return n


def _pick_provider():
    """优先 local，否则 deepseek；都不可用返回 None。"""
    from core.apps.finetune.schemas import FineTuneProvider
    from core.apps.finetune.job_manager import JobManager

    mgr = JobManager()
    for pref in (FineTuneProvider.LOCAL, FineTuneProvider.DEEPSEEK):
        try:
            prov = mgr._get_provider(pref)
        except Exception:
            continue
        if not getattr(prov, "available", False):
            continue
        quota = {}
        try:
            quota = prov.check_quota() or {}
        except Exception:
            quota = {}
        avail = quota.get("available")
        if avail is None:
            avail = max(0, int(quota.get("total", 0)) - int(quota.get("used", 0)))
        if int(avail) <= 0:
            continue
        return pref, mgr
    return None, mgr


def _resolve_base_model() -> str:
    """解析微调基座模型：只走 best_model_for_purpose（禁止硬编码/直读 MODEL env）。"""
    try:
        from core.harness.utils.model_injection import best_model_for_purpose

        m = best_model_for_purpose("chat")
        if m and str(m).strip() and str(m).strip().lower() != "auto":
            return str(m).strip()
    except Exception:
        logger.debug("base model resolve failed", exc_info=True)
    return ""


def maybe_submit_digital_human_sft(
    *,
    force: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """策展样本达标后导入数据集并提交 JobManager 微调任务。

    Args:
        force: 忽略指纹防抖，强制再提交（仍需样本≥N 且 auto 开启，除非 dry_run 仅统计）。
        dry_run: 只导出/计数，不建 dataset/job。

    Returns:
        含 submitted/reason/sample_count 等字段的结果 dict。
    """
    from core.harness.digital_human.trajectory_collector import (
        export_curated_sharegpt_dataset,
    )

    min_n = _min_samples()
    export = export_curated_sharegpt_dataset()
    out_path = str(export.get("output_path") or "")
    sample_count = int(export.get("samples") or 0)
    if sample_count <= 0 and out_path:
        sample_count = count_curated_in_export(out_path)

    result: Dict[str, Any] = {
        "submitted": False,
        "sample_count": sample_count,
        "min_samples": min_n,
        "export_path": out_path,
        "dry_run": dry_run,
    }

    if sample_count < min_n:
        result["reason"] = "need_more"
        st = _read_state()
        st.update(
            {
                "status": "need_more",
                "last_sample_count": sample_count,
                "updated_at": int(time.time()),
            }
        )
        _write_state(st)
        return result

    if dry_run or not _auto_submit_enabled():
        result["reason"] = "dry_run" if dry_run else "auto_submit_disabled"
        st = _read_state()
        st.update(
            {
                "status": result["reason"],
                "last_sample_count": sample_count,
                "updated_at": int(time.time()),
            }
        )
        _write_state(st)
        return result

    if not out_path or not Path(out_path).is_file():
        result["reason"] = "no_export_file"
        return result

    try:
        raw_sharegpt = Path(out_path).read_text(encoding="utf-8")
    except OSError as e:
        result["reason"] = f"read_export_failed:{e}"
        return result

    messages_jsonl = sharegpt_to_messages_jsonl(raw_sharegpt)
    msg_count = sum(1 for ln in messages_jsonl.splitlines() if ln.strip())
    if msg_count < min_n:
        result["reason"] = "need_more_after_convert"
        result["converted_count"] = msg_count
        return result

    fingerprint = _sha256_text(messages_jsonl)
    state = _read_state()
    if (
        not force
        and state.get("content_sha256") == fingerprint
        and state.get("status") in ("submitted", "queued", "training")
        and state.get("last_job_id")
    ):
        result["reason"] = "already_submitted"
        result["job_id"] = state.get("last_job_id")
        result["dataset_id"] = state.get("last_dataset_id")
        return result

    provider, job_mgr = _pick_provider()
    if provider is None:
        state.update(
            {
                "status": "pending_provider",
                "last_sample_count": sample_count,
                "content_sha256": fingerprint,
                "export_path": out_path,
                "updated_at": int(time.time()),
            }
        )
        _write_state(state)
        result["reason"] = "pending_provider"
        return result

    try:
        from core.apps.finetune.schemas import (
            DatasetCreateRequest,
            DatasetSourceType,
            FineTuneTemplate,
            JobCreateRequest,
        )
        from core.apps.finetune.dataset_manager import DatasetManager

        ds_mgr = DatasetManager()
        # 复用同名数据集：找到则覆盖 import；否则新建
        existing_id = ""
        listed = ds_mgr.list_all(limit=200)
        for ds in listed.datasets or []:
            if getattr(ds, "name", "") == _DATASET_NAME:
                existing_id = ds.id
                break
        if existing_id:
            dataset_id = existing_id
        else:
            created = ds_mgr.create(
                DatasetCreateRequest(
                    name=_DATASET_NAME,
                    description="小朱策展 good/gold 自动导入（ShareGPT→messages）",
                    source_type=DatasetSourceType.UPLOAD,
                )
            )
            dataset_id = created.id

        imported = ds_mgr.import_jsonl(dataset_id, messages_jsonl)
        base_model = _resolve_base_model()
        if not base_model:
            result["reason"] = "no_base_model"
            return result
        ts = time.strftime("%Y%m%d%H%M")
        job = job_mgr.create(
            JobCreateRequest(
                base_model=base_model,
                dataset_id=dataset_id,
                provider=provider,
                template=FineTuneTemplate.GENERAL,
                custom_name=f"dh-curated:{ts}",
            )
        )
        state.update(
            {
                "status": "submitted",
                "last_sample_count": int(getattr(imported, "sample_count", msg_count) or msg_count),
                "last_job_id": job.id,
                "last_dataset_id": dataset_id,
                "content_sha256": fingerprint,
                "export_path": out_path,
                "provider": provider.value,
                "base_model": base_model,
                "updated_at": int(time.time()),
            }
        )
        _write_state(state)
        result.update(
            {
                "submitted": True,
                "reason": "ok",
                "job_id": job.id,
                "dataset_id": dataset_id,
                "provider": provider.value,
                "base_model": base_model,
                "converted_count": msg_count,
            }
        )
        logger.info(
            "digital_human SFT auto-submitted job=%s dataset=%s samples=%s provider=%s",
            job.id,
            dataset_id,
            msg_count,
            provider.value,
        )
        try:
            from core.harness.digital_human.evolution_proposals import (
                maybe_propose_sft_promote,
            )

            maybe_propose_sft_promote(result)
        except Exception:
            logger.debug("sft_promote proposal after submit failed", exc_info=True)
        return result
    except Exception as e:
        logger.warning("digital_human SFT auto-submit failed: %s", e, exc_info=True)
        state.update(
            {
                "status": "error",
                "last_error": str(e)[:300],
                "last_sample_count": sample_count,
                "content_sha256": fingerprint,
                "updated_at": int(time.time()),
            }
        )
        _write_state(state)
        result["reason"] = f"error:{str(e)[:200]}"
        return result
