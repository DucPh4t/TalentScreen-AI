#!/usr/bin/env bash
# TalentScreen AI — Production Encrypted Backup Script (Task B24)
# Invariants: DB + Blobs consistency, SHA-256 manifest, zero secret leakage.

set -euo pipefail
umask 077

BACKUP_ROOT="${1:-./backups/$(date +%Y%m%d_%H%M%S)}"
PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-talentscreen}"
STORAGE_DIR="${PRIVATE_STORAGE_ROOT:-./private_storage}"
if [ -z "${BACKUP_ENCRYPTION_KEY:-}" ]; then
  echo "[ERROR] BACKUP_ENCRYPTION_KEY must be set; there is no default backup passphrase." >&2
  exit 1
fi
DOCKER_CONTAINER="${PG_DOCKER_CONTAINER:-}"

mkdir -p "${BACKUP_ROOT}"
chmod 700 "${BACKUP_ROOT}"

echo "[INFO] Starting TalentScreen AI backup at ${BACKUP_ROOT}..."

# 1. Stream PostgreSQL dump directly into encryption; no plaintext backup file.
echo "[INFO] Dumping PostgreSQL database (${PG_DB})..."
if command -v pg_dump >/dev/null 2>&1; then
  PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" pg_dump \
    -h "${PG_HOST}" \
    -p "${PG_PORT}" \
    -U "${PG_USER}" \
    -d "${PG_DB}" \
    --no-owner \
    --clean \
    --if-exists | openssl enc -aes-256-cbc -salt -pbkdf2 \
    -out "${BACKUP_ROOT}/db_dump.sql.enc" -pass env:BACKUP_ENCRYPTION_KEY
elif [ -n "${DOCKER_CONTAINER}" ] && docker container inspect "${DOCKER_CONTAINER}" >/dev/null 2>&1; then
  echo "[INFO] Using Docker container '${DOCKER_CONTAINER}' for pg_dump..."
  docker exec -i "${DOCKER_CONTAINER}" pg_dump \
    -U "${PG_USER}" \
    -d "${PG_DB}" \
    --no-owner \
    --clean \
    --if-exists | openssl enc -aes-256-cbc -salt -pbkdf2 \
    -out "${BACKUP_ROOT}/db_dump.sql.enc" -pass env:BACKUP_ENCRYPTION_KEY
else
  echo "[ERROR] Neither pg_dump nor an explicit PG_DOCKER_CONTAINER was found." >&2
  exit 1
fi

# 2. Stream private blob archive directly into encryption.
echo "[INFO] Archiving private blob storage (${STORAGE_DIR})..."
if [ -d "${STORAGE_DIR}" ] && [ "$(ls -A "${STORAGE_DIR}")" ]; then
  tar -czf - -C "${STORAGE_DIR}" . | openssl enc -aes-256-cbc -salt -pbkdf2 \
    -out "${BACKUP_ROOT}/blobs.tar.gz.enc" -pass env:BACKUP_ENCRYPTION_KEY
else
  tar -czf - --files-from /dev/null | openssl enc -aes-256-cbc -salt -pbkdf2 \
    -out "${BACKUP_ROOT}/blobs.tar.gz.enc" -pass env:BACKUP_ENCRYPTION_KEY
fi

# 4. Generate SHA256 integrity manifest
echo "[INFO] Computing SHA-256 integrity checksums..."
cd "${BACKUP_ROOT}"
shasum -a 256 db_dump.sql.enc blobs.tar.gz.enc > manifest.sha256
chmod 600 db_dump.sql.enc blobs.tar.gz.enc manifest.sha256

echo "[OK] Backup completed successfully."
echo "{\"backup_directory\": \"${BACKUP_ROOT}\", \"status\": \"success\", \"encrypted\": true}"
