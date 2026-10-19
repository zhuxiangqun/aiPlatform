import multiprocessing
import os

_port = os.getenv("AIPLAT_PORT", "8000")
bind = os.getenv("AIPLAT_MANAGEMENT_BIND", f"127.0.0.1:{_port}")
_bind_host = bind.rsplit(":", 1)[0].strip().strip("[]")
_mgmt_token = (
    os.getenv("AIPLAT_MANAGEMENT_API_TOKEN") or os.getenv("AIPLAT_MANAGEMENT_API_KEY") or ""
).strip()
if _bind_host not in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1") and not _mgmt_token:
    raise SystemExit(
        "Refusing to bind non-loopback without AIPLAT_MANAGEMENT_API_TOKEN "
        "(or AIPLAT_MANAGEMENT_API_KEY)"
    )

# Management service is memory-heavy (loads all agents/skills/knowledge).
# Hard cap at 8 workers to prevent OOM kills. Scale horizontally if needed.
workers = min(multiprocessing.cpu_count() * 2 + 1, 8)
worker_class = "uvicorn.workers.UvicornWorker"
preload_app = False
timeout = 180                # Management endpoints can be heavy (diagnostics, etc.)
graceful_timeout = 30
keepalive = 5
max_requests = 10000
max_requests_jitter = 1000

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("AIPLAT_LOG_LEVEL", "info")
