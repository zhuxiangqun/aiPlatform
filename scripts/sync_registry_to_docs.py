#!/usr/bin/env python3
"""
sync_registry_to_docs.py — registry → CAPABILITIES.md 方向同步 (P0-C3)

Reads symbols from core/capability_registry.yaml (the machine-readable
capability source) and ensures every registered symbol is present in
AIPLAT_CAPABILITIES.md (the human-readable capability list).

Usage:
  python3 scripts/sync_registry_to_docs.py            # report gaps only
  python3 scripts/sync_registry_to_docs.py --fix      # add missing rows
"""
from __future__ import annotations

import re
import sys
import yaml
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
REGISTRY = WORKSPACE / "aiPlat-core" / "core" / "capability_registry.yaml"
CAPS = WORKSPACE / "AIPLAT_CAPABILITIES.md"

# registry domain name → CAPABILITIES section heading
SECTION_ALIASES = {
    "harness-execution-engine": "## 一、Harness 执行引擎",
    "memory-subsystem": "## 二、记忆子系统",
    "knowledge-engine-ontology": "## 三、知识引擎（本体）",
    "rag-retrieval": "## 四、RAG 检索",
    "knowledge-infrastructure": "## 四附、知识基础设施（Knowledge）",
    "agent-system": "## 五、Agent 系统",
    "skill-system": "## 六、Skill 系统",
    "security-and-governance": "## 七、安全与治理",
    "observability": "## 八、可观测性",
    "model-infrastructure": "## 九、模型基础设施",
    "deploy-and-operations": "## 十、部署与运维",
    "extension-and-learning": "## 十一、扩展与学习",
    "gate-system": "## 十二、Gate 系统",
    "evaluation-system": "## 十三、评估系统",
    "mcp-protocol": "## 十四、MCP 协议",
    "a2a-protocol": "## 十四附、A2A 协议 (Agent-to-Agent)",
    "document-intelligence": "## 十五、文档智能",
    "tool-ecosystem": "## 十六、工具生态",
    "fine-tuning-system": "## 十七、微调系统",
    "deploy-and-canary": "## 十八、部署与灰度",
    "runtime-intervention": "## 十九、运行时干预",
    "arena-and-scheduling": "## 二十、Arena & 调度",
    "platform-governance": "## 二十一、平台治理",
    "infra-infrastructure": "## 二十二、Infra 基础设施",
    "core-api-unified-entry": "## 二十三、核心API统一入口",
    "orchestration-system": "## 二十四、编排系统",
    "management-and-quality": "## 二十五、管理 & 质量",
    "orchestration-layer": "## 二十六、编排层 (Orchestration)",
    # domains without a dedicated CAPABILITIES section → extension & learning
    "l6-autonomy": "## 十一、扩展与学习",
    "memory-white-boxing": "## 二、记忆子系统",
    "memory-runtime-filtering": "## 二、记忆子系统",
    "moa-multi-model-reasoning": "## 十一、扩展与学习",
    "hermes-compression": "## 二、记忆子系统",
    "ai-knowledge-layer": "## 三、知识引擎（本体）",
}


def registry_symbols() -> list[tuple[str, str, str]]:
    """Return [(symbol, domain, module)] from registry."""
    data = yaml.safe_load(open(REGISTRY))
    out = []
    for dname, d in (data.get("domains") or {}).items():
        if not isinstance(d, dict):
            continue
        for p in d.get("provides", []):
            if isinstance(p, dict) and p.get("symbol"):
                out.append((str(p["symbol"]), dname, str(p.get("module", ""))))
    return out


def section_for(domain: str) -> str:
    return SECTION_ALIASES.get(domain, "")


def main() -> int:
    fix = "--fix" in sys.argv
    caps_text = CAPS.read_text(encoding="utf-8")
    symbols = registry_symbols()
    missing: list[tuple[str, str, str, str]] = []
    for sym, domain, module in symbols:
        if sym in caps_text:
            continue
        missing.append((sym, domain, module, section_for(domain)))

    # dedupe by (symbol, domain)
    seen = set()
    unique = []
    for m in missing:
        key = (m[0], m[1])
        if key not in seen:
            seen.add(key)
            unique.append(m)

    if not unique:
        print(f"✅ registry → docs 同步: {len(symbols)} 符号全部在 CAPABILITIES 中")
        return 0

    print(f"❌ registry → docs 漂移: {len(unique)} 个符号不在 CAPABILITIES.md:")
    for sym, domain, module, section in unique:
        print(f"  - {sym:35s} | {domain:28s} | {section or '(无映射)'}")

    if not fix:
        print("\n  (用 --fix 自动补登)")
        return 1

    # ── Fix: insert missing rows under the correct section ──
    lines = caps_text.splitlines(True)
    added = 0
    no_section: list[str] = []
    for sym, domain, module, section in unique:
        if not section:
            no_section.append(sym)
            continue
        if sym in CAPS.read_text(encoding="utf-8"):
            continue  # another symbol inserted it
        # Build row: | symbol | module | ✅ | 自动同步 | 已合入 |
        # registry module is 'core/...' — keep the core/ prefix so the path
        # resolves relative to aiPlat-core/ (same convention as CAPABILITIES).
        short = module.replace("aiPlat-core/", "")
        row = f"| {sym} | `{short}` | ✅ | 自动同步 | 已合入 |"
        # find section heading, insert after header row (| 能力 | 位置 | ...)
        inserted = False
        for i, line in enumerate(lines):
            if line.strip() == section:
                # find next header row that starts with "| " and contains 能力
                for j in range(i + 1, min(i + 8, len(lines))):
                    if re.match(r"^\|.*能力.*\|", lines[j]) and "位置" in lines[j]:
                        lines.insert(j + 1, row + "\n")
                        inserted = True
                        added += 1
                        break
                break
        if not inserted:
            no_section.append(sym)

    if added:
        CAPS.write_text("".join(lines), encoding="utf-8")
        print(f"\n✅ 已补登 {added} 个符号")
    if no_section:
        print(f"⚠️ {len(no_section)} 个符号无 section 映射: {no_section[:10]}")
    return 0 if not no_section else 1


if __name__ == "__main__":
    sys.exit(main())
