"""应用工厂生成物契约校验器（Generated-Artifact Conformance, 2026-08-26）。

借鉴 skill-based-architecture 的 conformance 模式：应用工厂（agent 模式）生成的
AGENT.md / SKILL.md 在注册到工作区前，必须通过本校验器 —— 生成物不是"LLM 碰运气"，
而是可机器验收的契约。

契约文件：generated_conformance.yaml
挂点：builder_project_service.py 注册循环（AGENT.md/SKILL.md 复制前校验，不通过则跳过注册）。

契约类型（见 generated_conformance.yaml）：
  first_line_must_be    — 首行必须等于（防 ```markdown / 空行 残留导致 frontmatter 解析失败）
  must_contain          — 必须包含子串（治理字段存在性）
  must_not_contain      — 禁止包含子串
  must_contain_in_order — 必须按顺序出现的一组子串
  per_field_must_contain— 对 frontmatter 某字段的值必须包含子串（如 input_schema 值含 "type:"）

用法：
    from builder.generated_conformance import validate_text, validate_file
    violations = validate_text(skill_md_text, kind="skill")   # → list[str]，空=通过
    violations = validate_file("/path/SKILL.md", kind="skill")
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_DEFAULT_CONTRACT_PATH = Path(__file__).resolve().parent / "generated_conformance.yaml"
_KINDS = ("skill", "agent")

_contract_cache: Optional[Dict[str, Any]] = None


def load_contract(path: Optional[str] = None) -> Dict[str, Any]:
    """加载契约（默认 generated_conformance.yaml，缓存）。"""
    global _contract_cache
    p = Path(path) if path else _DEFAULT_CONTRACT_PATH
    if _contract_cache is None or str(p) != str(_DEFAULT_CONTRACT_PATH):
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"contract not a mapping: {p}")
        _contract_cache = data
    return _contract_cache


def validate_text(text: str, kind: str, contract: Optional[Dict[str, Any]] = None) -> List[str]:
    """校验生成物文本，返回违规消息列表（空 = 通过）。

    kind: "skill" | "agent"
    """
    if kind not in _KINDS:
        raise ValueError(f"kind must be one of {_KINDS}, got {kind!r}")
    c = contract or load_contract()
    rules = c.get(kind) or {}
    if not isinstance(rules, dict):
        raise ValueError(f"contract[{kind!r}] not a mapping")

    violations: List[str] = []
    text = text or ""
    first_line = text.split("\n", 1)[0]

    # 1. 首行契约
    expected_first = rules.get("first_line_must_be")
    if expected_first is not None and first_line != expected_first:
        violations.append(
            f"first_line_must_be: 期望首行为 {expected_first!r}，实际 {first_line!r}"
            "（```markdown/```yaml/空行 残留会导致 frontmatter 解析失败）"
        )

    # 2. 顺序断言
    for ordered in rules.get("must_contain_in_order") or []:
        pos = 0
        for token in ordered:
            idx = text.find(token, pos)
            if idx < 0:
                violations.append(f"must_contain_in_order: 找不到 {token!r}（在 {ordered!r} 顺序中）")
                break
            pos = idx + len(token)

    # 3. 存在性断言
    for token in rules.get("must_contain") or []:
        if token not in text:
            violations.append(f"must_contain: 缺少 {token!r}（生成物未声明必要治理字段）")

    # 4. 禁止断言
    for token in rules.get("must_not_contain") or []:
        if token in text:
            violations.append(f"must_not_contain: 含禁止内容 {token!r}")

    # 5. 字段级断言（frontmatter 字段值：dict 键必须存在 / str 必须含子串）
    fm = _parse_frontmatter(text)
    for field, reqs in (rules.get("per_field_must_contain") or {}).items():
        val = fm.get(field)
        reqs = [reqs] if isinstance(reqs, str) else list(reqs or [])
        if val is None:
            violations.append(f"per_field_must_contain[{field}]: frontmatter 缺字段 {field!r}")
        else:
            # dict（如 {field: {type,required,description}}）做递归子串检查
            val_str = str(val)
            for req in reqs:
                if req not in val_str:
                    violations.append(f"per_field_must_contain[{field}]: 值缺少 {req!r}")

    # 6. 上下文预算（B2 路由-知识分离：正文行数上限，防大而全）
    max_body = rules.get("body_max_lines")
    if max_body is not None:
        body_lines = _body_line_count(text)
        if body_lines > int(max_body):
            violations.append(
                f"body_max_lines: 正文 {body_lines} 行超过预算 {max_body} 行"
                "（上下文预算——知识应拆分到独立文件，而非堆进单个 SKILL.md）"
            )

    # 7. description/triggers 一致性（B2 深化：每个触发短语必须出现在 description 中，
    #    保证"用户自然语言 → trigger → description 命中"的路由链成立）
    if rules.get("triggers_in_description"):
        _desc = fm.get("description")
        _triggers = fm.get("triggers")
        if not isinstance(_desc, str) or not _desc.strip():
            violations.append("triggers_in_description: frontmatter 缺 description（字符串）")
        elif not isinstance(_triggers, list) or not _triggers:
            violations.append("triggers_in_description: frontmatter 缺 triggers（列表）")
        else:
            for _t in _triggers:
                if not isinstance(_t, str) or _t not in _desc:
                    violations.append(
                        f"triggers_in_description: 触发短语 {_t!r} 未出现在 description 中"
                        "（路由命中一致性——用户说触发短语应能命中 description）"
                    )

    return violations


def validate_file(path: str, kind: str, contract: Optional[Dict[str, Any]] = None) -> List[str]:
    """校验生成物文件，返回违规消息列表。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return [f"file unreadable: {e}"]
    return validate_text(text, kind, contract)


