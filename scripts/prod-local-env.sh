#!/usr/bin/env bash
# Writes a throwaway env file to try the production stack on this machine over plain http (no domain, no TLS).
# Never use it for a real deployment (start from deploy/env.prod.example instead).
#
#   scripts/prod-local-env.sh /tmp/housetel-prod.env [port]
#   make prod-build prod-up PROD_ENV_FILE=/tmp/housetel-prod.env
set -euo pipefail

OUT="${1:-/tmp/housetel-prod.env}"
PORT="${2:-8080}"
command -v python3 > /dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
[ -e "$OUT" ] && { echo "$OUT already exists: remove it or choose another path" >&2; exit 1; }

read -r SECRET FERNET DBPASS < <(python3 -c '
import base64, os, secrets
print(secrets.token_urlsafe(50), base64.urlsafe_b64encode(os.urandom(32)).decode(), secrets.token_hex(16))')

umask 077
cat > "$OUT" <<ENV
# Throwaway env for trying the production stack locally (scripts/prod-local-env.sh). Not a real deployment.
FRONTEND_URL=http://localhost:$PORT
DJANGO_SECRET_KEY=$SECRET
FERNET_KEY=$FERNET
POSTGRES_PASSWORD=$DBPASS
HOUSETEL_HTTP_PORT=$PORT
NUM_PROXIES=1
# Plain http on localhost only: production keeps the redirect to https on.
DJANGO_SECURE_SSL_REDIRECT=0
GUNICORN_WORKERS=2
CELERY_CONCURRENCY=1
ADMIN_ENABLED=0
HOUSETEL_ALLOW_SIMULATIONS=0
SUPPORT_EMAIL=soporte@housetel.co
EMAIL_HOST=localhost
EMAIL_PORT=1025
BACKUP_DIR=backups
ENV
echo "Wrote $OUT (port $PORT). Next: make prod-build prod-up PROD_ENV_FILE=$OUT"
