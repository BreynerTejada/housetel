#!/usr/bin/env bash
# Housetel backup (plan P1): PostgreSQL (`pg_dump -Fc`) + public and private media, stamped, verified, with a
# retention of N days and an optional off-site copy to S3. `make backup` runs it against the production stack.
#
#   scripts/backup.sh
#
# Settings (shell environment first, then the prod env file PROD_ENV_FILE, default .env.prod):
#   COMPOSE_PROJECT        compose project of the stack (housetel-prod)
#   BACKUP_DIR             where the files go (backups/, created with mode 700)
#   BACKUP_RETENTION_DAYS  local files older than this are deleted (14)
#   BACKUP_DATABASE_URL    managed PostgreSQL outside the stack: dumped with a throwaway postgres:17 container
#   BACKUP_S3_URI          s3://bucket/prefix for an off-site copy (aws CLI, or the amazon/aws-cli image)
#   BACKUP_AWS_ACCESS_KEY_ID / BACKUP_AWS_SECRET_ACCESS_KEY / BACKUP_AWS_DEFAULT_REGION / BACKUP_S3_ENDPOINT_URL
#                          credentials for that copy (default: the AWS_* of the env file)
#
# Output: <BACKUP_DIR>/housetel-<UTC stamp>-db.dump, housetel-<stamp>-media.tar.gz and housetel-<stamp>.sha256.
# The Fernet key (FERNET_KEY) is NOT in the backup: keep it with your secrets, a restore needs the same one.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="${PROD_ENV_FILE:-.env.prod}"

setting() {  # setting NAME DEFAULT → shell value, else the env file's, else DEFAULT (the file is not sourced)
  local name="$1" default="${2:-}" value="${!1:-}"
  if [ -z "$value" ] && [ -f "$ENV_FILE" ]; then
    value="$(grep -E "^${name}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
  fi
  printf '%s' "${value:-$default}"
}
log() { printf '[backup %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { printf '[backup] ERROR: %s\n' "$*" >&2; exit 1; }

[ -f "$ENV_FILE" ] || die "env file not found: $ENV_FILE (set PROD_ENV_FILE)"
PROJECT="$(setting COMPOSE_PROJECT housetel-prod)"
BACKUP_DIR="$(setting BACKUP_DIR backups)"
RETENTION="$(setting BACKUP_RETENTION_DAYS 14)"
DATABASE_URL_EXTERNAL="$(setting BACKUP_DATABASE_URL)"
S3_URI="$(setting BACKUP_S3_URI)"
COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.prod.yml --env-file "$ENV_FILE")
export PROD_ENV_FILE="$ENV_FILE"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
DB_FILE="$BACKUP_DIR/housetel-$STAMP-db.dump"
MEDIA_FILE="$BACKUP_DIR/housetel-$STAMP-media.tar.gz"
SUM_FILE="$BACKUP_DIR/housetel-$STAMP.sha256"
trap 'rm -f "$DB_FILE.partial" "$MEDIA_FILE.partial"' EXIT

# 1. Database (custom format: compressed, restorable table by table) + a readability check of the archive.
log "database → $DB_FILE"
if [ -n "$DATABASE_URL_EXTERNAL" ]; then
  docker run --rm --network host postgres:17-alpine \
    pg_dump -Fc --no-owner --no-privileges "$DATABASE_URL_EXTERNAL" > "$DB_FILE.partial"
  docker run --rm -i postgres:17-alpine pg_restore --list < "$DB_FILE.partial" > /dev/null
else
  "${COMPOSE[@]}" exec -T db sh -c 'pg_dump -Fc --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    > "$DB_FILE.partial"
  "${COMPOSE[@]}" exec -T db pg_restore --list < "$DB_FILE.partial" > /dev/null
fi
mv "$DB_FILE.partial" "$DB_FILE"

# 2. Media: public photos (/data/media) and private files (/data/private), read from the backend container.
log "media → $MEDIA_FILE"
"${COMPOSE[@]}" exec -T backend tar -C /data -czf - media private > "$MEDIA_FILE.partial"
tar -tzf "$MEDIA_FILE.partial" > /dev/null
mv "$MEDIA_FILE.partial" "$MEDIA_FILE"
chmod 600 "$DB_FILE" "$MEDIA_FILE"

(cd "$BACKUP_DIR" && sha256sum "$(basename "$DB_FILE")" "$(basename "$MEDIA_FILE")" > "$(basename "$SUM_FILE")")
log "sizes: $(du -h "$DB_FILE" | cut -f1) database, $(du -h "$MEDIA_FILE" | cut -f1) media"

# 3. Retention of the local copies.
if [ "$RETENTION" -gt 0 ] 2>/dev/null; then
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'housetel-*' -mtime +"$RETENTION" -print -delete \
    | sed 's/^/[backup] deleted (older than '"$RETENTION"' days): /'
fi

# 4. Optional off-site copy (give the bucket a lifecycle rule for its own retention).
if [ -n "$S3_URI" ]; then
  export AWS_ACCESS_KEY_ID="$(setting BACKUP_AWS_ACCESS_KEY_ID "$(setting AWS_ACCESS_KEY_ID)")"
  export AWS_SECRET_ACCESS_KEY="$(setting BACKUP_AWS_SECRET_ACCESS_KEY "$(setting AWS_SECRET_ACCESS_KEY)")"
  export AWS_DEFAULT_REGION="$(setting BACKUP_AWS_DEFAULT_REGION "$(setting AWS_S3_REGION_NAME us-east-1)")"
  ENDPOINT="$(setting BACKUP_S3_ENDPOINT_URL)"
  for file in "$DB_FILE" "$MEDIA_FILE" "$SUM_FILE"; do
    log "upload $(basename "$file") → ${S3_URI%/}/"
    if command -v aws > /dev/null 2>&1; then
      aws s3 cp --only-show-errors ${ENDPOINT:+--endpoint-url "$ENDPOINT"} "$file" "${S3_URI%/}/$(basename "$file")"
    else
      docker run --rm -v "$(cd "$BACKUP_DIR" && pwd):/backup:ro" \
        -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_DEFAULT_REGION amazon/aws-cli \
        s3 cp --only-show-errors ${ENDPOINT:+--endpoint-url "$ENDPOINT"} "/backup/$(basename "$file")" \
        "${S3_URI%/}/$(basename "$file")"
    fi
  done
fi

log "done: $STAMP"
