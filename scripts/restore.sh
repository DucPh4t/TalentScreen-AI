#!/usr/bin/env bash
# TalentScreen AI — Production Encrypted Restore Script (Task B24)
# Invariants: SHA256 verification, Decryption, DB+Blobs consistency, SEC-11 Deletion Ledger sweep.

set -euo pipefail

BACKUP_DIR="${1:?Usage: ./scripts/restore.sh <path_to_backup_directory>}"
PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-talentscreen}"
STORAGE_DIR="${PRIVATE_STORAGE_ROOT:-./private_storage}"
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-TalentScreen_Secure_Backup_Passphrase_2026}"
DOCKER_CONTAINER="${PG_DOCKER_CONTAINER:-talentscreen-postgres}"

echo "[INFO] Starting TalentScreen AI restore from ${BACKUP_DIR}..."

# 1. Verify SHA-256 integrity
echo "[INFO] Verifying archive checksums against manifest.sha256..."
(cd "${BACKUP_DIR}" && shasum -a 256 -c manifest.sha256)

# 2. Decrypt artifacts
echo "[INFO] Decrypting database dump..."
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in "${BACKUP_DIR}/db_dump.sql.enc" \
  -out "${BACKUP_DIR}/db_dump.restored.sql" \
  -pass "pass:${ENCRYPTION_KEY}"

echo "[INFO] Decrypting blob archive..."
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in "${BACKUP_DIR}/blobs.tar.gz.enc" \
  -out "${BACKUP_DIR}/blobs.restored.tar.gz" \
  -pass "pass:${ENCRYPTION_KEY}"

# 3. Restore PostgreSQL database
echo "[INFO] Restoring database (${PG_DB})..."
if command -v psql >/dev/null 2>&1; then
  PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" psql \
    -h "${PG_HOST}" \
    -p "${PG_PORT}" \
    -U "${PG_USER}" \
    -d "${PG_DB}" \
    < "${BACKUP_DIR}/db_dump.restored.sql"
elif docker ps --format '{{.Names}}' | grep -q "${DOCKER_CONTAINER}"; then
  echo "[INFO] Using Docker container '${DOCKER_CONTAINER}' for psql..."
  docker exec -i "${DOCKER_CONTAINER}" psql \
    -U "${PG_USER}" \
    -d "${PG_DB}" \
    < "${BACKUP_DIR}/db_dump.restored.sql"
else
  echo "[ERROR] Neither psql nor docker container '${DOCKER_CONTAINER}' was found." >&2
  exit 1
fi

# 4. Restore blob files
echo "[INFO] Unpacking blobs to ${STORAGE_DIR}..."
mkdir -p "${STORAGE_DIR}"
tar -xzf "${BACKUP_DIR}/blobs.restored.tar.gz" -C "${STORAGE_DIR}"

# Remove temporary plain files
rm -f "${BACKUP_DIR}/db_dump.restored.sql" "${BACKUP_DIR}/blobs.restored.tar.gz"

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
