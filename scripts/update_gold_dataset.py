#!/usr/bin/env python3
"""update_gold_dataset.py — 从工具和技能中提取 gold examples 并合并到种子数据集。

扫描路径：
  1. apps/tools/*.py   → BaseTool 子类的 gold_examples 类属性
  2. apps/skills/*/SKILL.md → ## Gold Examples 区块

用法：
  python scripts/update_gold_dataset.py          # 扫描并合并
  python scripts/update_gold_dataset.py --check  # 仅检查覆盖率（不修改）
"""
import ast
import glob
import json
import os
import sys

GOLD_FILE = "aiPlat-core/core/tests/data/gold_tool_selection.json"


def extract_from_tools(root: str) -> list:
    """从 BaseTool 子类的 gold_examples 类属性提取。"""
    cases = []
    tools_dir = os.path.join(root, "aiPlat-core/core/apps/tools")
    if not os.path.isdir(tools_dir):
        return cases

    for py_path in glob.glob(os.path.join(tools_dir, "*.py")):
        try:
            with open(py_path) as f:
                tree = ast.parse(f.read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "gold_examples":
                                try:
                                    cases.extend(ast.literal_eval(item.value))
                                except Exception:
                                    pass
    return cases


def extract_from_skills(root: str) -> list:
    """从 SKILL.md 的 ## Gold Examples 区块提取。"""
    cases = []
    skills_dir = os.path.join(root, "aiPlat-core/core/apps/skills")
    if not os.path.isdir(skills_dir):
        return cases

    for md_path in glob.glob(os.path.join(skills_dir, "*", "SKILL.md")):
        try:
            with open(md_path) as f:
                content = f.read()
        except Exception:
            continue
        if "## Gold Examples" in content:
            start = content.index("## Gold Examples") + len("## Gold Examples")
            block = content[start:].split("##")[0]
            try:
                import yaml
                parsed = yaml.safe_load(block)
                if isinstance(parsed, list):
                    cases.extend(parsed)
            except Exception:
                pass
    return cases


def main():
    root = os.getcwd()
    all_cases = extract_from_tools(root) + extract_from_skills(root)

    if not os.path.exists(GOLD_FILE):
        print(f"❌ Gold file not found: {GOLD_FILE}")
        sys.exit(1)

    with open(GOLD_FILE) as f:
        existing = json.load(f)

    check_only = "--check" in sys.argv

    existing_inputs = {c["user_input"] for c in existing}
    existing_ids = [int(c["id"].split("_")[1]) for c in existing if c["id"].startswith("ts_")]
    max_id = max(existing_ids) if existing_ids else 0

    added = 0
    for case in all_cases:
        ui = case.get("user_input", "")
        if ui and ui not in existing_inputs:
            if check_only:
                print(f"  ⚠ Not in gold file: {ui}")
                continue
            max_id += 1
            case["id"] = f"ts_{max_id:03d}"
            existing.append(case)
            added += 1

    if check_only:
        print(f"  Seed cases: {len(existing)}")
        print(f"  Extracted but not in seed: {len(all_cases) - len(existing) + len(existing_inputs & {c.get('user_input','') for c in all_cases})}")
        return

    with open(GOLD_FILE, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"✅ Dataset updated: {len(existing)} cases ({added} added)")


if __name__ == "__main__":
    main()
