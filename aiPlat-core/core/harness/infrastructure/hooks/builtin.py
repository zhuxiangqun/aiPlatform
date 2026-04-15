"""
Built-in Hooks

Predefined hooks for common automation scenarios.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import re


@dataclass
class HookEvent:
    """Hook event data received via stdin"""
    session_id: str
    hook_event_name: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "HookEvent":
        return HookEvent(
            session_id=data.get("session_id", ""),
            hook_event_name=data.get("hook_event_name", ""),
            tool_name=data.get("tool_name"),
            tool_input=data.get("tool_input"),
            tool_result=data.get("tool_result"),
            prompt=data.get("prompt"),
            response=data.get("response"),
            metadata=data.get("metadata", {})
        )


class ExitCode:
    """Hook exit code meanings"""
    CONTINUE = 0
    LOG = 1
    BLOCK = 2


class AutoAdaptHook:
    """
    Permission auto-adaptive learning hook.
    
    When user manually approves a tool operation, automatically generalizes
    the permission rule to handle similar operations.
    """
    
    HARD_BLOCKED_PATTERNS = [
        r"rm\s+-rf",
        r"sudo\s+",
        r"npm\s+publish",
        r"git\s+push\s+--force",
        r"DROP\s+TABLE",
        r"DELETE\s+FROM\s+\w+\s*;?\s*$",
    ]
    
    def __init__(self):
        self.learned_rules: Dict[str, List[str]] = {}
    
    def can_learn(self, command: str) -> bool:
        """Check if command can be learned"""
        for pattern in self.HARD_BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return False
        return True
    
    def generalize_command(self, command: str) -> str:
        """Generalize command pattern for learning"""
        parts = command.split()
        if not parts:
            return "*"
        
        tool = parts[0]
        if len(parts) > 1:
            subcmd = parts[1]
            if subcmd.startswith("-"):
                return f"{tool} *"
            return f"{tool} {subcmd} *"
        return f"{tool} *"
    
    def learn(self, approved_command: str) -> bool:
        """Learn from approved command"""
        if not self.can_learn(approved_command):
            return False
        
        generalized = self.generalize_command(approved_command)
        tool = approved_command.split()[0] if approved_command.split() else "*"
        
        if tool not in self.learned_rules:
            self.learned_rules[tool] = []
        
        if generalized not in self.learned_rules[tool]:
            self.learned_rules[tool].append(generalized)
        
        return True
    
    def check_permission(self, command: str) -> bool:
        """Check if command matches learned rules"""
        tool = command.split()[0] if command.split() else "*"
        
        if tool in self.learned_rules:
            for rule in self.learned_rules[tool]:
                if self._match_pattern(command, rule):
                    return True
        
        if "*" in self.learned_rules:
            for rule in self.learned_rules["*"]:
                if self._match_pattern(command, rule):
                    return True
        
        return False
    
    def _match_pattern(self, command: str, pattern: str) -> bool:
        """Match command against pattern"""
        cmd_parts = command.split()
        pattern_parts = pattern.split()
        
        for i, part in enumerate(pattern_parts):
            if part == "*":
                continue
            if i >= len(cmd_parts):
                return False
            if not cmd_parts[i].startswith(part):
                return False
        
        return True
    
    def get_rules(self) -> Dict[str, List[str]]:
        return self.learned_rules.copy()


class ContextTrackerHook:
    """
    Token consumption tracker hook.
    
    Tracks token usage by recording start (PreToolUse) and end (Stop) points.
    """
    
    def __init__(self):
        self.session_tokens: Dict[str, List[int]] = {}
        self.current_session: Optional[str] = None
        self.request_start_token: Optional[int] = None
    
    def record_request_start(self, session_id: str, token_count: int):
        """Record the start of a request"""
        self.current_session = session_id
        self.request_start_token = token_count
    
    def record_request_end(self, token_count: int) -> Optional[int]:
        """Record the end of a request and return consumption"""
        if self.current_session and self.request_start_token is not None:
            consumed = token_count - self.request_start_token
            
            if self.current_session not in self.session_tokens:
                self.session_tokens[self.current_session] = []
            
            self.session_tokens[self.current_session].append(consumed)
            
            return consumed
        return None
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get token stats for a session"""
        tokens = self.session_tokens.get(session_id, [])
        
        if not tokens:
            return {"total": 0, "avg": 0, "count": 0}
        
        return {
            "total": sum(tokens),
            "avg": sum(tokens) / len(tokens),
            "count": len(tokens),
            "max": max(tokens),
            "min": min(tokens)
        }


