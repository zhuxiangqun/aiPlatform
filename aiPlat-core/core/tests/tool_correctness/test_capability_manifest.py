"""
Test for capability verification: verify that capability_manifest.yaml can be
loaded and key capabilities pass their verification checks.

This test runs as part of the CI via architecture_guard.sh.
"""
import sys
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))


class TestCapabilityManifest:

    def test_manifest_loads(self):
        """capability_manifest.yaml should load without YAML errors."""
        import yaml
        manifest_file = WORKSPACE_ROOT / "aiPlat-core/core/management/capability_manifest.yaml"
        assert manifest_file.exists(), f"Manifest not found: {manifest_file}"
        with open(manifest_file) as f:
            data = yaml.safe_load(f)
        caps = data.get("capabilities", [])
        assert len(caps) >= 30, f"Expected >=30 capabilities, got {len(caps)}"

    def test_all_capabilities_have_required_fields(self):
        """Each capability must have id, name, domain, entry_points, provided_by."""
        import yaml
        manifest_file = WORKSPACE_ROOT / "aiPlat-core/core/management/capability_manifest.yaml"
        with open(manifest_file) as f:
            data = yaml.safe_load(f)

        required = ["id", "name", "domain", "entry_points", "provided_by"]
        for cap in data["capabilities"]:
            for field in required:
                assert field in cap, f"Capability '{cap.get('id','?')}' missing field: {field}"
            assert isinstance(cap["provided_by"], list), \
                f"Capability '{cap['id']}': provided_by must be a list"
            for p in cap["provided_by"]:
                assert "module" in p, f"Capability '{cap['id']}': provider missing 'module'"

    def test_entry_points_exist(self):
        """Each capability's entry_point modules should exist as files."""
        import yaml
        manifest_file = WORKSPACE_ROOT / "aiPlat-core/core/management/capability_manifest.yaml"
        with open(manifest_file) as f:
            data = yaml.safe_load(f)

        missing = []
        for cap in data["capabilities"]:
            for ep in cap.get("entry_points", []):
                # Skip script/bash-based entry points
                if ep.endswith(".sh") or not ep.endswith(".py"):
                    continue
                full = WORKSPACE_ROOT / ep
                if not full.exists():
                    missing.append(f"{cap['id']}: {ep}")

        assert missing == [], f"Entry point files not found: {missing}"

    def test_provided_by_modules_exist(self):
        """Each capability's provided_by modules should exist."""
        import yaml
        manifest_file = WORKSPACE_ROOT / "aiPlat-core/core/management/capability_manifest.yaml"
        with open(manifest_file) as f:
            data = yaml.safe_load(f)

        missing = []
        for cap in data["capabilities"]:
            for p in cap.get("provided_by", []):
                mod = p.get("module", "")
                if not mod:
                    continue
                # Skip script/bash-based modules and test directories
                if "/tests/" in mod or mod.endswith(".sh"):
                    continue
                full = WORKSPACE_ROOT / mod
                if not full.exists():
                    missing.append(f"{cap['id']}: {mod}")

        assert missing == [], f"Provider modules not found: {missing}"

    def test_no_duplicate_capability_ids(self):
        """No two capabilities should share the same id."""
        import yaml
        manifest_file = WORKSPACE_ROOT / "aiPlat-core/core/management/capability_manifest.yaml"
        with open(manifest_file) as f:
            data = yaml.safe_load(f)

        ids = [c["id"] for c in data["capabilities"]]
        dups = [i for i in ids if ids.count(i) > 1]
        assert dups == [], f"Duplicate capability IDs: {set(dups)}"
