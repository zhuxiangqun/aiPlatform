"""Tests for infra/storage/clients.py — storage backends."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
import os as _os2; _REPO = _os2.path.basename(str(ROOT))
sys.path.insert(0, str(ROOT / _REPO))


class TestLocalStorageClient:
    def test_import(self):
        from infra.storage.clients import LocalStorageClient
        assert LocalStorageClient is not None

    def test_construction(self):
        from infra.storage.schemas import StorageConfig
        from infra.storage.clients import LocalStorageClient
        cfg = StorageConfig(type="local")
        client = LocalStorageClient(cfg)
        assert client._base_path is not None

    def test_async_methods_exist(self):
        from infra.storage.schemas import StorageConfig
        from infra.storage.clients import LocalStorageClient
        import asyncio
        client = LocalStorageClient(StorageConfig(type="local"))
        assert asyncio.iscoroutinefunction(client.save)
        assert asyncio.iscoroutinefunction(client.load)
        assert asyncio.iscoroutinefunction(client.delete)


class TestS3StorageClient:
    def test_import(self):
        from infra.storage.clients import S3StorageClient
        assert S3StorageClient is not None


class TestGCSStorageClient:
    def test_import(self):
        from infra.storage.clients import GCSStorageClient
        assert GCSStorageClient is not None


class TestAzureStorageClient:
    def test_import(self):
        from infra.storage.clients import AzureStorageClient
        assert AzureStorageClient is not None


class TestStorageFactory:
    def test_import(self):
        from infra.storage.factory import create_storage_client
        assert callable(create_storage_client)
