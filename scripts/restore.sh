#!/usr/bin/env bash
# TalentScreen AI — Production Encrypted Restore Script (Task B24)
# Invariants: SHA256 verification, Decryption, DB+Blobs consistency, SEC-11 Deletion Ledger sweep.

set -euo pipefail
umask 077

BACKUP_DIR="${1:?Usage: ./scripts/restore.sh <path_to_backup_directory>}"
PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-talentscreen}"
STORAGE_DIR="${PRIVATE_STORAGE_ROOT:-./private_storage}"
if [ -z "${BACKUP_ENCRYPTION_KEY:-}" ]; then
  echo "[ERROR] BACKUP_ENCRYPTION_KEY must be set; there is no default backup passphrase." >&2
  exit 1
fi
if [ "${RESTORE_CONFIRM_DB:-}" != "${PG_DB}" ]; then
  echo "[ERROR] Set RESTORE_CONFIRM_DB to the exact target database name before restore." >&2
  exit 1
fi
DOCKER_CONTAINER="${PG_DOCKER_CONTAINER:-}"

echo "[INFO] Starting TalentScreen AI restore from ${BACKUP_DIR}..."

# 1. Verify SHA-256 integrity
echo "[INFO] Verifying archive checksums against manifest.sha256..."
(cd "${BACKUP_DIR}" && shasum -a 256 -c manifest.sha256)

# Verify the key and archive format before any database mutation. CBC is not
# authenticated, so the protected backup directory still requires access control.
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in "${BACKUP_DIR}/db_dump.sql.enc" -pass env:BACKUP_ENCRYPTION_KEY >/dev/null
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in "${BACKUP_DIR}/blobs.tar.gz.enc" -pass env:BACKUP_ENCRYPTION_KEY | tar -tzf - >/dev/null

# 2. Stream decrypted database dump into the target; never write plaintext SQL.
echo "[INFO] Restoring database (${PG_DB})..."
if command -v psql >/dev/null 2>&1; then
  openssl enc -d -aes-256-cbc -pbkdf2 \
    -in "${BACKUP_DIR}/db_dump.sql.enc" -pass env:BACKUP_ENCRYPTION_KEY | \
  PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" psql -q -v ON_ERROR_STOP=1 \
    -h "${PG_HOST}" \
    -p "${PG_PORT}" \
    -U "${PG_USER}" \
    -d "${PG_DB}"
elif [ -n "${DOCKER_CONTAINER}" ] && docker container inspect "${DOCKER_CONTAINER}" >/dev/null 2>&1; then
  echo "[INFO] Using Docker container '${DOCKER_CONTAINER}' for psql..."
  openssl enc -d -aes-256-cbc -pbkdf2 \
    -in "${BACKUP_DIR}/db_dump.sql.enc" -pass env:BACKUP_ENCRYPTION_KEY | \
  docker exec -i "${DOCKER_CONTAINER}" psql -q -v ON_ERROR_STOP=1 \
    -U "${PG_USER}" \
    -d "${PG_DB}"
else
  echo "[ERROR] Neither psql nor an explicit PG_DOCKER_CONTAINER was found." >&2
  exit 1
fi

# 3. Restore blob files without writing a plaintext archive.
echo "[INFO] Unpacking blobs to ${STORAGE_DIR}..."
mkdir -p "${STORAGE_DIR}"
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in "${BACKUP_DIR}/blobs.tar.gz.enc" -pass env:BACKUP_ENCRYPTION_KEY | \
  tar -xzf - -C "${STORAGE_DIR}"

# 5. Run Alembic migrations forward
echo "[INFO] Running Alembic migrations forward (upgrade head)..."
if [ -f "./alembic.ini" ]; then
  .venv/bin/alembic upgrade head
elif [ -f "./services/backend/alembic.ini" ]; then
  (cd "./services/backend" && ../../.venv/bin/alembic upgrade head)
fi

# 6. Apply SEC-11 Deletion Ledger to purge any restored zombie records
echo "[INFO] SEC-11 Enforcement: Applying deletion ledger to re-tombstone purged records..."
PYTHONPATH=services/backend .venv/bin/python -m app.cli apply-deletion-ledger

echo "[OK] Restore drill completed successfully. Database and blobs synchronized and deletion ledger applied."
