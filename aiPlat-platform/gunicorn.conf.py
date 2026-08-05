import multiprocessing
import os

_port = os.getenv("AIPLAT_PORT", "8003")
bind = f"0.0.0.0:{_port}"

workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
preload_app = True
timeout = 120
graceful_timeout = 30
keepalive = 5
max_requests = 10000
max_requests_jitter = 1000

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("AIPLAT_LOG_LEVEL", "info")
