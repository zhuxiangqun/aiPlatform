#!/usr/bin/env python3
"""Pi bundle / app-home delivery scan (HYBRID_ENTERPRISE_DELIVERY §2.1).

Builder path (A): run at export time → delivery_scan.json + DELIVERY_CHECKLIST.md.
FDE path (B): human signs the checklist; does not replace this scan.

Usage:
  python3 scripts/scan_pi_bundle_delivery.py --root dist/aiplat-app-<id>
  python3 scripts/scan_pi_bundle_delivery.py --root ~/.aiplat/apps/<id>/current --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".turbo",
}

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".json",
    ".md",
    ".yaml",
    ".yml",
    ".env",
    ".toml",
    ".sh",
    ".txt",
}

# (rule_id, severity, pattern, note) — severity: error blocks export when --strict
RULES: Sequence[Tuple[str, str, re.Pattern[str], str]] = (
    (
        "debug_true",
        "error",
        re.compile(r"\bdebug\s*=\s*True\b"),
        "面向客户产物禁止 debug=True",
    ),
    (
        "hardcoded_api_key",
        "error",
        re.compile(
            r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"
        ),
        "疑似明文密钥/Token 硬编码",
    ),
    (
        "openai_sk",
        "error",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "疑似 OpenAI 风格 sk- 密钥",
    ),
    (
        "localhost_hardcoded",
        "warning",
        re.compile(r"https?://(localhost|127\.0\.0\.1)(:\d+)?"),
        "本机 URL；交付包 README 可保留示例，配置文件中应改用环境变量",
    ),
    (
        "todo_customer_facing",
        "warning",
        re.compile(r"\b(TODO|FIXME|XXX)\b"),
        "临时标记；确认不对客户暴露未完成能力",
    ),
    (
        "mock_stub",
        "warning",
        re.compile(r"(?i)\b(mock[_-]?endpoint|NotImplemented|return\s+\{\s*['\"]ok['\"]\s*:\s*True\s*\}\s*#\s*stub)"),
        "疑似 mock/stub；确认非假绿端点",
    ),
)

CHECKLIST_ITEMS = [
    ("1", "调试痕迹", "无面向客户的 console.log / 裸 print / debug=True / 临时 TODO 暴露"),
    ("2", "裸环境变量", "无硬编码密钥、无明文 API Key、无客户包内必依赖的本机 localhost"),
    ("3", "假绿端点", "无 mock/stub 伪装真实能力；接线能力有真实后端响应"),
    ("4", "未接线能力", "feature-flag 掩盖的未完成功能不暴露，或明确标「预览」"),
    ("5", "标准化输出", "Agent 回复有统一结构（标题/正文/引用/异常）"),
    ("6", "异常兜底", "工具失败退回包内 SOP；失败可重试；不向用户抛栈"),
    ("7", "一键启动", "含启动说明；客户无需手搓全栈即可跑 Pi 包（企业回连按文档选配）"),
]


@dataclass
class Finding:
    rule_id: str
    severity: str
    path: str
    line: int
    snippet: str
    note: str


@dataclass
class ScanResult:
    root: str
    ok: bool
    error_count: int
    warning_count: int
    findings: List[Finding] = field(default_factory=list)
    scanned_files: int = 0
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def _iter_text_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES and p.name not in (
            ".env",
            "Dockerfile",
        ):
            continue
        # skip generated checklist itself
        if p.name in ("DELIVERY_CHECKLIST.md", "delivery_scan.json", "USAGE_BOUNDARY.md"):
            continue
        yield p


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def scan_root(root: Path) -> ScanResult:
    root = root.resolve()
    findings: List[Finding] = []
    n_files = 0
    for path in _iter_text_files(root):
        n_files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # README / docs: localhost examples are OK as warnings only already;
        # still scan for secrets.
        rel = _rel(root, path)
        for i, line in enumerate(text.splitlines(), 1):
            for rule_id, severity, pat, note in RULES:
                if rule_id == "localhost_hardcoded" and (
                    rel.endswith("README.md")
                    or "/docs/" in rel.replace("\\", "/")
                    or rel.startswith("docs/")
                ):
                    continue
                if rule_id == "todo_customer_facing" and (
                    "/tests/" in rel.replace("\\", "/")
                    or rel.endswith("_test.py")
                    or rel.endswith(".test.ts")
                ):
                    continue
                if pat.search(line):
                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=severity,
                            path=rel,
                            line=i,
                            snippet=line.strip()[:160],
                            note=note,
                        )
                    )
    err = sum(1 for f in findings if f.severity == "error")
    warn = sum(1 for f in findings if f.severity == "warning")
    return ScanResult(
        root=str(root),
        ok=err == 0,
        error_count=err,
        warning_count=warn,
        findings=findings,
        scanned_files=n_files,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def render_checklist(result: ScanResult, *, project_id: str = "") -> str:
    lines = [
        "# 出厂交付清单（A 扫描 + B 签收）",
        "",
        f"> 生成时间: {result.generated_at}  ",
        f"> 扫描根目录: `{result.root}`  ",
        f"> 项目: `{project_id or '-'}`  ",
        f"> 自动扫描: **{'PASS' if result.ok else 'FAIL'}** "
        f"(errors={result.error_count}, warnings={result.warning_count}, files={result.scanned_files})",
        "",
        "规格: `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md` §2.1",
        "",
        "## A. 自动扫描结果",
        "",
    ]
    if not result.findings:
        lines.append("- 未发现匹配规则的问题。")
    else:
        lines.append("| 级别 | 规则 | 文件:行 | 说明 |")
        lines.append("|------|------|---------|------|")
        for f in result.findings[:80]:
            lines.append(
                f"| {f.severity} | `{f.rule_id}` | `{f.path}:{f.line}` | {f.note} |"
            )
        if len(result.findings) > 80:
            lines.append(f"| … | … | … | 另有 {len(result.findings) - 80} 条见 delivery_scan.json |")
    lines.extend(
        [
            "",
            "## B. FDE / 交付负责人签收（人工）",
            "",
            "请逐项勾选后签字归档，纳入交付包。",
            "",
        ]
    )
    for num, title, desc in CHECKLIST_ITEMS:
        lines.append(f"- [ ] **{num}. {title}** — {desc}")
    lines.extend(
        [
            "",
            "### 签收",
            "",
            "| 角色 | 姓名 | 日期 | 签名 |",
            "|------|------|------|------|",
            "| Builder / 出厂 |  |  |  |",
            "| FDE / 交付负责人 |  |  |  |",
            "| 客户（可选） |  |  |  |",
            "",
            "## 企业混合补充（若启用 AIPLAT_ENTERPRISE）",
            "",
            "- [ ] KB citation V2/V3a/V6 已验收（见 HYBRID_ENTERPRISE_DELIVERY §3）",
            "- [ ] `/aiplat-status` 客户向状态可读（enterprise / tools / memory / approval）",
            "- [ ] 使用边界一页纸已交付（见 USAGE_BOUNDARY.md）",
            "",
        ]
    )
    return "\n".join(lines)


def render_usage_boundary(*, project_id: str = "") -> str:
    return f"""# 使用边界一页纸

