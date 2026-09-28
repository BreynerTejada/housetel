"""gunicorn settings for production (`gunicorn config.wsgi:application -c config/gunicorn_conf.py`).

Tuned through the environment: GUNICORN_WORKERS (default 2 × CPUs + 1, max 8), GUNICORN_THREADS (2),
GUNICORN_TIMEOUT (60 s: exports and PDF generation can take a while), GUNICORN_BIND (0.0.0.0:8000). Access
logs are off (nginx writes them, with the same request id Django logs); errors go to stderr.
"""

import multiprocessing
import os


def _int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = _int("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 8))
threads = _int("GUNICORN_THREADS", 2)
worker_class = "gthread" if threads > 1 else "sync"
timeout = _int("GUNICORN_TIMEOUT", 60)
graceful_timeout = _int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = 5
# Recycle workers now and then (bounded memory growth), with jitter so they do not restart together.
max_requests = _int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _int("GUNICORN_MAX_REQUESTS_JITTER", 100)
# gunicorn is only reachable from nginx on the internal Docker network: trust its X-Forwarded-* headers.
forwarded_allow_ips = "*"
accesslog = None
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
worker_tmp_dir = "/dev/shm"
