#!/usr/bin/env python3
"""
aiPlat 文档系统治理验证脚本

验证规则（基于 docs/DOCUMENT_SYSTEM.md）：
1. (阻断) docs/by-role/ 下所有 .md 文件的相对链接必须可解析
2. (阻断) docs/reports/ 下所有 .md 必须包含"不手动编辑"头部声明
3. (阻断) docs/archive/README.md 必须包含"仅做历史参考"免责声明
4. (告警) AIPLAT_CAPABILITIES.md 以外的文件不应硬编码当前能力数
5. (告警) 检测是否存在重复的"唯一真相源"声明

退出码：
  0: 全部通过（仅有告警）
  1: 阻断性错误
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).parent.parent.absolute()
DOCS_ROOT = REPO_ROOT / "docs"
ROLE_DIR = DOCS_ROOT / "by-role"
REPORTS_DIR = DOCS_ROOT / "reports"
ARCHIVE_README = DOCS_ROOT / "archive" / "README.md"
CAPABILITIES_FILE = REPO_ROOT / "AIPLAT_CAPABILITIES.md"

errors: List[str] = []
warnings: List[str] = []

# ── 可配置阈值（源自 DOCUMENT_SYSTEM.md §十一 配置清单） ──
DESIGN_STALE_DAYS = int(os.environ.get("AIPLAT_DOC_DESIGN_STALE_DAYS", "90"))
DRAFT_EXPIRY_DAYS = int(os.environ.get("AIPLAT_DOC_DRAFT_EXPIRY_DAYS", "180"))


def log_error(msg: str) -> None:
    errors.append(f"\u274c {msg}")
    print(f"[ERROR] {msg}")


def log_warning(msg: str) -> None:
    warnings.append(f"\u26a0\ufe0f {msg}")
    print(f"[WARN] {msg}")


# ── 检查 1：by-role 链接有效性（阻断） ──
def check_role_links() -> None:
    if not ROLE_DIR.exists():
        log_warning(f"by-role 目录不存在: {ROLE_DIR}")
        return

    md_files = list(ROLE_DIR.glob("**/*.md"))
    if not md_files:
        log_warning(f"by-role/ 下无 .md 文件")
        return

    link_pattern = re.compile(r'\[.*?\]\((?!https?://)([^)]+)\)')

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        rel_dir = md_file.parent

        for match in link_pattern.finditer(content):
            raw_path = match.group(1)
            if '#' in raw_path:
                target_path = raw_path.split('#')[0]
            else:
                target_path = raw_path

            if not target_path:
                continue

            abs_target = (rel_dir / target_path).resolve()
            try:
                abs_target.relative_to(REPO_ROOT)
            except ValueError:
                log_error(f"{md_file.relative_to(REPO_ROOT)} 链接指向仓库外: {raw_path}")
                continue

            if not abs_target.exists():
                log_error(f"{md_file.relative_to(REPO_ROOT)} 链接损坏: {raw_path}")


# ── 检查 2：报告头部声明（阻断） ──
def check_report_headers() -> None:
    if not REPORTS_DIR.exists():
        log_warning(f"reports 目录不存在: {REPORTS_DIR}")
        return

    md_files = list(REPORTS_DIR.glob("*.md"))
    if not md_files:
        return

    required = ["不手动编辑", "生成时间"]
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        found = all(phrase in content for phrase in required)
        if not found:
            log_error(f"{md_file.relative_to(REPO_ROOT)} 缺少报告头部声明（须包含: {required}）")


# ── 检查 3：归档免责声明（阻断） ──
def check_archive_disclaimer() -> None:
    if not ARCHIVE_README.exists():
        log_error(f"归档说明文件缺失: {ARCHIVE_README.relative_to(REPO_ROOT)}")
        return

    content = ARCHIVE_README.read_text(encoding="utf-8")
    if "\u4ec5\u505a\u5386\u53f2\u53c2\u8003" not in content:
        log_error(f"{ARCHIVE_README.relative_to(REPO_ROOT)} 必须包含 \"\u4ec5\u505a\u5386\u53f2\u53c2\u8003\" 声明")


# ── 检查 4：数字硬编码（告警） ──
def check_hardcoded_numbers() -> None:
    if not CAPABILITIES_FILE.exists():
        log_warning("能力清单文件不存在，跳过硬编码检查")
        return

    content = CAPABILITIES_FILE.read_text(encoding="utf-8")
    current_count = content.count("\u2705")
    if current_count == 0:
        log_warning("能力清单中未检测到 \u2705 标记")
        return

    all_md = list(REPO_ROOT.glob("**/*.md"))
    excluded = {CAPABILITIES_FILE.resolve()}
    target_files = [f for f in all_md
                    if f.resolve() not in excluded
                    and "node_modules" not in str(f)
                    and ".venv" not in str(f)
                    and "__pycache__" not in str(f)]

    pattern = re.compile(rf'\b{current_count}\b')
    for md_file in target_files:
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if not pattern.search(text):
            continue

        lines = text.splitlines()
        for line in lines:
            if pattern.search(line):
                if "CAPABILITIES" not in line and "\u51fa\u5904" not in line and "\u5f15\u7528" not in line:
                    rel = md_file.relative_to(REPO_ROOT)
                    log_warning(f"{rel} 中裸写了数字 {current_count}，应引用 CAPABILITIES.md 而非硬编码")
                    break


# ── 检查 5：重复的"唯一真相源"声明（告警） ──
def check_duplicate_authority() -> None:
    if not DOCS_ROOT.exists():
        return

    patterns = [r"\u552f\u4e00\u771f\u76f8\u6e90", r"\u552f\u4e00\u51fa\u5904",
                r"single source of truth"]
    combined = re.compile('|'.join(patterns), re.IGNORECASE)

    allowed = {
        DOCS_ROOT / "DOCUMENT_SYSTEM.md",
        DOCS_ROOT / "architecture" / "overview.md",
        REPO_ROOT / "AIPLAT_CAPABILITIES.md",
    }

    md_files = list(DOCS_ROOT.glob("**/*.md"))
    for md_file in md_files:
        if md_file.resolve() in {p.resolve() for p in allowed}:
            continue
        if "archive" in md_file.parts:
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if combined.search(text):
            rel = md_file.relative_to(REPO_ROOT)
            log_warning(f"{rel} 中出现了\"唯一真相源\"类声明，未被列入权威白名单")


# ── 检查 6：架构重叠检测（告警） ──
def check_architecture_duplication() -> None:
    """检查 docs/architecture/ 是否重复了 private-control-plane.md 的核心内容。"""
    pcp_path = DOCS_ROOT / "articles" / "private-control-plane.md"
    if not pcp_path.exists():
        return

    # 核心控制平面模块关键词
    key_modules = ["ErrorTranslator", "PolicyGate", "ApprovalGate", "SkillsGuard",
                   "TrendDetector", "FeedbackTranslator"]
    arch_dir = DOCS_ROOT / "architecture"
    if not arch_dir.exists():
        return

    for md_file in arch_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for mod in key_modules:
            if mod in content and "private-control-plane" not in content:
                rel = md_file.relative_to(REPO_ROOT)
                log_warning(f"{rel} 中描述了 {mod}，但未引用 private-control-plane.md（可能内容重复）")
                break


# ── 检查 7：设计文档时效性（告警） ──
def check_design_freshness() -> None:
    """检查 docs/design/ 下的文件是否超过了 DESIGN_STALE_DAYS 未更新。"""
    design_dir = DOCS_ROOT / "design"
    if not design_dir.exists():
        return

    now = time.time()
    for md_file in design_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # 检查 frontmatter 中的 last_synced 或 最后更新 日期
        import re as _re
        # 格式：last_synced: 2026-07-04 或 最后更新: 2026-07-04
        match = _re.search(r'(?:last_synced|最后更新)[:：]\s*(\d{4}-\d{2}-\d{2})', content)
        if not match:
            rel = md_file.relative_to(REPO_ROOT)
            log_warning(f"{rel} 缺少 'last_synced' 或 '最后更新' 日期声明")
            continue

        date_str = match.group(1)
        try:
            from datetime import datetime
            doc_date = datetime.strptime(date_str, "%Y-%m-%d")
            doc_ts = doc_date.timestamp()
        except ValueError:
            continue

        age_days = (now - doc_ts) / 86400
        if age_days > DESIGN_STALE_DAYS:
            rel = md_file.relative_to(REPO_ROOT)
            log_warning(f"{rel} 已超过 {DESIGN_STALE_DAYS} 天未更新（最后: {date_str}，距今 {age_days:.0f} 天）")


# ── 检查 8：骨架占位过期（告警） ──
def check_draft_expiry() -> None:
    """检查所有 .md 文件中标记为 status: draft 的文档是否超过 DRAFT_EXPIRY_DAYS。"""
    now = time.time()
    import re as _re

    for md_file in REPO_ROOT.glob("**/*.md"):
        if "archive" in md_file.parts or "__pycache__" in md_file.parts:
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Only check YAML frontmatter (between first and second ---)
        lines = content.split("\n")
        if len(lines) < 3 or lines[0].strip() != "---":
            continue
        # Find closing ---
        fm_end = -1
        for i in range(1, min(len(lines), 20)):
            if lines[i].strip() == "---":
                fm_end = i
                break
        if fm_end < 0:
            continue
        frontmatter = "\n".join(lines[1:fm_end])

        if "status: draft" not in frontmatter and "status:draft" not in frontmatter:
            continue

        match = _re.search(r'draft_date[:：]\s*(\d{4}-\d{2}-\d{2})', frontmatter)
        if not match:
            rel = md_file.relative_to(REPO_ROOT)
            log_warning(f"{rel} 标记为 draft 但缺少 'draft_date' 声明")
            continue

        date_str = match.group(1)
        try:
            from datetime import datetime
            draft_date = datetime.strptime(date_str, "%Y-%m-%d")
            draft_ts = draft_date.timestamp()
        except ValueError:
            continue

        age_days = (now - draft_ts) / 86400
        if age_days > DRAFT_EXPIRY_DAYS:
            rel = md_file.relative_to(REPO_ROOT)
            log_warning(f"{rel} 标记为 draft 已超过 {DRAFT_EXPIRY_DAYS} 天（draft_date: {date_str}，距今 {age_days:.0f} 天）— 建议归档或删除")


# ── 检查 9：代码引用验证（告警） ──
def check_code_references() -> None:
    """
    Verify that `file:line` references in CAPABILITIES.md point to existing code.
    Pattern: `path/to/file.py` or `path/to/file.py:123`
    """
    if not CAPABILITIES_FILE.exists():
        return

    content = CAPABILITIES_FILE.read_text(encoding="utf-8")
    # Match code references: `some/path.py` or `some/path.py:42`
    refs = re.findall(r'`([a-zA-Z0-9_/.-]+\.py)(?::(\d+))?`', content)
    broken = 0
    for match in refs:
        file_path = match[0]
        line_num = match[1] if len(match) > 1 and match[1] else None
        found = False
        # Handle platform/ prefixed paths — search directly under aiPlat-platform
        prefix_map = {"platform": "aiPlat-platform", "management": "aiPlat-management",
                      "infra": "aiPlat-infra", "app": "aiPlat-app"}
        for prefix, base in prefix_map.items():
            if file_path.startswith(f"{prefix}/"):
                full = REPO_ROOT / base / file_path[len(prefix) + 1:]
                if full.exists():
                    found = True
                    break
        if found:
            break

        # Search bases in order: sub-project directories
        for base in ["aiPlat-core", "aiPlat-infra", "aiPlat-platform", "aiPlat-management", "aiPlat-app"]:
            full = REPO_ROOT / base / "core" / file_path
            if full.exists():
                found = True
                break
            full = REPO_ROOT / base / file_path
            if full.exists():
                found = True
                break
        # For bare filenames (no path prefix), do a recursive search
        if not found and "/" not in file_path and ".." not in file_path:
            matches = list(REPO_ROOT.glob(f"**/{file_path}"))
            found = any("__pycache__" not in str(m) for m in matches)
        if not found:
            # Try root-level
            if (REPO_ROOT / file_path).exists():
                found = True
        if not found:
            log_warning(f"CAPABILITIES 引用文件不存在: {file_path}")
            broken += 1
            if broken >= 10:
                break


# ── 检查 10：环境变量声明检测（告警） ──
def check_undocumented_env_vars() -> None:
    """
    Check that all AIPLAT_* environment variables used in code are documented.
    Opt-in: requires AIPLAT_DOC_CHECK_ENV=1 to run (avoids noisy first-run on legacy code).
    """
    if os.environ.get("AIPLAT_DOC_CHECK_ENV", "0") != "1":
        return

    known_envs = set()
    for doc_path in [DOCS_ROOT / "DOCUMENT_SYSTEM.md",
                     DOCS_ROOT / "articles" / "private-control-plane.md"]:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8")
        known_envs.update(re.findall(r'`(AIPLAT_[A-Z_]+)`', text))

    if not known_envs:
        return

    code_envs = set()
    for py_file in REPO_ROOT.glob("aiPlat-core/core/**/*.py"):
        if "__pycache__" in str(py_file) or "/tests/" in str(py_file):
            continue
        try:
            for line in py_file.read_text(encoding="utf-8").split("\n")[:200]:
                match = re.search(r'getenv\(["\'](AIPLAT_[A-Z_]+)', line)
                if match:
                    code_envs.add(match.group(1))
        except Exception:
            continue

    missing = sorted(code_envs - known_envs)
    capped = 20
    for env in missing[:capped]:
        log_warning(f"环境变量 {env} 在代码中使用但未在文档中声明")
    if len(missing) > capped:
        log_warning(f"... 还有 {len(missing) - capped} 个未声明的环境变量（设置 AIPLAT_DOC_CHECK_ENV=1 查看全部）")


# ── 检查 11：git diff 新增 public API 登记（BLOCK after grace period）──

def check_new_public_api() -> None:
    """
    Detect newly added public functions/classes/endpoints in recent .py changes
    that are NOT yet registered in CAPABILITIES.md.

    Before grace period: WARN
    After grace period: BLOCK (exit 1)
    """
    import subprocess
    from datetime import datetime
    caps_text = CAPABILITIES_FILE.read_text(encoding="utf-8") if CAPABILITIES_FILE.exists() else ""
    blocking = datetime.now().strftime("%Y-%m-%d") >= HARDCODE_GRACE_END

    # Get recently changed .py files (last commit)
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "HEAD~1", "--name-only", "--diff-filter=AM"],
            capture_output=True, text=True, timeout=10,
        )
        changed_files = [f.strip() for f in result.stdout.split("\n") if f.endswith(".py")]
    except Exception:
        return

    if not changed_files:
        return

    # Build a template mapping: file path → suggested CAPABILITIES section
    section_hints = {
        "api/routers/": ("二十三", "核心API统一入口"),
        "api/core_facade.py": ("二十三", "核心API统一入口"),
        "harness/": ("一", "Harness 执行引擎"),
        "apps/": ("应用", "对应模块"),
    }

    unregistered = 0
    for fpath in changed_files:
        full_path = REPO_ROOT / fpath
        if not full_path.exists():
            continue
        if "/tests/" in str(full_path) or "__pycache__" in str(full_path):
            continue

        try:
            result = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "diff", "HEAD~1", "--", fpath],
                capture_output=True, text=True, timeout=10,
            )
            diff_lines = result.stdout.split("\n")
        except Exception:
            continue

        import re
        new_symbols = set()
        for line in diff_lines:
            if not line.startswith("+"):
                continue
            if line.startswith("+++"):
                continue
            m = re.match(r'^\+\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', line)
            if m and not m.group(1).startswith("_"):
                new_symbols.add(m.group(1))
            m = re.match(r'^\+\s*class\s+([A-Z][a-zA-Z0-9_]*)', line)
            if m:
                new_symbols.add(m.group(1))
            if '@router.' in line:
                endpoint_match = re.search(r'@router\.(get|post|put|delete|patch)\("([^"]+)"', line)
                if endpoint_match:
                    new_symbols.add(f"endpoint:{endpoint_match.group(2)}")

        if not new_symbols:
            continue

        # Find matching section for this file
        section_hint = ("未知", "")
        for prefix, (sec, name) in section_hints.items():
            if fpath.startswith(prefix):
                section_hint = (sec, name)
                break

        for sym in sorted(new_symbols):
            if sym in ("__init__", "__post_init__", "main", "router", "to_dict", "from_dict",
                        "get_stats", "to_json", "from_json", "validate", "to_select_star"):
                continue
            if sym not in caps_text:
                rel = full_path.relative_to(REPO_ROOT)
                # Build registration template
                if sym.startswith("endpoint:"):
                    ep = sym.replace("endpoint:", "")
                    template = f'| {ep} | `{rel}` | ✅ | <描述> | 2026-{datetime.now().strftime("%m-%d")} |'
                else:
                    template = f'| {sym} | `{rel}` | ✅ | <描述> | 2026-{datetime.now().strftime("%m-%d")} |'
                msg = (
                    f"{rel} 新增了 '{sym}' 但未在 CAPABILITIES 中登记 → "
                    f"请在 §{section_hint[0]} {section_hint[1]} 追加: {template}"
                )
                if blocking:
                    log_error(f"BLOCK: {msg}")
                else:
                    log_warning(msg)
                unregistered += 1
                if unregistered >= 10:
                    break

        if unregistered >= 10:
            break


# ── R13: Route validity — doc API routes vs code router registrations (WARN) ──
def check_route_validity() -> None:
    """Check that /api/* routes referenced in docs actually exist in code routers."""
    import importlib, pkgutil
    # Collect all registered routes from code
    code_routes = set()
    try:
        sys.path.insert(0, str(REPO_ROOT / "aiPlat-core"))
        from core.api.routers.system import router as sys_router
        code_routes.update(f"/api/core{route.path}" for route in sys_router.routes if hasattr(route, 'path'))
    except Exception:
        pass  # router not available, skip

    # Scan docs for /api/* references (but NOT in code blocks)
    for md_file in DOCS_ROOT.glob("**/*.md"):
        if "_archive" in str(md_file):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            # Find API routes in regular text (not backtick-quoted)
            routes = re.findall(r'`(/api/(?:core|platform|infra|app)/[a-zA-Z0-9_/-]+)`', text)
            for route in routes:
                if code_routes and route not in code_routes:
                    log_warning(f"{md_file.relative_to(REPO_ROOT)} 引用了未注册路由: {route}")
        except Exception:
            continue