class SecurityScanHook:
    """
    Security scan hook for detecting hardcoded secrets.
    
    Scans file write operations for sensitive information.
    """
    
    SECRET_PATTERNS = {
        "aws_key": r"AKIA[0-9A-Z]{16}",
        "openai_key": r"sk-[a-zA-Z0-9]{20,}",
        "github_token": r"ghp_[a-zA-Z0-9]{36,}",
        "generic_api_key": r"(api[_-]?key|apikey)\s*[=:]\s*['\"]?[a-zA-Z0-9_-]{20,}['\"]?",
        "password": r"password\s*[=:]\s*['\"][^'\"]+['\"]",
        "private_key": r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
    }
    
    def __init__(self, scan_on_write: bool = True):
        self.scan_on_write = scan_on_write
        self.findings: List[Dict[str, Any]] = []
    
    def scan_content(self, content: str, file_path: str = "") -> List[Dict[str, Any]]:
        """Scan content for secrets"""
        findings = []
        
        for secret_type, pattern in self.SECRET_PATTERNS.items():
            for match in re.finditer(pattern, content, re.IGNORECASE):
                findings.append({
                    "type": secret_type,
                    "match": match.group(),
                    "location": f"{file_path}:{content[:match.start()].count(chr(10)) + 1}",
                    "severity": "high"
                })
        
        return findings
    
    def scan_tool_input(self, tool_name: str, tool_input: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scan tool input for security issues"""
        if tool_name not in ["Write", "Edit"]:
            return []
        
        content = tool_input.get("content", "")
        file_path = tool_input.get("path", "")
        
        return self.scan_content(content, file_path)


class PreCommitHook:
    """
    Pre-commit hook for automatic testing.
    
    Detects git commits and automatically runs appropriate tests.
    """
    
    LANGUAGE_TEST_COMMANDS = {
        "package.json": "npm test",
        "requirements.txt": "pytest",
        "setup.py": "python -m pytest",
        "go.mod": "go test",
        "Cargo.toml": "cargo test",
        "pom.xml": "mvn test",
    }
    
    def detect_language(self, project_root: str) -> Optional[str]:
        """Detect project language from lock files"""
        for file_pattern, _ in self.LANGUAGE_TEST_COMMANDS.items():
            import os
            if os.path.exists(os.path.join(project_root, file_pattern)):
                return file_pattern
        return None
    
    def get_test_command(self, language_file: str) -> Optional[str]:
        """Get test command for detected language"""
        return self.LANGUAGE_TEST_COMMANDS.get(language_file)


class FormatCodeHook:
    """
    Auto-format hook for file writes.
    
    Automatically formats code files after Write operations.
    """
    
    FORMATTERS = {
        ".js": "prettier",
        ".ts": "prettier",
        ".jsx": "prettier",
        ".tsx": "prettier",
        ".py": "black",
        ".go": "gofmt",
        ".rs": "rustfmt",
        ".java": "google-java-format",
    }
    
    def get_formatter(self, file_path: str) -> Optional[str]:
        """Get formatter for file type"""
        import os
        ext = os.path.splitext(file_path)[1]
        return self.FORMATTERS.get(ext)
    
    def can_format(self, file_path: str) -> bool:
        """Check if file can be formatted"""
        return self.get_formatter(file_path) is not None


class TokenLimitHook:
    """
    Token limit enforcement hook.
    
    Monitors context size and triggers compaction when approaching limits.
    """
    
    DEFAULT_LIMIT = 100000
    
    def __init__(self, token_limit: int = DEFAULT_LIMIT):
        self.token_limit = token_limit
        self.warn_threshold = int(token_limit * 0.8)
    
    def should_warn(self, current_tokens: int) -> bool:
        """Check if warning threshold reached"""
        return current_tokens >= self.warn_threshold
    
    def should_compact(self, current_tokens: int) -> bool:
        """Check if compaction needed"""
        return current_tokens >= self.token_limit
    
    def get_remaining(self, current_tokens: int) -> int:
        """Get remaining token budget"""
        return max(0, self.token_limit - current_tokens)


class NotificationHook:
    """
    Custom notification hook.
    
    Handles custom notification delivery for specific events.
    """
    
    def __init__(self):
        self.handlers: Dict[str, List[callable]] = {}
    
    def register_handler(self, event_type: str, handler: callable):
        """Register notification handler"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    async def notify(self, event_type: str, data: Dict[str, Any]):
        """Trigger notification handlers"""
        handlers = self.handlers.get(event_type, [])
        for handler in handlers:
            if callable(handler):
                if hasattr(handler, '__await__'):
                    await handler(data)
                else:
                    handler(data)


BUILTIN_HOOKS = {
    "auto-adapt": AutoAdaptHook,
    "context-tracker": ContextTrackerHook,
    "security-scan": SecurityScanHook,
    "pre-commit": PreCommitHook,
    "format-code": FormatCodeHook,
    "token-limit": TokenLimitHook,
    "notification": NotificationHook,
}


__all__ = [
    "HookEvent",
    "ExitCode",
    "AutoAdaptHook",
    "ContextTrackerHook",
    "SecurityScanHook",
    "PreCommitHook",
    "FormatCodeHook",
    "TokenLimitHook",
    "NotificationHook",
    "BUILTIN_HOOKS",
]