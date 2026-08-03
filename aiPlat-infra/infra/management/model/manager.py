"""
Model Manager - 模型管理器

Manages AI models from three sources:
- config_models: Models from YAML config (read-only)
- local_models: Models from Ollama (dynamic scan)
- external_models: User-added models (JSON storage)
"""

import asyncio
import logging
import os
import subprocess
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

try:
    import psutil
    _psutil_available = True
except ImportError:
    psutil = None
    _psutil_available = False

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


# ── Provider capability registry (mirrors get_providers() for sync access in scoring) ──
_PROVIDER_CAPABILITIES = {
    "deepseek": {"chat", "reasoning"},
    "openai": {"chat", "embedding", "image", "audio"},
    "anthropic": {"chat"},
    "ollama": {"chat", "embedding"},
    "local-embedding": {"embedding"},
    "custom": {"chat", "embedding"},
}

# ── Platform resources (cached, TTL 5s) ──
from dataclasses import dataclass as _dc

@_dc
class PlatformResources:
    ram_bytes: int
    vram_bytes: int           # Apple=vram==ram, NVIDIA=nvidia-smi, no-GPU=0
    gpu_vendor: Optional[str] # "apple" | "nvidia" | "amd" | None
    gpu_compatible: bool
    cpu_cores: int
    disk_free_bytes: int
    _collected_at: float = 0.0

_RESOURCE_CACHE: Optional[tuple] = None
_RESOURCE_CACHE_TTL = 5.0


def collect_platform_resources() -> PlatformResources:
    """采集平台资源，带 5s TTL 缓存。Apple Silicon 统一内存架构下 vram=ram。"""
    global _RESOURCE_CACHE
    import time as _time
    now = _time.time()
    if _RESOURCE_CACHE and now - _RESOURCE_CACHE[0] < _RESOURCE_CACHE_TTL:
        return _RESOURCE_CACHE[1]

    import platform as _platform

    ram = psutil.virtual_memory().available if _psutil_available else 0
    disk = psutil.disk_usage("/").free if _psutil_available else 0
    cpu = os.cpu_count() or 1

    sys_name = _platform.system()
    machine = _platform.machine()

    if sys_name == "Darwin" and machine == "arm64":
        gpu_vendor, vram, gpu_compatible = "apple", ram, True
    elif sys_name == "Linux":
        vram, gpu_vendor = _detect_nvidia_gpu()
        gpu_compatible = gpu_vendor is not None
    else:
        vram, gpu_vendor, gpu_compatible = 0, None, False

    res = PlatformResources(
        ram_bytes=ram or 0,
        vram_bytes=vram or 0,
        gpu_vendor=gpu_vendor,
        gpu_compatible=gpu_compatible,
        cpu_cores=cpu,
        disk_free_bytes=disk or 0,
        _collected_at=now,
    )
    _RESOURCE_CACHE = (now, res)
    return res


def _detect_nvidia_gpu() -> tuple:
    """检测 NVIDIA GPU 和可用显存。无 NVIDIA 时返回 (0, None)。"""
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.free, "nvidia"
    except Exception:
        return 0, None


def _extract_base_name(full_name: str) -> str:
    """提取 Ollama 模型基础名（去除量化后缀）。
    先按 ':' 分割 repo:tag，只对 tag 部分去量化后缀。
    'qwen2.5-coder:7b-q8_0' -> 'qwen2.5-coder:7b'
    'mistral:7b-v0.3-q4_K_M' -> 'mistral:7b-v0.3'
    """
    if ":" not in full_name:
        return full_name

    import re
    repo, tag = full_name.split(":", 1)
    clean = re.sub(r'-[qQ][0-9a-zA-Z_]+$', '', tag)    # -q4_K_M, -Q8_0
    clean = re.sub(r'-[fF][pP][0-9]+$', '', clean)      # -fp16, -FP32
    clean = re.sub(r'-[iI][0-9]+$', '', clean)          # -i1, -I8
    return f"{repo}:{clean}" if clean else repo


# ═══ 硬过滤 + 软过滤 + 评分（模块级辅助函数） ═══

# ── 用途 prefer 标签 → 模型 strength_areas 标签的别名映射 ──
_CAPABILITY_ALIASES = {
    "chat":      {"chat", "instruction_following", "fact_lookup", "multi_doc_synthesis", "long_form_summary"},
    "code":      {"code", "code_generation"},
    "reasoning": {"reasoning"},
}


def _get_model_caps(m, profile_data: dict = None) -> set:
    """合并模型自身能力 + provider 级能力 + YAML strength_areas。"""
    caps = set(m.capabilities or ["chat"]) | set(m.tags or [])
    provider_caps = _PROVIDER_CAPABILITIES.get(m.provider, set())
    caps |= provider_caps
    if profile_data:
        mc = profile_data.get("model_capabilities", {}).get(m.name, {})
        caps |= set(mc.get("strength_areas", []))
    return caps


