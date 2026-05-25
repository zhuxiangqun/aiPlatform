"""
test_layer_ownership.py — Layer responsibility ownership checks.

Encodes the "does this code belong in this layer?" dimension of architecture
compliance. Covers checks that grep-level architecture_guard.sh cannot perform
because they require understanding of what each module DOES, not just which
imports it makes.

Add new violation patterns here as they are discovered during audits.
Each test should be documented with:
  - The architecture contract paragraph it enforces
  - Known exceptions (with file+line documentation)
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
CORE_DIR = ROOT / "aiPlat-core" / "core"
PLATFORM_DIR = ROOT / "aiPlat-platform"
INFRA_DIR = ROOT / "aiPlat-infra" / "infra"
APP_DIR = ROOT / "aiPlat-app"
MANAGEMENT_DIR = ROOT / "aiPlat-management" / "management"


def _read_head(path: Path, lines: int = 80) -> str:
    try:
        with open(path) as f:
            return "".join(f.readline() for _ in range(lines))
    except Exception:
        return ""


def _has_boundary_marker(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


# ═══════════════════════════════════════════════════════════════════════
# §L1: Platform-Only Responsibilities — Must NOT Live in Core
# Per docs/index.md §Layer 2: tenant/billing/quota belongs in platform
# ═══════════════════════════════════════════════════════════════════════


class TestPlatformResponsibilitiesNotInCore:
    """Core must not own platform-layer responsibilities."""

    def test_no_tenant_management_in_core(self):
        """Tenant policies, quotas, and usage CRUD must live in platform.

        Allowed exceptions:
        - syscall-level usage tracking (add_tenant_usage in llm.py) — legitimate
        - ops/exporter.py CSV exports — admin utility
        - Comments/documentation referencing tenant concepts
        Only flag: DDL (CREATE TABLE), full CRUD methods, and policy engine tenant logic.
        """
        violations = []
        exempt = re.compile(r"tests/|__pycache__|\.bak$")
        # Only check for DDL-level tenant management (CREATE TABLE tenant_*)
        # and full CRUD methods (get/upsert/list tenant_*)
        for pat in ["tenant_quotas", "tenant_policies"]:
            for f in sorted(CORE_DIR.rglob("*.py")):
                if exempt.search(str(f)):
                    continue
                try:
                    text = f.read_text(errors="ignore")
                except Exception:
                    continue
                if pat not in text:
                    continue
                # File has transitional marker → allowed
                if _has_boundary_marker(text, r"DEPRECATED:.*migrate\s+to\s+platform"):
                    continue
                # Check for DDL or CRUD patterns (not syscall tracking or comments)
                for i, line in enumerate(text.split("\n"), 1):
                    if pat not in line:
                        continue
                    lower = line.strip().lower()
                    # Skip: syscall tracking, ops exports, comments, migration plans
                    if any(kw in lower for kw in ("add_tenant_usage", "export_tenant", "#", "//", "migrate", "transitional")):
                        continue
                    # Flag: DDL or CRUD operations
                    if any(kw in lower for kw in ("create table", "upsert_tenant", "get_tenant_", "list_tenant_")):
                        violations.append(
                            f"  {f.relative_to(ROOT)}:{i}: {line.strip()[:120]}"
                        )
                        break

        assert not violations, (
            f"Core MUST NOT manage tenant quotas/policies DDL or CRUD directly. "
            f"Tenant management belongs in platform layer per docs/index.md §Layer 2. "
            f"Found {len(violations)} violations:\n" + "\n".join(violations[:10])
        )

    def test_no_marketplace_in_core_routers(self):
        """Workspace/marketplace skill CRUD must move to platform API.

        These routers serve platform-level concerns (governance, installer,
        marketplace) from core's FastAPI server. The code itself acknowledges
        this with ⚠ BOUNDARY BLUR markers.
        """
        marketplace_routers = [
            "workspace_skills_meta.py",
            "workspace_packages.py",
            "skill_packs.py",
            "packages_registry.py",
        ]
        violations = []
        for name in marketplace_routers:
            path = CORE_DIR / "api" / "routers" / name
            if not path.exists():
                continue
            text = _read_head(path, 20)
            if not _has_boundary_marker(text, r"BOUNDARY BLUR"):
                violations.append(
                    f"  {path.relative_to(ROOT)}: missing ⚠ BOUNDARY BLUR marker"
                )

        assert not violations, (
            f"Marketplace/workspace routers in core/api/routers/ must have ⚠ BOUNDARY BLUR "
            f"markers acknowledging they belong in platform layer.\n"
            f"Add: '⚠ BOUNDARY BLUR (cross-layer audit): ... belongs in aiPlat-platform'\n"
            + "\n".join(violations)
        )

    def test_no_hardcoded_business_roles_in_core_orchestration(self):
        """Orchestration logic must not hardcode business role names or step IDs.

        Enforced by CLAUDE.md §0.8 (内核无关应用). Role→mode and role→gate
        mappings must come from config (env vars), not if/elif on Chinese text.
        """
        orch = CORE_DIR / "orchestration" / "orchestrator.py"
        if not orch.exists():
            return  # orchestration module may not exist
        text = orch.read_text(errors="ignore")
        # Detect patterns like: if "验证" in step.role, if step.id == "arch"
        hardcoded_patterns = [
            r'if\s+"[^"]+"\s+in\s+step\.role',
            r'if\s+step\.id\s*==\s*"[^"]+"',
        ]
        violations = []
        for pat in hardcoded_patterns:
            for m in re.finditer(pat, text):
                line_no = text[: m.start()].count("\n") + 1
                line = text.split("\n")[line_no - 1].strip()[:120]
                if "os.getenv" in line or "AIPLAT_" in line or "role_modes" in line:
                    continue  # config-driven — allowed
                violations.append(f"  {orch.relative_to(ROOT)}:{line_no}: {line}")

        assert not violations, (
            f"Core orchestration must not hardcode business role names or step IDs. "
            f"Use config-driven mappings (env vars). "
            f"Found {len(violations)} violations:\n" + "\n".join(violations[:10])
        )


# ═══════════════════════════════════════════════════════════════════════
# §L2: Core-Only Responsibilities — Must NOT Live in Platform
# Per boundary-standard.md §铁律1: 模型推理归属 Core
# ═══════════════════════════════════════════════════════════════════════


class TestCoreResponsibilitiesNotInPlatform:
    """Platform must not own core-layer responsibilities."""

    def test_no_ai_model_inference_in_platform(self):
        """Model inference (LLM, Whisper, Tesseract) must live in core, not platform.

        Doc parsing and model loading belong in core/harness/document/.
        Platform should delegate via core or CoreFacade, not call directly.
        """
        violations = []
        exempt = re.compile(r"tests/|__pycache__|poc/|BOUNDARY\.yaml")
        model_imports = [
            r"import\s+faster_whisper",
            r"import\s+whisper\b",
            r"from\s+faster_whisper",
            r"from\s+whisper\b",
            r"import\s+pytesseract",
            r"import\s+paddleocr",
            r"import\s+sentence_transformers",
            r"from\s+sentence_transformers",
        ]

        for f in sorted(PLATFORM_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for pat in model_imports:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    line_no = text[: m.start()].count("\n") + 1
                    violations.append(
                        f"  {f.relative_to(ROOT)}:{line_no}: {m.group()}"
                    )

        assert not violations, (
            f"Platform MUST NOT directly import AI model libraries. "
            f"Model inference belongs in core per boundary-standard.md §铁律1. "
            f"Found {len(violations)} violations:\n" + "\n".join(violations[:10])
        )

    def test_platform_delegates_parsing_to_core(self):
        """Document parsing in platform should delegate to core's document layer.

        Platform's KB module at kb/intelligence/doc_parser.py correctly re-exports
        from core. Other parsing code in platform should follow the same pattern
        or be marked as PoC/experimental.
        """
        # Check that kb/intelligence/doc_parser.py re-exports from core
        parser = PLATFORM_DIR / "kb" / "intelligence" / "doc_parser.py"
        if parser.exists():
            text = _read_head(parser, 10)
            assert "core.harness.document" in text, (
                f"Platform's doc_parser.py must delegate to core.harness.document. "
                f"Found: {text[:200]}"
            )

        # Check kb/poc/mineru_extract.py has boundary blur marker
        mineru = PLATFORM_DIR / "kb" / "poc" / "mineru_extract.py"
        if mineru.exists():
            text = _read_head(mineru, 20)
            assert _has_boundary_marker(text, r"BOUNDARY BLUR"), (
                f"Platform's MinerU parser must have BOUNDARY BLUR marker "
                f"acknowledging it should delegate to core's document layer."
            )


# ═══════════════════════════════════════════════════════════════════════
# §L3: Infra-Agnostic — No Business or Application Knowledge in Infra
# Per infra/CLAUDE.md §2.1: infra 必须对应用完全无知
# ═══════════════════════════════════════════════════════════════════════


class TestInfraAgnostic:
    """Infra must contain zero business or application-specific knowledge."""

    def test_no_business_role_names_in_infra(self):
        """Infra must not reference agent/role names like 'architect', 'pm', 'qa'."""
        violations = []
        exempt = re.compile(r"tests/|__pycache__|\.bak$")
        role_names = [
            r"\barchitect_agent\b",
            r"\bpm_agent\b",
            r"\bprogrammer_agent\b",
            r"\bqa_agent\b",
            r"\bfrontend_engineer\b",
            r"\bbackend_developer\b",
        ]

        for f in sorted(INFRA_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for pat in role_names:
                for m in re.finditer(pat, text):
                    line_no = text[: m.start()].count("\n") + 1
                    violations.append(
                        f"  {f.relative_to(ROOT)}:{line_no}: {m.group()}"
                    )

        assert not violations, (
            f"Infra MUST NOT reference business role names. "
            f"Found {len(violations)} violations:\n" + "\n".join(violations[:10])
        )

    def test_no_application_names_in_infra_defaults(self):
        """Infra defaults must use empty strings or generic names, not 'aiPlat' etc."""
        violations = []
        exempt = re.compile(r"tests/|__pycache__|CLAUDE\.md|BOUNDARY\.yaml")
        # Check for "aiPlat" or "ai-platform" used as literal string defaults
        # (not inside env var names like os.getenv("AIPLAT_*"))
        app_patterns = [
            r'=\s*"aiPlat', r'=\s*"aiplat', r'=\s*"ai-platform',
            r'=\s*"frontend"', r'=\s*"management"',
        ]

        for f in sorted(INFRA_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for pat in app_patterns:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    line_no = text[: m.start()].count("\n") + 1
                    line = text.split("\n")[line_no - 1].strip()[:120]
                    # Exclude: env var references (AIPLAT_*)
                    if "AIPLAT_" in line or "os.getenv" in line:
                        continue
                    violations.append(f"  {f.relative_to(ROOT)}:{line_no}: {line}")

        assert not violations, (
            f"Infra defaults must not hardcode application names. "
            f"Found {len(violations)} violations:\n" + "\n".join(violations[:10])
        )

    def test_no_hardware_vendor_strings_in_infra_defaults(self):
        """GPU model defaults must be empty strings, not 'A100'/'H100' etc."""
        violations = []
        exempt = re.compile(r"tests/|__pycache__|CLAUDE\.md")
        gpu_patterns = [r'"A100"', r'"H100"', r'"V100"', r'"T4"', r'"A10G"']

        for f in sorted(INFRA_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for pat in gpu_patterns:
                for m in re.finditer(pat, text):
                    line_no = text[: m.start()].count("\n") + 1
                    violations.append(
                        f"  {f.relative_to(ROOT)}:{line_no}: {m.group()}"
                    )

        assert not violations, (
            f"Infra GPU model defaults must use empty strings, not specific models. "
            f"Found {len(violations)} violations:\n" + "\n".join(violations[:10])
        )


# ═══════════════════════════════════════════════════════════════════════
# §L4: Cross-Layer Call Integrity
# ═══════════════════════════════════════════════════════════════════════


class TestCrossLayerCalls:
    """Verify call patterns match architecture contract."""

    def test_platform_uses_corefacade_for_core_access(self):
        """Platform must use CoreFacade or core.schemas for all core access.

        Direct harness imports are acceptable for:
        - core.harness.knowledge.* (retrieval delegation)
        - core.harness.document.* (parsing delegation)
        - core.harness.infrastructure.infra_bridge (DB access bridge)
        Everything else should go through CoreFacade.
        """
        violations = []
        exempt = re.compile(r"tests/|__pycache__|poc/|\.bak$")
        # Approved direct harness imports (boundary-standard.md §5.2 whitelist)
        approved = re.compile(
            r"infrastructure\.infra_bridge|infrastructure\.database_port|"
            r"knowledge\.db|knowledge\.embedder|knowledge\.utils|"
            r"harness\.document|apps/document_intelligence|"
            r"llm_env|syscalls\.llm|model_injection|intelligence"
        )

        for f in sorted(PLATFORM_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for m in re.finditer(r"from\s+core\.harness\.(\S+)", text):
                target = m.group(1)
                if not approved.search(target):
                    line_no = text[: m.start()].count("\n") + 1
                    violations.append(
                        f"  {f.relative_to(ROOT)}:{line_no}: from core.harness.{target}"
                    )

        # Allow up to 15 violations (known debt: kb/ module needs migration)
        max_allowed = 15
        assert len(violations) <= max_allowed, (
            f"Platform has {len(violations)} unapproved direct core.harness imports "
            f"(max {max_allowed} allowed as known debt). "
            f"Use CoreFacade or add to approved whitelist in boundary-standard.md.\n"
            + "\n".join(violations[:20])
        )

    def test_app_does_not_import_core_or_infra(self):
        """App layer must not have Python imports from core or infra."""
        violations = []
        exempt = re.compile(r"tests/|__pycache__|generated/|\.bak$")

        for f in sorted(APP_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for pat in [r"from\s+core\.", r"import\s+core\.", r"from\s+infra\.", r"import\s+infra\."]:
                for m in re.finditer(pat, text):
                    line_no = text[: m.start()].count("\n") + 1
                    violations.append(
                        f"  {f.relative_to(ROOT)}:{line_no}: {m.group()}"
                    )

        assert not violations, (
            f"App layer MUST NOT import core or infra directly. "
            f"Use HTTP calls to platform API instead. "
            f"Found {len(violations)} violations:\n" + "\n".join(violations[:10])
        )
