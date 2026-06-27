"""Golden-path e2e package — 行为平面检查。

这是系统的"行为平面"测试：真正运行链路并断言结果正确，而非静态 grep 源码形状。
本 conftest 负责把 aiPlat-core 加入 import 路径，并提供共享的隔离环境 fixture。
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORE = ROOT / "aiPlat-core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """把全部状态隔离到 tmp，并强制零外部依赖的 embedding 后端。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_KB_TENANTS_DIR", str(tmp_path / "kb" / "tenants"))
    monkeypatch.setenv("AIPLAT_EMBED_BACKEND", "hash")
    return tmp_path


@pytest.fixture(scope="session")
def http_client():
    """进程内 TestClient — 整个测试会话共用一次 reload(server)。

    原因：server lifespan 未取消其创建的后台 task（_evolution_cron 等 while-True
    async task），多次 reload(server) 会累积未清理的 task 导致死锁/卡顿。因此所有
    需要真实 HTTP 服务的 e2e 测试共用此单例，全程只 reload 一次。
    """
    import importlib
    import os
    import tempfile

    tmp = tempfile.mkdtemp(prefix="aiplat_http_")
    keys = ("HOME", "AIPLAT_EXECUTION_DB_PATH", "AIPLAT_KB_TENANTS_DIR", "AIPLAT_EMBED_BACKEND")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["HOME"] = tmp
    os.environ["AIPLAT_EXECUTION_DB_PATH"] = os.path.join(tmp, "exec.sqlite3")
    os.environ["AIPLAT_KB_TENANTS_DIR"] = os.path.join(tmp, "kb", "tenants")
    os.environ["AIPLAT_EMBED_BACKEND"] = "hash"

    import core.server as server

    importlib.reload(server)
    from fastapi.testclient import TestClient

    with TestClient(server.app) as client:
        yield client

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
