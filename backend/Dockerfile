FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends gettext curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# docker-compose runs these containers as ${HOST_UID:-1000}:${HOST_GID:-1000} (files written through the bind
# mount stay editable on the host). Give that uid/gid a passwd/group entry: without one, Celery's privilege
# check cannot resolve the group, "assumes root" and warns on every worker start.
ARG APP_UID=1000
ARG APP_GID=1000
RUN (getent group "$APP_GID" >/dev/null || groupadd --gid "$APP_GID" app) \
    && (getent passwd "$APP_UID" >/dev/null \
        || useradd --uid "$APP_UID" --gid "$APP_GID" --no-create-home --home-dir /tmp --shell /usr/sbin/nologin app)
COPY . .
EXPOSE 8000
