import multiprocessing
import os

_port = os.getenv("AIPLAT_PORT", "8003")
bind = os.getenv("AIPLAT_PLATFORM_BIND", f"127.0.0.1:{_port}")
from auth.bind_gate import assert_platform_bind_allowed

assert_platform_bind_allowed(bind.rsplit(":", 1)[0].strip().strip("[]"))

workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
preload_app = True
timeout = 600
graceful_timeout = 30
keepalive = 5
max_requests = 10000
max_requests_jitter = 1000

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("AIPLAT_LOG_LEVEL", "info")
