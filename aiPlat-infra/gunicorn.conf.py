"""gunicorn.conf：模块接口。"""

import multiprocessing
import os

# Local default loopback; non-loopback needs AIPLAT_INFRA_API_TOKEN (see run_server.py).
# Docker/LAN: export AIPLAT_INFRA_API_HOST=0.0.0.0 and set the token.
_host = os.getenv("AIPLAT_INFRA_API_HOST", "127.0.0.1")
_port = os.getenv("AIPLAT_PORT", os.getenv("AIPLAT_INFRA_API_PORT", "8001"))
bind = f"{_host}:{_port}"

workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
preload_app = False
timeout = 600
graceful_timeout = 30
keepalive = 5
max_requests = 10000
max_requests_jitter = 1000

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("AIPLAT_LOG_LEVEL", "info")
