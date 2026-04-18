import os

from core.harness.context.engine import DefaultContextEngine


def test_context_engine_compacts_when_too_many_messages(monkeypatch):
    monkeypatch.setenv("AIPLAT_CONTEXT_MAX_MESSAGES", "20")
    monkeypatch.setenv("AIPLAT_CONTEXT_KEEP_LAST", "5")

    eng = DefaultContextEngine()
    msgs = [{"role": "system", "content": "S"}]
    for i in range(30):
        msgs.append({"role": "user", "content": f"u{i} hello"})
        msgs.append({"role": "assistant", "content": f"a{i} world"})

    res = eng.apply(messages=msgs, metadata={}, repo_root=None)
    assert res.metadata.get("context_compacted") is True
    assert any(m.get("role") == "system" and "# Context Summary" in str(m.get("content", "")) for m in res.messages)

    # cleanup env for other tests
    os.environ.pop("AIPLAT_CONTEXT_MAX_MESSAGES", None)
    os.environ.pop("AIPLAT_CONTEXT_KEEP_LAST", None)

