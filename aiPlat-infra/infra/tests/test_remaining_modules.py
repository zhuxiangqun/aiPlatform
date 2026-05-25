"""Tests for infra modules: vector chroma/pinecone, cache file/redis."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
import os as _os2; _REPO = _os2.path.basename(str(ROOT))
sys.path.insert(0, str(ROOT / _REPO))


class TestChromaStore:
    def test_import(self):
        from infra.vector.chroma import ChromaStore
        assert ChromaStore is not None


class TestPineconeStore:
    def test_import(self):
        from infra.vector.pinecone import PineconeStore
        assert PineconeStore is not None


class TestCacheFileClient:
    def test_import(self):
        from infra.cache.file_client import FileCacheClient
        assert FileCacheClient is not None


class TestCacheRedisClient:
    def test_import(self):
        from infra.cache.redis_client import RedisCacheClient
        assert RedisCacheClient is not None
