"""
Health Checker - 模型健康检查

Performs connectivity and response tests for models.
"""

import aiohttp
from typing import Dict, Any
from datetime import datetime

from .schemas import ModelInfo, ModelStatus


class HealthChecker:
    """模型健康检查器"""
    
    async def check_connectivity(self, model: ModelInfo) -> Dict[str, Any]:
        """检查模型连通性（不发送实际请求）"""
        result = {
            "success": False,
            "model_id": model.id,
            "timestamp": datetime.now().isoformat(),
            "error": None,
        }
        
        try:
            provider = model.provider.lower()
            
            if provider == "ollama":
                result = await self._check_ollama_connectivity(model)
            elif provider == "openai":
                result = await self._check_openai_connectivity(model)
            elif provider == "anthropic":
                result = await self._check_anthropic_connectivity(model)
            elif provider == "deepseek":
                result = await self._check_deepseek_connectivity(model)
            elif provider == "local-embedding":
                result = await self._check_local_embedding_connectivity(model)
            elif provider == "custom":
                result = await self._check_custom_connectivity(model)
            else:
                result["error"] = f"Unknown provider: {provider}"
        
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    async def check_response(self, model: ModelInfo) -> Dict[str, Any]:
        """检查模型响应（发送最小请求）"""
        result = {
            "success": False,
            "model_id": model.id,
            "timestamp": datetime.now().isoformat(),
            "latency_ms": 0,
            "tokens_used": 0,
            "error": None,
        }
        
        try:
            provider = model.provider.lower()
            
            if provider == "ollama":
                result = await self._check_ollama_response(model)
            elif provider == "openai":
                result = await self._check_openai_response(model)
            elif provider == "anthropic":
                result = await self._check_anthropic_response(model)
            elif provider == "deepseek":
                result = await self._check_deepseek_response(model)
            elif provider == "local-embedding":
                result = await self._check_local_embedding_response(model)
            elif provider == "custom":
                result = await self._check_custom_response(model)
            else:
                result["error"] = f"Unknown provider: {provider}"
        
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    async def _check_ollama_connectivity(self, model: ModelInfo) -> Dict[str, Any]:
        """检查 Ollama 连通性"""
        base_url = model.config.base_url or "http://localhost:11434"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    return {"success": True, "model_id": model.id}
                return {"success": False, "error": f"HTTP {resp.status}"}
        
    async def _check_ollama_response(self, model: ModelInfo) -> Dict[str, Any]:
        """检查 Ollama 响应"""
        import time
        
        base_url = model.config.base_url or "http://localhost:11434"
        model_name = model.name
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "Hi",
                    "stream": False
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                latency_ms = int((time.time() - start_time) * 1000)
                
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "success": True,
                        "model_id": model.id,
                        "latency_ms": latency_ms,
                        "tokens_used": data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
                    }
                return {"success": False, "error": f"HTTP {resp.status}", "latency_ms": latency_ms}
    
    async def _check_openai_connectivity(self, model: ModelInfo) -> Dict[str, Any]:
        """检查 OpenAI 连通性"""
        base_url = model.config.base_url or "https://api.openai.com"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/v1/models",
                headers=self._get_auth_headers(model),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status in [200, 401, 403]:
                    return {"success": True, "model_id": model.id}
                return {"success": False, "error": f"HTTP {resp.status}"}
    
    async def _check_openai_response(self, model: ModelInfo) -> Dict[str, Any]:
        """检查 OpenAI 响应"""
        import time
        import os
        
        api_key = os.environ.get(model.config.api_key_env or "OPENAI_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "API key not configured"}
        
        base_url = model.config.base_url or "https://api.openai.com"
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model.name,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 10
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                latency_ms = int((time.time() - start_time) * 1000)
                
                if resp.status == 200:
                    data = await resp.json()
                    usage = data.get("usage", {})
                    return {
                        "success": True,
                        "model_id": model.id,
                        "latency_ms": latency_ms,
                        "tokens_used": usage.get("total_tokens", 0),
                    }
                
                error_data = await resp.json()
                return {"success": False, "error": error_data.get("error", {}).get("message", f"HTTP {resp.status}"), "latency_ms": latency_ms}
    
    async def _check_anthropic_connectivity(self, model: ModelInfo) -> Dict[str, Any]:
        """检查 Anthropic 连通性"""
        base_url = model.config.base_url or "https://api.anthropic.com"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/v1/messages",
                headers=self._get_auth_headers(model),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status in [200, 401, 403, 404]:
                    return {"success": True, "model_id": model.id}
                return {"success": False, "error": f"HTTP {resp.status}"}
    
    async def _check_anthropic_response(self, model: ModelInfo) -> Dict[str, Any]:
        """检查 Anthropic 响应"""
        import time
        import os
        
        api_key = os.environ.get(model.config.api_key_env or "ANTHROPIC_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "API key not configured"}
        
        base_url = model.config.base_url or "https://api.anthropic.com"
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model.name,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Hi"}]
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                latency_ms = int((time.time() - start_time) * 1000)
                
                if resp.status == 200:
                    data = await resp.json()
                    usage = data.get("usage", {})
                    return {
                        "success": True,
                        "model_id": model.id,
                        "latency_ms": latency_ms,
                        "tokens_used": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                    }
                
                error_data = await resp.json()
                return {"success": False, "error": error_data.get("error", {}).get("message", f"HTTP {resp.status}"), "latency_ms": latency_ms}
    
    async def _check_deepseek_connectivity(self, model: ModelInfo) -> Dict[str, Any]:
        """检查 DeepSeek 连通性"""
        import os
        
        api_key = os.environ.get(model.config.api_key_env or "DEEPSEEK_API_KEY", "")
        base_url = model.config.base_url or "https://api.deepseek.com"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status in [200, 401, 403]:
                    return {"success": True, "model_id": model.id}
                return {"success": False, "error": f"HTTP {resp.status}"}
    
    async def _check_deepseek_response(self, model: ModelInfo) -> Dict[str, Any]:
        """检查 DeepSeek 响应"""
        import time
        import os
        
        api_key = os.environ.get(model.config.api_key_env or "DEEPSEEK_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "API key not configured"}
        
        base_url = model.config.base_url or "https://api.deepseek.com"
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model.name,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 10
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                latency_ms = int((time.time() - start_time) * 1000)
                
                if resp.status == 200:
                    data = await resp.json()
                    usage = data.get("usage", {})
                    return {
                        "success": True,
                        "model_id": model.id,
                        "latency_ms": latency_ms,
                        "tokens_used": usage.get("total_tokens", 0),
                    }
                
                error_data = await resp.json()
                return {"success": False, "error": error_data.get("error", {}).get("message", f"HTTP {resp.status}"), "latency_ms": latency_ms}
    
    async def _check_local_embedding_connectivity(self, model: ModelInfo) -> Dict[str, Any]:
        """检查本地 Embedding 模型连通性"""
        try:
            from sentence_transformers import SentenceTransformer
            return {"success": True, "model_id": model.id}
        except ImportError:
            return {"success": False, "error": "sentence-transformers not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _check_local_embedding_response(self, model: ModelInfo) -> Dict[str, Any]:
        """检查本地 Embedding 模型响应"""
        import time
        
        try:
            from sentence_transformers import SentenceTransformer
            
            model_path = model.config.base_url or f"sentence-transformers/{model.name}"
            start_time = time.time()
            
            emb_model = SentenceTransformer(model_path)
            embeddings = emb_model.encode(["Hi"])
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "model_id": model.id,
                "latency_ms": latency_ms,
                "tokens_used": len("Hi".split()),
            }
        except ImportError:
            return {"success": False, "error": "sentence-transformers not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _check_custom_connectivity(self, model: ModelInfo) -> Dict[str, Any]:
        """检查自定义模型连通性"""
        base_url = model.config.base_url
        if not base_url:
            return {"success": False, "error": "Base URL not configured"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url.rstrip('/')}/models",
                headers=model.config.headers or {},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status in [200, 401, 403]:
                    return {"success": True, "model_id": model.id}
                return {"success": False, "error": f"HTTP {resp.status}"}
    
    async def _check_custom_response(self, model: ModelInfo) -> Dict[str, Any]:
        """检查自定义模型响应"""
        import time
        import os
        
        base_url = model.config.base_url
        if not base_url:
            return {"success": False, "error": "Base URL not configured"}
        
        api_key = os.environ.get(model.config.api_key_env or "", "")
        headers = model.config.headers or {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model.name,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 10
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                latency_ms = int((time.time() - start_time) * 1000)
                
                if resp.status == 200:
                    data = await resp.json()
                    usage = data.get("usage", {})
                    return {
                        "success": True,
                        "model_id": model.id,
                        "latency_ms": latency_ms,
                        "tokens_used": usage.get("total_tokens", 0),
                    }
                
                error_data = await resp.json()
                return {"success": False, "error": error_data.get("error", {}).get("message", f"HTTP {resp.status}"), "latency_ms": latency_ms}
    
    def _get_auth_headers(self, model: ModelInfo) -> Dict[str, str]:
        """获取认证头"""
        import os
        
        headers = {"Content-Type": "application/json"}
        
        if model.config.api_key_env:
            api_key = os.environ.get(model.config.api_key_env, "")
            if api_key:
                if model.provider.lower() == "anthropic":
                    headers["x-api-key"] = api_key
                else:
                    headers["Authorization"] = f"Bearer {api_key}"
        
        return headers