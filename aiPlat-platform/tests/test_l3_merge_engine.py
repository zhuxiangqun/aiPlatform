"""Dynamic tests for L3 incremental merge engine (plan-app-factory-l3 §3.3/§3.5)."""
import pytest

from builder.merge_engine import (
    analyze_impact,
    build_merge_preview,
    syntax_check,
    verify_interface_preserved,
    apply_merge,
    snapshot_affected_files,
    verify_snapshot,
    _categorize_hunk,
)


def _write(tmp_path, rel, content):
    fp = tmp_path / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content)
    return fp


class TestImpactAnalyzer:
    def test_affected_includes_checked(self, tmp_path):
        _write(tmp_path, "src/auth/login.py", "import user\n")
        _write(tmp_path, "src/models/user.py", "class User: pass\n")
        manifest = [{"path": "src/auth/login.py"}, {"path": "src/models/user.py"}]
        result = analyze_impact(str(tmp_path), [{"path": "src/auth/login.py", "intent": "加验证码"}], manifest)
        assert "src/auth/login.py" in result["affected"]
        # import user → src.models.user resolves to src/models/user.py
        assert "src/models/user.py" in result["auto_added"]

    def test_importers_detected(self, tmp_path):
        _write(tmp_path, "core/api.py", "def f(): pass\n")
        _write(tmp_path, "core/usage.py", "from core.api import f\n")
        manifest = [{"path": "core/api.py"}, {"path": "core/usage.py"}]
        result = analyze_impact(str(tmp_path), [{"path": "core/api.py", "intent": "改接口"}], manifest)
        assert "core/usage.py" in result["auto_added"]  # reverse reference

    def test_non_python_ignored(self, tmp_path):
        _write(tmp_path, "app.ts", "import { x } from './y'\n")
        _write(tmp_path, "y.ts", "export const x = 1\n")
        manifest = [{"path": "app.ts"}, {"path": "y.ts"}]
        result = analyze_impact(str(tmp_path), [{"path": "app.ts", "intent": "改"}], manifest)
        assert result["auto_added"] == []  # v1: python-only


class TestDiffMerger:
    def test_preview_counts(self):
        old = "def login():\n    return 'old'\n\n\n"
        new = "def login():\n    return 'new'\n\n\n"
        pv = build_merge_preview(old, new, "src/auth/login.py")
        assert pv["has_changes"] is True
        assert pv["changed_lines"] >= 1
        assert pv["hunks"], "must have at least one hunk"

    def test_unchanged_file_has_no_changes(self):
        content = "def f():\n    pass\n"
        pv = build_merge_preview(content, content, "a.py")
        assert pv["has_changes"] is False
        assert pv["changed_lines"] == 0

    def test_syntax_check(self):
        assert syntax_check("def f():\n    pass\n", "a.py")["ok"] is True
        bad = syntax_check("def f(:\n", "a.py")
        assert bad["ok"] is False and "line" in bad["error"]

    def test_interface_preserved(self):
        old = "def login():\n    pass\n\n@app.post('/login')\ndef do_login():\n    pass\n"
        new = "def login():\n    return 'new'\n"
        check = verify_interface_preserved(old, new, "auth.py")
        assert check["ok"] is False
        assert any("login" in m for m in check["missing"])

    def test_interface_ok_when_preserved(self):
        old = "def login():\n    pass\n"
        new = "def login():\n    return 'new'\n"
        check = verify_interface_preserved(old, new, "auth.py")
        assert check["ok"] is True


