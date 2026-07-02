"""
Architecture Constitution Tests: Infra Agnostic (infra MUST be application-unaware)

Enforces aiPlat-infra CLAUDE.md §"基础设施无关应用原则":
    infra MUST be deployable independently of aiPlat.

These tests verify that:
1. No hardcoded application names in defaults ("ai-platform", "aiPlat", etc.)
2. No hardcoded service name mappings
3. No business process labels
4. No developer-specific paths
5. No vendor-specific GPU model defaults
6. No application-specific directory names in code

Design authority: aiPlat-infra/CLAUDE.md §5.6, docs/index.md §Layer 0
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _find_py_files(dir_path: str) -> List[Path]:
    dir_full = WORKSPACE_ROOT / dir_path
    if not dir_full.exists():
        return []
    files = []
    for root, dirs, filenames in os.walk(str(dir_full)):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", "tests")]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(root) / f)
    return files


def _grep_files(files: List[Path], pattern: str) -> List[Tuple[Path, int, str]]:
    compiled = re.compile(pattern)
    hits = []
    for fp in files:
        try:
            for i, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").split("\n"), 1):
                if compiled.search(line):
                    hits.append((fp, i, line.strip()))
        except Exception:
            pass
    return hits


# Patterns that are ALLOWED (environment variable names, env-var-driven config)
_ALLOWED_PATTERN = re.compile(
    r"os\.getenv\(|AIPLAT_.*=|AIPLAT_[A-Z_]+|"
    r"config\.\w+\.\w+\s*(or|=|if)|"
    r"self\._config\b|"
    r"get_config_value\(|"
    r"#.*ai.platform|#.*aiPlat"  # comments are allowed
)

# Files that are exempt (CLAUDE.md references, changelogs)
_EXEMPT_FILES = re.compile(r"(CLAUDE\.md|CHANGELOG|README|\.md$|__init__\.py$)")


def _filter_app_specific_only(hits, files) -> List:
    """Only flag hits that are NOT env-var-driven, NOT in exempt files."""
    filtered = []
    for f, l, s in hits:
        if _EXEMPT_FILES.search(str(f)):
            continue
        if _ALLOWED_PATTERN.search(s):
            continue
        filtered.append((f, l, s))
    return filtered


# ============================================================================
# Category 1: Application Names in Defaults
# ============================================================================


class TestNoApplicationNamesInDefaults:
    """Infra MUST NOT use 'ai-platform', 'aiPlat', etc. as default values."""

    def test_no_ai_platform_in_defaults(self):
        files = _find_py_files("aiPlat-infra/infra")
        pattern = r'"(ai.platform|aiplat|aiPlat|ai-platform)'
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        assert not filtered, (
            f"Infra MUST NOT hardcode 'ai-platform' / 'aiPlat' in defaults. "
            f"Use environment variables with empty fallback. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:20])
        )

    def test_no_ai_platform_in_management(self):
        files = _find_py_files("aiPlat-infra/infra/management")
        pattern = r'"(ai.platform|aiplat|aiPlat|ai-platform)'
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        assert not filtered, (
            f"Infra management MUST NOT hardcode 'ai-platform' / 'aiPlat'. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:20])
        )


# ============================================================================
# Category 2: Service Name Mappings
# ============================================================================


class TestNoHardcodedServiceMappings:
    """Infra MUST NOT map port numbers to specific service names as hardcoded defaults."""

    def test_no_known_services_dicts(self):
        files = _find_py_files("aiPlat-infra/infra")
        # Only flag actual hardcoded port→service mappings in dicts, not variable names
        # that are populated from environment variables at runtime
        pattern = r'\{\s*\d+\s*:\s*"(?!\s*$)'  # port: "non-empty-service-name"
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        filtered = [(f, l, s) for f, l, s in filtered if "tests/" not in str(f) and ".md" not in str(f)]
        assert not filtered, (
            f"Infra MUST NOT hardcode port→service name mappings. "
            f"Use runtime discovery or environment variables. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )

    def test_no_port_to_service_mappings(self):
        files = _find_py_files("aiPlat-infra/infra")
        pattern = r'\{\s*\d+\s*:\s*"'
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        # Also exclude test files
        filtered = [(f, l, s) for f, l, s in filtered if "tests/" not in str(f)]
        assert not filtered, (
            f"Infra MUST NOT map port numbers to service names. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )


# ============================================================================
# Category 3: GPU Model Names and Vendor-Specific Defaults
# ============================================================================


class TestNoVendorSpecificDefaults:
    """Infra MUST NOT hardcode specific GPU models or vendor names."""

    def test_no_gpu_model_defaults(self):
        files = _find_py_files("aiPlat-infra/infra")
        pattern = r'"(A100|H100|V100|T4|A10|A10G|L4|L40S)"'
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        # Exclude test files where A100 might appear in test data
        filtered = [(f, l, s) for f, l, s in filtered if "tests/" not in str(f)]
        assert not filtered, (
            f"Infra MUST NOT hardcode GPU model names as defaults. "
            f"Use empty string or environment variable. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )

    def test_no_vendor_specific_scheduler_names(self):
        files = _find_py_files("aiPlat-infra/infra")
        # Flag hardcoded vendor-specific scheduler/device names as defaults
        # but NOT hardware detection commands (nvidia-smi) or runtime GPU model detection
        pattern = r'nvidia.gpu.scheduler'
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        filtered = [(f, l, s) for f, l, s in filtered if "tests/" not in str(f) and ".md" not in str(f)]
        assert not filtered, (
            f"Infra MUST NOT hardcode vendor-specific scheduler names as defaults. "
            f"Use environment variable with empty fallback. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )


# ============================================================================
# Category 4: Business Error Categories and Field Names
# ============================================================================


class TestNoBusinessFieldNames:
    """Infra MUST NOT use business-specific field names like 'team'."""

    def test_no_team_field_in_quota_info(self):
        files = _find_py_files("aiPlat-infra/infra")
        # QuotaInfo should use 'label' not 'team'
        pattern = r'team\s*=\s*"'
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        # Exclude test files and CLAUDE.md references
        filtered = [(f, l, s) for f, l, s in filtered
                    if "tests/" not in str(f) and ".md" not in str(f)]
        assert not filtered, (
            f"Infra MUST use 'label' not 'team' in QuotaInfo constructor. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )

    def test_no_business_error_categories(self):
        files = _find_py_files("aiPlat-infra/infra")
        pattern = r"ErrorCategory\.BUSINESS|BUSINESS.*error"
        hits = _grep_files(files, pattern)
        filtered = [(f, l, s) for f, l, s in hits
                    if not s.strip().startswith("#") and "tests/" not in str(f) and ".md" not in str(f)]
        assert not filtered, (
            f"Infra MUST NOT define business error categories. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )


# ============================================================================
# Category 5: Developer-Specific Paths
# ============================================================================


class TestNoDeveloperPaths:
    """Infra MUST NOT contain developer-specific paths."""

    def test_no_home_directory_paths(self):
        files = _find_py_files("aiPlat-infra/infra")
        pattern = r"/Users/"
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        assert not filtered, (
            f"Infra MUST NOT contain developer-specific paths. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )

    def test_no_etc_aiplat_paths(self):
        files = _find_py_files("aiPlat-infra/infra")
        pattern = r"/etc/ai.plat"
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        assert not filtered, (
            f"Infra MUST NOT hardcode '/etc/aiplat' paths. Use environment variable. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )


# ============================================================================
# Category 6: Cryptographic and Security Defaults
# ============================================================================


class TestNoApplicationSpecificCrypto:
    """Infra MUST NOT use application-specific cryptographic salts or keys."""

    def test_no_ai_platform_salt(self):
        files = _find_py_files("aiPlat-infra/infra")
        pattern = r'ai.platform.salt|ai-platform-salt'
        hits = _grep_files(files, pattern)
        filtered = _filter_app_specific_only(hits, files)
        filtered = [(f, l, s) for f, l, s in filtered if "tests/" not in str(f)]
        assert not filtered, (
            f"Infra MUST NOT use application-specific cryptographic salts. "
            f"Generate from environment variable or random. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )
