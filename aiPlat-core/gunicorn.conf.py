import multiprocessing
import os

_port = os.getenv("AIPLAT_PORT", "8002")
bind = f"0.0.0.0:{_port}"

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