def _body_line_count(text: str) -> int:
    """frontmatter 之后的正文行数（含空行），用于上下文预算检查。"""
    if not text.startswith("---"):
        return len(text.split("\n"))
    parts = text.split("---", 2)
    if len(parts) < 3:
        return 0
    body = parts[2].strip("\n")
    return len(body.split("\n")) if body else 0


def _parse_frontmatter(text: str) -> Dict[str, Any]:
    """解析 --- frontmatter 为 dict（失败返回空 dict，由 per_field 断言兜底报缺字段）。"""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# 便捷：注册前批量校验（供 builder_project_service 调用）
def validate_generated_file_and_report(path: str, kind: str) -> List[str]:
    """校验并返回违规；供注册循环调用（违规则跳过注册）。"""
    return validate_file(path, kind)


# ── 原则 13：失败经验立即写回并接入下次动作（SBA, 2026-08-26） ──
# conformance 拒绝（失败）→ 审计落盘 → 聚合出"生成规范改进建议"（哪些字段频繁缺失），
# 供 agent_engineering 模板迭代——失败不沉淀为被动日志，而是可行动的改进信号。

def _rejections_path() -> str:
    """拒绝审计文件路径：AIPLAT_HOME/builder/conformance_rejections.jsonl。"""
    import os as _os
    _home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    _dir = _os.path.join(_home, "builder")
    _os.makedirs(_dir, exist_ok=True)
    return _os.path.join(_dir, "conformance_rejections.jsonl")


