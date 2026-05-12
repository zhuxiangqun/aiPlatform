"""
Tests for plugin_validator.py — manifest validation at the platform boundary.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from registry.plugin_validator import validate_plugin_manifest


def test_valid_manifest_passes():
    manifest = {
        "name": "weather-plugin",
        "version": "1.0.0",
        "skills": [{
            "name": "weather",
            "effects": [{"type": "read", "resources": ["http"], "idempotent": True}],
        }],
    }
    assert validate_plugin_manifest(manifest) == []


def test_missing_name():
    manifest = {"version": "1.0.0", "skills": [{"name": "x", "effects": [{"type": "read", "idempotent": True}]}]}
    errors = validate_plugin_manifest(manifest)
    assert any("name is required" in e for e in errors)


def test_no_entry_points():
    manifest = {"name": "test", "version": "1.0.0"}
    errors = validate_plugin_manifest(manifest)
    assert any("skills" in e for e in errors)


def test_skill_no_effects():
    manifest = {"name": "test", "version": "1.0.0", "skills": [{"name": "bad-skill"}]}
    errors = validate_plugin_manifest(manifest)
    assert any("effects declaration required" in e for e in errors)


def test_skill_effects_missing_type():
    manifest = {
        "name": "test", "version": "1.0.0",
        "skills": [{"name": "bad", "effects": [{"idempotent": True}]}],
    }
    errors = validate_plugin_manifest(manifest)
    assert any("effects[].type required" in e for e in errors)


def test_skill_effects_missing_idempotent():
    manifest = {
        "name": "test", "version": "1.0.0",
        "skills": [{"name": "bad", "effects": [{"type": "read"}]}],
    }
    errors = validate_plugin_manifest(manifest)
    assert any("effects[].idempotent required" in e for e in errors)


def test_write_effect_requires_rollback():
    manifest = {
        "name": "test", "version": "1.0.0",
        "skills": [{
            "name": "writer",
            "effects": [{"type": "write", "resources": ["fs"], "idempotent": False}],
            "idempotent": False,
        }],
    }
    errors = validate_plugin_manifest(manifest)
    assert any("rollback_available=true" in e for e in errors)


def test_high_risk_no_permissions():
    manifest = {
        "name": "test", "version": "1.0.0",
        "risk_level": "high",
        "skills": [{"name": "s", "effects": [{"type": "read", "idempotent": True}]}],
    }
    errors = validate_plugin_manifest(manifest)
    assert any("permissions" in e for e in errors)


def test_invalid_mcp_url():
    manifest = {
        "name": "test", "version": "1.0.0",
        "mcp_servers": [{"name": "bad", "url": "ftp://evil.com"}],
    }
    errors = validate_plugin_manifest(manifest)
    assert any("invalid URL" in e for e in errors)


def test_tool_no_schema():
    manifest = {
        "name": "test", "version": "1.0.0",
        "tools": [{"name": "bad-tool"}],
    }
    errors = validate_plugin_manifest(manifest)
    assert any("input_schema required" in e for e in errors)


def test_write_effect_with_idempotent_true():
    manifest = {
        "name": "test", "version": "1.0.0",
        "skills": [{
            "name": "writer",
            "idempotent": True,
            "effects": [{"type": "write", "resources": ["fs"], "idempotent": True, "rollback_available": True}],
        }],
    }
    errors = validate_plugin_manifest(manifest)
    assert any("idempotent=true" in e for e in errors)