# ── R14: Menu path residual — detect old menu nav patterns (WARN) ──
def check_menu_paths() -> None:
    """Detect old-style menu path patterns (→) in docs that should use stable URLs."""
    # Know to skip design docs (describe intent, not state)
    design_dirs = {str(DOCS_ROOT / "design"), str(DOCS_ROOT / "architecture")}
    for md_file in DOCS_ROOT.glob("**/*.md"):
        if "_archive" in str(md_file) or any(str(md_file).startswith(d) for d in design_dirs):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            # Detect patterns like "XX → YY → ZZ" or "XX组 → YY页面"
            menu_patterns = re.findall(r'[A-Z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff ]+ → [A-Za-z\u4e00-\u9fff /]+', text)
            if menu_patterns:
                rel = md_file.relative_to(REPO_ROOT)
                log_warning(f"{rel} 包含菜单导航路径（建议用稳定路由替代）: {menu_patterns[0][:60]}")
        except Exception:
            continue


# ── R15: Hardcoded capability numbers — BLOCK after grace period ──
HARDCODE_GRACE_END = "2026-08-20"  # 30-day grace from 2026-07-20

def check_hardcoded_numbers_blocking() -> None:
    """After grace period, bare capability counts (700-999 range) in non-CAPABILITIES files → BLOCK."""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d")
    if now < HARDCODE_GRACE_END:
        return  # still in grace period

    cap_count = 0
    if CAPABILITIES_FILE.exists():
        m = re.search(r'\*\*(\d+)\*\*', CAPABILITIES_FILE.read_text(encoding="utf-8")[:2000])
        if m:
            cap_count = int(m.group(1))

    if not cap_count:
        return

    for md_file in DOCS_ROOT.glob("**/*.md"):
        if "_archive" in str(md_file) or "AIPLAT_CAPABILITIES.md" in str(md_file):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            bare = re.findall(r'(?<!\*)(?<!\`)(?<!\#)(?<!见 AIPLAT_CAPABILITIES\.md 当前计数[）)])' +
                              r'(?:[7-9]\d\d)(?!\d)(?![\*`])', text)
            for num in bare:
                if 700 <= int(num) <= 999:
                    rel = md_file.relative_to(REPO_ROOT)
                    log_error(f"BLOCK: {rel} 中硬编码了能力数 {num}（30天宽限期已过，必须改为引用格式）")
        except Exception:
            continue


