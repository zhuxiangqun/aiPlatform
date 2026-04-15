"""memory 模块测试"""

import pytest


class TestMemoryManager:
    """内存管理器测试"""

    def test_ram_memory_manager(self):
        """测试 RAM 内存管理器"""
        from infra.memory.manager import RAMMemoryManager
        from infra.memory.schemas import MemoryConfig

        config = MemoryConfig()
        manager = RAMMemoryManager(config)
        assert manager is not None


class TestMemorySchema:
    """内存数据模型测试"""

    def test_memory_config(self):
        """测试 MemoryConfig"""
        from infra.memory.schemas import MemoryConfig

        config = MemoryConfig()
        assert config is not None

    def test_allocation(self):
        """测试 Allocation"""
        from infra.memory.schemas import Allocation

        alloc = Allocation(size=1024)
        assert alloc.size == 1024
