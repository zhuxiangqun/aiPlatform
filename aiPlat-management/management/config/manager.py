"""
配置管理器
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ConfigVersion:
    """配置版本"""
    version: str
    layer: str
    config: Dict[str, Any]
    timestamp: datetime
    author: str = ""
    

class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.configs: Dict[str, Dict[str, Any]] = {
            "infra": {},
            "core": {},
            "platform": {},
            "app": {}
        }
        self.versions: Dict[str, list] = {
            "infra": [],
            "core": [],
            "platform": [],
            "app": []
        }
        
    async def get_config(self, layer: str) -> Dict[str, Any]:
        """获取层配置"""
        return self.configs.get(layer, {})
        
    async def update_config(
        self, 
        layer: str, 
        config: Dict[str, Any],
        author: str = ""
    ) -> str:
        """更新配置"""
        # 保存旧版本
        old_config = self.configs.get(layer, {})
        version = ConfigVersion(
            version=f"v{len(self.versions[layer]) + 1}",
            layer=layer,
            config=old_config,
            timestamp=datetime.utcnow(),
            author=author
        )
        self.versions[layer].append(version)
        
        # 更新配置
        self.configs[layer] = config
        
        return version.version
        
    async def get_versions(self, layer: str) -> list:
        """获取配置历史"""
        return self.versions.get(layer, [])
        
    async def rollback(self, layer: str, version: str) -> bool:
        """回滚到指定版本"""
        versions = self.versions.get(layer, [])
        for v in versions:
            if v.version == version:
                self.configs[layer] = v.config
                return True
        return False
