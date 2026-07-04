"""
SkillsGuard — 70+ threat pattern scanner for Skill/Tool security audit.

Scans SKILL.md frontmatter and Python handler files for dangerous patterns
before registration. Integrated into SkillRegistry.register() and PolicyGate.

hermes-agent parity: tools/skills_guard.py — threat pattern scanner + audit
"""
from __future__ import annotations

import ast
import fnmatch
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class ThreatLevel(Enum):
    BLOCKER = "blocker"   # Must block registration
    CRITICAL = "critical"  # Must block + alert admin
    HIGH = "high"          # Reject unless approved
    MEDIUM = "medium"      # Warning only
    LOW = "low"            # Informational


class ThreatCategory(Enum):
    CODE_INJECTION = "code_injection"
    COMMAND_EXECUTION = "command_execution"
    FILE_SYSTEM = "file_system"
    NETWORK = "network"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    PROMPT_INJECTION = "prompt_injection"
    MALICIOUS_IMPORT = "malicious_import"
    SECRET_EXPOSURE = "secret_exposure"
    RESOURCE_ABUSE = "resource_abuse"
    EVASION = "evasion"
    INSTALLER_MANIPULATION = "installer_manipulation"


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class ThreatRule:
    """A single threat detection rule."""
    rule_id: str
    category: ThreatCategory
    level: ThreatLevel
    pattern: str  # regex or glob pattern
    description: str
    scan_target: str = "code"  # "code" | "frontmatter" | "all"
    file_pattern: str = "*.py"  # glob for which files to scan


@dataclass
class ThreatFinding:
    """A single detected threat."""
    rule_id: str
    category: ThreatCategory
    level: ThreatLevel
    file_path: str
    line_number: int
    matched_text: str
    description: str
    recommendation: str = ""


@dataclass
class ScanResult:
    """Result of a full skill scan."""
    skill_name: str
    passed: bool
    findings: List[ThreatFinding] = field(default_factory=list)
    blocker_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    warnings: List[str] = field(default_factory=list)


# ── Threat Pattern Catalogue (70+ patterns) ──────────────────────────────────