> 项目: `{project_id or "（填写）"}`  
> 请与客户一并留存。详情见交付手册与 HYBRID_ENTERPRISE.md。

## 能做什么

- 在约定范围内使用包内 Skills / SOP 完成对话与任务
- （可选）企业回连：只读知识库检索、允许列表内工具、会话摘要回写、审批等待

## 不能做什么

- 不在 Pi 内代批审批（approve/reject 须走平台管理端）
- 不编造知识库未返回的引用或文档
- 不绕过企业模式下的原生写操作门禁（除非运维显式放行）
- 不把本机调试配置（localhost / 明文密钥）当作生产配置

## 常见问题 TOP5

1. **企业能力不可用** — 检查 `AIPLAT_ENTERPRISE=1`、PLATFORM_URL、Token
2. **工具被拒绝** — 是否在 `AIPLAT_ENTERPRISE_TOOLS` 允许列表中
3. **知识库无结果** — 回复应以「未在知识库中找到相关内容」开头；请补文档入库
4. **写文件/bash 被拦** — 企业默认门禁；副作用走 `aiplat_tool_execute` 或运维放行
5. **审批卡住** — 在平台审批 UI 处理；Pi 只等待不裁决

## 联系方式

- 技术支持：________________
- 交付 FDE：________________
"""


def write_scan_artifacts(
    root: Path,
    *,
    project_id: str = "",
    result: Optional[ScanResult] = None,
) -> ScanResult:
    root = root.resolve()
    result = result or scan_root(root)
    (root / "delivery_scan.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "DELIVERY_CHECKLIST.md").write_text(
        render_checklist(result, project_id=project_id),
        encoding="utf-8",
    )
    ub = root / "USAGE_BOUNDARY.md"
    if not ub.is_file():
        ub.write_text(render_usage_boundary(project_id=project_id), encoding="utf-8")
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Scan Pi bundle for delivery hygiene")
    ap.add_argument("--root", type=Path, required=True, help="Bundle or app-home root")
    ap.add_argument("--project-id", default="", help="Project id for checklist header")
    ap.add_argument(
        "--write",
        action="store_true",
        help="Write DELIVERY_CHECKLIST.md + delivery_scan.json (+ USAGE_BOUNDARY.md if missing)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any error-severity finding exists",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    root = args.root
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2
    result = scan_root(root)
    if args.write:
        write_scan_artifacts(root, project_id=args.project_id, result=result)
        print(f"Wrote checklist under {root}")
    print(
        json.dumps(
            {
                "ok": result.ok,
                "error_count": result.error_count,
                "warning_count": result.warning_count,
                "scanned_files": result.scanned_files,
            },
            ensure_ascii=False,
        )
    )
    if args.strict and not result.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
