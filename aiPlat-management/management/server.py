"""
aiPlat-management 服务器 - FastAPI 应用
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yaml
from pathlib import Path
from typing import Dict, Any

from management.api import dashboard, alerting, diagnostics, infra, core, audit, policies, onboarding
from management.api.proxy import build_app_proxy_router, build_platform_proxy_router
from management.api.alerting import router as alerting_router, alias_router as alerts_router
from management.dashboard import DashboardAggregator, InfraAdapter, CoreAdapter, PlatformAdapter, AppAdapter
from management.monitoring import InfraMetricsCollector, CoreMetricsCollector, PlatformMetricsCollector, AppMetricsCollector
from management.diagnostics import InfraHealthChecker, CoreHealthChecker, PlatformHealthChecker, AppHealthChecker
from management.alerting import AlertEngine
from management.config import ConfigManager
from management.infra_client import InfraAPIClient, InfraAPIClientConfig
from management.core_client import CoreAPIClient, CoreAPIClientConfig, CoreAPIError


def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = Path(__file__).parent.parent / "config" / "management.yaml"
    
    if not config_path.exists():
        return get_default_config()
    
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_default_config() -> Dict[str, Any]:
    """获取默认配置"""
    return {
        "management": {
            "layers": {
                "infra": {"endpoint": "http://localhost:8001", "enabled": True},
                "core": {"endpoint": "http://localhost:8002", "enabled": True},
                "platform": {"endpoint": "http://localhost:8003", "enabled": True},
                "app": {"endpoint": "http://localhost:8004", "enabled": True},
            },
            "monitoring": {"interval": 60},
            "dashboard": {"refresh_interval": 10},
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8000,
            "api": {"prefix": "/api"},
        }
    }


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    config = load_config()
    
    app = FastAPI(
        title="aiPlat-management",
        description="AI Platform Management System - Dashboard, Monitoring, Alerting, Diagnostics",
        version="0.1.0",
    )

    # Proxy core errors as-is (preserve gate/approval envelopes).
    @app.exception_handler(CoreAPIError)
    async def _handle_core_api_error(_: Request, exc: CoreAPIError):
        return JSONResponse(status_code=exc.status_code, content=exc.payload)

    # PR-01: propagate tenant/actor headers to downstream core/platform/app clients.
    try:
        from management.request_context import set_forward_headers, reset_forward_headers

        @app.middleware("http")
        async def _forward_identity_headers(req: Request, call_next):
            forward: Dict[str, str] = {}
            for k in ("x-aiplat-tenant-id", "x-aiplat-actor-id", "x-aiplat-actor-role", "x-aiplat-request-id"):
                v = req.headers.get(k) or req.headers.get(k.upper())
                if v:
                    # keep canonical header casing
                    forward[k.upper()] = v
            token = set_forward_headers(forward if forward else None)
            try:
                return await call_next(req)
            finally:
                try:
                    reset_forward_headers(token)
                except Exception:
                    pass
    except Exception:
        pass
    
    # 配置 CORS
    cors_config = config.get("server", {}).get("api", {}).get("cors", {})
    if cors_config.get("enabled", True):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_config.get("origins", ["*"]),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # 注册 API 路由
    api_prefix = config.get("server", {}).get("api", {}).get("prefix", "/api")
    app.include_router(dashboard.router, prefix=api_prefix)
    app.include_router(alerting.router, prefix=api_prefix)
    app.include_router(alerts_router, prefix=api_prefix)  # 别名路由 /api/alerts
    app.include_router(diagnostics.router, prefix=api_prefix)
    app.include_router(infra.router, prefix=api_prefix)
    app.include_router(core.router, prefix=api_prefix)
    app.include_router(onboarding.router, prefix=api_prefix)
    app.include_router(audit.router, prefix=api_prefix)
    app.include_router(policies.router, prefix=api_prefix)
    app.include_router(build_platform_proxy_router(), prefix=api_prefix)
    app.include_router(build_app_proxy_router(), prefix=api_prefix)
    
    # 创建聚合器和适配器
    aggregator = DashboardAggregator()
    layers_config = config.get("management", {}).get("layers", {})
    
    if layers_config.get("infra", {}).get("enabled", True):
        aggregator.register_adapter("infra", InfraAdapter(
            endpoint=layers_config["infra"]["endpoint"]
        ))
    
    if layers_config.get("core", {}).get("enabled", True):
        aggregator.register_adapter("core", CoreAdapter(
            endpoint=layers_config["core"]["endpoint"]
        ))
    
    if layers_config.get("platform", {}).get("enabled", True):
        aggregator.register_adapter("platform", PlatformAdapter(
            endpoint=layers_config["platform"]["endpoint"]
        ))
    
    if layers_config.get("app", {}).get("enabled", True):
        aggregator.register_adapter("app", AppAdapter(
            endpoint=layers_config["app"]["endpoint"]
        ))
    
    # 存储到应用状态
    app.state.config = config
    app.state.aggregator = aggregator
    # Single source of truth for mutable runtime state
    app.state.active_alerts = {}
    app.state.collectors = {
        "infra": InfraMetricsCollector(),
        "core": CoreMetricsCollector(),
        "platform": PlatformMetricsCollector(),
        "app": AppMetricsCollector(),
    }
    app.state.health_checkers = {
        "infra": InfraHealthChecker(endpoint=layers_config.get("infra", {}).get("endpoint")),
        "core": CoreHealthChecker(endpoint=layers_config.get("core", {}).get("endpoint")),
        "platform": PlatformHealthChecker(endpoint=layers_config.get("platform", {}).get("endpoint")),
        "app": AppHealthChecker(endpoint=layers_config.get("app", {}).get("endpoint")),
    }
    app.state.alert_engine = AlertEngine()
    app.state.config_manager = ConfigManager()

    # HTTP clients (configured by management.yaml)
    infra_ep = layers_config.get("infra", {}).get("endpoint", "http://localhost:8001")
    core_ep = layers_config.get("core", {}).get("endpoint", "http://localhost:8002")
    app.state.infra_client = InfraAPIClient(InfraAPIClientConfig(base_url=infra_ep, timeout=30.0))
    app.state.core_client = CoreAPIClient(CoreAPIClientConfig(base_url=core_ep, timeout=30.0))
    # Backward compatibility: keep module-level singletons aligned if present
    try:
        from management.api import core as _core_api
        _core_api._core_client = app.state.core_client
    except Exception:
        pass
    
    # 健康检查端点
    @app.get("/health")
    async def health_check():
        """健康检查"""
        return {"status": "healthy", "version": "0.1.0"}
    
    # 根路径 - API 信息
    @app.get("/")
    async def root():
        """根路径 - API 信息"""
        return {
            "name": "aiPlat-management",
            "version": "0.1.0",
            "description": "AI Platform Management System",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": "/health",
            "endpoints": {
                "dashboard": "/api/dashboard",
                "infra": "/api/infra",
                "core": "/api/core",
                "alerting": "/api/alerting",
                "alerts": "/api/alerts",  # 别名
                "diagnostics": "/api/diagnostics",
            }
        }
    
    # API 文档端点
    @app.get("/api")
    async def api_docs():
        """API 总览"""
        return {
            "endpoints": {
                "dashboard": {
                    "status": "/api/dashboard/status",
                    "health": "/api/dashboard/health",
                    "metrics": "/api/dashboard/metrics"
                },
                "infra": {
                    "nodes": "/api/infra/nodes",
                    "models": "/api/infra/models",
                    "services": "/api/infra/services",
                    "scheduler": "/api/infra/scheduler",
                    "storage": "/api/infra/storage",
                    "network": "/api/infra/network",
                    "monitoring": "/api/infra/monitoring"
                },
                "core": {
                    "agents": "/api/core/agents",
                    "skills": "/api/core/skills",
                    "memory": "/api/core/memory/sessions",
                    "knowledge": "/api/core/knowledge/collections",
                    "adapters": "/api/core/adapters",
                    "harness": "/api/core/harness"
                },
                "alerting": {
                    "alerts": "/api/alerting/alerts",
                    "rules": "/api/alerting/rules"
                },
                "diagnostics": {
                    "health": "/api/diagnostics/health/{layer}",
                    "all": "/api/diagnostics/health/all"
                }
            }
        }
    
    return app


def run_server():
    """运行服务器"""
    import uvicorn
    
    config = load_config()
    server_config = config.get("server", {})
    
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8000)
    
    print(f"\n{'='*60}")
    print("  aiPlat-management - AI Platform Management System")
    print(f"{'='*60}")
    print(f"  Version: 0.1.0")
    print(f"  Server: http://{host}:{port}")
    print(f"  API Docs: http://{host}:{port}/docs")
    print(f"{'='*60}\n")
    
    uvicorn.run(
        "management.server:create_app",
        host=host,
        port=port,
        reload=False,
        factory=True,
    )


if __name__ == "__main__":
    run_server()