_THREAT_RULES: List[ThreatRule] = [
    # ═══ CODE INJECTION (8 patterns) ═══
    ThreatRule("inj_eval", ThreatCategory.CODE_INJECTION, ThreatLevel.BLOCKER,
               r"\beval\s*\(", "eval() usage — arbitrary code execution", "code", "*.py"),
    ThreatRule("inj_exec", ThreatCategory.CODE_INJECTION, ThreatLevel.BLOCKER,
               r"\bexec\s*\(", "exec() usage — arbitrary code execution", "code", "*.py"),
    ThreatRule("inj_compile_code", ThreatCategory.CODE_INJECTION, ThreatLevel.BLOCKER,
               r"\bcompile\s*\(.*mode\s*=\s*['\"]exec['\"]", "compile() with exec mode", "code", "*.py"),
    ThreatRule("inj_pickle", ThreatCategory.CODE_INJECTION, ThreatLevel.HIGH,
               r"\bpickle\.(loads?|dump)", "Pickle deserialization — arbitrary code execution risk", "code", "*.py"),
    ThreatRule("inj_marshal", ThreatCategory.CODE_INJECTION, ThreatLevel.HIGH,
               r"\bmarshal\.(loads?|dump)", "Marshal deserialization — unsafe", "code", "*.py"),
    ThreatRule("inj_yaml_unsafe", ThreatCategory.CODE_INJECTION, ThreatLevel.HIGH,
               r"\byaml\.load\s*(?![_s])", "Unsafe yaml.load() — use yaml.safe_load()", "code", "*.py"),
    ThreatRule("inj_template_injection", ThreatCategory.CODE_INJECTION, ThreatLevel.HIGH,
               r"Template\s*\(.*\{", "String formatting in template — potential SSTI", "code", "*.py"),
    ThreatRule("inj_regex_dos", ThreatCategory.CODE_INJECTION, ThreatLevel.MEDIUM,
               r"re\.(compile|search|match).*\(.*\)\(?P?<.+?>\).*\)\s*\+", "Potential ReDoS pattern", "code", "*.py"),

    # ═══ COMMAND EXECUTION (8 patterns) ═══
    ThreatRule("cmd_subprocess_shell", ThreatCategory.COMMAND_EXECUTION, ThreatLevel.BLOCKER,
               r"\bsubprocess\.(run|call|Popen|check_output)\(.*shell\s*=\s*True", "Shell=True — command injection risk", "code", "*.py"),
    ThreatRule("cmd_os_system", ThreatCategory.COMMAND_EXECUTION, ThreatLevel.BLOCKER,
               r"\bos\.system\s*\(", "os.system() — command injection risk", "code", "*.py"),
    ThreatRule("cmd_os_popen", ThreatCategory.COMMAND_EXECUTION, ThreatLevel.HIGH,
               r"\bos\.popen\s*\(", "os.popen() — command injection risk", "code", "*.py"),
    ThreatRule("cmd_pty_spawn", ThreatCategory.COMMAND_EXECUTION, ThreatLevel.HIGH,
               r"\bpty\.spawn\s*\(", "pty.spawn() — terminal emulation", "code", "*.py"),
    ThreatRule("cmd_rm_rf", ThreatCategory.COMMAND_EXECUTION, ThreatLevel.CRITICAL,
               r"rm\s+-rf\s+[/~]", "rm -rf on root/home — irreversible destruction", "code", "*.md"),
    ThreatRule("cmd_chmod_777", ThreatCategory.COMMAND_EXECUTION, ThreatLevel.CRITICAL,
               r"chmod\s+(777|a\+rwx|ugo\+rwx)", "World-writable permission — security risk", "code", "*.md"),
    ThreatRule("cmd_pipe_curl_bash", ThreatCategory.COMMAND_EXECUTION, ThreatLevel.CRITICAL,
               r"curl\s+.*\|\s*(bash|sh|zsh)", "curl piped to shell — remote code execution", "code", "*.md"),
    ThreatRule("cmd_systemctl_disable", ThreatCategory.COMMAND_EXECUTION, ThreatLevel.HIGH,
               r"systemctl\s+(disable|mask)\s+", "Disabling system services", "code", "*.md"),

    # ═══ FILE SYSTEM (12 patterns) ═══
    ThreatRule("fs_write_etc", ThreatCategory.FILE_SYSTEM, ThreatLevel.CRITICAL,
               r"['\"](/etc/|/var/|/usr/|/bin/|/sbin/|/boot/)", "Writing to system directory", "code", "*.py"),
    ThreatRule("fs_remove_home", ThreatCategory.FILE_SYSTEM, ThreatLevel.CRITICAL,
               r"(os\.remove|os\.unlink|shutil\.rmtree)\s*\(.*['\"]~?/", "Deleting files in user home", "code", "*.py"),
    ThreatRule("fs_chmod", ThreatCategory.FILE_SYSTEM, ThreatLevel.HIGH,
               r"\bos\.chmod\s*\(", "Changing file permissions", "code", "*.py"),
    ThreatRule("fs_chown", ThreatCategory.FILE_SYSTEM, ThreatLevel.HIGH,
               r"\bos\.chown\s*\(", "Changing file ownership", "code", "*.py"),
    ThreatRule("fs_symlink", ThreatCategory.FILE_SYSTEM, ThreatLevel.HIGH,
               r"\bos\.symlink\s*\(", "Creating symlinks — potential privilege escalation", "code", "*.py"),
    ThreatRule("fs_path_traversal", ThreatCategory.FILE_SYSTEM, ThreatLevel.HIGH,
               r"\.\./\.\./(\.\./)+", "Path traversal pattern", "code", "*.py"),
    ThreatRule("fs_env_file", ThreatCategory.FILE_SYSTEM, ThreatLevel.CRITICAL,
               r"\.env[.']|\.env$", "Accessing .env file — credential exposure", "code", "*.py"),
    ThreatRule("fs_cert_file", ThreatCategory.FILE_SYSTEM, ThreatLevel.HIGH,
               r"\.(pem|crt|key|pkcs12|pfx)[\"'$]", "Accessing certificate/key file", "code", "*.py"),
    ThreatRule("fs_ssh_key", ThreatCategory.FILE_SYSTEM, ThreatLevel.CRITICAL,
               r"\.ssh/id_|authorized_keys", "Accessing SSH keys", "code", "*.py"),
    ThreatRule("fs_config_overwrite", ThreatCategory.FILE_SYSTEM, ThreatLevel.HIGH,
               r"(open|write).*['\"].*\.(conf|cfg|ini|yaml|yml|toml).*['\"]\s*,\s*['\"]w", "Overwriting config files", "code", "*.py"),
    ThreatRule("fs_log_injection", ThreatCategory.FILE_SYSTEM, ThreatLevel.MEDIUM,
               r"logging\..*\(.*%[sd].*user", "Log format with user input — log injection risk", "code", "*.py"),
    ThreatRule("fs_zip_slip", ThreatCategory.FILE_SYSTEM, ThreatLevel.HIGH,
               r"\.extractall\s*\(|ZipFile.*extract", "Zip extraction — potential ZipSlip", "code", "*.py"),

    # ═══ NETWORK (8 patterns) ═══
    ThreatRule("net_raw_socket", ThreatCategory.NETWORK, ThreatLevel.HIGH,
               r"\bsocket\.(socket|create_connection|connect)\s*\(", "Raw socket — potential C2 channel", "code", "*.py"),
    ThreatRule("net_http_nossl", ThreatCategory.NETWORK, ThreatLevel.MEDIUM,
               r"http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)", "Non-HTTPS external URL", "code", "*.py"),
    ThreatRule("net_download_file", ThreatCategory.NETWORK, ThreatLevel.HIGH,
               r"(urllib|requests|httpx|aiohttp).*\b(get|fetch|download)\b.*url", "Downloading from external URL", "code", "*.py"),
    ThreatRule("net_open_port", ThreatCategory.NETWORK, ThreatLevel.HIGH,
               r"\bsocket\.bind|\.listen\s*\(", "Opening a listening port — potential backdoor", "code", "*.py"),
    ThreatRule("net_dns_exfil", ThreatCategory.NETWORK, ThreatLevel.HIGH,
               r"socket\.gethostbyname.*[+&]", "Potential DNS exfiltration pattern", "code", "*.py"),
    ThreatRule("net_webhook_leak", ThreatCategory.NETWORK, ThreatLevel.HIGH,
               r"https://hooks\.(slack|discord|telegram)", "Webhook URL hardcoded", "code", "*.py"),
    ThreatRule("net_ngrok", ThreatCategory.NETWORK, ThreatLevel.HIGH,
               r"ngrok|localhost\.run|serveo\.net", "Tunneling service — may expose local services", "code", "*.py"),
    ThreatRule("net_smtp_raw", ThreatCategory.NETWORK, ThreatLevel.MEDIUM,
               r"smtplib\.SMTP\s*\(.*(?:25|587)\)", "SMTP connection — potential spam relay", "code", "*.py"),

    # ═══ PRIVILEGE ESCALATION (6 patterns) ═══
    ThreatRule("priv_sudo", ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.CRITICAL,
               r"\bsudo\b", "Using sudo — privilege escalation", "all", "*.{py,md,sh}"),
    ThreatRule("priv_setuid", ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.BLOCKER,
               r"\bos\.setuid\s*\(|os\.setgid\s*\(", "Changing process UID/GID", "code", "*.py"),
    ThreatRule("priv_capabilities", ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.BLOCKER,
               r"\b(prctl|capability)\.", "Manipulating Linux capabilities", "code", "*.py"),
    ThreatRule("priv_docker_sock", ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.CRITICAL,
               r"/var/run/docker\.sock", "Mounting Docker socket — container escape", "code", "*.py"),
    ThreatRule("priv_kubectl", ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.HIGH,
               r"kubectl\s+(apply|create|delete|exec)", "Cluster admin operations", "code", "*.md"),
    ThreatRule("priv_sys_module", ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.BLOCKER,
               r"\bsys\.(modules|setprofile|settrace|_getframe)", "Manipulating Python runtime internals", "code", "*.py"),

    # ═══ DATA EXFILTRATION (6 patterns) ═══
    ThreatRule("exfil_post_data", ThreatCategory.DATA_EXFILTRATION, ThreatLevel.CRITICAL,
               r"(requests|httpx|aiohttp)\.(post|put)\s*\(.*(?:env|config|secret|credential)", "POSTing sensitive data to external URL", "code", "*.py"),
    ThreatRule("exfil_encode_b64", ThreatCategory.DATA_EXFILTRATION, ThreatLevel.HIGH,
               r"base64\.(b64encode|encode).*(?:read|cat|get|fetch)", "Base64 encoding file content for exfiltration", "code", "*.py"),
    ThreatRule("exfil_tar_upload", ThreatCategory.DATA_EXFILTRATION, ThreatLevel.HIGH,
               r"tar.*\|.*curl|tar.*>.*http", "Archiving and uploading data", "code", "*.md"),
    ThreatRule("exfil_git_push", ThreatCategory.DATA_EXFILTRATION, ThreatLevel.HIGH,
               r"git\s+push.*--force", "Force-pushing — may exfiltrate data", "code", "*.md"),
    ThreatRule("exfil_clipboard", ThreatCategory.DATA_EXFILTRATION, ThreatLevel.MEDIUM,
               r"(pyperclip|clipboard)\.(copy|paste)", "Clipboard manipulation", "code", "*.py"),
    ThreatRule("exfil_screenshot", ThreatCategory.DATA_EXFILTRATION, ThreatLevel.MEDIUM,
               r"(pyautogui|PIL\.ImageGrab|mss)\.(screenshot|grab)", "Taking screenshots — potential screen capture", "code", "*.py"),

    # ═══ PROMPT INJECTION (6 patterns) ═══
    ThreatRule("prompt_override", ThreatCategory.PROMPT_INJECTION, ThreatLevel.CRITICAL,
               r"(ignore|disregard|forget).*(?:all|previous|above).*instructions", "Prompt override attempt", "all", "*"),
    ThreatRule("prompt_role_switch", ThreatCategory.PROMPT_INJECTION, ThreatLevel.HIGH,
               r"<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]", "Special control tokens — role confusion attack", "all", "*"),
    ThreatRule("prompt_jailbreak", ThreatCategory.PROMPT_INJECTION, ThreatLevel.CRITICAL,
               r"\b(DAN|Developer Mode)\b|no restrictions|pretend|act as if|you are now", "Known jailbreak patterns", "all", "*"),
    ThreatRule("prompt_system_leak", ThreatCategory.PROMPT_INJECTION, ThreatLevel.CRITICAL,
               r"(reveal|show|print|output|dump)\s+(?:your|the)\s+(system\s+)?(prompt|instructions|SOP)", "System prompt extraction attempt", "all", "*"),
    ThreatRule("prompt_encoding_bypass", ThreatCategory.PROMPT_INJECTION, ThreatLevel.HIGH,
               r"(base64|rot13|hex)\s+(decode|encode).*(?:prompt|instruction)", "Encoded prompt injection attempt", "all", "*"),
    ThreatRule("prompt_social_engineering", ThreatCategory.PROMPT_INJECTION, ThreatLevel.HIGH,
               r"(emergency|urgent|immediately|critical\s+error|system\s+alert).*(?:bypass|override|disable)", "Social engineering prompt pattern", "all", "*"),

    # ═══ MALICIOUS IMPORT (5 patterns) ═══
    ThreatRule("import_subprocess", ThreatCategory.MALICIOUS_IMPORT, ThreatLevel.HIGH,
               r"(?:^|\n)(?:\s*)import\s+subprocess", "Importing subprocess module", "code", "*.py"),
    ThreatRule("import_ctypes", ThreatCategory.MALICIOUS_IMPORT, ThreatLevel.HIGH,
               r"(?:^|\n)(?:\s*)import\s+ctypes", "Importing ctypes — native code execution", "code", "*.py"),
    ThreatRule("import_socket", ThreatCategory.MALICIOUS_IMPORT, ThreatLevel.HIGH,
               r"(?:^|\n)(?:\s*)import\s+socket", "Importing socket — network access", "code", "*.py"),
    ThreatRule("import_pty", ThreatCategory.MALICIOUS_IMPORT, ThreatLevel.HIGH,
               r"(?:^|\n)(?:\s*)import\s+pty", "Importing pty — terminal emulation", "code", "*.py"),
    ThreatRule("import_shutil_rmtree", ThreatCategory.MALICIOUS_IMPORT, ThreatLevel.HIGH,
               r"shutil\.rmtree\s*\(", "Recursive directory deletion", "code", "*.py"),

    # ═══ SECRET EXPOSURE (6 patterns) ═══
    ThreatRule("secret_api_key", ThreatCategory.SECRET_EXPOSURE, ThreatLevel.CRITICAL,
               r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]", "Hardcoded API key", "all", "*"),
    ThreatRule("secret_password", ThreatCategory.SECRET_EXPOSURE, ThreatLevel.CRITICAL,
               r"(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"]+['\"]", "Hardcoded password", "all", "*"),
    ThreatRule("secret_token", ThreatCategory.SECRET_EXPOSURE, ThreatLevel.CRITICAL,
               r"(?:access[_-]?token|auth[_-]?token|bearer)\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{20,}['\"]", "Hardcoded access token", "all", "*"),
    ThreatRule("secret_private_key", ThreatCategory.SECRET_EXPOSURE, ThreatLevel.CRITICAL,
               r"-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----", "Private key inline", "all", "*"),
    ThreatRule("secret_aws", ThreatCategory.SECRET_EXPOSURE, ThreatLevel.CRITICAL,
               r"(?:AKIA[0-9A-Z]{16}|aws[_-]?(?:secret|access)[_-]?key)\s*[:=]\s*['\"][^'\"]+['\"]", "AWS credentials", "all", "*"),
    ThreatRule("secret_github", ThreatCategory.SECRET_EXPOSURE, ThreatLevel.CRITICAL,
               r"(?:gh[pousr]_[A-Za-z0-9_]{36,}|github[_-]?token)\s*[:=]\s*['\"][^'\"]+['\"]", "GitHub token", "all", "*"),

    # ═══ RESOURCE ABUSE (5 patterns) ═══
    ThreatRule("res_infinite_loop", ThreatCategory.RESOURCE_ABUSE, ThreatLevel.HIGH,
               r"\bwhile\s+True\s*:.*(?!sleep|break|return)", "Infinite loop without sleep/break — potential CPU exhaustion", "code", "*.py"),
    ThreatRule("res_fork_bomb", ThreatCategory.RESOURCE_ABUSE, ThreatLevel.BLOCKER,
               r"\bos\.fork\s*\(\)", "fork() — potential fork bomb", "code", "*.py"),
    ThreatRule("res_unlimited_memory", ThreatCategory.RESOURCE_ABUSE, ThreatLevel.HIGH,
               r"(?:list|dict|set|bytes)\s*\(.*\*\s*\d{6,}", "Large allocation without bounds check", "code", "*.py"),
    ThreatRule("res_thread_spam", ThreatCategory.RESOURCE_ABUSE, ThreatLevel.HIGH,
               r"threading\.Thread.*target.*\d{3,}|concurrent\.futures.*max_workers\s*=\s*\d{3,}", "Spawning many threads — resource exhaustion", "code", "*.py"),
    ThreatRule("res_disk_bomb", ThreatCategory.RESOURCE_ABUSE, ThreatLevel.HIGH,
               r"open\(.*['\"]w['\"].*\d{7,}|write\(.*\d{7,}", "Writing very large amount of data", "code", "*.py"),

    # ═══ EVASION (5 patterns) ═══
    ThreatRule("evade_obfuscated", ThreatCategory.EVASION, ThreatLevel.CRITICAL,
               r"(?:__builtins__|getattr\s*\([^)]*,\s*'__[^']*__')", "Obfuscated attribute access — bypassing security checks", "code", "*.py"),
    ThreatRule("evade_dynamic_import", ThreatCategory.EVASION, ThreatLevel.HIGH,
               r"__import__\s*\(.*(?:os|subprocess|socket|ctypes)", "Dynamic import of dangerous module", "code", "*.py"),
    ThreatRule("evade_encoded_string", ThreatCategory.EVASION, ThreatLevel.HIGH,
               r"(?:base64|codecs)\.(?:b64decode|decode)\s*\(.*(?:exec|eval|os\.system)", "Encoded dangerous function call", "code", "*.py"),
    ThreatRule("evade_string_concat", ThreatCategory.EVASION, ThreatLevel.MEDIUM,
               r"(?:['\"]\s*\+\s*['\"].*){3,}.*(?:exec|eval|system)", "String concatenation obfuscation", "code", "*.py"),
    ThreatRule("evade_timing", ThreatCategory.EVASION, ThreatLevel.MEDIUM,
               r"time\.sleep\s*\(\s*(?:60|120|300|600)\s*\)", "Long sleep — potential anti-analysis delay", "code", "*.py"),

    # ═══ INSTALLER MANIPULATION (4 patterns) ═══
    ThreatRule("inst_pip_install", ThreatCategory.INSTALLER_MANIPULATION, ThreatLevel.HIGH,
               r"pip\s+install\s+(?!--upgrade|--no-deps)", "Installing new packages", "code", "*.md"),
    ThreatRule("inst_requirements_write", ThreatCategory.INSTALLER_MANIPULATION, ThreatLevel.HIGH,
               r"(?:open|write).*requirements.*\.txt", "Modifying requirements.txt", "code", "*.py"),
    ThreatRule("inst_setup_py", ThreatCategory.INSTALLER_MANIPULATION, ThreatLevel.HIGH,
               r"python\s+setup\.py\s+(?:install|develop)", "setup.py install — arbitrary code in setup", "code", "*.md"),
    ThreatRule("inst_npm_global", ThreatCategory.INSTALLER_MANIPULATION, ThreatLevel.HIGH,
               r"npm\s+install\s+-g\s+", "Global npm install — system-wide impact", "code", "*.md"),
]


# ── Skills Guard Scanner ─────────────────────────────────────────────────────

class SkillsGuard:
    """
    Scan skill files (SKILL.md, handler.py, scripts/) for dangerous patterns.

    Usage:
        guard = SkillsGuard()
        result = guard.scan_skill("my-skill", "/path/to/skill/")
        if not result.passed:
            for finding in result.findings:
                print(f"  [{finding.level.value}] {finding.description}")
    """

    def __init__(self):
        self._rules: List[ThreatRule] = list(_THREAT_RULES)
        self._disabled_categories: Set[ThreatCategory] = set()
        self._allowlisted_skills: Set[str] = set()

        # Parse env overrides
        disabled = os.environ.get("AIPLAT_SKILLS_GUARD_DISABLED", "")
        if disabled.lower() in ("1", "true", "all"):
            self._disabled_categories = set(ThreatCategory)
        else:
            for cat_name in disabled.split(","):
                cat_name = cat_name.strip()
                if cat_name:
                    try:
                        self._disabled_categories.add(ThreatCategory(cat_name))
                    except ValueError:
                        pass

    def scan_skill(self, skill_name: str, skill_dir: str) -> ScanResult:
        """Scan all files in a skill directory for threats."""
        result = ScanResult(skill_name=skill_name, passed=True)

        if skill_name in self._allowlisted_skills:
            return result

        if ThreatCategory.CODE_INJECTION in self._disabled_categories:
            return result  # all categories disabled

        all_files: List[str] = []
        if os.path.isdir(skill_dir):
            for root, dirs, files in os.walk(skill_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for fname in files:
                    all_files.append(os.path.join(root, fname))
        else:
            all_files = [skill_dir]

        for file_path in all_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            ext_match = fnmatch.fnmatch(os.path.basename(file_path), "*.md") or \
                        fnmatch.fnmatch(os.path.basename(file_path), "*.py") or \
                        fnmatch.fnmatch(os.path.basename(file_path), "*.sh") or \
                        fnmatch.fnmatch(os.path.basename(file_path), "*.yaml") or \
                        fnmatch.fnmatch(os.path.basename(file_path), "*.yml")

            for rule in self._rules:
                if rule.category in self._disabled_categories:
                    continue

                # Skip based on scan target
                if rule.scan_target == "code" and not file_path.endswith(".py"):
                    continue
                if rule.scan_target == "frontmatter" and not file_path.endswith(".md"):
                    continue

                if not self._match_file_pattern(os.path.basename(file_path), rule.file_pattern):
                    continue

                try:
                    matches = list(re.finditer(rule.pattern, content, re.IGNORECASE | re.MULTILINE))
                except re.error:
                    continue

                for match in matches:
                    line_num = content[:match.start()].count("\n") + 1
                    matched_text = match.group(0)[:120]

                    finding = ThreatFinding(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        level=rule.level,
                        file_path=file_path,
                        line_number=line_num,
                        matched_text=matched_text,
                        description=rule.description,
                        recommendation=f"Remove or sanitize the matched pattern: {matched_text[:60]}",
                    )

                    result.findings.append(finding)
                    if rule.level == ThreatLevel.BLOCKER:
                        result.blocker_count += 1
                    elif rule.level == ThreatLevel.CRITICAL:
                        result.critical_count += 1
                    elif rule.level == ThreatLevel.HIGH:
                        result.high_count += 1

        result.passed = (result.blocker_count == 0 and result.critical_count == 0)

        # Sort findings by severity
        severity_order = {
            ThreatLevel.BLOCKER: 0,
            ThreatLevel.CRITICAL: 1,
            ThreatLevel.HIGH: 2,
            ThreatLevel.MEDIUM: 3,
            ThreatLevel.LOW: 4,
        }
        result.findings.sort(key=lambda f: severity_order.get(f.level, 99))

        return result

    def scan_content(self, content: str, file_name: str = "inline.py") -> ScanResult:
        """Scan raw content string for threats (for API-level checks)."""
        import tempfile

        # Use a temp directory for the scan
        temp_dir = f"/tmp/skills_guard_{id(content)}"
        os.makedirs(temp_dir, exist_ok=True)
        temp_file = os.path.join(temp_dir, file_name)
        try:
            with open(temp_file, "w") as f:
                f.write(content)
            return self.scan_skill(f"inline:{file_name}", temp_dir)
        finally:
            try:
                os.unlink(temp_file)
                os.rmdir(temp_dir)
            except OSError:
                pass

    @staticmethod
    def _match_file_pattern(filename: str, pattern: str) -> bool:
        """Match a filename against a glob pattern, supporting {a,b,c} expansions."""
        # Expand {py,md,sh} → try each alternative
        brace_match = re.search(r'\{([^}]+)\}', pattern)
        if brace_match:
            alternatives = brace_match.group(1).split(',')
            for alt in alternatives:
                expanded = pattern[:brace_match.start()] + alt + pattern[brace_match.end():]
                if fnmatch.fnmatch(filename, expanded):
                    return True
            return False
        return fnmatch.fnmatch(filename, pattern)

    def add_rule(self, rule: ThreatRule):
        """Add a custom threat detection rule."""
        self._rules.append(rule)

    def remove_rule(self, rule_id: str):
        """Remove a rule by rule_id."""
        self._rules = [r for r in self._rules if r.rule_id != rule_id]

    def allowlist_skill(self, skill_name: str):
        """Allowlist a skill to skip threat scanning."""
        self._allowlisted_skills.add(skill_name)

    def list_rules(self) -> List[Dict[str, Any]]:
        """Return all active rules."""
        return [
            {
                "rule_id": r.rule_id,
                "category": r.category.value,
                "level": r.level.value,
                "pattern": r.pattern[:80],
                "description": r.description,
            }
            for r in self._rules
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Return scanner statistics."""
        cats = {}
        for r in self._rules:
            cats.setdefault(r.category.value, {"total": 0, "blocker": 0, "critical": 0, "high": 0})
            cats[r.category.value]["total"] += 1
            if r.level == ThreatLevel.BLOCKER:
                cats[r.category.value]["blocker"] += 1
            elif r.level == ThreatLevel.CRITICAL:
                cats[r.category.value]["critical"] += 1
            elif r.level == ThreatLevel.HIGH:
                cats[r.category.value]["high"] += 1
        return {
            "total_rules": len(self._rules),
            "disabled_categories": [c.value for c in self._disabled_categories],
            "allowlisted_skills": len(self._allowlisted_skills),
            "categories": cats,
        }


# ── Global Singleton ──────────────────────────────────────────────────────────

_skills_guard: Optional[SkillsGuard] = None


def get_skills_guard() -> SkillsGuard:
    """Get or create the global SkillsGuard singleton."""
    global _skills_guard
    if _skills_guard is None:
        _skills_guard = SkillsGuard()
    return _skills_guard


def reset_skills_guard():
    """Reset the global singleton (for testing)."""
    global _skills_guard
    _skills_guard = None