def _hard_filter(model, res: PlatformResources) -> tuple:
    """物理硬约束。返回 (通过: bool, 原因: str)。永不放宽。"""
    if not model.enabled:
        return False, "disabled"

    if model.size is None:
        return True, "ok (unknown size)"
    if model.size == 0:
        return True, "ok"  # API 模型

    if model.size > res.ram_bytes:
        return False, (f"requires {model.size/1e9:.1f}GB RAM, "
                       f"only {res.ram_bytes/1e9:.1f}GB available")

    if res.vram_bytes > 0 and model.size > res.vram_bytes:
        return False, (f"requires {model.size/1e9:.1f}GB VRAM, "
                       f"only {res.vram_bytes/1e9:.1f}GB available")

    if not model.is_downloaded and model.size > res.disk_free_bytes:
        return False, (f"requires {model.size/1e9:.1f}GB disk to download, "
                       f"only {res.disk_free_bytes/1e9:.1f}GB free")

    return True, "ok"


def _filter_capability(model, purpose: str, profile: dict, profile_data: dict = None) -> bool:
    """Requirement-driven capability matching. Reads 'require' from profile, checks model_capabilities.

    Replaces the old prefer/avoid/prefer_local/prefer_external logic.
    Engine derives suitability from model capabilities vs task requirements.
    """
    caps = _get_model_caps(model, profile_data)
    # Always require chat type (all pipeline models are chat)
    require_type = profile.get("require", {}).get("type", "chat")
    if require_type and require_type not in caps:
        return False
    # Check capability requirements from model_capabilities
    model_caps_data = profile_data.get("model_capabilities", {}).get(model.name, {}) if profile_data else {}
    require = profile.get("require", {})
    if require.get("reasoning_quality", 0) > 0:
        if model_caps_data.get("reasoning_quality", 1) < require["reasoning_quality"]:
            return False
    if require.get("context_window", 0) > 0:
        if model_caps_data.get("context_window", 1) < require["context_window"]:
            return False
    if require.get("hallucination_max", 1.0) < 1.0:
        if model_caps_data.get("hallucination_rate", 1.0) > require["hallucination_max"]:
            return False
    return True


def _filter_health(model) -> bool:
    """健康过滤。Level 2 可放宽。取不到数据默认健康。"""
    try:
        from .health_checker import HealthChecker
        return HealthChecker.get_failure_rate(model.name) <= 0.5
    except Exception:
        return True


def _filter_latency(model) -> bool:
    """延迟过滤。Level 3 可放宽。取不到数据默认可用。"""
    try:
        from .latency_tracker import get_latency_tracker
        return get_latency_tracker().p95_latency_seconds(model.name) <= 30
    except Exception:
        return True


def _get_scoring_weights(purpose: str, profile_data: dict) -> dict:
    """Read scoring weights from profile. 'weights' key (v3) takes priority, 'scoring_weights' (v2) as fallback."""
    default = {
        "reasoning": 1.0,
        "quality": 1.0,
        "latency": -1.0,
        "api_credential": 3.0,
        "resource_pressure": 1.0,
        "gpu_compat": 1.0,
        "concurrency": 1.0,
        "cost": -1.0,
    }
    profile = profile_data.get("purpose_profiles", {}).get(purpose, {})
    weights = profile.get("weights") or profile.get("scoring_weights") or {}
    return {**default, **weights}


