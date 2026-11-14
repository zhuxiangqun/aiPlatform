"""按命名工作区登记外部评测目标（``http_chat_pull``）。

职责
----
在 ``AIPLAT_HOME`` / 工作区目录下读写 ``external_targets.yaml``：
校验 ID、SSRF 守卫、公开视图、鉴权头解析与原子落盘。

非目标
------
- 不执行拉评本身（仅登记与解析）
- 不把密钥写入 YAML（只存 ``auth_secret_env`` 名）
- 不解锁 ``accuracy_claim``

读序
----
``upsert_external_target`` / ``list_external_targets`` →
``get_external_target`` → ``build_invoke_url`` / ``resolve_auth_header``。
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from core.utils.paths import get_aiplat_home

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
KIND_HTTP_CHAT_PULL = "http_chat_pull"
_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
_RESPONSE_MODES = frozenset({"aiplat_v0", "openai_chat", "plain_text"})
MAX_TIMEOUT_MS = 120_000
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_PATH = "/v1/chat"


def validate_target_id(target_id: str) -> str:
    """校验并规范化外部目标 ID。

    Args:
        target_id: 原始目标 ID。

    Returns:
        规范化后的 ID。

    Raises:
        ValueError: 为空、格式非法或含路径分隔符。
    """
    tid = (target_id or "").strip()
    if not tid or not _ID_RE.match(tid):
        raise ValueError(f"invalid target_id: {target_id!r}")
    if tid in {".", ".."} or "/" in tid or "\\" in tid:
        raise ValueError(f"invalid target_id: {target_id!r}")
    return tid


def external_agent_id(target_id: str) -> str:
    """生成写入 eval_results 的合成 ``agent_id``（``ext:{id}``）。

    Args:
        target_id: 外部目标 ID。

    Returns:
        ``ext:<validated_id>`` 字符串。
    """
    return f"ext:{validate_target_id(target_id)}"


def targets_path_for_workspace(workspace_id: str) -> Path:
    """解析工作区对应的 ``external_targets.yaml`` 路径。

    Args:
        workspace_id: 工作区 ID；``default`` 落在 AIPLAT_HOME 根下。

    Returns:
        YAML 文件 Path。
    """
    home = Path(get_aiplat_home())
    wid = (workspace_id or "default").strip() or "default"
    if wid == "default":
        return home / "external_targets.yaml"
    return home / "workspaces" / wid / "external_targets.yaml"


def _lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock")


def _empty_doc() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "targets": []}


def _atomic_write_yaml(path: Path, doc: Dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"yaml unavailable: {e}") from e

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass  # noqa: cleanup-best-effort

    lock = _lock_path(path)
    lock_fd = None
    try:
        lock_fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            import fcntl  # type: ignore

            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        except Exception:
            logger.debug("fcntl flock unavailable; proceeding without", exc_info=True)

        data = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".ext_targets.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, str(path))
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass  # noqa: cleanup-best-effort
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass  # noqa: cleanup-best-effort
    finally:
        if lock_fd is not None:
            try:
                import fcntl  # type: ignore

                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass  # noqa: optional-dependency
            try:
                os.close(lock_fd)
            except OSError:
                pass  # noqa: cleanup-best-effort


def load_targets_doc(workspace_id: str) -> Dict[str, Any]:
    """加载工作区外部目标文档（缺失则返回空文档）。

    Args:
        workspace_id: 工作区 ID。

    Returns:
        含 ``schema_version`` / ``targets`` 的文档 dict。

    Raises:
        RuntimeError: YAML 不可用、损坏或 schema 版本不支持。
    """
    path = targets_path_for_workspace(workspace_id)
    if not path.exists():
        return _empty_doc()
    try:
        import yaml  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"yaml unavailable: {e}") from e
    try:
        raw = path.read_text(encoding="utf-8")
        doc = yaml.safe_load(raw) or {}
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"external_targets corrupt: {e}") from e
    if not isinstance(doc, dict):
        raise RuntimeError("external_targets corrupt: not a mapping")
    ver = int(doc.get("schema_version") or 0)
    if ver != SCHEMA_VERSION:
        raise RuntimeError(f"external_targets unsupported schema_version={ver}")
    items = doc.get("targets")
    if items is None:
        doc["targets"] = []
    elif not isinstance(items, list):
        raise RuntimeError("external_targets corrupt: targets not a list")
    return doc


def list_external_targets(workspace_id: str) -> List[Dict[str, Any]]:
    """列出工作区外部目标的公开视图（不含密钥原文）。

    Args:
        workspace_id: 工作区 ID。

    Returns:
        公开目标 dict 列表。
    """
    doc = load_targets_doc(workspace_id)
    out: List[Dict[str, Any]] = []
    for row in doc.get("targets") or []:
        if not isinstance(row, dict):
            continue
        pub = public_target_view(row)
        if pub:
            out.append(pub)
    return out


def get_external_target(workspace_id: str, target_id: str) -> Optional[Dict[str, Any]]:
    """按 ID 取完整目标行（含 ``auth_secret_env`` 名，不含密钥值）。

    Args:
        workspace_id: 工作区 ID。
        target_id: 目标 ID。

    Returns:
        完整行 dict，或 ``None``。
    """
    tid = validate_target_id(target_id)
    doc = load_targets_doc(workspace_id)
    for row in doc.get("targets") or []:
        if isinstance(row, dict) and str(row.get("target_id") or "") == tid:
            return dict(row)
    return None


def public_target_view(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """将存储行转为 API 安全公开视图。

    Args:
        row: 存储中的目标行。

    Returns:
        公开字段 dict；缺 ``target_id`` 时返回 ``None``。
    """
    tid = str(row.get("target_id") or "").strip()
    if not tid:
        return None
    return {
        "target_id": tid,
        "label": str(row.get("label") or tid),
        "kind": str(row.get("kind") or KIND_HTTP_CHAT_PULL),
        "base_url": str(row.get("base_url") or ""),
        "path": str(row.get("path") or DEFAULT_PATH),
        "auth_header_name": str(row.get("auth_header_name") or "") or None,
        "auth_secret_configured": bool(str(row.get("auth_secret_env") or "").strip()),
        "timeout_ms": int(row.get("timeout_ms") or DEFAULT_TIMEOUT_MS),
        "response_mode": str(row.get("response_mode") or "aiplat_v0"),
        "agent_id": external_agent_id(tid),
    }


def _normalize_base_url(base_url: str) -> str:
    u = (base_url or "").strip().rstrip("/")
    if not u:
        raise ValueError("base_url required")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("base_url must be http(s)")
    if not parsed.hostname:
        raise ValueError("base_url missing host")
    return u


def assert_url_allowed(url: str) -> None:
    """对已登记外部评测端点做 SSRF 守卫。

    Args:
        url: 待校验完整 URL。

    Raises:
        ValueError: 命中阻断且未开启私网放行时，码形如 ``ssrf_blocked:...``。
    """
    from core.harness.execution.true_test_runtime import is_blocked_url

    allow_private = os.environ.get("AIPLAT_EXTERNAL_EVAL_ALLOW_PRIVATE", "").strip() in (
        "1",
        "true",
        "TRUE",
        "yes",
    )
    blocked, reason = is_blocked_url(url)
    if blocked and allow_private:
        # 为什么：显式 env 旁路仅用于受控内网评测，仍记审计告警
        logger.warning(
            "external_eval_allow_private: would block url reason=%s (audit)",
            reason,
        )
        return
    if blocked:
        raise ValueError(f"ssrf_blocked:{reason}")


def build_invoke_url(base_url: str, path: str) -> str:
    """拼接调用 URL，并强制同主机 / SSRF 校验。

    Args:
        base_url: 已登记的 http(s) 基址。
        path: 相对路径（默认 ``/v1/chat``）。

    Returns:
        可调用的完整 URL。

    Raises:
        ValueError: 基址非法、path 逃逸主机或 SSRF 阻断。
    """
    base = _normalize_base_url(base_url)
    p = (path or DEFAULT_PATH).strip() or DEFAULT_PATH
    if not p.startswith("/"):
        p = "/" + p
    url = urljoin(base + "/", p.lstrip("/"))
    # 重建后必须仍落在登记主机
    bp, up = urlparse(base), urlparse(url)
    if (up.hostname or "").lower() != (bp.hostname or "").lower():
        raise ValueError("path escapes registered host")
    if up.scheme != bp.scheme:
        raise ValueError("scheme mismatch")
    assert_url_allowed(url)
    return url


def upsert_external_target(
    workspace_id: str,
    *,
    target_id: str,
    label: str = "",
    base_url: str = "",
    path: str = DEFAULT_PATH,
    auth_header_name: str = "",
    auth_secret_env: str = "",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    response_mode: str = "aiplat_v0",
    kind: str = KIND_HTTP_CHAT_PULL,
) -> Dict[str, Any]:
    """创建或更新外部目标并原子写入 YAML。

    Args:
        workspace_id: 工作区 ID。
        target_id: 目标 ID。
        label: 展示名；空则用 ``target_id``。
        base_url: http(s) 基址。
        path: 调用路径。
        auth_header_name: 鉴权头名（可选）。
        auth_secret_env: 存放密钥的环境变量名（可选）。
        timeout_ms: 超时毫秒，范围 ``1..MAX_TIMEOUT_MS``。
        response_mode: ``aiplat_v0`` / ``openai_chat`` / ``plain_text``。
        kind: 当前仅支持 ``http_chat_pull``。

    Returns:
        公开视图 dict。

    Raises:
        ValueError: 字段非法或 SSRF 校验失败。
        RuntimeError: 落盘/YAML 失败。
    """
    tid = validate_target_id(target_id)
    if (kind or KIND_HTTP_CHAT_PULL) != KIND_HTTP_CHAT_PULL:
        raise ValueError(f"unsupported kind: {kind}")
    mode = (response_mode or "aiplat_v0").strip()
    if mode not in _RESPONSE_MODES:
        raise ValueError(f"unsupported response_mode: {response_mode}")
    base = _normalize_base_url(base_url)
    p = (path or DEFAULT_PATH).strip() or DEFAULT_PATH
    build_invoke_url(base, p)  # validate SSRF at register time
    to = int(timeout_ms or DEFAULT_TIMEOUT_MS)
    if to < 1 or to > MAX_TIMEOUT_MS:
        raise ValueError(f"timeout_ms out of range 1..{MAX_TIMEOUT_MS}")

    entry = {
        "target_id": tid,
        "label": (label or tid).strip() or tid,
        "kind": KIND_HTTP_CHAT_PULL,
        "base_url": base,
        "path": p if p.startswith("/") else f"/{p}",
        "auth_header_name": (auth_header_name or "").strip(),
        "auth_secret_env": (auth_secret_env or "").strip(),
        "timeout_ms": to,
        "response_mode": mode,
    }
    doc = load_targets_doc(workspace_id)
    items = [r for r in (doc.get("targets") or []) if isinstance(r, dict)]
    replaced = False
    for i, row in enumerate(items):
        if str(row.get("target_id") or "") == tid:
            items[i] = entry
            replaced = True
            break
    if not replaced:
        items.append(entry)
    doc["schema_version"] = SCHEMA_VERSION
    doc["targets"] = items
    _atomic_write_yaml(targets_path_for_workspace(workspace_id), doc)
    return public_target_view(entry) or entry


def resolve_auth_header(row: Dict[str, Any]) -> Optional[tuple]:
    """从环境变量解析鉴权头 ``(name, value)``。

    Args:
        row: 目标行（含 ``auth_header_name`` / ``auth_secret_env``）。

    Returns:
        ``(header_name, secret)``；未配置头名或 env 名时返回 ``None``。

    Raises:
        ValueError: 已配置 env 名但环境变量未设置。
    """
    name = str(row.get("auth_header_name") or "").strip()
    env_key = str(row.get("auth_secret_env") or "").strip()
    if not name or not env_key:
        return None
    val = os.environ.get(env_key, "")
    if not val:
        raise ValueError(f"auth_secret_env unset: {env_key}")
    return name, val