def check_stale_descriptions() -> None:
    """R16: Compare CAPABILITIES code references (file:line) against actual code.

    Uses a heuristic: if the referenced line is in the first 5% of a large file (>300 lines),
    the code has likely shifted and the reference may be stale.
    """
    if not CAPABILITIES_FILE.exists():
        return

    content = CAPABILITIES_FILE.read_text(encoding="utf-8")
    refs = re.findall(r'`([a-zA-Z0-9_/.-]+\.py):(\d+)`', content)
    stale = 0
    for file_path, line_str in refs:
        try:
            line_num = int(line_str)
        except ValueError:
            continue
        resolved = None
        for base in ["aiPlat-core", "aiPlat-infra", "aiPlat-platform", "aiPlat-management", "aiPlat-app"]:
            for sub in ["core/", ""]:
                candidate = REPO_ROOT / base / sub / file_path
                if candidate.exists():
                    resolved = candidate
                    break
            if resolved:
                break
        if not resolved:
            candidate = REPO_ROOT / file_path
            if candidate.exists():
                resolved = candidate

        if not resolved:
            continue

        try:
            current_lines = len(resolved.read_text(encoding="utf-8").split("\n"))
        except Exception:
            continue

        # Heuristic: if line is in first 5% of file AND file > 300 lines, likely stale
        ratio = line_num / max(current_lines, 1)
        if current_lines > 300 and ratio < 0.05:
            rel = resolved.relative_to(REPO_ROOT)
            log_warning(
                f"CAPABILITIES 引用 {file_path}:{line_num} 可能过时 — "
                f"行号在文件开头 {ratio:.1%} 处（{current_lines} 行），代码可能已下移"
            )
            stale += 1
            if stale >= 5:
                break


