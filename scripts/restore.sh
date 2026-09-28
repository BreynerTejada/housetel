#!/usr/bin/env bash
# Housetel restore (plan P1): puts a backup made by scripts/backup.sh back into the production stack.
#
#   scripts/restore.sh backups/housetel-<stamp>-db.dump [--yes]      (make restore FILE=...)
#
# - Verifies the checksums when housetel-<stamp>.sha256 is next to the dump.
# - Stops nginx, backend, worker and beat; recreates the database and restores the dump into it (--exit-on-error).
# - Restores housetel-<stamp>-media.tar.gz (public + private media) when it exists, replacing the current files.
# - Starts the stack again (the backend applies any newer migrations on start-up).
# It destroys the current data: it asks you to type RESTORE unless --yes (or RESTORE_CONFIRM=yes) is given.
# The database is restored with the same FERNET_KEY in the env file as when the backup was made.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="${PROD_ENV_FILE:-.env.prod}"
FILE="${1:-}"
CONFIRM="${RESTORE_CONFIRM:-}"
[ "${2:-}" = "--yes" ] && CONFIRM=yes

log() { printf '[restore %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { printf '[restore] ERROR: %s\n' "$*" >&2; exit 1; }
setting() {
  local name="$1" default="${2:-}" value="${!1:-}"
  if [ -z "$value" ] && [ -f "$ENV_FILE" ]; then
    value="$(grep -E "^${name}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
  fi
  printf '%s' "${value:-$default}"
}

[ -n "$FILE" ] || die "usage: scripts/restore.sh backups/housetel-<stamp>-db.dump [--yes]"
[ -f "$FILE" ] || die "file not found: $FILE"
[ -f "$ENV_FILE" ] || die "env file not found: $ENV_FILE (set PROD_ENV_FILE)"
NAME="$(basename "$FILE")"
[[ "$NAME" =~ ^housetel-([0-9]{8}T[0-9]{6}Z)-db\.dump$ ]] || die "expected housetel-<stamp>-db.dump, got $NAME"
STAMP="${BASH_REMATCH[1]}"
DIR="$(cd "$(dirname "$FILE")" && pwd)"
MEDIA_FILE="$DIR/housetel-$STAMP-media.tar.gz"
SUM_FILE="$DIR/housetel-$STAMP.sha256"
PROJECT="$(setting COMPOSE_PROJECT housetel-prod)"
COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.prod.yml --env-file "$ENV_FILE")
export PROD_ENV_FILE="$ENV_FILE"

if [ -f "$SUM_FILE" ]; then
  log "checking checksums ($SUM_FILE)"
  (cd "$DIR" && sha256sum --check --ignore-missing --quiet "$(basename "$SUM_FILE")") || die "checksum mismatch"
fi

echo "This replaces the database$([ -f "$MEDIA_FILE" ] && echo ' and all media files') of project '$PROJECT' with backup $STAMP."
if [ "$CONFIRM" != "yes" ]; then
  read -r -p "Type RESTORE to continue: " answer
  [ "$answer" = "RESTORE" ] || die "cancelled"
fi

log "stopping nginx, backend, worker and beat"
"${COMPOSE[@]}" stop nginx backend worker beat
"${COMPOSE[@]}" up -d --wait db redis

log "recreating the database and restoring $NAME"
"${COMPOSE[@]}" exec -T db sh -c \
  'dropdb -U "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
"${COMPOSE[@]}" exec -T db sh -c \
  'pg_restore --no-owner --no-privileges --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$FILE"

if [ -f "$MEDIA_FILE" ]; then
  log "restoring media ($(basename "$MEDIA_FILE"))"
  "${COMPOSE[@]}" run --rm --no-deps -T backend sh -c \
    'find /data/media /data/private -mindepth 1 -delete && tar -C /data -xzf -' < "$MEDIA_FILE"
else
  log "no media archive for $STAMP: media files left as they are"
fi

log "starting the stack"
"${COMPOSE[@]}" up -d --wait --wait-timeout 300
log "done: restored $STAMP"
