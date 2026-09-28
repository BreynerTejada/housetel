# Housetel backend — production image (gunicorn / celery worker / celery beat share it).
# Build context: ./backend (see docker-compose.prod.yml). Only runtime dependencies and the application code are
# copied: no tests tooling, no media, no private documents from a developer's machine.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime section of requirements.txt only (everything above "# Tests and lint").
COPY requirements.txt /tmp/requirements.txt
RUN sed '/^# Tests and lint/,$d' /tmp/requirements.txt > /tmp/requirements-runtime.txt \
    && pip install -r /tmp/requirements-runtime.txt \
    && rm /tmp/requirements*.txt

# Unprivileged user; the data folders are created here so fresh named volumes inherit their ownership.
RUN groupadd --system --gid 10001 housetel \
    && useradd --system --uid 10001 --gid housetel --home-dir /app --no-create-home --shell /usr/sbin/nologin housetel \
    && mkdir -p /data/media /data/private /app/staticfiles \
    && chown -R housetel:housetel /data /app/staticfiles

COPY manage.py pyproject.toml ./
COPY config ./config
COPY apps ./apps

ENV DJANGO_ENV=production \
    MEDIA_ROOT=/data/media \
    PRIVATE_MEDIA_ROOT=/data/private \
    STATIC_ROOT=/app/staticfiles

USER housetel
EXPOSE 8000

# The web process (docker-compose.prod.yml runs migrate + collectstatic first); worker/beat override the command.
CMD ["gunicorn", "config.wsgi:application", "-c", "config/gunicorn_conf.py"]
