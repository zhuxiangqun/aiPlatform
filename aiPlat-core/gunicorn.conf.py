import multiprocessing
import os

_port = os.getenv("AIPLAT_PORT", "8002")
bind = f"0.0.0.0:{_port}"

workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
preload_app = True            # Resolve fork + asyncio conflict on macOS/Linux
timeout = 120                 # Max seconds per worker request
graceful_timeout = 30         # Graceful shutdown window
keepalive = 5
max_requests = 10000          # Auto-restart worker after N requests (memory leak guard)
max_requests_jitter = 1000    # Jitter to avoid simultaneous restarts

accesslog = "-"               # stdout (Docker log collector)
errorlog = "-"
loglevel = os.getenv("AIPLAT_LOG_LEVEL", "info")
