"""
Test: Core/infra genericity — no business domain knowledge leaks.

Phase A-F: Verifies that domain IDs, agent names, business keywords, and
business-specific actions do NOT leak into the core/infra engine layers.
Prevention against adding new domain knowledge without going through
the extensibility mechanisms (YAML config, env vars, file-system discovery).
"""
import ast
import os
import sys


CORE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
HARNESS_DIR = os.path.join(CORE_DIR, "core", "harness")
API_DIR = os.path.join(CORE_DIR, "core", "api")

# Domain IDs must never appear in core engine modules
FORBIDDEN_DOMAIN_IDS = [
    "fde-delivery", "lock-service",
    "bell-consulting", "bell-data-cloud", "bell-healthcare", "bell-global",
    "enterprise-terms",
]

# Business class names must never appear in core routers
FORBIDDEN_CLASS_NAMES = [
    "DiagnosisSession", "DeliveryAction", "Term",
]

# Business keywords must never appear in core ingestion logic
FORBIDDEN_INGEST_KEYWORDS = [
    "审核路径", "七步周天", "认知同化",
]

# Engine modules that must remain domain-agnostic
ENGINE_MODULES = [
    os.path.join(HARNESS_DIR, "execution"),
    os.path.join(HARNESS_DIR, "infrastructure"),
    os.path.join(HARNESS_DIR, "knowledge_pipeline"),
    os.path.join(HARNESS_DIR, "ontology_engine"),
    os.path.join(API_DIR, "routers"),
]


def _walk_python_files(root: str):
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".py") and "__pycache__" not in dirpath:
                yield os.path.join(dirpath, fn)


def _file_contains(filepath: str, pattern: str) -> bool:
    """Check if file contains a pattern, skipping comments."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if pattern in line:
                    return True
    except Exception:
        pass
    return False


class TestNoDomainIDInEngine:
    """Engine modules must not contain hardcoded domain IDs."""

    ALLOWED_FILES = {
        "builtin_handlers.py",    # now reads domain_id from entity/params
        "builtin_actions.py",     # now only has generic bridge actions
        "domain_router.py",       # legitimately manages domain lists
        "ontology_loader.py",     # legitimately reads domain YAML
        "resolver.py",             # seed function now writes empty config
        "prompt_loader.py",       # now scans domains from YAML
    }

    def _is_allowed(self, fname: str) -> bool:
        return os.path.basename(fname) in self.ALLOWED_FILES

    def test_no_domain_id_hardcode_in_engine(self):
        violations = []
        for fpath in _walk_python_files(os.path.join(HARNESS_DIR, "execution")):
            if self._is_allowed(fpath):
                continue
            for did in FORBIDDEN_DOMAIN_IDS:
                if _file_contains(fpath, f'"{did}"') or _file_contains(fpath, f"'{did}'"):
                    violations.append((fpath, did))
        assert not violations, f"Engine files contain hardcoded domain IDs: {violations}"

    def test_no_domain_id_hardcode_in_pipeline(self):
        violations = []
        for fpath in _walk_python_files(os.path.join(HARNESS_DIR, "knowledge_pipeline")):
            if self._is_allowed(fpath):
                continue
            for did in FORBIDDEN_DOMAIN_IDS:
                if _file_contains(fpath, f'"{did}"') or _file_contains(fpath, f"'{did}'"):
                    violations.append((fpath, did))
        assert not violations, f"Pipeline files contain hardcoded domain IDs: {violations}"

    def test_no_domain_id_hardcode_in_infrastructure(self):
        violations = []
        for fpath in _walk_python_files(os.path.join(HARNESS_DIR, "infrastructure")):
            if self._is_allowed(fpath):
                continue
            for did in FORBIDDEN_DOMAIN_IDS:
                if _file_contains(fpath, f'"{did}"') or _file_contains(fpath, f"'{did}'"):
                    violations.append((fpath, did))
        assert not violations, f"Infrastructure files contain hardcoded domain IDs: {violations}"


class TestNoBusinessKeywordsInCore:
    """Core modules must not contain business-specific keywords."""

    def test_no_cognitive_keywords_in_ingestion(self):
        fpath = os.path.join(HARNESS_DIR, "knowledge", "conversation_ingestor.py")
        if not os.path.exists(fpath):
            return  # skip if file doesn't exist
        for kw in FORBIDDEN_INGEST_KEYWORDS:
            assert not _file_contains(fpath, kw), \
                f"conversation_ingestor.py contains business keyword: {kw}"


class TestNoDefaultBusinessTeam:
    """Team planner must not embed business-specific defaults."""

    def test_default_team_empty(self):
        fpath = os.path.join(HARNESS_DIR, "execution", "team_planner.py")
        if not os.path.exists(fpath):
            return
        with open(fpath, "r") as f:
            content = f.read()
        # _DEFAULT_TEAM_STAGES must be empty list, not contain business agent IDs
        assert "architect_agent" not in content, \
            "team_planner.py contains business-specific agent IDs"
        assert "programmer_agent" not in content, \
            "team_planner.py contains business-specific agent IDs"
        assert "qa_agent" not in content, \
            "team_planner.py contains business-specific agent IDs"


class TestNoDomainClassNamesInRouters:
    """Core API routers must not contain hardcoded domain-specific class names."""

    def test_no_domain_class_names_in_system_router(self):
        fpath = os.path.join(API_DIR, "routers", "system.py")
        if not os.path.exists(fpath):
            return
        for cn in FORBIDDEN_CLASS_NAMES:
            assert not _file_contains(fpath, f'"{cn}"'), \
                f"system.py contains hardcoded class name: {cn}"


class TestNoCrossDomainSeedData:
    """Resolver must not contain hardcoded cross-domain seed data."""

    def test_no_seed_domain_combination(self):
        fpath = os.path.join(HARNESS_DIR, "knowledge_pipeline", "resolver.py")
        if not os.path.exists(fpath):
            return
        with open(fpath, "r") as f:
            content = f.read()
        # lock-service + fde-delivery must not appear together as seed data
        assert '"客户现场"' not in content, \
            "resolver.py contains business-specific seed data"


class TestBuiltinActionsGeneric:
    """Builtin_actions must only contain generic bridge actions."""

    def test_no_business_domain_ids(self):
        fpath = os.path.join(HARNESS_DIR, "ontology_engine", "builtin_actions.py")
        if not os.path.exists(fpath):
            return
        with open(fpath, "r") as f:
            content = f.read()
        for did in ["fde-delivery", "lock-service", "bell-consulting",
                     "bell-data-cloud", "bell-healthcare", "bell-global"]:
            if f'domain_id="{did}"' in content or f"domain_id='{did}'" in content:
                # Check it's not in a comment
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if f'domain_id="{did}"' in line or f"domain_id='{did}'" in line:
                        assert False, f"builtin_actions.py contains business domain_id: {did} in line: {stripped[:80]}"
