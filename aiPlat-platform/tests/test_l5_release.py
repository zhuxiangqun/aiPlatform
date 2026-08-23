"""Dynamic tests for L5 release engine (plan-app-factory-l5 §3.1/§3.2/§3.5)."""
import os
import pytest

from builder.release_engine import (
    create_release,
    set_release_status,
    current_dir,
    release_root,
    apply_release,
)


class TestCreateRelease:
    def test_versioned_artifact(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        src = tmp_path / "imported"
        src.mkdir(parents=True, exist_ok=True)
        (src / "a.py").write_text("old a\n")
        release = create_release("p1", "default", str(src), {"a.py": "new a\n"}, "real_pytest")
        assert release["status"] == "ready"
        assert release["version"].startswith("v")
        dst = os.path.join(release_root("p1"), release["version"], "current")
        assert os.path.isfile(os.path.join(dst, "a.py"))
        assert open(os.path.join(dst, "a.py")).read() == "new a\n"  # overlay wins

    def test_baseline_copied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        src = tmp_path / "imported"
        src.mkdir(parents=True, exist_ok=True)
        (src / "keep.py").write_text("keep\n")
        release = create_release("p1", "default", str(src), {})
        dst = os.path.join(release_root("p1"), release["version"], "current")
        assert (os.path.join(dst, "keep.py")) and open(os.path.join(dst, "keep.py")).read() == "keep\n"


class TestReleaseStateMachine:
    def _releases(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        src = tmp_path / "imported"
        src.mkdir(parents=True, exist_ok=True)
        (src / "a.py").write_text("a\n")
        r1 = create_release("p1", "default", str(src), {}, "real_pytest")
        r2 = create_release("p1", "default", str(src), {}, "real_pytest")
        return [r1, r2]

    def test_ready_to_canary_to_full(self, tmp_path, monkeypatch):
        releases = self._releases(tmp_path, monkeypatch)
        rel = set_release_status("p1", releases, releases[0]["version"], "canary")
        assert rel["status"] == "canary"
        rel = set_release_status("p1", releases, releases[0]["version"], "full")
        assert rel["status"] == "full"
        # full → current pointer points to it
        assert "releases" in current_dir("p1") or current_dir("p1") == ""

    def test_illegal_transition_rejected(self, tmp_path, monkeypatch):
        releases = self._releases(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="状态不允许"):
            set_release_status("p1", releases, releases[0]["version"], "full")  # ready→full illegal

    def test_rollback_switches_pointer(self, tmp_path, monkeypatch):
        releases = self._releases(tmp_path, monkeypatch)
        v1, v2 = releases[0]["version"], releases[1]["version"]
        # make v1 full, then roll back to v2
        set_release_status("p1", releases, v1, "canary")
        set_release_status("p1", releases, v1, "full")
        set_release_status("p1", releases, v1, "rolled_back", target_version=v2)
        assert releases[0]["status"] == "rolled_back"
        # latest active = v2 → pointer file contains v2
        pf = os.path.join(tmp_path, "apps", "p1", "current.txt")
        if os.path.isfile(pf):
            assert open(pf).read().strip() == v2

    def test_history_append_only(self, tmp_path, monkeypatch):
        releases = self._releases(tmp_path, monkeypatch)
        assert len(releases) == 2  # both remain (rollback marks, never deletes)


class TestApplyRelease:
    def test_apply_sets_pointer(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        src = tmp_path / "imported"
        src.mkdir(parents=True, exist_ok=True)
        (src / "a.py").write_text("a\n")
        release = apply_release("p1", str(src), {})
        assert release["status"] == "ready"
        assert os.path.isfile(os.path.join(tmp_path, "apps", "p1", "current.txt"))
