import anyio


def test_exec_driver_capabilities_shape():
    from core.apps.exec_drivers.local import LocalExecDriver
    from core.apps.exec_drivers.docker import DockerExecDriver
    from core.apps.exec_drivers.ssh import SSHExecDriver

    loc = LocalExecDriver().capabilities()
    assert "supported_languages" in loc
    assert set(loc["supported_languages"]) >= {"python", "javascript"}
    assert loc["isolation"]["network_isolated"] is False

    dock = DockerExecDriver().capabilities()
    assert dock["isolation"]["network_isolated"] is True
    assert "AIPLAT_DOCKER_MEM" in dock["config"]["env"]

    ssh = SSHExecDriver().capabilities()
    assert ssh["config"]["required"] is True
    assert "AIPLAT_SSH_HOST" in ssh["config"]["env"]


def test_registry_healthcheck_includes_capabilities(monkeypatch):
    monkeypatch.delenv("AIPLAT_SSH_HOST", raising=False)
    from core.apps.exec_drivers.registry import healthcheck_backends

    out = anyio.run(healthcheck_backends)
    assert isinstance(out, dict)
    backends = out.get("backends")
    assert isinstance(backends, list)
    assert len(backends) >= 2
    assert all(isinstance(b, dict) and "capabilities" in b for b in backends)

