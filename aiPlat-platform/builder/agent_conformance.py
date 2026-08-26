"""workspace agent 符合度校验器（Agent Conformance, 2026-08-26）。

与 generated_conformance（生成物契约）同源思路：~/.aiplat/agents/*/AGENT.md 是
无机器校验的维护面——规范（CLAUDE.md §5.27/§12/内容归属）存在但执行靠自觉。
本校验器把 4 项核心规范变成可机器验收的断言，接入 architecture_guard.sh §96。

断言（对每个 AGENT.md）:
  1. max_lines ≤ 100          — §5.27 规则 3（超限拆分 docs/）
  2. 无 model: 硬编码           — §12 模型解析中心化（走 skill_model_purpose 路由）
  3. 交接协议 5 字段完整         — §5.27 规则 2.1（做了什么/产出物在哪/如何验证/已知问题/下一步）
  4. 输出格式无详细模板          — 内容归属规范（输出格式唯一归属 SKILL.md；
                                 "## 输出格式"段内不得含 ```json/```yaml 代码块——只允许引用）

用法：
    from builder.agent_conformance import validate_agents_dir
    violations = validate_agents_dir()   # {agent_name: [违规消息]}
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List

MAX_LINES = 100
HANDOFF_FIELDS = ["做了什么", "产出物在哪", "如何验证", "已知问题", "下一步"]


def validate_agent_md(path: str) -> List[str]:
    """校验单个 AGENT.md，返回违规消息列表（空 = 通过）。"""
    violations: List[str] = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return [f"file unreadable: {e}"]

    # 1. 行数
    lines = len(text.splitlines())
    if lines > MAX_LINES:
        violations.append(f"max_lines: {lines} 行超过预算 {MAX_LINES}（§5.27 规则 3——超限拆分 docs/）")

    # 2. model 硬编码（frontmatter）
    fm = _frontmatter(text)
    if "model" in fm:
        violations.append(f"model: frontmatter 硬编码模型名 {fm['model']!r}（§12——走 skill_model_purpose 路由）")

    # 3. 交接协议 5 字段
    handoff = _section(text, "交接规范")
    if handoff is None:
        violations.append("handoff: 缺「## 交接规范」段（§5.27 规则 2.1）")
    else:
        for f in HANDOFF_FIELDS:
            if f not in handoff:
                violations.append(f"handoff: 缺交接字段「{f}」（§5.27 规则 2.1 五字段）")

    # 4. 输出格式无详细模板（内容归属：格式唯一归属 SKILL.md）
    fmt = _section(text, "输出格式")
    if fmt is not None and re.search(r"```(json|yaml|yml)", fmt):
        violations.append(
            "output_format: 「## 输出格式」段含代码块模板——输出格式唯一归属 SKILL.md，"
            "AGENT.md 只留引用（内容归属规范）"
        )

    return violations


def validate_agents_dir(agents_dir: str | None = None) -> Dict[str, List[str]]:
    """扫描 agents 目录下所有 AGENT.md，返回 {agent_name: [违规]}（空 dict = 全部通过）。"""
    base = agents_dir or os.path.expanduser("~/.aiplat/agents")
    result: Dict[str, List[str]] = {}
    if not os.path.isdir(base):
        return result
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name, "AGENT.md")
        if os.path.isfile(p):
            v = validate_agent_md(p)
            if v:
                result[name] = v
    return result


def _frontmatter(text: str) -> Dict[str, Any]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        import yaml
        data = yaml.safe_load(parts[1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _section(text: str, title: str) -> str | None:
    """提取 `## {title}` 段内容（到下一个 ## 前）。"""
    m = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else None


# ── Ratchet 模式（2026-08-26）：存量违规入基线容忍，新增违规阻断 ──
# workspace 有 50+ agent，历史遗留违规无法一次性治理完。采用 ruff F821 ratchet
# 先例：基线快照当前违规，guard 对比"新增违规/新 agent"才 FAIL，推动逐步治理。

_BASELINE_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "baselines" / "agent_conformance_baseline.json"


def load_baseline() -> Dict[str, List[str]]:
    """加载违规基线（不存在 → 空 dict，即全部视为新增）。"""
    try:
        import json
        with open(_BASELINE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_baseline(violations: Dict[str, List[str]]) -> None:
    """把当前违规写为基线（治理一批后更新）。"""
    import json
    with open(_BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(violations, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def ratchet_diff(current: Dict[str, List[str]], baseline: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """返回"新增违规"（基线里没有的违规 + 基线里没有的 agent 的全部违规）。"""
    new: Dict[str, List[str]] = {}
    for agent, viols in current.items():
        base_viols = set(baseline.get(agent, []))
        added = [v for v in viols if v not in base_viols]
        if agent not in baseline or added:
            new[agent] = added
    return new
