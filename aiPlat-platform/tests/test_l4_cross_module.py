"""Dynamic tests for L4 cross-module analysis (plan-app-factory-l4 §3.3/§3.4)."""
import pytest

from builder.cross_module import (
    analyze_cross_module,
    impact_closure,
    topological_order,
    scan_module_contracts,
    verify_changed_module_contracts,
)


def _write(root, rel, content):
    fp = root / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content)


def _mod(tmp_path, mid, files):
    root = tmp_path / mid
    for rel, content in files.items():
        _write(root, rel, content)
    return {"module_id": mid, "root": str(root)}


class TestScanContracts:
    def test_api_and_event_declared(self, tmp_path):
        mod = _mod(tmp_path, "auth", {
            "src/auth/main.py": "@router.post('/api/auth/login')\ndef login(): pass\n",
            "src/auth/events.py": "publish('auth.login')\n",
        })
        c = scan_module_contracts(mod["root"])
        assert "/api/auth/login" in c["apis"]
        assert "auth.login" in c["events"]


class TestCrossModuleAnalysis:
    def test_api_contract_dependency(self, tmp_path):
        auth = _mod(tmp_path, "auth", {
            "main.py": "@router.post('/api/auth/login')\ndef login(): pass\n"})
        billing = _mod(tmp_path, "billing", {
            "client.py": "fetch('/api/auth/login')\n"})
        result = analyze_cross_module([auth, billing], str(tmp_path))
        graph = result["graph"]
        assert "billing" in graph["auth"]["depended_by"]
        assert "auth" in graph["billing"]["depends_on"]
        assert graph["billing"]["evidence"]["auth"]["apis"]

    def test_entity_import_dependency(self, tmp_path):
        auth = _mod(tmp_path, "auth", {"models.py": "class User: pass\n"})
        billing = _mod(tmp_path, "billing", {
            "svc.py": "from auth.models import User\n"})
        result = analyze_cross_module([auth, billing], str(tmp_path))
        assert "auth" in result["graph"]["billing"]["depends_on"]
        assert result["graph"]["billing"]["evidence"]["auth"]["entities"]

    def test_event_contract_dependency(self, tmp_path):
        order = _mod(tmp_path, "order", {"events.py": "publish('order.created')\n"})
        notif = _mod(tmp_path, "notif", {"worker.py": "subscribe('order.created')\n"})
        result = analyze_cross_module([order, notif], str(tmp_path))
        assert "order" in result["graph"]["notif"]["depends_on"]

    def test_no_dependency(self, tmp_path):
        a = _mod(tmp_path, "a", {"x.py": "def f(): pass\n"})
        b = _mod(tmp_path, "b", {"y.py": "def g(): pass\n"})
        result = analyze_cross_module([a, b], str(tmp_path))
        assert result["graph"]["a"]["depends_on"] == []
        assert result["graph"]["b"]["depends_on"] == []


class TestImpactClosure:
    def test_transitive_closure(self):
        graph = {
            "a": {"depends_on": [], "depended_by": ["b"]},
            "b": {"depends_on": ["a"], "depended_by": ["c"]},
            "c": {"depends_on": ["b"], "depended_by": []},
        }
        assert set(impact_closure("a", graph)) == {"a", "b", "c"}
        assert impact_closure("c", graph) == ["c"]


class TestTopologicalOrder:
    def test_dependency_first(self):
        graph = {
            "a": {"depends_on": [], "depended_by": ["b"]},
            "b": {"depends_on": ["a"], "depended_by": []},
        }
        assert topological_order(["a", "b"], graph) == ["a", "b"]

    def test_chain_order(self):
        graph = {
            "a": {"depends_on": [], "depended_by": ["b"]},
            "b": {"depends_on": ["a"], "depended_by": ["c"]},
            "c": {"depends_on": ["b"], "depended_by": []},
        }
        order = topological_order(["a", "b", "c"], graph)
        assert order.index("a") < order.index("b") < order.index("c")

    def test_cycle_guard(self):
        graph = {
            "a": {"depends_on": ["b"], "depended_by": []},
            "b": {"depends_on": ["a"], "depended_by": []},
        }
        order = topological_order(["a", "b"], graph)
        assert set(order) == {"a", "b"}  # cycle → fallback, no hang


class TestContractGate:
    """L4 v1.5 §3.5: cross-module merge contract gate."""

    def _graph(self, tmp_path, auth_files, billing_files):
        auth = _mod(tmp_path, "auth", auth_files)
        billing = _mod(tmp_path, "billing", billing_files)
        return analyze_cross_module([auth, billing], str(tmp_path))["graph"]

    def test_route_preserved_ok(self, tmp_path):
        graph = self._graph(tmp_path,
                            {"main.py": "@router.post('/api/auth/login')\ndef login(): pass\n"},
                            {"client.py": "fetch('/api/auth/login')\n"})
        previews = [{"path": "main.py", "new_content": "@router.post('/api/auth/login')\ndef login(): return 1\n"}]
        r = verify_changed_module_contracts("auth", previews, graph)
        assert r["ok"] is True and r["broken"] == []

    def test_route_missing_broken(self, tmp_path):
        graph = self._graph(tmp_path,
                            {"main.py": "@router.post('/api/auth/login')\ndef login(): pass\n"},
                            {"client.py": "fetch('/api/auth/login')\n"})
        # new version deleted the route
        previews = [{"path": "main.py", "new_content": "def login(): return 1\n"}]
        r = verify_changed_module_contracts("auth", previews, graph)
        assert r["ok"] is False
        assert any(b["kind"] == "api" and b["ref"] == "/api/auth/login" for b in r["broken"])
        assert any(b["dependent"] == "billing" for b in r["broken"])

    def test_entity_missing_broken(self, tmp_path):
        graph = self._graph(tmp_path,
                            {"models.py": "class User:\n    pass\n"},
                            {"svc.py": "from auth.models import User\n"})
        previews = [{"path": "models.py", "new_content": "class Account:\n    pass\n"}]
        r = verify_changed_module_contracts("auth", previews, graph)
        assert r["ok"] is False
        assert any(b["kind"] == "entity" and b["ref"] == "User" for b in r["broken"])

    def test_no_dependents_ok(self, tmp_path):
        graph = self._graph(tmp_path,
                            {"a.py": "def f(): pass\n"},
                            {"b.py": "def g(): pass\n"})
        r = verify_changed_module_contracts("a", [], graph)
        assert r["ok"] is True
