import multiprocessing
import os

_port = os.getenv("AIPLAT_PORT", "8002")
bind = os.getenv("AIPLAT_CORE_BIND", f"127.0.0.1:{_port}")
from core.api.bind_gate import assert_core_bind_allowed

assert_core_bind_allowed(bind.rsplit(":", 1)[0].strip().strip("[]"))

workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
preload_app = False          # Avoid loading all agents/skills in master; OBJC_DISABLE_... handles fork safety
timeout = 600                # Pipeline can run 5-6 min per stage (LLM calls)
graceful_timeout = 30         # Graceful shutdown window
keepalive = 5
max_requests = 10000          # Auto-restart worker after N requests (memory leak guard)
max_requests_jitter = 1000    # Jitter to avoid simultaneous restarts

accesslog = "-"               # stdout (Docker log collector)
errorlog = "-"
loglevel = os.getenv("AIPLAT_LOG_LEVEL", "info")
