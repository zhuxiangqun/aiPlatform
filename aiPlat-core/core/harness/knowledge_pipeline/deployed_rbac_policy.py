"""部署侧 RBAC/ACL 真源（附录 N N18 deepen）。

职责：
  - 从部署配置加载策略（env / AIPLAT_HOME），**不**以 ``reference_policy.json`` 为权威
  - 评估 permission（跨租户 deny + 角色动作 allow/deny/approval）
  - 套件/门槛门：``certified`` / ``n18_full`` 恒 false

非目标：
  - 不宣称生产 RBAC 全路径（召回过滤/聚合/导出/缓存）已覆盖
  - 不删除标准包 ``reference_policy.json``（仍为参考资产）
  - 不关闭 N18 certified / 不冒充附录 N 全量符合
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SUITE_CASES = (
    "source_not_reference_file",
    "same_tenant_allow",
    "same_tenant_deny",
    "cross_tenant_deny",
    "approval_outcome",
    "honesty_certified_false",
)

# 部署侧默认策略（结构对齐 reference_policy，但权威路径不同）
_DEFAULT_DEPLOYED: Dict[str, Any] = {
    "policy_id": "deployed-rbac-default-v1",
    "tenant_rule": "actor.tenant == target.tenant",
    "roles": {
        "support_agent": {
            "Ticket.read": "allow",
            "Ticket.close": "deny",
            "Ticket.close_high_risk": "approval",
        },
        "support_lead": {
            "Ticket.read": "allow",
            "Ticket.close": "allow",
            "Ticket.close_high_risk": "approval",
        },
        "auditor": {
            "Ticket.read": "allow",
            "Ticket.close": "deny",
            "Ticket.close_high_risk": "deny",
        },
    },
}


class DeployedRbacError(ValueError):
    """部署侧 RBAC 契约错误。"""


def _home_policy_path() -> Optional[Path]:
    """解析 ``AIPLAT_HOME/rbac/deployed_policy.json``。"""
    home = (os.environ.get("AIPLAT_HOME") or "").strip()
    if not home:
        return None
    return Path(home) / "rbac" / "deployed_policy.json"


def load_deployed_policy(
    *,
    policy_json: Optional[str] = None,
    policy_path: Optional[str] = None,
) -> Dict[str, Any]:
    """加载部署侧 RBAC 策略（权威源；永不读标准包 reference_policy）。

    优先级：显式 ``policy_json`` → ``policy_path`` → ``AIPLAT_DEPLOYED_RBAC_POLICY``
    → ``AIPLAT_DEPLOYED_RBAC_POLICY_PATH`` → ``AIPLAT_HOME/rbac/deployed_policy.json``
    → 内置部署默认。

    Args:
        policy_json: 可选 JSON 字符串。
        policy_path: 可选文件路径。
    """
    # 为什么：N18 要求权威源为部署侧；禁止静默回落标准包 reference_policy.json
    raw = (policy_json or "").strip()
    source = "arg_json"
    if not raw:
        path = (policy_path or "").strip()
        if not path:
            path = (os.environ.get("AIPLAT_DEPLOYED_RBAC_POLICY_PATH") or "").strip()
        if not path:
            env_json = (os.environ.get("AIPLAT_DEPLOYED_RBAC_POLICY") or "").strip()
            if env_json:
                raw = env_json
                source = "env_json"
            else:
                home_p = _home_policy_path()
                if home_p and home_p.is_file():
                    path = str(home_p)
        if path and not raw:
            p = Path(path)
            # 为什么：拒绝把标准包 reference_policy 路径当作部署权威
            if "reference_policy.json" in p.name or "schemas/conformance" in str(p):
                raise DeployedRbacError("reference_policy_forbidden_as_deployed_source")
            if not p.is_file():
                raise DeployedRbacError(f"deployed_policy_missing:{path}")
            raw = p.read_text(encoding="utf-8")
            source = f"file:{p}"
    if not raw:
        return {
            **_DEFAULT_DEPLOYED,
            "_source": "builtin_deployed_default",
            "_reference_policy_used": False,
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeployedRbacError(f"deployed_policy_invalid_json:{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("roles"), dict):
        raise DeployedRbacError("deployed_policy_roles_required")
    out = dict(data)
    out["_source"] = source
    out["_reference_policy_used"] = False
    return out


def evaluate_permission(
    *,
    role: str,
    action: str,
    actor_tenant: str,
    target_tenant: str,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """评估角色×动作权限（跨租户恒 deny）。

    Args:
        role: 角色。
        action: 动作（如 ``Ticket.read``）。
        actor_tenant: 调用方租户。
        target_tenant: 目标租户。
        policy: 可选已加载策略；缺省 ``load_deployed_policy()``。
    """
    pol = policy if policy is not None else load_deployed_policy()
    if pol.get("_reference_policy_used") is True:
        raise DeployedRbacError("reference_policy_used_forbidden")
    a_t = (actor_tenant or "").strip()
    t_t = (target_tenant or "").strip()
    if not a_t or not t_t:
        raise DeployedRbacError("actor_and_target_tenant_required")
    if a_t != t_t:
        decision = "deny"
    else:
        roles = pol.get("roles") or {}
        role_map = roles.get(role) if isinstance(roles, dict) else None
        if not isinstance(role_map, dict):
            decision = "deny"
        else:
            decision = str(role_map.get(action) or "deny").strip().lower() or "deny"
            if decision not in ("allow", "deny", "approval"):
                decision = "deny"
    return {
        "ok": True,
        "decision": decision,
        "role": role,
        "action": action,
        "actor_tenant": a_t,
        "target_tenant": t_t,
        "policy_id": pol.get("policy_id") or "",
        "source": pol.get("_source") or "",
        "reference_policy_used": False,
        "certified": False,
        "n18_full_conformance": False,
    }


def evaluate_deployed_rbac_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N18 deepen 门槛门（certified / n18_full 恒 false）。

    Args:
        suite: ``run_deployed_rbac_suite`` 回执。
    """
    s = suite or {}
    issues: List[str] = []
    # 为什么：禁止套件自签 certified（部署源 deepen ≠ N18 全量认证）
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    # 为什么：禁止套件自签 n18_full（加深刀 ≠ 附录 N 全量符合）
    if s.get("n18_full_conformance") is True:
        issues.append("honesty_n18_full_flag_forbidden")
    if s.get("reference_policy_used") is True:
        issues.append("honesty_reference_policy_used")
    cases = s.get("cases") or []
    if cases:
        failed = [c for c in cases if isinstance(c, dict) and not c.get("ok")]
        if failed:
            issues.append(f"suite_cases_failed:{len(failed)}")
        ids = {str(c.get("id") or "") for c in cases if isinstance(c, dict)}
        missing = [x for x in _SUITE_CASES if x not in ids]
        if missing:
            issues.append(f"suite_cases_missing:{','.join(missing)}")
    elif not s.get("ok"):
        issues.append("suite_not_ok")
    return {
        "ok": not issues and bool(s.get("ok", True)),
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n18_full_conformance": False,
        "reference_policy_used": False,
        "note": "Deployed RBAC deepen; not N18 certified / not full recall-path coverage",
    }


