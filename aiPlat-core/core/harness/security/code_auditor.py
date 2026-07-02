"""
CodeAuditor — 代码安全审计 (Phase 6)

在 Skill 生成流程中检测安全漏洞。5条规则覆盖 OWASP Top 10 的前3项。

Usage:
    auditor = CodeAuditor()
    result = auditor.audit(skill_code)
    if result.high_count > 0:
        print(f"BLOCKED: {result.high_count} critical issues")

集成点:
    - SkillSimulator.validate() — 沙盒回放后调用审计
    - AutoLearner.process_pending() — 自动审批前调用审计
"""

from __future__ import annotations

import re, time, json, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.code_auditor")


@dataclass
# disposition: internal data type — used within code auditor module
class SecurityIssue:
    rule_id: str = ""
    severity: str = ""       # "high" / "medium"
    description: str = ""
    line_snippet: str = ""   # 触发规则的代码行 (前80字符)
    suggestion: str = ""


@dataclass
# disposition: internal data type — used within code auditor module
class AuditResult:
    skill_name: str = ""
    issues: List[SecurityIssue] = field(default_factory=list)
    status: str = "pass"     # "pass" / "blocked"
    high_count: int = 0
    medium_count: int = 0
    audited_at: str = ""


# ── 白名单: 占位符模式 (不触发 S3 密钥检测) ───────────────────────────

_PLACEHOLDER_PATTERNS = [
    r"your[-_]api[-_]key", r"your[-_]secret", r"your[-_]token",
    r"your[-_]password", r"YOUR_API_KEY", r"YOUR_SECRET",
    r"<your[-_]key>", r"<YOUR_KEY>", r"placeholder",
    r"sk-xxx", r"sk-your", r"example[-_]key", r"demo[-_]key",
]

# ── 5 条安全规则 ────────────────────────────────────────────────────────

RULES = [
    # S1: SQL 注入检测
    {
        "id": "S1",
        "name": "SQL_INJECTION",
        "severity": "high",
        "patterns": [
            # f-string 拼接变量
            r'(?:f|F)["\']\s*(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b[^"\']*\{',
            r'(?:f|F)["\'].*\b(?:WHERE|SET|VALUES|JOIN)\b[^"\']*\{',
            # format/percent 拼接
            r'(?:\.format\(|%\s*)\s*.*\b(?:SELECT|INSERT|UPDATE|DELETE)\b',
            r'(?:SELECT|INSERT|UPDATE|DELETE)\b.*\.format\(',
            # sqlalchemy 不安全调用
            r'sqlalchemy\.text\s*\(\s*(?:f["\']|["\'].*\{|["\'].*\+)',
            r'\.execute\s*\(\s*(?:f["\']|["\'].*\{|["\'].*\+)',
            r'\.raw\s*\(\s*(?:f["\']|["\'].*\{|["\'].*\+)',
            # 字符串拼接构造 SQL
            r'(?:SELECT|INSERT|UPDATE|DELETE).*\s*\+\s*\w+',
            r'\w+\s*\+\s*.*\b(?:SELECT|INSERT|UPDATE|DELETE)\b',
        ],
        "suggestion": "使用参数化查询 (sqlalchemy.bindparam / ? 占位符) 替代字符串拼接构造SQL",
    },
    # S2: XSS 风险检测
    {
        "id": "S2",
        "name": "XSS_RISK",
        "severity": "high",
        "patterns": [
            r'dangerouslySetInnerHTML\s*=\s*\{',
            r'dangerouslySetInnerHTML\s*:\s*\{',
            r'v-html\s*=\s*["\']\s*\{',
            r'\.innerHTML\s*=\s*',
            r'document\.write\s*\(',
            r'\.outerHTML\s*=\s*',
            r'\.insertAdjacentHTML\s*\(',
            r'__html\s*:\s*\w+\b',
        ],
        "suggestion": "使用 React/Vue 框架默认转义 (textContent, {{ }}) 替代 innerHTML/dangerouslySetInnerHTML。如需渲染 HTML，使用 DOMPurify 过滤。",
    },
    # S3: 硬编码密钥检测
    {
        "id": "S3",
        "name": "HARDCODED_SECRET",
        "severity": "high",
        "patterns": [
            r'\bapi[_-]?key\s*=\s*["\'](?!\s*$)(?!\s*["\']\s*\))',
            r'\bpassword\s*=\s*["\'](?!\s*$)',
            r'\bsecret\s*=\s*["\'](?!\s*$)',
            r'\btoken\s*=\s*["\'](?!\s*$)',
            r'\bcredential\s*=\s*["\'](?!\s*$)',
            r'\bjwt[_-]?secret\s*=\s*["\'](?!\s*$)',
            r'\bprivate[_-]?key\s*=\s*["\'](?!\s*$)',
            r'\baccess[_-]?token\s*=\s*["\'](?!\s*$)',
            r'\bauth[_-]?token\s*=\s*["\'](?!\s*$)',
        ],
        "suggestion": "使用环境变量 (os.getenv) 或密钥管理服务存储敏感凭证，禁止硬编码在代码中",
    },
    # S4: 路径遍历检测
    {
        "id": "S4",
        "name": "PATH_TRAVERSAL",
        "severity": "medium",
        "patterns": [
            r'os\.path\.join\s*\([^)]*\b(request|user|input|query|param|body|file)',
            r'open\s*\(\s*os\.path\.join\s*\([^)]*\b(request|user|input|query|param)',
            r'Path\s*\(\s*[^)]*\{',
            r'\.\./\.\./',
            r'\.\.\\\.\.\\',
            r'shutil\.(?:copy|move|rmtree|make_archive)\s*\([^)]*\+',
        ],
        "suggestion": "使用 os.path.realpath + 白名单校验路径，或使用 pathlib 的 resolve() 防止目录穿越",
    },
    # S5: 资源泄漏检测
    {
        "id": "S5",
        "name": "RESOURCE_LEAK",
        "severity": "medium",
        "patterns": [
            # open() 不在 with 语句中，且没有 close()
            r'(?:^|\n)\s*(?!.*\bwith\b)(?!.*\bclose\(\))(?!.*finally).*open\s*\(',
            # 更简单的检测: open() 后紧跟 .read()/.write() 但没有 close
            r'open\s*\([^)]+\)\s+as\s+\w+\s*:',
        ],
        "suggestion": "使用 'with open() as f:' 上下文管理器确保文件自动关闭。对于数据库连接，使用连接池并确保在 finally 中关闭。",
    },
]


