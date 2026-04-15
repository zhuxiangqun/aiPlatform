"""
Config Module - Base Interfaces

配置模块基础接口定义
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional

from .config import Config


class ConfigLoader(ABC):
    """
    配置加载器抽象基类
    
    负责从多个配置源加载和合并配置
    
    Methods:
        load(path: Optional[str]) -> Config: 加载配置
        reload() -> Config: 重新加载配置
        watch(callback: Callable) -> None: 监听配置变化
    """

    @abstractmethod
    def load(self, path: Optional[str] = None) -> Config:
        """
        加载配置，自动合并多源
        
        Args:
            path: 配置文件路径（可选）
        
        Returns:
            Config: 配置对象
        
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置格式错误
        """
        pass

    @abstractmethod
    def reload(self) -> Config:
        """
        重新加载配置
        
        Returns:
            Config: 重新加载后的配置对象
        """
        pass

    @abstractmethod
    def watch(self, callback: Callable[[List[str], Config], None]) -> None:
        """
        监听配置变化
        
        Args:
            callback: 配置变化时的回调函数
                - changed_keys: 变化的配置项列表
                - new_config: 新的配置对象
        """
        pass


class ConfigSource(ABC):
    """
    配置源抽象基类
    
    定义配置源的统一接口
    
    Attributes:
        priority: 配置源优先级（数值越大优先级越高）
    
    Methods:
        load() -> dict: 加载配置
        watch(callback: Callable) -> None: 监听配置源变化
    """

    @property
    @abstractmethod
    def priority(self) -> int:
        """
        配置源优先级
        
        Returns:
            int: 优先级数值（数值越大优先级越高）
        
        Examples:
            FileSource: 0 (默认) / 75 (环境)
            EnvSource: 100 (最高)
        """
        pass

    @abstractmethod
    def load(self) -> dict:
        """
        加载配置
        
        Returns:
            dict: 配置字典
        """
        pass

    def watch(self, callback: Callable[[List[str]], None]) -> None:
        """
        监听配置源变化（可选实现）
        
        Args:
            callback: 配置变化时的回调函数
        """
        pass