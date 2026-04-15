"""storage 模块测试"""

import pytest
import tempfile


class TestStorageClient:
    """存储客户端测试"""

    def test_local_storage(self):
        """测试本地存储"""
        from infra.storage.clients import LocalStorageClient
        from infra.storage.schemas import StorageConfig, FileConfig

        config = StorageConfig(file=FileConfig(base_path=tempfile.gettempdir()))
        client = LocalStorageClient(config)
        assert client is not None


class TestStorageFactory:
    """存储工厂测试"""

    def test_create_storage(self):
        """测试创建存储客户端"""
        from infra.storage.factory import create

        client = create()
        assert client is not None