# ── 跳过模式: 注释和字符串常量中的匹配 ────────────────────────────────

def _is_in_comment_or_string(line: str, match_start: int) -> bool:
    """简单启发: 如果匹配在 # 或 \"\"\" 之后, 可能是注释/文档, 降低置信度"""
    before = line[:match_start]
    # Python 注释
    if '#' in before and '"' not in before[before.rfind('#'):]:
        return True
    # 文档字符串
    if before.count('"""') % 2 == 1:
        return True
    return False


def _matches_placeholder(line: str) -> bool:
    """检查是否匹配占位符模式 (如 'your-api-key')"""
    return any(re.search(p, line, re.IGNORECASE) for p in _PLACEHOLDER_PATTERNS)


class CodeAuditor:
    """代码安全审计器。

    对 Skill SOP body 中的代码块做安全扫描。
    高危阻断 (S1-S3), 中危记录 (S4-S5)。
    纯正则, <100ms。

    Usage:
        auditor = CodeAuditor()
        result = auditor.audit(skill_sop_body)
        if result.high_count > 0:
            return SecurityBlock(result.issues)
    """

    def __init__(self):
        self._rules = RULES

    def audit(self, code: str, *, skill_name: str = "") -> AuditResult:
        """审计一段代码 (Skill SOP body)。

        Args:
            code: 代码文本 (SKILL.md SOP body)
            skill_name: Skill 名称 (可选)

        Returns:
            AuditResult
        """
        issues = []
        lines = code.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            for rule in self._rules:
                for pattern in rule["patterns"]:
                    match = re.search(pattern, stripped)
                    if match:
                        # 跳过注释中的匹配
                        if _is_in_comment_or_string(stripped, match.start()):
                            continue
                        # S3 特殊: 跳过占位符
                        if rule["id"] == "S3" and _matches_placeholder(stripped):
                            continue

                        issues.append(SecurityIssue(
                            rule_id=rule["id"],
                            severity=rule["severity"],
                            description=f"{rule['name']}: 第{i+1}行检测到风险: {stripped[:60]}",
                            line_snippet=stripped[:80],
                            suggestion=rule["suggestion"],
                        ))
                        break  # 每行每条规则只报一次

        high = [i for i in issues if i.severity == "high"]
        medium = [i for i in issues if i.severity == "medium"]
        blocked = len(high) > 0

        if blocked:
            _log.warning(f"CodeAuditor: {skill_name} blocked — {len(high)} high, {len(medium)} medium issues")
        elif medium:
            _log.info(f"CodeAuditor: {skill_name} pass (with {len(medium)} medium notes)")

        return AuditResult(
            skill_name=skill_name,
            issues=issues,
            status="blocked" if blocked else "pass",
            high_count=len(high),
            medium_count=len(medium),
            audited_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def audit_quick(self, code: str) -> bool:
        """快速审计: 返回 True 表示通过 (0 高危)"""
        return self.audit(code).high_count == 0


# ── Global singleton ─────────────────────────────────────────────────────────