class TestApplyMerge:
    def test_apply_atomic_all_approved(self, tmp_path):
        import_root = tmp_path / "imported"
        _write(import_root, "a.py", "old a\n")
        _write(import_root, "b.py", "old b\n")
        deploy_dir = tmp_path / "deploy"
        # simulate an existing deployment (prior state snapshot target)
        _write(deploy_dir, "a.py", "old a\n")
        _write(deploy_dir, "b.py", "old b\n")
        previews = [
            {"path": "a.py", "new_content": "new a\n"},
            {"path": "b.py", "new_content": "new b\n"},
        ]
        result = apply_merge("p1", str(import_root), str(deploy_dir), previews,
                             {"a.py": "approved", "b.py": "approved"})
        assert result["applied"] == ["a.py", "b.py"]
        assert result["rejected"] == []
        assert (deploy_dir / "a.py").read_text() == "new a\n"
        assert (deploy_dir / "b.py").read_text() == "new b\n"
        # snapshot created with pre-merge content
        assert (tmp_path / "deploy.prev").is_dir()
        assert (tmp_path / "deploy.prev" / "a.py").read_text() == "old a\n"

    def test_apply_partial_approval_rejected_atomically(self, tmp_path):
        """L3-P0-01: any missing/rejected path → ValueError, nothing written."""
        import_root = tmp_path / "imported"
        _write(import_root, "a.py", "old a\n")
        _write(import_root, "b.py", "old b\n")
        deploy_dir = tmp_path / "deploy"
        _write(deploy_dir, "a.py", "old a\n")
        _write(deploy_dir, "b.py", "old b\n")
        previews = [
            {"path": "a.py", "new_content": "new a\n"},
            {"path": "b.py", "new_content": "new b\n"},
        ]
        with pytest.raises(ValueError, match="原子化"):
            apply_merge("p2", str(import_root), str(deploy_dir), previews,
                        {"a.py": "approved", "b.py": "rejected"})
        # nothing written
        assert (deploy_dir / "a.py").read_text() == "old a\n"
        assert (deploy_dir / "b.py").read_text() == "old b\n"

    def test_apply_missing_preview_ignored(self, tmp_path):
        import_root = tmp_path / "imported"
        _write(import_root, "a.py", "old\n")
        deploy_dir = tmp_path / "deploy"
        with pytest.raises(ValueError, match="没有合并预览"):
            apply_merge("p3", str(import_root), str(deploy_dir), [], {"a.py": "approved"})


class TestSnapshotGuard:
    """L3-P0-02: sha256 snapshot before generation, verify before apply."""

    def test_snapshot_and_verify_unchanged(self, tmp_path):
        _write(tmp_path, "a.py", "old a\n")
        snap = snapshot_affected_files(str(tmp_path), ["a.py", "missing.py"])
        assert "a.py" in snap
        assert "missing.py" not in snap  # nonexistent skipped
        ok, changed = verify_snapshot(str(tmp_path), snap)
        assert ok is True and changed == []

    def test_verify_detects_external_modification(self, tmp_path):
        _write(tmp_path, "a.py", "old a\n")
        snap = snapshot_affected_files(str(tmp_path), ["a.py"])
        # external modification during generation
        _write(tmp_path, "a.py", "user edited a\n")
        ok, changed = verify_snapshot(str(tmp_path), snap)
        assert ok is False and changed == ["a.py"]

    def test_verify_detects_deleted_file(self, tmp_path):
        _write(tmp_path, "a.py", "old a\n")
        snap = snapshot_affected_files(str(tmp_path), ["a.py"])
        (tmp_path / "a.py").unlink()
        ok, changed = verify_snapshot(str(tmp_path), snap)
        assert ok is False and "a.py" in changed


class TestHunkCategorization:
    """L3-P1-04: formatting (whitespace-only) vs logic hunks."""

    def test_formatting_hunk(self):
        lines = ["@@ -1,3 +1,3 @@", "-a=1", "+a = 1"]
        assert _categorize_hunk(lines) == "formatting"

    def test_blank_line_hunk(self):
        lines = ["@@ -1,2 +1,3 @@", "-", "+"]
        assert _categorize_hunk(lines) == "formatting"

    def test_logic_hunk(self):
        lines = ["@@ -1,3 +1,3 @@", "-return 'old'", "+return 'new'"]
        assert _categorize_hunk(lines) == "logic"

    def test_preview_marks_logic_changes(self):
        old = "def login():\n    return 'old'\n\n\n"
        new = "def login():\n    return 'new'\n\n\n"
        pv = build_merge_preview(old, new, "a.py")
        assert pv["logic_changes"] >= 1
        assert any(h.get("category") == "logic" for h in pv["hunks"])
