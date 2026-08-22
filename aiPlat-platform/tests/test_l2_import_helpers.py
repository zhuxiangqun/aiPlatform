"""Dynamic tests for L2 import helpers (plan-app-factory-l2-import-repo.md §3.3/§3.6/§3.8).

Covers: zip-slip rejection, manifest scan with sensitive-file skip, has_tests
detection, missing_deps pre-check hints.
"""
import io
import zipfile

import pytest

from builder.builder_project_service import (
    _safe_extract_zip,
    _scan_imported,
    _detect_tests,
    _detect_missing_deps,
)


def _make_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestSafeExtractZip:
    def test_normal_zip_extracts_all(self, tmp_path):
        data = _make_zip({
            "src/auth/login.py": "def login(): pass\n",
            "src/models/user.py": "class User: pass\n",
            "README.md": "# demo\n",
        })
        _safe_extract_zip(data, str(tmp_path))
        assert (tmp_path / "src/auth/login.py").is_file()
        assert (tmp_path / "src/models/user.py").is_file()
        assert (tmp_path / "README.md").is_file()

    def test_zip_slip_rejected(self, tmp_path):
        data = _make_zip({"../evil.txt": "pwned\n"})
        with pytest.raises(ValueError, match="zip-slip|路径越界"):
            _safe_extract_zip(data, str(tmp_path))
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_absolute_path_rejected(self, tmp_path):
        data = _make_zip({"/etc/passwd": "root:x\n"})
        with pytest.raises(ValueError):
            _safe_extract_zip(data, str(tmp_path))

    def test_nested_traversal_rejected(self, tmp_path):
        data = _make_zip({"a/../../evil.txt": "pwned\n"})
        with pytest.raises(ValueError, match="zip-slip|路径越界"):
            _safe_extract_zip(data, str(tmp_path))


class TestScanImported:
    def test_manifest_counts(self, tmp_path):
        for rel in ("a.py", "b.py", "sub/c.py"):
            fp = tmp_path / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text("print('x')\n")
        manifest, too_many = _scan_imported(str(tmp_path))
        assert too_many is False
        assert len(manifest) == 3
        paths = {m["path"] for m in manifest}
        assert paths == {"a.py", "b.py", "sub/c.py"}
        assert all(m["lang"] for m in manifest)

    def test_sensitive_files_skipped(self, tmp_path):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src/app.py").write_text("ok\n")
        (tmp_path / ".env").write_text("SECRET=1\n")
        (tmp_path / "src/keys.pem").write_text("PRIVATE\n")
        (tmp_path / "secrets").mkdir(exist_ok=True)
        (tmp_path / "secrets/db.yaml").write_text("password: x\n")
        manifest, _ = _scan_imported(str(tmp_path))
        paths = {m["path"] for m in manifest}
        assert "src/app.py" in paths
        assert ".env" not in paths
        assert "src/keys.pem" not in paths
        assert "secrets/db.yaml" not in paths


class TestDetectTests:
    def test_tests_dir(self, tmp_path):
        (tmp_path / "tests").mkdir()
        assert _detect_tests(str(tmp_path)) is True

    def test_test_dir(self, tmp_path):
        (tmp_path / "test").mkdir()
        assert _detect_tests(str(tmp_path)) is True

    def test_no_tests(self, tmp_path):
        (tmp_path / "src").mkdir()
        assert _detect_tests(str(tmp_path)) is False


class TestDetectMissingDeps:
    def test_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text(
            "pymysql>=1.0\n# comment\nflask==2.0\n")
        hints = _detect_missing_deps(str(tmp_path))
        joined = " | ".join(hints)
        assert "pymysql" in joined
        assert "flask" in joined
        assert "comment" not in joined

    def test_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react": "^18", "axios": "^1"}, "devDependencies": {"typescript": "^5"}}')
        hints = _detect_missing_deps(str(tmp_path))
        joined = " | ".join(hints)
        assert "react" in joined and "axios" in joined

    def test_no_dep_files(self, tmp_path):
        assert _detect_missing_deps(str(tmp_path)) == []
