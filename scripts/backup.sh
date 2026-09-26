#!/usr/bin/env bash
# TalentScreen AI — Production Encrypted Backup Script (Task B24)
# Invariants: DB + Blobs consistency, SHA-256 manifest, zero secret leakage.

set -euo pipefail

BACKUP_ROOT="${1:-./backups/$(date +%Y%m%d_%H%M%S)}"
PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-talentscreen}"
STORAGE_DIR="${PRIVATE_STORAGE_ROOT:-./private_storage}"
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-TalentScreen_Secure_Backup_Passphrase_2026}"
DOCKER_CONTAINER="${PG_DOCKER_CONTAINER:-talentscreen-postgres}"

mkdir -p "${BACKUP_ROOT}"
chmod 700 "${BACKUP_ROOT}"

echo "[INFO] Starting TalentScreen AI backup at ${BACKUP_ROOT}..."

# 1. Dump PostgreSQL database (plain SQL before encryption)
echo "[INFO] Dumping PostgreSQL database (${PG_DB})..."
if command -v pg_dump >/dev/null 2>&1; then
  PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" pg_dump \
    -h "${PG_HOST}" \
    -p "${PG_PORT}" \
    -U "${PG_USER}" \
    -d "${PG_DB}" \
    --no-owner \
    --clean \
    --if-exists \
    > "${BACKUP_ROOT}/db_dump.sql"
elif docker ps --format '{{.Names}}' | grep -q "${DOCKER_CONTAINER}"; then
  echo "[INFO] Using Docker container '${DOCKER_CONTAINER}' for pg_dump..."
  docker exec -i "${DOCKER_CONTAINER}" pg_dump \
    -U "${PG_USER}" \
    -d "${PG_DB}" \
    --no-owner \
    --clean \
    --if-exists \
    > "${BACKUP_ROOT}/db_dump.sql"
else
  echo "[ERROR] Neither pg_dump nor docker container '${DOCKER_CONTAINER}' was found." >&2
  exit 1
fi

# 2. Archive private blob storage
echo "[INFO] Archiving private blob storage (${STORAGE_DIR})..."
if [ -d "${STORAGE_DIR}" ] && [ "$(ls -A "${STORAGE_DIR}")" ]; then
  tar -czf "${BACKUP_ROOT}/blobs.tar.gz" -C "${STORAGE_DIR}" .
else
  tar -czf "${BACKUP_ROOT}/blobs.tar.gz" --files-from /dev/null
fi

# 3. Encrypt both artifacts with AES-256-CBC
echo "[INFO] Encrypting backup archives with AES-256-CBC..."
openssl enc -aes-256-cbc -salt -pbkdf2 \
  -in "${BACKUP_ROOT}/db_dump.sql" \
  -out "${BACKUP_ROOT}/db_dump.sql.enc" \
  -pass "pass:${ENCRYPTION_KEY}"

openssl enc -aes-256-cbc -salt -pbkdf2 \
  -in "${BACKUP_ROOT}/blobs.tar.gz" \
  -out "${BACKUP_ROOT}/blobs.tar.gz.enc" \
  -pass "pass:${ENCRYPTION_KEY}"

# Remove unencrypted plain files
rm -f "${BACKUP_ROOT}/db_dump.sql" "${BACKUP_ROOT}/blobs.tar.gz"

# 4. Generate SHA256 integrity manifest
echo "[INFO] Computing SHA-256 integrity checksums..."
cd "${BACKUP_ROOT}"
shasum -a 256 db_dump.sql.enc blobs.tar.gz.enc > manifest.sha256
chmod 600 db_dump.sql.enc blobs.tar.gz.enc manifest.sha256

echo "[OK] Backup completed successfully."
echo "{\"backup_directory\": \"${BACKUP_ROOT}\", \"status\": \"success\", \"encrypted\": true}"