def check_claude_debt_verification() -> None:
    """Verify every '✅ 已修复' claim in CLAUDE.md §16 has a grep verification command.

    Per §0.4: marking as 'resolved' MUST include executable evidence (grep/bash/pytest).
    """
    claude_md = REPO_ROOT / "CLAUDE.md"
    if not claude_md.exists():
        errors.append("CLAUDE.md 不存在，无法验证 §16 债务条目")
        return

    content = claude_md.read_text(encoding="utf-8")

    # Locate §16 section
    m = re.search(r'(?:###?\s*)?16[.\s、].*已知例外.*债务', content)
    if not m:
        return

    section_start = m.start()
    next_sec = re.search(r'\n(?:##|#)\s+\d+[.\s、]', content[section_start + 1:])
    section_text = content[section_start:section_start + 1 + (next_sec.start() if next_sec else 0)]

    # Find all '✅ 已修复' rows
    fixed = re.finditer(
        r'\|\s*([A-Z]+)\s*\|[^|]*\|([^|]*)\|.*?✅\s*已修复',
        section_text, re.MULTILINE
    )
    verify_pat = re.compile(r'验证[：:]\s*(?:grep|bash|pytest|python|find|ls)')

    for match in fixed:
        eid = match.group(1).strip()
        desc = match.group(2).strip()[:60]
        ctx = section_text[match.end():match.end() + 500]
        if not verify_pat.search(ctx):
            errors.append(
                f"CLAUDE.md §16 条目 {eid}（{desc}）标记为 '✅ 已修复' "
                f"但缺少 grep/验证命令（违反 §0.4）"
            )


