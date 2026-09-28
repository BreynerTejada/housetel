#!/usr/bin/env bash
# Crea el archivo .env a partir de .env.example con claves nuevas (DJANGO_SECRET_KEY y FERNET_KEY).
# Es seguro correrlo varias veces: si .env ya existe, no lo toca.
# Uso (Linux, macOS o WSL):  ./scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env ya existe: no se modifica."
  exit 0
fi

gen_secret() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
  else
    openssl rand -base64 48 | tr '+/' '-_' | tr -d '=\n'
  fi
}

gen_fernet() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
  else
    openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
  fi
}

secret="$(gen_secret)"
fernet="$(gen_fernet)"

awk -v s="$secret" -v f="$fernet" '
  /^DJANGO_SECRET_KEY=$/ { print "DJANGO_SECRET_KEY=" s; next }
  /^FERNET_KEY=$/ { print "FERNET_KEY=" f; next }
  { print }
' .env.example > .env

chmod 600 .env
echo ".env creado con claves nuevas."
echo "Siguiente paso: docker compose up -d --build"
