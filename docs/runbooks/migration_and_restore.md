# TalentScreen AI — Operational Runbook: Packaging, Migration & Restore (Task B24)

## 1. Overview & Architecture

TalentScreen AI utilizes a containerized modular architecture designed for high privacy, strict role separation, and deterministic scoring.

### Services Topology
1. **`postgres`**: PostgreSQL 16 with `pgvector` extension. Confined exclusively to internal private network `talentscreen-internal`. No host-bound port exposure in production.
2. **`backend`**: FastAPI application running as unprivileged user `appuser` (UID 10001). Handles authentication, CSRF, intake, provenance, scoring, and audit.
3. **`worker`**: Background worker process running as unprivileged user. Processes jobs with `FOR UPDATE SKIP LOCKED`, lease epochs (fencing tokens), and cooperative cancellation.
4. **`web`**: Next.js 15 standalone frontend running as unprivileged user `nextjs` (UID 1001). Zero candidate PII embedded in client bundles.

---

## 2. Zero-Downtime Database Migration Runbook

All database schema evolutions are managed via Alembic.

### Pre-requisites
- Ensure persistent storage is mounted.
- Execute a full encrypted backup before running migrations.

### Running Migrations Forward
```bash
# Production container
docker exec -it talentscreen-prod-backend alembic upgrade head

# Local / CI environment
.venv/bin/alembic upgrade head
```

### Rollback Procedures
If a migration fails or must be rolled back:
```bash
# Rollback single migration step
docker exec -it talentscreen-prod-backend alembic downgrade -1

# Rollback to specific stable revision
docker exec -it talentscreen-prod-backend alembic downgrade <revision_id>
```

---

## 3. Encrypted Backup Runbook

### Security Invariants
- Backup includes **both** database dump (`db_dump.sql`) and private blob storage (`blobs.tar.gz`).
- Both artifacts are streamed through **AES-256-CBC with PBKDF2** salt derivation; no plaintext dump/archive is written to the backup directory.
- `BACKUP_ENCRYPTION_KEY` is mandatory; scripts have no built-in passphrase. The SHA-256 manifest catches accidental corruption but does not authenticate against a malicious editor of the backup directory.
- A cryptographic integrity manifest `manifest.sha256` is generated.
- Restrictive file permissions (`chmod 600`) are applied immediately.

### Creating a Backup
```bash
# Set secure encryption passphrase
export BACKUP_ENCRYPTION_KEY="<strong_random_secret_passphrase>"
export PG_DOCKER_CONTAINER="<exact_postgres_container_name>"  # if pg_dump/psql are not installed locally

# Execute backup script
./scripts/backup.sh ./backups/prod_$(date +%Y%m%d_%H%M%S)
```

The output directory contains:
```
db_dump.sql.enc       # Encrypted PostgreSQL dump
blobs.tar.gz.enc      # Encrypted private blobs archive
manifest.sha256       # SHA-256 integrity checksums
```

---

## 4. Isolated Restore & SEC-11 Enforcement Runbook

### The SEC-11 Backup Restoration Invariant
> **Invariant (Spec 05 / SEC-11):** When a database is restored from an earlier backup, candidates or applications that were legitimately deleted (GDPR / Right to be forgotten) prior to the disaster recovery event must **NOT** be resurrected into active status. The deletion ledger must be automatically re-applied to purge and re-tombstone any zombie records.

### Running the Restore Drill
```bash
# Execute restore script
./scripts/restore.sh ./backups/prod_20260926_120000
```

### Script Execution Sequence:
1. **Integrity Verification**: Verifies `manifest.sha256` against encrypted archives. Aborts immediately if checksum mismatch is detected.
2. **Decryption**: Streams database dump and blobs using `BACKUP_ENCRYPTION_KEY` without temporary plaintext files. Set `RESTORE_CONFIRM_DB` to the exact target database name and `PG_DOCKER_CONTAINER` to the exact container when local `psql` is absent.
3. **Database Restoration**: Restores schema and records via `psql`.
4. **Blob Storage Synchronization**: Unpacks blobs to `PRIVATE_STORAGE_ROOT`.
5. **Schema Forward Migration**: Executes `alembic upgrade head` to align schema with latest code.
6. **SEC-11 Ledger Sweep**: Runs `python -m app.cli apply-deletion-ledger` which scans `deletion_requests` with status `completed` and ensures all associated target applications/candidates remain tombstoned (`status="deleted"`).
7. **Plaintext Handling**: No decrypted SQL or tar files are written to disk by the script.

---

## 5. Observability & SLI Monitoring

### Admin Endpoints
- **Health / Readiness Probe**: `GET /api/v1/admin/readiness`
  Returns HTTP 200 with `{"database": true, "storage": true}` when services are ready.
- **Aggregated Metrics**: `GET /api/v1/admin/metrics` (Requires `ADMIN` role)
  Provides SLI status, queue latency, worker health, and budget tracking.

### SLI Alarm Thresholds
| SLI Metric | Alarm Threshold | Reason Code | Action |
|---|---|---|---|
| Queue Latency | > 60s average | `ALARM_QUEUE_LATENCY_EXCEEDED` | Scale worker concurrency |
| Worker Health | 0 active workers with queued jobs | `ALARM_WORKER_HEARTBEAT_LOST` | Restart worker container |
| Daily Budget | Spent > Daily Cap ($10.00) | `ALARM_BUDGET_CAP_EXCEEDED` | Suspend paid LLM batch calls |
| Error Rate | > 5% failed jobs | `ALARM_ERROR_RATE_HIGH` | Check provider status & logs |
