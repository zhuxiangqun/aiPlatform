"""Coding intensity ladder (B0–B2): lite | full | ultra + hard security floor.

- Hard constraints always inject for coding skills (never weakened by lite).
- Soft layers scale: lite < full(=karpathy_v1) < ultra.
- Env: AIPLAT_CODING_INTENSITY (preferred) or AIPLAT_CODING_POLICY_PROFILE_*.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Optional

INTENSITY_OFF = "off"
INTENSITY_LITE = "lite"
INTENSITY_FULL = "full"
INTENSITY_ULTRA = "ultra"

CODING_INTENSITIES = frozenset(
    {INTENSITY_OFF, INTENSITY_LITE, INTENSITY_FULL, INTENSITY_ULTRA}
)

_ALIASES = {
    "karpathy_v1": INTENSITY_FULL,
    "karpathy": INTENSITY_FULL,
    "ponytail": INTENSITY_FULL,
    "default": INTENSITY_FULL,
    "standard": INTENSITY_FULL,
    "strict": INTENSITY_ULTRA,
    "lazy": INTENSITY_LITE,
}

STRICT_INTENSITIES = frozenset(
    {INTENSITY_LITE, INTENSITY_FULL, INTENSITY_ULTRA, "karpathy_v1"}
)

_HARD = (
    "编码安全硬约束（所有档位强制，不可降级）：\n"
    "1) 禁止 except Exception: pass 静默吞错；须 logging / raise / 显式降级之一。\n"
    "2) 禁止把密钥、token、密码写入源码或日志。\n"
    "3) 禁止无边界删除仓库目录或覆盖无关文件；改动限于任务所需路径。\n"
    "4) 禁止引入未声明的远程代码执行或任意 URL 拉取执行。\n"
)

_LITE = (
    "编码强度 lite（少写）：\n"
    "- 最小改动：只改必须文件与必须行。\n"
    "- 禁止未请求的新抽象（新基类/工厂/框架层）。\n"
    "- 能复用现有函数就不新建。\n"
)

_FULL = (
    "编码行为规范（full / karpathy_v1）：\n"
    "1) 编码前思考：不要做未证实假设；遇歧义先列出确认问题与可选方案。\n"
    "2) 简洁优先：最小可行实现；不引入未经请求的抽象/架构/额外功能。\n"
    "3) 精准修改：只改必须改的地方；避免无关格式化/无关文件改动。\n"
    "4) 目标驱动：把任务转成可验证目标；给出验收标准（测试/复现/检查清单）。\n"
    "5) 错误可见：禁止 except Exception: pass（同硬约束）。\n"
    "防过度设计（over_engineering）：\n"
    "- 不为假想未来需求预留接口/配置面。\n"
    "- 不新增第三依赖，除非现有依赖无法完成。\n"
)

_ULTRA = (
    "编码强度 ultra（在 full 之上）：\n"
    "- 输出前自检：是否可用更少文件/更少类完成？若能，删掉多余层。\n"
    "- 每个新文件须在摘要中说明「为何不能并入已有文件」。\n"
    "- 新增依赖必须写明理由；默认拒绝新依赖。\n"
    "- 禁止「先搭框架再填空」；先写可运行主路径。\n"
)


def normalize_coding_intensity(raw: Any, *, default: str = INTENSITY_FULL) -> str:
    """Normalize to off|lite|full|ultra."""
    val = str(raw or "").strip().lower()
    if not val:
        return default if default in CODING_INTENSITIES else INTENSITY_FULL
    if val in _ALIASES:
        return _ALIASES[val]
    if val in CODING_INTENSITIES:
        return val
    return default if default in CODING_INTENSITIES else INTENSITY_FULL


def resolve_coding_intensity(
    *,
    explicit: Any = None,
    project: Optional[Mapping[str, Any]] = None,
    state: Optional[Mapping[str, Any]] = None,
    scope: str = "engine",
    default: str = INTENSITY_FULL,
) -> str:
    """Resolve intensity: explicit → state → project → env → default."""
    if explicit not in (None, ""):
        return normalize_coding_intensity(explicit, default=default)
    if isinstance(state, Mapping):
        for key in ("_coding_intensity", "coding_intensity", "_coding_policy_profile"):
            if state.get(key) not in (None, ""):
                return normalize_coding_intensity(state.get(key), default=default)
    if isinstance(project, Mapping):
        for key in ("coding_intensity", "coding_policy_profile"):
            if project.get(key) not in (None, ""):
                return normalize_coding_intensity(project.get(key), default=default)
    env_intensity = os.getenv("AIPLAT_CODING_INTENSITY", "").strip()
    if env_intensity:
        return normalize_coding_intensity(env_intensity, default=default)
    scope_l = str(scope or "engine").strip().lower()
    if scope_l == "workspace":
        env_prof = os.getenv("AIPLAT_CODING_POLICY_PROFILE_WORKSPACE", "").strip()
    else:
        env_prof = os.getenv("AIPLAT_CODING_POLICY_PROFILE_ENGINE", "").strip()
    if env_prof:
        return normalize_coding_intensity(env_prof, default=default)
    return normalize_coding_intensity(default, default=INTENSITY_FULL)


def intensity_to_policy_profile(intensity: str) -> str:
    """Map intensity → legacy coding_policy_profile label for traces/gates."""
    inten = normalize_coding_intensity(intensity)
    if inten == INTENSITY_OFF:
        return "off"
    if inten == INTENSITY_FULL:
        return "karpathy_v1"
    return inten


def is_strict_coding_profile(profile_or_intensity: str) -> bool:
    raw = str(profile_or_intensity or "").strip().lower()
    inten = normalize_coding_intensity(raw, default=INTENSITY_OFF)
    strict_env = os.getenv("AIPLAT_STRICT_CODING_PROFILES", "").strip()
    if strict_env:
        allowed = {x.strip().lower() for x in strict_env.split(",") if x.strip()}
        return (
            raw in allowed
            or inten in allowed
            or intensity_to_policy_profile(inten) in allowed
        )
    if raw in ("", "off") or inten == INTENSITY_OFF:
        return False
    return inten in (INTENSITY_LITE, INTENSITY_FULL, INTENSITY_ULTRA) or raw in STRICT_INTENSITIES


def build_coding_policy_block(
    profile_or_intensity: Any,
    *,
    include_hard: bool = True,
) -> str:
    """Build prompt overlay for a coding skill. Empty when off."""
    raw = str(profile_or_intensity or "").strip().lower()
    if raw in ("", "off"):
        return ""
    inten = normalize_coding_intensity(profile_or_intensity, default=INTENSITY_FULL)
    if inten == INTENSITY_OFF:
        return ""
    parts: list[str] = []
    if include_hard:
        parts.append(_HARD)
    if inten == INTENSITY_LITE:
        parts.append(_LITE)
    elif inten == INTENSITY_ULTRA:
        parts.append(_FULL)
        parts.append(_ULTRA)
    else:
        parts.append(_FULL)
    return "\n".join(parts).strip() + "\n"


def ponytail_overlay_for_intensity(intensity: str) -> str:
    """Short ponytail-style overlay (no full SKILL.md dump)."""
    inten = normalize_coding_intensity(intensity, default=INTENSITY_FULL)
    if inten == INTENSITY_OFF:
        return ""
    if inten == INTENSITY_LITE:
        return (
            "## Ponytail (lite)\n"
            "Prefer the smallest diff. Do not add helpers/classes until a second call site exists.\n"
        )
    if inten == INTENSITY_ULTRA:
        return (
            "## Ponytail (ultra)\n"
            "Act as a lazy senior: delete speculative abstractions; "
            "one obvious way; refuse new deps unless blocked otherwise.\n"
        )
    return (
        "## Ponytail (full)\n"
        "Lazy senior defaults: reuse first, smallest change, no speculative architecture.\n"
    )


def resolve_ponytail_mode() -> str:
    """Read PONYTAIL_MODE with typo fallback PONytail_MODE; default full."""
    return normalize_coding_intensity(
        os.getenv("PONYTAIL_MODE")
        or os.getenv("PONytail_MODE")
        or INTENSITY_FULL,
        default=INTENSITY_FULL,
    )


def default_intensity_for_factory_mode(factory_mode: str) -> str:
    """Factory code/hybrid → full; agent conversational → lite for coding stages."""
    mode = str(factory_mode or "").strip().lower()
    if mode in ("code", "hybrid"):
        return INTENSITY_FULL
    if mode == "agent":
        return INTENSITY_LITE
    return INTENSITY_FULL
