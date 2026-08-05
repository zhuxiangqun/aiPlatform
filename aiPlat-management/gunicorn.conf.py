import multiprocessing
import os

_port = os.getenv("AIPLAT_PORT", "8000")
bind = f"0.0.0.0:{_port}"

# Management service is memory-heavy (loads all agents/skills/knowledge).
# Hard cap at 8 workers to prevent OOM kills. Scale horizontally if needed.
workers = min(multiprocessing.cpu_count() * 2 + 1, 8)
worker_class = "uvicorn.workers.UvicornWorker"
preload_app = True
timeout = 180                # Management endpoints can be heavy (diagnostics, etc.)
graceful_timeout = 30
keepalive = 5
max_requests = 10000
max_requests_jitter = 1000

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("AIPLAT_LOG_LEVEL", "info")
