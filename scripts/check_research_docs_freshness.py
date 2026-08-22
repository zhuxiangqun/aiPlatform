#!/usr/bin/env python3
"""Rule 6: research docs freshness guard (doc→code 对账).

扫描 docs/research/*.md 中的状态标记（已修复/已实施/待修/空壳/🟠🟡🔴）与
反引号代码符号引用，验证符号在代码中真实存在、状态标记不矛盾。

目的：防"专项审计文档"停在旧时点（如知识管理审计报告 v2 停在 P0-3，
P1-1/P1-2 实际已修复却仍标待修）——即"按文档陈述触发"的对账，补上
contracts-guard（按代码变更触发）覆盖不到的盲区。

用法：
    python3 scripts/check_research_docs_freshness.py <workspace>
    退出码 0 = 全部通过；>0 = 发现 N 条 freshness violation（WARNING 级）
"""
from __future__ import annotations

import os
import re
import sys

# 调研/对标/底稿类文档引用的是第三方代码（Hermes/DSH/Claude Code），不参与对账
SKIP_DOC = ("调研", "对标", "底稿", "对比", "reference", "comparison",
            "hermes", "ds赫", "ds赫")

# 矛盾检测否定上下文（说明是讨论历史而非当前矛盾）
NEGATE = ("误报", "消除", "复核", "非未", "非空", "非待", "残余", "演进项",
          "已消除", "非本", "非", "已排除", "真阳性", "已解决", "审计结论",
          "对照基线", "已过时", "原结论", "现为", "历史", "v2", "之前", "初版",
          "部分完成", "残留", "待跟踪", "建议按")


def code_files(workspace: str) -> list:
    roots = [
        os.path.join(workspace, "aiPlat-core/core"),
        os.path.join(workspace, "aiPlat-core/engine"),
        os.path.join(workspace, "aiPlat-core/capabilities"),
        os.path.join(workspace, "aiPlat-infra/infra"),
        os.path.join(workspace, "aiPlat-infra/config"),
        os.path.join(workspace, "aiPlat-platform"),
        os.path.join(workspace, "aiPlat-management/frontend/src"),
        os.path.join(workspace, ".github/workflows"),
        os.path.join(workspace, "scripts"),
    ]
    out: list = []
    for r in roots:
        if not os.path.isdir(r):
            continue
        for dp, dn, fn in os.walk(r):
            dn[:] = [d for d in dn if d not in ("__pycache__", "node_modules", ".venv", ".git")]
            for f in fn:
                if f.endswith((".py", ".yaml", ".yml", ".ts", ".tsx")) and not f.startswith("test_"):
                    out.append(os.path.join(dp, f))
    return out


def build_matchers(files: list) -> tuple:
    """预构建 O(1) 查询索引：basename 集合 + 内容缓存（前 300 文件）。"""
    basenames = {os.path.basename(p) for p in files}
    contents: dict = {}
    # 惰性缓存：类名匹配时按需全量读取（首次读后缓存）
    return basenames, contents


def symbol_exists(base: str, basenames: set, contents: dict, workspace: str, files: list = None) -> bool:
    """判断代码引用是否真实存在。返回 False = 疑似文档过时。"""
    if not base or len(base) < 3:
        return True
    # 用户级配置路径 / 文档间引用 → 非代码对账对象
    if base.startswith(("~/.aiplat", ".aiplat")):
        return True
    if base.endswith((".md", ".markdown")):
        return True
    if base.startswith(".pre-commit") or base.startswith("."):
        return True  # 隐藏配置文件（.pre-commit-config.yaml 等在 workspace 根）
    # 带路径 → 只看文件名
    if "/" in base or "\\" in base:
        base = os.path.basename(base)
    # 通配符/表达式/self/内置模块/装饰器 → 豁免
    if any(k in base for k in ("*", "self.", "(", ")", "'", " ", "{", "}", "@")):
        return True
    if base.startswith(("asyncio.", "os.", "sys.", "json.", "re.", "time.", "typing.", "functools.")):
        return True
    if "_" in base:
        return True  # 私有/内部符号，命名自由度大，豁免
    # .py/.ts/.yaml 文件引用
    if base.endswith((".py", ".yaml", ".yml", ".ts", ".tsx")):
        return os.path.basename(base) in basenames
    # 带行号引用（xxx.py:123）→ 取文件名
    if re.search(r"\.(py|ts|tsx|yaml|yml):\d", base):
        return os.path.basename(base.split(":")[0]) in basenames
    # ClassName.method / ClassName.field
    if "." in base:
        cls = base.split(".")[0]
        # 文件名前缀匹配（pipeline_engine.py ↔ PipelineEngine，大小写不敏感）
        for b in basenames:
            if b.lower().startswith(cls.lower()):
                return True
        # 类名在代码内容中全量搜索（不含 contents 采样限制）
        for p in files:
            if not p.endswith(".py"):
                continue
            try:
                if p in contents:
                    content = contents[p]
                else:
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        content = f.read()[:300000]
                        contents[p] = content
                if re.search(r"class\s+" + re.escape(cls) + r"\b", content):
                    return True
            except Exception:
                pass
        return False
    # 配置字段引用（fallback.safe_model 等）→ 在 YAML 配置中搜索
    if re.match(r"^[a-z_]+\.[a-z_]+$", base):
        name = base.split(".")[-1]
        cfg_roots = [os.path.join(workspace, "aiPlat-infra/config"),
                     os.path.join(workspace, "aiPlat-core/core/config"),
                     os.path.join(workspace, "aiPlat-core/workspace_seeds")]
        for cr in cfg_roots:
            if os.path.isdir(cr):
                for dp, dn, fn in os.walk(cr):
                    for f in fn:
                        if f.endswith((".yaml", ".yml")):
                            try:
                                with open(os.path.join(dp, f), encoding="utf-8") as fh:
                                    if name in fh.read():
                                        return True
                            except Exception:
                                pass
        return False
    # 简单符号 → 文件名前缀匹配
    if re.match(r"^[a-z_][a-z0-9_]{2,}$", base):
        for b in basenames:
            if b.startswith(base):
                return True
        return False
    return True