def record_rejection(project_id: str, kind: str, path: str, violations: List[str]) -> None:
    """记录一次生成物拒绝（append 审计 JSONL）+ L2 经验回写（生成物侧接线，2026-08-27）。

    best-effort 不抛异常：审计/经验登记失败不影响主流程。
    生成物 conformance 拒绝 = 生成失败经验（机器判定，confidence=1.0）→ experience_feedback
    登记（CLAUDE.md §23 生成物适用：待接线 → 已接线）。
    """
    import json as _json
    import time as _t
    try:
        with open(_rejections_path(), "a", encoding="utf-8") as f:
            f.write(_json.dumps({
                "ts": _t.time(),
                "project_id": project_id,
                "kind": kind,
                "path": path,
                "violations": list(violations),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # noqa: cleanup-best-effort — 审计失败不影响主流程
    # ── L2 经验回写：生成失败登记为待验证经验（生成物侧接线） ──
    try:
        import importlib.util as _iu
        import sys as _sys
        _spec = _iu.spec_from_file_location(
            "experience_feedback",
            str(Path(__file__).resolve().parents[1] / "governance/experience_feedback/experience_feedback.py"))
        _mod = _iu.module_from_spec(_spec)
        # dataclass 装饰器需要模块已注册进 sys.modules（Experience 含 @dataclass）
        _sys.modules["experience_feedback"] = _mod
        _spec.loader.exec_module(_mod)
        _mod.register_failure(
            f"generated-conformance-reject-{kind}",
            f"生成物 {kind} 契约校验拒绝：{path}（{len(violations)} 项违规：{'; '.join(violations[:3])}）",
            source="generated_conformance", confidence=1.0, risk="low")
    except Exception:
        pass  # noqa: cleanup-best-effort — 经验登记失败不影响主流程


def aggregate_rejections(limit: int = 10) -> Dict[str, Any]:
    """聚合拒绝审计：统计 top 缺失字段/断言类型（→ 生成规范改进建议）。

    返回 {total, by_kind: {skill: n, agent: n}, top_violations: [(断言类型, 次数)],
          top_fields: [(缺失字段, 次数)], suggestion}。
    """
    import collections
    import json as _json
    _path = _rejections_path()
    total = 0
    by_kind = collections.Counter()
    by_assert = collections.Counter()
    by_field = collections.Counter()
    if not os.path.isfile(_path):
        return {"total": 0, "by_kind": {}, "top_violations": [], "top_fields": [],
                "suggestion": "暂无 conformance 拒绝记录——生成物均通过契约校验。"}
    try:
        with open(_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = _json.loads(line)
                except Exception:
                    continue
                total += 1
                by_kind[rec.get("kind", "?")] += 1
                for v in rec.get("violations", []):
                    _tag = _violation_tag(v)
                    by_assert[_tag] += 1
                    if _tag in ("must_contain", "per_field_must_contain"):
                        _f = _violation_field(v)
                        if _f:
                            by_field[_f] += 1
    except Exception:
        return {"total": total, "by_kind": dict(by_kind),
                "top_violations": by_assert.most_common(limit),
                "top_fields": by_field.most_common(limit), "suggestion": ""}
    top_fields = by_field.most_common(limit)
    _sugg = ""
    if top_fields:
        _names = "、".join(f"`{f}`({n} 次)" for f, n in top_fields[:5])
        _sugg = (f"生成规范建议：模板高频缺失字段 {_names}——agent_engineering 模板应补强"
                 "这些字段的必填说明/示例，减少同型拒绝（SBA 原则 13 失败写回）。")
    return {"total": total, "by_kind": dict(by_kind),
            "top_violations": by_assert.most_common(limit),
            "top_fields": top_fields, "suggestion": _sugg}


def _violation_tag(v: str) -> str:
    """从违规消息提取断言类型（first_line_must_be / must_contain / ...）。"""
    for tag in ("first_line_must_be", "must_contain_in_order", "must_contain",
                "must_not_contain", "per_field_must_contain", "body_max_lines",
                "triggers_in_description"):
        if v.startswith(tag):
            return tag
    return "other"


def _violation_field(v: str) -> str:
    """从 per_field/must_contain 违规消息提取缺失字段名。"""
    import re as _re
    m = _re.search(r"\[([^\]]+)\]", v)
    if m:
        return m.group(1)
    m = _re.search(r"缺少 '([^']+)'", v)
    if m:
        return m.group(1).rstrip(":")
    return ""
