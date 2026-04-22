import anyio


def test_ssh_exec_driver_not_configured(monkeypatch):
    monkeypatch.delenv("AIPLAT_SSH_HOST", raising=False)
    from core.apps.exec_drivers.ssh import SSHExecDriver

    d = SSHExecDriver()
    h = anyio.run(d.health)
    assert h["ok"] is False
    assert h["error"] == "ssh_not_configured"

