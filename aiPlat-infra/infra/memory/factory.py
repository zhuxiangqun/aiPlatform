"""factory：模块接口。"""

from typing import Optional
from .schemas import MemoryConfig
from .base import MemoryManager


def create(config: Optional[MemoryConfig] = None) -> MemoryManager:
    """创建内存管理器（便捷函数）。

    Args:
        config: config 参数。
    """
    return create_memory_manager(config)


def create_memory_manager(config: Optional[MemoryConfig] = None) -> MemoryManager:
    """创建 memory_manager。

    Args:
        config: config 参数。
    """
    config = config or MemoryConfig()

    if config.type == "ram":
        from .manager import RAMMemoryManager

        return RAMMemoryManager(config)
    elif config.type == "vram":
        from .manager import VRAMMemoryManager

        return VRAMMemoryManager(config)
    else:
        raise ValueError(f"Unknown memory type: {config.type}")