def main():
    print(f"\U0001f50d 文档系统验证开始 (REPO_ROOT: {REPO_ROOT})")
    print("=" * 60)

    check_role_links()
    check_report_headers()
    check_archive_disclaimer()
    check_hardcoded_numbers()
    check_duplicate_authority()
    check_architecture_duplication()
    check_design_freshness()
    check_draft_expiry()
    check_code_references()
    check_undocumented_env_vars()
    check_new_public_api()

    # ── R13: Route validity — doc API routes vs code router registrations ──
    check_route_validity()

    # ── R14: Menu path residual — detect old menu navigation patterns ──
    check_menu_paths()

    # ── R15: Promote bare number to BLOCK (30-day grace) ──
    check_hardcoded_numbers_blocking()

    # ── Rule 16: Stale description detection (line number drift) ──
    check_stale_descriptions()

    # ── Rule 12: CLAUDE.md §16 debt verification (§0.4 mandatory grep evidence) ──
    check_claude_debt_verification()

    print("=" * 60)
    if errors:
        print(f"\u274c 阻断性错误: {len(errors)} 个")
        for e in errors:
            print(f"  {e}")
        print(f"\u26a0\ufe0f 告警: {len(warnings)} 个（不阻断）")
        sys.exit(1)
    elif warnings:
        print(f"\u26a0\ufe0f 告警: {len(warnings)} 个（不阻断）")
        for w in warnings:
            print(f"  {w}")
        sys.exit(0)
    else:
        print("\u2705 所有验证通过！文档系统健康。")
        sys.exit(0)


if __name__ == "__main__":
    main()
