"""
Model Manager - 模型管理器

Manages AI models from three sources:
- config_models: Models from YAML config (read-only)
- local_models: Models from Ollama (dynamic scan)
- external_models: User-added models (JSON storage)
"""

import asyncio
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from .schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig
from ..base import Status, HealthStatus
from .storage import ExternalModelStorage
from .config_loader import ConfigLoader
from .local_model_scanner import scan_local_models
from .health_checker import HealthChecker


def _write_env_local(key: str, value: str) -> None:
    """Write an env var to ~/.aiplat/.env.local, creating or updating the line."""
    from pathlib import Path
    env_file = Path.home() / ".aiplat" / ".env.local"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}=") or line.startswith(f"export {key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    env_file.write_text("\n".join(lines) + "\n")


class ModelManager:
    """模型管理器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._models: Dict[str, ModelInfo] = {}
        self._providers: Dict[str, Any] = {}
        self._local_scanned = False
        
        # 初始化组件
        config_path = self.config.get("config_path")
        data_path = self.config.get("data_path")
        
        self._config_loader = ConfigLoader(config_path)
        self._storage = ExternalModelStorage(data_path)
        self._health_checker = HealthChecker()
        self._local_endpoints: List[str] = []
        
        # 加载所有模型
        self._load_all_models()
    
    def _load_all_models(self):
        """加载所有模型"""
        # 1. 加载配置文件模型
        config_models = self._config_loader.load()
        for model in config_models:
            self._models[model.id] = model
        
        # 2. 加载用户添加的外部模型
        external_models = self._storage.load()
        for model in external_models:
            self._models[model.id] = model
        
        # 3. 扫描本地 Ollama / LM Studio / vLLM 模型（同步，短超时）
        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(asyncio.wait_for(
                    self._scan_local_models(), timeout=10.0))
            finally:
                loop.close()
        except Exception:
            pass
    
    async def initialize(self):
        """异步初始化 - 扫描本地模型"""
        await self._scan_local_models()
    
    async def _scan_local_models(self):
        """Scan local model endpoints (Ollama, LM Studio, oMLX, etc.)."""
        try:
            endpoints = self._config_loader.get_local_scan_endpoints()
            if not endpoints:
                return
            self._local_endpoints = endpoints
            local_models = await scan_local_models(endpoints)
            for model in local_models:
                if model.id not in self._models:
                    self._models[model.id] = model
                else:
                    existing = self._models[model.id]
                    if existing.source == ModelSource.LOCAL:
                        existing.status = model.status
                        existing.config.base_url = model.config.base_url
        except Exception:
            pass
    
    # ===== 查询接口 =====
    
    async def list_models(
        self,
        source: Optional[str] = None,
        type: Optional[str] = None,
        enabled: Optional[bool] = None,
        status: Optional[str] = None
    ) -> List[ModelInfo]:
        """获取模型列表（首次调用自动扫描本地模型）"""
        if not self._local_scanned:
            self._local_scanned = True
            await self._scan_local_models()
        models = list(self._models.values())
        
        # 过滤
        if source:
            models = [m for m in models if m.source.value == source]
        if type:
            models = [m for m in models if m.type.value == type]
        if enabled is not None:
            models = [m for m in models if m.enabled == enabled]
        if status:
            models = [m for m in models if m.status.value == status]
        
        # 按来源和名称排序
        def sort_key(m):
            source_order = {"config": 0, "external": 1, "local": 2}
            return (source_order.get(m.source.value, 3), m.name)
        
        models.sort(key=sort_key)
        return models
    
    async def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """获取单个模型"""
        return self._models.get(model_id)

    def get_default_model(self, purpose: str = "default") -> str:
        """Resolve purpose to model name via env vars (unique resolution point).

        Covers all 9 purposes for centralized, env-driven model selection.
        """
        import os
        purpose_env_map = {
            "agent":       ("AIPLAT_AGENT_MODEL", "AIPLAT_DEFAULT_AGENT_MODEL"),
            "reasoning":   ("AIPLAT_AGENT_MODEL", "AIPLAT_DEFAULT_AGENT_MODEL"),
            "document":    ("AIPLAT_DOC_LLM_MODEL",),
            "code_gen":    ("AIPLAT_CODE_GEN_MODEL",),
            "code":        ("AIPLAT_CODE_GEN_MODEL",),
            "query_translation": ("AIPLAT_QUERY_MODEL",),
            "wiki_curation": ("AIPLAT_WIKI_CURATION_MODEL",),
            "eval_code":   ("AIPLAT_EVAL_MODEL",),
        }
        if purpose in purpose_env_map:
            for env_name in purpose_env_map[purpose]:
                val = os.getenv(env_name, "").strip()
                if val:
                    return val
        return (os.getenv("AIPLAT_DEFAULT_CHAT_MODEL", "").strip()
                or os.getenv("AIPLAT_LLM_MODEL", "").strip()
                or os.getenv("AIPLAT_DEFAULT_MODEL", "").strip())

    def select_by_purpose(self, purpose: str) -> Optional[str]:
        """Select best model for purpose via capability scoring.

        Loads PURPOSE_PROFILE from llm_profile.yaml, filters enabled chat models,
        scores by capability match + source preference, returns best model name.
        This is the canonical model selection for all core purpose-driven calls.
        """
        try:
            import yaml
            from pathlib import Path
            config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
                str(Path(__file__).resolve().parent.parent.parent.parent /
                    "config" / "infra" / "llm_profile.yaml"))
            profile_data = yaml.safe_load(open(config_path))
        except Exception:
            profile_data = {}

        profiles = profile_data.get("purpose_profiles", {})
        profile = profiles.get(purpose, {"prefer": ["chat"], "avoid": []})
        fallback_model = profile_data.get("fallback", {}).get("ultimate_model", "deepseek-chat")

        # Priority: explicit model_overrides in config
        overrides = profile_data.get("model_overrides", {})
        if purpose in overrides:
            override_name = overrides[purpose]
            if override_name:
                # Match by model name (not ID — IDs have provider prefix)
                for m in self._models.values():
                    if m.name == override_name and m.enabled:
                        return m.name
                # Fallback: try matching by ID
                if override_name in self._models:
                    return override_name

        # Filter chat models
        chat_models = [m for m in self._models.values()
                       if hasattr(m, 'type') and m.type.value == "chat" and m.enabled]

        scored = []
        for m in chat_models:
            caps = set(m.capabilities or ["chat"]) | set(m.tags or [])
            if not any(c in caps for c in profile.get("prefer", ["chat"])):
                continue
            if any(c in caps for c in profile.get("avoid", [])):
                continue

            score = 0
            if profile.get("prefer_local"):
                if m.source.value == "local":
                    score += 120
                elif m.source.value == "external":
                    score += 60
                else:
                    score += 40
            elif m.source.value == "config":
                score += 100

            if "reasoning" in caps:
                if profile.get("prefer", [""])[0] == "reasoning":
                    score += 80
                else:
                    score -= 30
            else:
                if profile.get("prefer", [""])[0] != "reasoning":
                    score += 50

            if "function_call" in caps:
                score += 20

            scored.append((score, m.name))

        if not scored:
            return fallback_model

        scored.sort(key=lambda x: (x[0], x[1] == fallback_model), reverse=True)
        return scored[0][1]  # model name

    def select(self, model_name: str = "", purpose: str = "") -> Optional[ModelInfo]:
        """Select model by name or purpose. Returns full ModelInfo with provider/base_url/api_key_env.

        Resolution order:
          1. model_name given → use directly
          2. purpose given → resolve via get_default_model(purpose)
          3. fallback → get_default_model("default")
        Returns None if model not found in registry.
        """
        name = model_name.strip() if model_name else ""
        if not name and purpose:
            name = self.get_default_model(purpose)
        if not name:
            name = self.get_default_model("default")
        if not name:
            return None
        return self._models.get(name)

    # ===== 管理接口 =====
    
    def _generate_model_id(self, name: str, provider: str) -> str:
        """生成模型 ID"""
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())
        safe_provider = re.sub(r'[^a-zA-Z0-9_-]', '-', provider.lower())
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{safe_provider}:{safe_name}-{timestamp}"
    
    async def add_model(self, model: ModelInfo) -> ModelInfo:
        """添加模型（仅支持 external 来源）"""
        if model.source != ModelSource.EXTERNAL:
            raise ValueError("Only external models can be added")
        
        # 生成 ID
        if not model.id:
            model.id = self._generate_model_id(model.name, model.provider)
        
        model.created_at = datetime.now(timezone.utc)
        model.updated_at = datetime.now(timezone.utc)
        
        self._models[model.id] = model
        self._storage.save(list(self._models.values()))
        
        return model
    
    async def update_model(self, model_id: str, updates: Dict[str, Any]) -> Optional[ModelInfo]:
        """更新模型配置"""
        model = self._models.get(model_id)
        if not model:
            return None
        
        if model.source == ModelSource.CONFIG:
            # Config models: allow updating apiKeyEnv (env var name) and writing the key to .env.local
            cfg_updates = updates.get("config") if isinstance(updates.get("config"), dict) else {}
            api_key_val = cfg_updates.get("apiKey") or cfg_updates.get("api_key") or ""
            api_key_env = cfg_updates.get("apiKeyEnv") or cfg_updates.get("api_key_env") or ""
            if api_key_val and api_key_env:
                _write_env_local(api_key_env, api_key_val)
                os.environ[api_key_env] = api_key_val
                model.config.api_key_env = api_key_env
                model.updated_at = datetime.now(timezone.utc)
                return model
            if api_key_env and api_key_env != model.config.api_key_env:
                model.config.api_key_env = api_key_env
                model.updated_at = datetime.now(timezone.utc)
                return model
            raise ValueError("Config models: please provide apiKey + apiKeyEnv to update the key, or apiKeyEnv alone to change the env var name")
        
        # 更新字段
        for key, value in updates.items():
            if key == "config" and isinstance(value, dict):
                for cfg_key, cfg_value in value.items():
                    if hasattr(model.config, cfg_key):
                        setattr(model.config, cfg_key, cfg_value)
            elif hasattr(model, key):
                setattr(model, key, value)
        
        model.updated_at = datetime.now(timezone.utc)
        
        if model.source == ModelSource.EXTERNAL:
            self._storage.save(list(self._models.values()))
        
        return model
    
    async def delete_model(self, model_id: str) -> bool:
        """删除模型（仅支持 external 来源）"""
        model = self._models.get(model_id)
        if not model:
            return False
        
        if model.source != ModelSource.EXTERNAL:
            raise ValueError("Only external models can be deleted")
        
        del self._models[model_id]
        self._storage.save(list(self._models.values()))
        
        return True
    
    async def enable_model(self, model_id: str) -> Optional[ModelInfo]:
        """启用模型"""
        return await self.update_model(model_id, {"enabled": True})
    
    async def disable_model(self, model_id: str) -> Optional[ModelInfo]:
        """禁用模型"""
        return await self.update_model(model_id, {"enabled": False})
    
    # ===== 测试接口 =====
    
    async def test_connectivity(self, model_id: str) -> Dict[str, Any]:
        """测试模型连通性"""
        model = self._models.get(model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        
        result = await self._health_checker.check_connectivity(model)
        
        # 更新模型状态
        if result.get("success"):
            model.status = ModelStatus.AVAILABLE
        else:
            model.status = ModelStatus.UNAVAILABLE
        
        model.updated_at = datetime.now(timezone.utc)
        
        return result
    
    async def test_response(self, model_id: str) -> Dict[str, Any]:
        """测试模型响应"""
        model = self._models.get(model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        
        result = await self._health_checker.check_response(model)
        
        # 更新模型状态和统计
        if result.get("success"):
            model.status = ModelStatus.AVAILABLE
            model.stats.requests_total += 1
            model.stats.requests_success += 1
            model.stats.tokens_total += result.get("tokens_used", 0)
            model.stats.last_request_at = datetime.now(timezone.utc)
        else:
            model.status = ModelStatus.ERROR if "error" in result else ModelStatus.UNAVAILABLE
            model.stats.requests_total += 1
            model.stats.requests_failed += 1
        
        model.updated_at = datetime.now(timezone.utc)
        
        return result
    
    # ===== 扫描接口 =====
    
    async def scan_local_models(self, endpoint: str = None) -> List[ModelInfo]:
        """重新扫描本地 Ollama 模型"""
        if endpoint:
            endpoints = [endpoint]
        else:
            endpoints = self._config_loader.get_local_scan_endpoints()
        if not endpoints:
            return []
        
        local_models = await scan_local_models(endpoints)
        
        # 更新本地模型列表（移除旧的 local 模型，添加新的）
        for key in list(self._models.keys()):
            if self._models[key].source == ModelSource.LOCAL:
                del self._models[key]
        
        for model in local_models:
            self._models[model.id] = model
        
        return local_models
    
    async def get_providers(self) -> List[Dict[str, Any]]:
        """获取支持的 Provider 列表"""
        return [
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "type": "external",
                "requires_api_key": True,
                "capabilities": ["chat", "reasoning"]
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "type": "external",
                "requires_api_key": True,
                "capabilities": ["chat", "embedding", "image", "audio"]
            },
            {
                "id": "anthropic",
                "name": "Anthropic",
                "type": "external",
                "requires_api_key": True,
                "capabilities": ["chat"]
            },
            {
                "id": "ollama",
                "name": "Ollama",
                "type": "local",
                "requires_api_key": False,
                "capabilities": ["chat", "embedding"]
            },
            {
                "id": "local-embedding",
                "name": "Local Embedding (HuggingFace)",
                "type": "local",
                "requires_api_key": False,
                "capabilities": ["embedding"]
            },
            {
                "id": "custom",
                "name": "Custom/OpenAI-Compatible",
                "type": "external",
                "requires_api_key": True,
                "capabilities": ["chat", "embedding"]
            }
        ]
    
    # ===== 引擎注册接口 =====
    
    def register_provider(self, name: str, provider: Any):
        """注册 Provider 实例"""
        self._providers[name] = provider
    
    def get_provider(self, model_id: str) -> Optional[Any]:
        """获取模型的 Provider"""
        model = self._models.get(model_id)
        if not model:
            return None
        return self._providers.get(model.provider)
    
    async def get_status(self) -> Status:
        """获取状态"""
        available_count = sum(1 for m in self._models.values() if m.status == ModelStatus.AVAILABLE)
        total_count = len(self._models)
        
        if total_count == 0:
            return Status.UNKNOWN
        elif available_count == total_count:
            return Status.HEALTHY
        elif available_count > 0:
            return Status.DEGRADED
        else:
            return Status.UNHEALTHY
    
    async def health_check(self) -> HealthStatus:
        """健康检查"""
        issues = []
        for model in self._models.values():
            if model.enabled and model.status in [ModelStatus.UNAVAILABLE, ModelStatus.ERROR]:
                issues.append(f"Model {model.name} is {model.status.value}")
        
        status = Status.HEALTHY if not issues else Status.UNHEALTHY
        return HealthStatus(
            status=status,
            message=f"Models: {len(self._models)} total, {sum(1 for m in self._models.values() if m.enabled)} enabled",
            details={
                "total_models": len(self._models),
                "available_models": sum(1 for m in self._models.values() if m.status == ModelStatus.AVAILABLE),
                "enabled_models": sum(1 for m in self._models.values() if m.enabled),
                "unhealthy": issues
            }
        )