def run_deployed_rbac_suite(
    *,
    policy_json: Optional[str] = None,
) -> Dict[str, Any]:
    """N18 deepen：部署侧 RBAC 套件（certified 恒 false）。

    Args:
        policy_json: 可选显式部署策略 JSON。
    """
    cases: List[Dict[str, Any]] = []
    pol = load_deployed_policy(policy_json=policy_json)
    src = str(pol.get("_source") or "")
    cases.append(
        {
            "id": "source_not_reference_file",
            "ok": pol.get("_reference_policy_used") is False
            and "reference_policy" not in src
            and "schemas/conformance" not in src,
            "detail": src,
        }
    )

    allow = evaluate_permission(
        role="support_agent",
        action="Ticket.read",
        actor_tenant="t1",
        target_tenant="t1",
        policy=pol,
    )
    cases.append(
        {
            "id": "same_tenant_allow",
            "ok": allow.get("decision") == "allow"
            and allow.get("reference_policy_used") is False,
            "detail": "",
        }
    )

    deny = evaluate_permission(
        role="support_agent",
        action="Ticket.close",
        actor_tenant="t1",
        target_tenant="t1",
        policy=pol,
    )
    cases.append(
        {
            "id": "same_tenant_deny",
            "ok": deny.get("decision") == "deny",
            "detail": "",
        }
    )

    xdeny = evaluate_permission(
        role="support_agent",
        action="Ticket.read",
        actor_tenant="t1",
        target_tenant="t2",
        policy=pol,
    )
    cases.append(
        {
            "id": "cross_tenant_deny",
            "ok": xdeny.get("decision") == "deny",
            "detail": "",
        }
    )

    appr = evaluate_permission(
        role="support_lead",
        action="Ticket.close_high_risk",
        actor_tenant="t1",
        target_tenant="t1",
        policy=pol,
    )
    cases.append(
        {
            "id": "approval_outcome",
            "ok": appr.get("decision") == "approval",
            "detail": "",
        }
    )

    cases.append(
        {
            "id": "honesty_certified_false",
            "ok": True,
            "detail": "",
        }
    )

    # 拒绝把标准包路径当部署源
    ref_blocked = False
    try:
        load_deployed_policy(
            policy_path=(
                "docs/standards/knowledge-system/v4.3.1/schemas/"
                "conformance/reference_policy.json"
            )
        )
    except DeployedRbacError as exc:
        ref_blocked = "reference_policy_forbidden" in str(exc)
    # 把拒绝标准包并入 source 用例细节（若失败则覆盖 source 用例）
    if not ref_blocked:
        for c in cases:
            if c["id"] == "source_not_reference_file":
                c["ok"] = False
                c["detail"] = "reference_policy_path_not_blocked"

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_SUITE_CASES),
        "passed": passed,
        "total": len(_SUITE_CASES),
        "cases": cases,
        "policy_id": pol.get("policy_id") or "",
        "source": src,
        "reference_policy_used": False,
        "certified": False,
        "n18_full_conformance": False,
        "measured_at": time.time(),
        "note": "Deployed RBAC deepen; not full recall/export/cache coverage / not certified",
    }
