"""
Ollama Scanner - 扫描本地 Ollama 模型

Scans locally installed Ollama models via API.
"""

import aiohttp
from typing import List
from datetime import datetime

from .schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig


class OllamaScanner:
    """Ollama 模型扫描器"""
    
    def __init__(self, endpoint: str = "http://localhost:11434"):
        self.endpoint = endpoint
    
    def set_endpoint(self, endpoint: str):
        """设置 Ollama 端点"""
        self.endpoint = endpoint
    
    async def is_available(self) -> bool:
        """检查 Ollama 是否可用"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.endpoint}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    async def scan(self) -> List[ModelInfo]:
        """扫描本地 Ollama 模型"""
        models = []
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.endpoint}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return models
                    
                    data = await resp.json()
                    
                    for item in data.get("models", []):
                        model_name = item.get("name", "")
                        if not model_name:
                            continue
                        
                        details = item.get("details", {})
                        
                        model = ModelInfo(
                            id=f"ollama:{model_name}",
                            name=model_name,
                            display_name=model_name.split(":")[0] if ":" in model_name else model_name,
                            type=ModelType.CHAT,
                            provider="ollama",
                            source=ModelSource.LOCAL,
                            enabled=True,
                            status=ModelStatus.AVAILABLE,
                            config=ModelConfig(
                                base_url=self.endpoint,
                                temperature=0.7,
                                max_tokens=4096,
                            ),
                            description=details.get("family", ""),
                            tags=["ollama", "local", details.get("family", "")] if details.get("family") else ["ollama", "local"],
                            capabilities=self._get_capabilities(details),
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                        )
                        models.append(model)
        
        except Exception as e:
            # Ollama 未运行时返回空列表
            pass
        
        return models
    
    def _get_capabilities(self, details: dict) -> List[str]:
        """获取模型能力"""
        capabilities = ["chat"]
        
        if details.get("embedding"):
            capabilities.append("embedding")
        if "vision" in details.get("families", []):
            capabilities.append("vision")
        
        return capabilities
    
    async def get_model_info(self, model_name: str) -> dict:
        """获取模型详细信息"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.endpoint}/api/show",
                    json={"name": model_name},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return {}