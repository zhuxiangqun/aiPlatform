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

    return violations


def validate_file(path: str, kind: str, contract: Optional[Dict[str, Any]] = None) -> List[str]:
    """校验生成物文件，返回违规消息列表。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return [f"file unreadable: {e}"]
    return validate_text(text, kind, contract)


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