def _score_model(
    model, purpose: str, profile: dict,
    res: PlatformResources, preferences: dict, profile_data: dict,
) -> int:
    """综合评分（v2.2 动态权重），分数越高越优先。"""
    weights = _get_scoring_weights(purpose, profile_data)
    score = 0

    # 0. 未知 size 惩罚（纵深防御：size=None 的本地模型即使绕过 _build_preferences 也会在此扣分）
    if model.size is None:
        if model.provider not in ("openai", "deepseek", "anthropic", "openrouter", "ollama"):
            score -= 150

    # 1. 资源压力
    if model.size and model.size > 0:
        ratio = model.size / max(res.ram_bytes, 1)
        penalty = 0
        if ratio > 0.8:       penalty = -100
        elif ratio > 0.5:     penalty = -30
        elif ratio > 0.3:     penalty = -10
        score += int(penalty * weights.get("resource_pressure", 1.0))

    # 2. Capability-driven origin scoring (v3: replaces prefer_local/prefer_external)
    src = getattr(model.source, 'value', '') if hasattr(model.source, 'value') else ''
    src_bias = 0
    if src == "external":      src_bias = 80   # API models: consistent quality, no RAM pressure
    elif src == "local":       src_bias = 40   # local models: free but RAM-heavy
    score += src_bias

    # 3. env var 匹配（不受权重影响，保持 +500 绝对优先）
    if preferences.get("env_var_model") == model.name:
        score += 500

    # 4. model_overrides 匹配（不受权重影响）
    if preferences.get("override_model") == model.name:
        score += 80

    # 5. GPU 兼容性
    gpu_score = 0
    if model.supports_gpu and res.gpu_compatible:
        gpu_score = 50
    elif not res.gpu_compatible and model.provider == "ollama":
        gpu_score = -200
    score += int(gpu_score * weights.get("gpu_compat", 1.0))

    # 6. Capability-driven reasoning scoring (v3: from model_capabilities, not profile tags)
    model_caps_data = profile_data.get("model_capabilities", {}).get(model.name, {})
    reasoning_quality = model_caps_data.get("reasoning_quality", 1)
    reasoning_score = 0
    if reasoning_quality >= 5:   reasoning_score = 100
    elif reasoning_quality >= 4: reasoning_score = 60
    elif reasoning_quality >= 3: reasoning_score = 35
    elif reasoning_quality >= 2: reasoning_score = 15
    # Bonus: model's reasoning meets or exceeds the purpose's requirement
    require = profile.get("require", {})
    req_reasoning = require.get("reasoning_quality", 0)
    if req_reasoning and reasoning_quality >= req_reasoning:
        reasoning_score += 30  # model is well-qualified for this task
    score += int(reasoning_score * weights.get("reasoning", 1.0))

    # 6b. Hallucination penalty (v3: capability-driven)
    hallucination_rate = model_caps_data.get("hallucination_rate", 0.10)
    hallucination_penalty = 0
    if hallucination_rate > 0.08:   hallucination_penalty = -60
    elif hallucination_rate > 0.05: hallucination_penalty = -20
    if require.get("hallucination_max", 1.0) < 1.0:
        if hallucination_rate > require["hallucination_max"]:
            hallucination_penalty -= 40
    score += hallucination_penalty

    # 6c. Context window bonus (v3: capability-driven)
    context_window = model_caps_data.get("context_window", 4096)
    req_context = require.get("context_window", 0)
    if req_context and context_window >= req_context:
        score += 20  # model has sufficient context for this task

    # 7. API 凭证检查（双路径：环境变量 + 适配器 ID）
    if model.provider in ("openai", "deepseek", "anthropic", "openrouter"):
        has_creds = False
        if hasattr(model, 'config') and model.config:
            # 路径 A：环境变量（传统部署，AIPLAT_*_MODEL 方式）
            env_name = getattr(model.config, 'api_key_env', '') or ''
            if env_name and os.getenv(env_name, "").strip():
                has_creds = True
            # 路径 B：适配器 ID（管理 UI 配置方式）
            if not has_creds:
                adapter_id = getattr(model.config, 'adapter_id', '') or ''
                if adapter_id:
                    has_creds = True  # 加载时已通过有效 key 过滤
        if not has_creds:
            score += int(-300 * weights.get("api_credential", 3.0))

    # 8. 质量反馈 (-80 ~ +80)
    try:
        from .quality_validator import get_quality_tracker
        qs = get_quality_tracker().get(model.name, purpose)
        score += int(qs * 80 * weights.get("quality", 1.0))
    except Exception:
        pass  # noqa: intentional — best-effort non-critical operation

    # 9. 延迟惩罚
    try:
        from .latency_tracker import get_latency_tracker
        p95 = get_latency_tracker().p95_latency_seconds(model.name)
    except Exception:
        p95 = 5
    latency_penalty = 0
    if p95 > 10:    latency_penalty = -40
    elif p95 > 5:   latency_penalty = -20
    score += int(latency_penalty * weights.get("latency", -1.0))

    # 10. 并发容量
    max_cc = getattr(model, 'max_concurrency', 0) or 0
    concurrency_score = 0
    if max_cc >= 50:    concurrency_score = 30
    elif max_cc >= 10:  concurrency_score = 15
    score += int(concurrency_score * weights.get("concurrency", 1.0))

    # 11. 成本
    model_costs = profile_data.get("model_cost", {})
    cost = model_costs.get(model.name, 0.0) if model_costs else 0.0
    cost_penalty = 0
    if cost > 0.01:   cost_penalty = -10
    elif cost > 0.001: cost_penalty = -5
    score += int(cost_penalty * weights.get("cost", -1.0))

    return score


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
        self._recent_failures: Dict[str, List[bool]] = {}  # model_name → [success/fail bools, last 20]
        self._first_failure_at: Dict[str, float] = {}  # model_name → timestamp of first failure
        self._failure_ttl = 300  # 5 minutes auto-recovery
        
        # 加载所有模型
        self._load_all_models()
    
    def _load_all_models(self):
        """加载所有模型"""
        # 1. 加载适配器 + 环境变量发现的模型
        config_models = self._config_loader.load()
        seen_names = set()
        for model in config_models:
            self._models[model.id] = model
            seen_names.add(model.name)
        
        # 2. Scan local Ollama / LM Studio / vLLM models
        try:
            # Use a separate thread to run the async scan synchronously,
            # avoiding "cannot run event loop while another is running" errors
            # when called from within uvicorn's existing event loop.
            import concurrent.futures as _cfutures
            with _cfutures.ThreadPoolExecutor(max_workers=1) as _pool:
                _future = _pool.submit(self._scan_local_models_sync)
                _future.result(timeout=10.0)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        # 4. 补全所有模型的 size / is_downloaded / supports_gpu
        try:
            self._resolve_model_sizes()
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    def _resolve_model_sizes(self) -> None:
        """补全所有模型的 size、quantization、is_downloaded、supports_gpu 字段。
        规则：
          - API 模型 (openai/deepseek/anthropic) → size=0, is_downloaded=True
          - Ollama 模型 → 从已扫描的同系列模型中匹配：
            · 优先精确匹配（名称完全相同）
            · 否则取同名基础型号中 size 最小的变体（保守策略）
          - 其余 → 保持原值
        """
        # 1. 构建 Ollama 变体索引: base_name → [{full_name, size, quantization}]
        ollama_variants: dict = {}
        for m in self._models.values():
            if not (m.size and m.size > 0 and m.source.value == "local" and m.provider == "ollama"):
                continue
            base = _extract_base_name(m.name)
            ollama_variants.setdefault(base, []).append({
                "full_name": m.name,
                "size": m.size,
                "quantization": getattr(m, 'quantization', None),
            })

        # 2. 补全所有模型
        for m in self._models.values():
            if m.size is not None and m.size > 0:
                continue

            # 优先尝试匹配 Ollama 已扫描的模型（覆盖 provider 字段的误判）
            base = _extract_base_name(m.name)
            variants = ollama_variants.get(base, [])
            if variants:
                exact = next((v for v in variants if v["full_name"] == m.name), None)
                if exact:
                    m.size = exact["size"]
                    m.quantization = exact["quantization"]
                else:
                    smallest = min(variants, key=lambda v: v["size"])
                    m.size = smallest["size"]
                    m.quantization = smallest["quantization"]
                    logging.info("Model %s: matched to %s (smallest variant, %.1fGB)",
                                 m.name, smallest["full_name"], smallest["size"] / 1e9)
                m.is_downloaded = any(v["full_name"] == m.name for v in variants)
                m.supports_gpu = True
                # 修正适配器注册时的类型/provider 误判
                if m.provider not in ("ollama",) and any(v["full_name"] == m.name for v in variants):
                    # 查找对应的 LOCAL 模型获取正确的 provider/type
                    for local_m in self._models.values():
                        if local_m.source.value == "local" and local_m.provider == "ollama" and local_m.name == m.name:
                            m.provider = "ollama"
                            m.type = local_m.type
                            break
                continue

            # 无 Ollama 匹配 → 按 provider 设默认值
            if m.provider in ("openai", "deepseek", "anthropic", "openrouter"):
                m.size = 0
                m.is_downloaded = True
                m.supports_gpu = False
            elif m.provider == "ollama":
                m.size = 0
                m.is_downloaded = False
                m.supports_gpu = True
                logging.warning("Model %s: no Ollama variant found, size unknown", m.name)

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
                # 按名称去重：同名的适配器模型已存在 → 合并 size/status，不创建重复条目
                existing = self._find_model_by_name(model.name)
                if existing is not None:
                    if not existing.size or existing.size == 0:
                        existing.size = getattr(model, 'size', None) or existing.size
                    if getattr(model, 'quantization', None):
                        existing.quantization = model.quantization
                    existing.is_downloaded = True
                    existing.supports_gpu = True
                    # 修正适配器注册时的类型/provider 误判
                    if model.provider and existing.provider in ("deepseek", "openai", "anthropic"):
                        existing.provider = model.provider
                    if model.type and model.type != existing.type:
                        existing.type = model.type
                    continue  # 不重复添加
                if model.id not in self._models:
                    self._models[model.id] = model
            # Sync scanned models to adapter table for management UI visibility
            try:
                await self._sync_local_to_adapter(local_models, endpoints)
            except Exception as e:
                logging.debug("Ollama→adapter sync skipped: %s", str(e)[:200], exc_info=True)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    async def _sync_local_to_adapter(self, local_models, endpoints):
        """同步本地扫描结果（Ollama/LM Studio/oMLX/vLLM）到适配器表。
        
        使管理 UI 可统一管理所有本地模型（启用/禁用/配置）。
        Ollama 模型的 size/quantization 从 API 获取；
        OpenAI 兼容端点（vLLM 等）的 size 留空，由 _resolve_model_sizes() 后续补全。
        """
        import json as _json
        import sqlite3
        import time as _time
        import os as _os

        db_path = _os.getenv("AIPLAT_EXECUTION_DB_PATH", "")
        if not db_path or not _os.path.isfile(db_path):
            return

        ollama_base = endpoints[0] if endpoints else ""
        now = _time.time()

        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            for model in local_models:
                provider = model.provider or "local-scan"
                adapter_id = f"local-scan:{provider}:{model.name}"
                size_str = f"{model.size/1e9:.1f}GB" if model.size else "unknown"
                quantization = getattr(model, 'quantization', None)
                metadata = {
                    "source": "local_scan",
                    "provider": provider,
                }
                if model.size:
                    metadata["size"] = model.size
                if quantization:
                    metadata["quantization"] = quantization
                models_json = _json.dumps([{"name": model.name}])
                conn.execute(
                    """INSERT INTO adapters(
                        adapter_id, name, provider, description, status,
                        api_key, api_base_url, organization_id,
                        api_key_enc, api_key_kid,
                        models_json, rate_limit_json, retry_config_json, metadata_json,
                        created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(adapter_id) DO UPDATE SET
                        name=excluded.name, provider=excluded.provider,
                        description=excluded.description,
                        status=excluded.status,
                        api_key=excluded.api_key,
                        api_base_url=excluded.api_base_url,
                        organization_id=excluded.organization_id,
                        models_json=excluded.models_json,
                        metadata_json=excluded.metadata_json,
                        updated_at=excluded.updated_at""",
                    (
                        adapter_id,
                        model.name,
                        provider,
                        f"Local {provider.upper()} model {model.name} ({size_str})",
                        "active",
                        "__local_scan__",  # sentinel — 本地模型不需要真实 API key
                        ollama_base or "",
                        None,
                        None,
                        None,
                        models_json,
                        "{}",
                        "{}",
                        _json.dumps(metadata),
                        now, now,
                    ),
                )
            conn.commit()
            logging.getLogger(__name__).info(
                "Synced %d local models to adapter table", len(local_models))
        finally:
            conn.close()

    def _scan_local_models_sync(self):
        """Sync wrapper for _scan_local_models — runs in a dedicated event loop."""
        new_loop = asyncio.new_event_loop()
        try:
            new_loop.run_until_complete(
                asyncio.wait_for(self._scan_local_models(), timeout=10.0))
        finally:
            new_loop.close()
    
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

    def record_success(self, model_name: str):
        """Passive health: record a successful call. Resets failure TTL on success."""
        stats = self._recent_failures.setdefault(model_name, [])
        stats.append(True)
        if len(stats) > 20:
            stats.pop(0)
        self._first_failure_at.pop(model_name, None)  # reset TTL on success

    def record_failure(self, model_name: str):
        """Passive health: record a failed call. Sets first_failure_at on first failure."""
        import time
        stats = self._recent_failures.setdefault(model_name, [])
        stats.append(False)
        if len(stats) > 20:
            stats.pop(0)
        if model_name not in self._first_failure_at:
            self._first_failure_at[model_name] = time.time()

    def _failure_rate(self, model_name: str) -> float:
        """Return failure rate (0-1) from last 20 calls.
        
        Auto-recovery: if 5 minutes have passed since first failure, reset and return 0.
        """
        import time
        stats = self._recent_failures.get(model_name, [])
        if not stats:
            return 0.0
        # TTL auto-recovery
        first_at = self._first_failure_at.get(model_name)
        if first_at and time.time() - first_at > self._failure_ttl:
            self._recent_failures.pop(model_name, None)
            self._first_failure_at.pop(model_name, None)
            return 0.0
        return sum(1 for s in stats if not s) / len(stats)

    def get_default_model(self, purpose: str = "default") -> str:
        """Resolve purpose to model name via env vars (unique resolution point).

        Covers all 9 purposes for centralized, env-driven model selection.
        """
        purpose_env_map = {
            "agent":       ("AIPLAT_AGENT_MODEL", "AIPLAT_DEFAULT_AGENT_MODEL"),
            "reasoning":   ("AIPLAT_AGENT_MODEL", "AIPLAT_DEFAULT_AGENT_MODEL"),
            "document":    ("AIPLAT_DOC_LLM_MODEL",),
            "code_gen":    ("AIPLAT_CODE_GEN_MODEL",),
            "code":        ("AIPLAT_CODE_GEN_MODEL",),
            "query_translation": ("AIPLAT_QUERY_MODEL",),
            "wiki_curation": ("AIPLAT_WIKI_CURATION_MODEL",),
            "ontology_gen": (),
            "reranker":    ("AIPLAT_RERANK_MODEL",),
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

    def get_credentials(self, provider: str) -> dict:
        """Resolve API credentials for a provider via credential pool.

        Returns dict with: api_key, base_url (optional), provider
        Returns empty dict if no credentials found.
        """
        from infra.management.model.credential_pool import get_credential_pool
        try:
            pool = get_credential_pool(provider)
            key = pool.next()
            return {"api_key": key, "provider": provider}
        except RuntimeError:
            return {}

    def select_by_purpose(self, purpose: str, complexity: str = None) -> Optional[str]:
        """Select best model for purpose via capability scoring.
        
        Phase 12.1: complexity filtering via routing_rules in llm_profile.yaml.
        """
        candidates = self.select_by_purpose_list(purpose, complexity=complexity)
        return candidates[0] if candidates else None

    def select_by_purpose_list(self, purpose: str, complexity: str = None) -> List[str]:
        """Return all eligible models for purpose, scored and sorted (best first).
        
        Useful for fallback: if the top model times out, try the next one.
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

        # Read explicit model_overrides (preferred model, not hard override)
        overrides = profile_data.get("model_overrides", {})
        preferred = overrides.get(purpose) if purpose in overrides else None
        if preferred:
            # Verify model exists and is enabled
            found = False
            for m in self._models.values():
                if m.name == preferred and m.enabled:
                    found = True
                    break
            if not found:
                import logging as _logging
                _logging.getLogger("infra.model").warning(
                    f"Preferred model '{preferred}' for '{purpose}' not found or disabled"
                )
                preferred = None

        # Filter chat models
        chat_models = [m for m in self._models.values()
                       if hasattr(m, 'type') and m.type.value == "chat" and m.enabled]

        # Collect system resource data for resource-aware scoring
        available_ram_bytes = 0
        if _psutil_available:
            try:
                available_ram_bytes = psutil.virtual_memory().available
            except Exception:  # noqa: ram-check-fallback
                pass

        scored = []
        for m in chat_models:
            caps = set(m.capabilities or ["chat"]) | set(m.tags or [])
            # Inherit provider-level capabilities (e.g., 'reasoning' from DeepSeek provider)
            provider_caps = _PROVIDER_CAPABILITIES.get(m.provider, set())
            caps |= provider_caps
            if not any(c in caps for c in profile.get("prefer", ["chat"])):
                continue
            if any(c in caps for c in profile.get("avoid", [])):
                continue
            # Hard require: model MUST have these capabilities (check merged caps including provider)
            require = profile.get("require", {}).get("capabilities", [])
            if require and not all(c in caps for c in require):
                continue

            # Phase 12.1: complexity-based filtering via model_capabilities.routing_rules
            if complexity:
                caps_data = profile_data.get("model_capabilities", {})
                model_caps = caps_data.get(m.name, {})
                routing_rules = model_caps.get("routing_rules", {})
                min_c = routing_rules.get("min_complexity", 0)
                max_c = routing_rules.get("max_complexity", 5)
                c_map = {"simple": 1, "medium": 2, "complex": 4}
                c_num = c_map.get(complexity, 2)
                if c_num < min_c or c_num > max_c:
                    continue  # model doesn't match this complexity tier

            # Inject capabilities from llm_profile.yaml model_capabilities into scoring
            prof_model_caps = profile_data.get("model_capabilities", {}).get(m.name, {})
            if prof_model_caps.get("reasoning_quality", 0) >= 3:
                caps.add("reasoning")
            if "code_generation" in prof_model_caps.get("strength_areas", []):
                caps.add("code")

            score = 0

            # Resource-aware scoring: hard-block models too large for available RAM
            if available_ram_bytes > 0 and hasattr(m, 'size') and m.size:
                model_bytes = m.size
                usage_ratio = model_bytes / available_ram_bytes
                if usage_ratio > 1.0:
                    continue  # hard block: model larger than free RAM — cannot load
                elif usage_ratio > 0.8:
                    score -= 100  # very tight fit
                elif usage_ratio > 0.5:
                    score -= 30   # moderate pressure
                elif usage_ratio > 0.3:
                    score -= 10   # slight pressure

            if profile.get("prefer_local"):
                if m.source.value == "local":
                    score += 120
                elif m.source.value == "external":
                    score += 60
                else:
                    score += 40
            elif profile.get("prefer_external"):
                if m.source.value == "external":
                    score += 120
                elif m.source.value == "local":
                    score += 40
                else:
                    score += 60
            elif m.source.value == "config":
                score += 100

            if "reasoning" in caps:
                if profile.get("prefer", [""])[0] == "reasoning":
                    score += 80
                else:
                    score += 30
            else:
                if profile.get("prefer", [""])[0] != "reasoning":
                    score -= 20

            if "function_call" in caps:
                score += 20

            # ── Quality feedback (v3.0: dynamic, programmatic validation) ──
            try:
                from .quality_validator import get_quality_tracker
                qs = get_quality_tracker().get(m.name, purpose)
                score += int(qs * 80)  # -80 to +80
            except Exception as e:
                logging.debug(str(e), exc_info=True)

            # ── Concurrency capacity (from model tags or env) ──
            max_cc = getattr(m, 'max_concurrency', 0) or 0
            if max_cc >= 50:
                score += 30
            elif max_cc >= 10:
                score += 15
            elif max_cc > 0:
                score += 5

            # ── v3.0: Latency penalty (P95 > threshold) ──
            try:
                from .latency_tracker import get_latency_tracker
                lt = get_latency_tracker()
                p95 = lt.p95_latency_seconds(m.name)
                if p95 > 10:
                    score -= 40
                elif p95 > 5:
                    score -= 20
            except Exception as e:
                logging.debug(str(e), exc_info=True)

            # ── v3.0: Congestion penalty (rate limiting / overload) ──
            try:
                from .latency_tracker import get_latency_tracker
                penalty = get_latency_tracker().congestion_penalty(m.name)
                score -= int(penalty)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

            # ── v3.0: Cost penalty (per 1k tokens) ──
            model_costs = profile_data.get("model_cost", {})
            cost_per_1k = model_costs.get(m.name, 0.0) if model_costs else 0.0
            if cost_per_1k > 0.01:
                score -= 10
            elif cost_per_1k > 0.001:
                score -= 5

            scored.append((score, m.name))

        if not scored:
            return [fallback_model] if fallback_model else []

        scored.sort(key=lambda x: (x[0], x[1] == fallback_model), reverse=True)
        result = [name for score, name in scored]

        # ── Passive health filter: skip models with >50% recent failure rate ──
        healthy = [name for name in result if self._failure_rate(name) <= 0.5]
        result = healthy if healthy else result  # keep at least 1

        # ── Preferred model (model_overrides) → move to head ──
        if preferred and preferred in result:
            result.remove(preferred)
            result.insert(0, preferred)
        elif preferred and preferred not in result:
            import logging
            logging.getLogger("infra.model").warning(
                f"Preferred model '{preferred}' for '{purpose}' not in scored list "
                f"(may have wrong capabilities or is disabled). Falling back to auto-selection."
            )

        return result

    # ═══ 统一评分管道 v2.1 ═══

    def _find_model_by_name(self, name: str) -> Optional[ModelInfo]:
        """按名称查找模型。"""
        for m in self._models.values():
            if m.name == name:
                return m
        return None

    def unified_pipeline(
        self, purpose: str, messages: list | None,
        preferences: dict, profile_data: dict,
    ) -> str:
        """统一评分管道。env var 和 model_overrides 作为偏好参数，不再硬覆盖。"""
        import time as _time
        res = collect_platform_resources()

        safe = profile_data.get("fallback", {})
        safe_model = safe.get("safe_model", "qwen2.5:3b")
        safe_model_alt = safe.get("safe_model_alt", "qwen2.5-coder:7b")
        safe_ram_limit_gb = safe.get("safe_model_ram_limit", 4)

        profile = profile_data.get("purpose_profiles", {}).get(purpose, {})

        models = [m for m in self._models.values()
                  if hasattr(m, 'type') and m.type.value == "chat"]

        # ── 降级链路（硬约束不变，逐级放宽软约束） ──
        soft_filters = [
            ("full",     lambda m: (_filter_capability(m, purpose, profile, profile_data)
                                    and _filter_health(m)
                                    and _filter_latency(m))),
            ("-cap",     lambda m: (_filter_health(m)
                                    and _filter_latency(m))),
            ("-cap-hlt", lambda m: _filter_latency(m)),
            ("none",     lambda m: True),
        ]

        for level_name, soft_fn in soft_filters:
            passed = [m for m in models
                       if _hard_filter(m, res)[0] and soft_fn(m)]
            if passed:
                if level_name != "full":
                    logging.getLogger(__name__).warning(
                        "Model selection degraded to level=%s for purpose=%s", level_name, purpose)
                scored = [(_score_model(m, purpose, profile, res, preferences, profile_data), m)
                           for m in passed]
                scored.sort(key=lambda x: x[0], reverse=True)
                return scored[0][1].name

        # ── Safe Model 保底：优先 API，再本地安全模型 ──
        for safe_name in [safe_model_alt, safe_model]:
            safe_m = self._find_model_by_name(safe_name)
            if safe_m is None:
                continue
            ok, _reason = _hard_filter(safe_m, res)
            if not ok:
                continue
            if safe_m.size and safe_m.size > 0:
                if res.ram_bytes < safe_ram_limit_gb * 1024**3:
                    logging.getLogger(__name__).warning(
                        "Safe model %s needs >=%.0fGB but only %.1fGB available",
                        safe_name, safe_ram_limit_gb, res.ram_bytes / 1e9)
                    continue
            logging.getLogger(__name__).warning("All models filtered, falling back to safe_model=%s", safe_name)
            return safe_name

        raise RuntimeError(
            f"No model can run on this hardware. "
            f"RAM={res.ram_bytes/1e9:.1f}GB, VRAM={res.vram_bytes/1e9:.1f}GB, "
            f"GPU={res.gpu_vendor}. "
            f"Safe models ({safe_model}, {safe_model_alt}) also cannot load."
        )

    def get_model_tier(self, model_name: str, profile_data: dict = None) -> str:
        """Determine tier from model capabilities (single source of truth).

        Uses model_capabilities.reasoning_quality + semantic_understanding
        to compute a complexity score, then maps to tiers via complexity_range.
        No static model lists in YAML.
        """
        if profile_data is None:
            try:
                from pathlib import Path
                import yaml as _yaml
                config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
                    str(Path(__file__).resolve().parent.parent.parent.parent /
                        "config" / "infra" / "llm_profile.yaml"))
                with open(config_path) as f:
                    profile_data = _yaml.safe_load(f) or {}
            except Exception:
                return "unknown"

        tiers = profile_data.get("tiers", {})
        caps = profile_data.get("model_capabilities", {})

        # Match model name: try exact, then shortened forms
        cap = caps.get(model_name)
        if not cap:
            for cn, cc in caps.items():
                if model_name in cn or cn in model_name:
                    cap = cc
                    break

        if isinstance(cap, dict):
            reasoning = cap.get("reasoning_quality", 1)
            semantic = cap.get("semantic_understanding", 1)
            complexity = min(max(reasoning * 0.6 + semantic * 0.4, 0.5), 4.99)
        else:
            complexity = 2.5

        for tier_name, tier_config in sorted(tiers.items()):
            if not isinstance(tier_config, dict):
                continue
            rng = tier_config.get("complexity_range", [0, 0])
            if len(rng) >= 2 and rng[0] <= complexity < rng[1]:
                return tier_name

        return "unknown"

    def select(self, model_name: str = "", purpose: str = "") -> Optional[ModelInfo]:
        """Select model by name or purpose. Returns full ModelInfo with provider/base_url/api_key_env.

        Resolution order:
          1. model_name given → find by name first (user-friendly), then by ID
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
        # Search by name first (user-friendly), then by ID
        # Prefer LOCAL models over EXTERNAL (faster, no API key needed)
        best = None
        for m in self._models.values():
            if m.name == name:
                if m.source == ModelSource.LOCAL:
                    return m
                if best is None:
                    best = m
        if best is not None:
            return best
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
                    # Map camelCase frontend keys to snake_case model fields
                    mapped = {"adapterId": "adapter_id", "apiKeyEnv": "api_key_env",
                              "maxTokens": "max_tokens", "topP": "top_p",
                              "baseUrl": "base_url", "apiKey": "api_key"}.get(cfg_key, cfg_key)
                    if hasattr(model.config, mapped):
                        setattr(model.config, mapped, cfg_value)
            elif hasattr(model, key):
                setattr(model, key, value)
        
        model.updated_at = datetime.now(timezone.utc)
        
        if model.source in (ModelSource.EXTERNAL, ModelSource.CONFIG):
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
        """重新扫描本地模型（管理 UI 调用）。去重后返回，避免重复显示。"""
        if endpoint:
            endpoints = [endpoint]
        else:
            endpoints = self._config_loader.get_local_scan_endpoints()
        if not endpoints:
            return []

        before = {m.name for m in self._models.values()}

        local_models = await scan_local_models(endpoints)

        for model in local_models:
            existing = self._find_model_by_name(model.name)
            if existing is not None:
                if not existing.size or existing.size == 0:
                    existing.size = getattr(model, 'size', None) or existing.size
                if getattr(model, 'quantization', None):
                    existing.quantization = model.quantization
                existing.is_downloaded = True
                existing.supports_gpu = True
                # 修正适配器注册时的类型/provider 误判
                if model.provider and existing.provider in ("deepseek", "openai", "anthropic"):
                    existing.provider = model.provider
                if model.type and model.type != existing.type:
                    existing.type = model.type
                continue
            if model.id not in self._models:
                self._models[model.id] = model

        try:
            await self._sync_local_to_adapter(local_models, endpoints)
        except Exception as e:
            logging.debug("scan→adapter sync skipped: %s", str(e)[:200], exc_info=True)

        after = {m.name for m in self._models.values()}
        self._scan_new_count = len(after - before)

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

    def retire_stale_models(self, inactivity_days: int = 30) -> int:
        """Phase 51: Auto-retire models unused for N days.

        Models from local_models or external_models that have zero usage
        and were added more than inactivity_days ago are marked as DEPRECATED.
        Config models (YAML) are never auto-retired.

        Returns count of retired models.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (inactivity_days * 86400)
        retired = 0
        for model in list(self._models.values()):
            if model.source == ModelSource.CONFIG:
                continue  # config models never auto-retire
            if model.status == ModelStatus.AVAILABLE:
                created = getattr(model, 'created_at', None)
                if isinstance(created, (int, float)):
                    created = datetime.fromtimestamp(created, tz=timezone.utc).timestamp()
                elif isinstance(created, datetime):
                    created = created.timestamp()
                else:
                    continue
                if created < cutoff:
                    model.status = ModelStatus.DEPRECATED
                    model.metadata["retired_reason"] = f"inactive {inactivity_days}+ days"
                    retired += 1
        if retired:
            logging.getLogger("infra.model").info(
                "Auto-retired %d stale models (inactive ≥%d days)", retired, inactivity_days
            )
        return retired

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

    def export_models(self, output_dir: str, progress_cb=None) -> dict:
        """Export model manifest for offline deployment (FDE Toolkit A).
        
        Generates a models_manifest.json listing all models (name, provider, source).
        Does NOT export model files (GGUF) — ollama models are re-pulled at customer site.
        Remote API models export as metadata only (FDE configures API keys at customer site).
        
        Args:
            output_dir: Target directory for manifest
            progress_cb: Optional callback(i, total, model_name) for progress tracking
        """
        manifests = {"local": [], "remote": [], "skipped": []}
        os.makedirs(output_dir, exist_ok=True)
        models = list(self._models.values())
        total = len(models)
        for i, model in enumerate(models):
            if progress_cb:
                progress_cb(i, total, model.name)
            entry = {"name": model.name, "provider": model.provider,
                     "source": model.source.value if hasattr(model.source, 'value') else str(model.source)}
            if model.provider == "ollama" and model.source in (ModelSource.LOCAL, "local"):
                manifests["local"].append(entry)
            elif model.provider in ("openai", "deepseek", "anthropic"):
                manifests["remote"].append(entry)
            else:
                manifests["skipped"].append(entry)
        # Write manifest
        import json as _json
        manifest_path = os.path.join(output_dir, "models_manifest.json")
        with open(manifest_path, "w") as fh:
            _json.dump(manifests, fh, indent=2, ensure_ascii=False)
        return manifests
