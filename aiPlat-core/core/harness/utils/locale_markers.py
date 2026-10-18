"""Locale markers for receipt / done_verify matching (kept out of harness/execution).

Engine §78b forbids inline CJK in ``harness/execution/``. Patterns that must
match Chinese model or user text live here and are imported by those modules.
"""

from __future__ import annotations

import re

# completion_receipt — claim detection + seal prefixes
FIX_CLAIM_RE = re.compile(
    r"(已经修好|已修好|已修复|修复完成|已经修复|bug\s*已修|"
    r"fixed the bug|bug is fixed|successfully fixed)",
    re.IGNORECASE,
)
PATH_CLAIM_RE = re.compile(
    r"(?:文件(?:路径)?(?:是|在|位于)|path is|located at)\s*[`'\"]?([/~][\w./-]{3,})",
    re.IGNORECASE,
)

SEAL_FAIL_MEASURED = "[失败] 预测回执的实测未通过，不能声明已修好。"
SEAL_FAIL_LAST_TOOL = "[失败] 最近一次工具回执失败，不能声明已修好。"
SEAL_FAIL_RECEIPT_PREFIX = "回执："
SEAL_UNVERIFIED_NO_RECEIPT = "[未核验] 完成声明没有成功的工具回执。"
SEAL_UNVERIFIED_PATH = "[未核验] 路径未经成功工具回执确认："

# done_verify — structural markers in agent output
PLAN_HEAD_RE = re.compile(
    r"^(?:#{1,3}\s*)?(?:refactor\s*plan|重构计划)\b|"
    r"\brefactor\s*plan\s*:|"
    r"重构计划\s*[：:]",
    re.IGNORECASE | re.MULTILINE,
)
SAFE_ZONE_RE = re.compile(r"(?i)(?:安全区|safe\s*zone|editable\s*zone)")
PROTECTED_ZONE_RE = re.compile(r"(?i)(?:保护区|protected\s*zone|read[- ]?only\s*zone)")
FEATURE_FLAG_RE = re.compile(
    r"(?i)(?:feature[_\s-]?flag|feature[_\s-]?toggle|"
    r"FEATURE_[A-Z0-9_]+|AIPLAT_FEATURE_|"
    r"灰度|canary\s*(?:percent|rollout|release)?|"
    r"USE_NEW_[A-Z0-9_]+)"
)
ROLLBACK_CMD_RE = re.compile(
    r"(?i)(?:git\s+(?:checkout|reset\s+--hard|revert|stash\s+pop|tag\s+-d)|"
    r"FEATURE_[A-Z0-9_]+\s*=\s*(?:false|0|off)|"
    r"AIPLAT_FEATURE_\w+\s*=\s*(?:false|0|off)|"
    r"(?:##\s*)?(?:Rollback|回滚)(?:\s*(?:Command|命令|步骤))?|"
    r"一键回[滚退]|rollback\s+command)"
)

MSG_PLAN_REQUIRED = (
    "done_verify: refactor plan required — include "
    "'## Refactor Plan' or '## 重构计划' before DONE"
)
MSG_DEP_MAP_REQUIRED = (
    "done_verify: dependency map required — name both "
    "安全区/safe zone and 保护区/protected zone before DONE"
)
MSG_FEATURE_FLAG_REQUIRED = (
    "done_verify: feature flag required — name a feature flag / "
    "FEATURE_* / 灰度 / canary switch before DONE"
)
MSG_ROLLBACK_CMD_REQUIRED = (
    "done_verify: rollback command required — write a one-click "
    "git checkout/reset or FEATURE_*=false before DONE"
)