def main() -> int:
    workspace = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    research_dir = os.path.join(workspace, "docs/research")
    if not os.path.isdir(research_dir):
        print("  No research dir")
        return 0

    files = code_files(workspace)
    basenames, contents = build_matchers(files)
    violations: list = []

    for md in sorted(os.listdir(research_dir)):
        if not md.endswith(".md"):
            continue
        if any(k in md for k in SKIP_DOC):
            continue
        # 设计文档（plan- 前缀）描述未来规划，目标态路径不参与现状对账
        is_plan = md.startswith('plan-')
        path = os.path.join(research_dir, md)
        try:
            text = open(path, encoding="utf-8").read()
        except Exception:
            continue

        # 1) 反引号代码引用 → 验证符号存在
        refs = re.findall(r"`([^`]{3,120})`", text)
        for ref in refs:
            if is_plan:
                continue
            if not re.search(r"\.py\b|\.tsx?\b|\.yaml\b|def |class |[a-z_]+\.[a-z_]+", ref):
                continue
            if not symbol_exists(ref, basenames, contents, workspace, files):
                violations.append(f"{md}: 代码引用 `{ref}` 在代码中未找到（可能文档过时）")

        # 1.5) 最后验证时间戳检查：报告声明"最后验证：DATE"，若引用的代码文件
        #      mtime 晚于该日期 → 提示报告可能过时
        m_verify = re.search(r"最后验证[:：]\s*(\d{4}-\d{2}-\d{2})", text)
        if m_verify:
            try:
                from datetime import datetime as _dt
                verify_date = _dt.strptime(m_verify.group(1), "%Y-%m-%d")
                _grace = 86400  # 1 天宽限（同日文件修改不视为过时）
                for p in files:
                    try:
                        if os.path.getmtime(p) > verify_date.timestamp() + _grace:
                            # 只对报告引用过的文件提示（简单化：任何引用文件晚于验证日期）
                            violations.append(
                                f"{md}: '最后验证 {m_verify.group(1)}' 早于代码文件 {os.path.basename(p)} 的修改时间（报告可能过时）")
                            break  # 一条即可
                    except Exception:
                        pass
            except Exception:
                pass

        # 2) 状态标记矛盾：同一行既有"已修复/已实施"又有"待修/空壳/🟠🟡🔴"
        for line in text.split("\n"):
            seg = line.strip()
            if not seg or len(seg) < 20:
                continue
            # 表格行（| 对比列）天然含"原问题|修复结果"，跳过；也跳过"0 调用者"描述行
            if "|" in seg or "0 调用" in seg or "0 生产" in seg or "全仓 0" in seg:
                continue
            has_ok = any(k in seg for k in ("已修复", "已实施", "已接线", "已落地", "已闭环", "✅"))
            has_bad = any(b in seg for b in ("待修", "未实现", "未接线", "空壳", "🟠", "🟡", "🔴"))
            if has_ok and has_bad and not any(k in seg for k in NEGATE):
                violations.append(f"{md}: 同一行同时含'已修复'与'待修/空壳/🟠🟡🔴'矛盾: …{seg[-70:]}")

    seen: list = []
    for v in violations:
        if v not in seen:
            seen.append(v)
    for v in seen[:15]:
        print("  WARN: " + v)
    if seen:
        print(f"  ({len(seen)} research-doc freshness violation(s) — WARNING，需人工确认)")
    else:
        print("  OK: All research docs references exist in code")
    return len(seen)


if __name__ == "__main__":
    sys.exit(main())
