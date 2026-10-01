# TalentScreen AI — Container deployment, migration and recovery

Updated 2026-10-01. This runbook supports an isolated sandbox. It does not certify recruitment gates G1–G7.

## Topology and configuration

PostgreSQL uses an internal network and named `pg_data` volume, with no exposed database port. A one-shot `migrate` service runs Alembic before the API starts. API and worker run as UID 10001 and share `storage_data:/app/private_storage`. Worker also joins the edge network to reach an approved external provider; it does not inherit the API HTTP healthcheck. Next.js runs as UID 1001 on port 2004; its `/api/*` proxy target is supplied at build time. Host ports bind to **127.0.0.1**. Public access requires separately tested HTTPS ingress.

Use a dedicated mode-600 deployment env file outside Git, not the development `.env`. Set POSTGRES_USER, POSTGRES_DB, POSTGRES_PASSWORD, SECRET_KEY, APP_ORIGIN, APP_ENV, PILOT_STAGE, LLM_PROVIDER and IMAGE_TAG. Generate independent random secrets. Prefer a hexadecimal database password because the connection URL interpolates it; metacharacters otherwise need percent encoding. Pilot rejects the default signing key, keys shorter than 32 characters and non-HTTPS origins, and requires sanitized approval.

Sandbox defaults to mock. An approved pilot requires APP_ENV=pilot, PILOT_STAGE=shadow, the actual HTTPS origin, verified provider/model/prices, explicit rate-card verification date and budget. Configuration values do not prove HR approval or gate completion.

## Build and first startup

Run from the repository root with your dedicated env file/project. Do not print expanded Compose config with secrets.

```bash
docker compose --env-file /secure/talentscreen.deploy.env -f docker-compose.prod.yml -p talentscreen-staging config --quiet
docker compose --env-file /secure/talentscreen.deploy.env -f docker-compose.prod.yml -p talentscreen-staging build backend web
docker compose --env-file /secure/talentscreen.deploy.env -f docker-compose.prod.yml -p talentscreen-staging up -d --no-build
docker compose --env-file /secure/talentscreen.deploy.env -f docker-compose.prod.yml -p talentscreen-staging ps -a
```

Verify migration exit status and backend/web health. Submit a synthetic job to verify the worker: there is no idle heartbeat probe yet. `scripts/deployment_smoke.py` exercises HTTP login, CSRF, JD/rubric, synthetic DOCX ingestion, sanitized approval, mock assessment and evidence. Use an isolated loopback sandbox with mock and an admin credentials file containing SMOKE_LOGIN/SMOKE_PASSWORD. It creates records; do not run against real recruitment data.

Python runtime packages are pinned in `services/backend/requirements.lock`; frontend uses `package-lock.json`/`npm ci`. Refresh deliberately and repeat audit/test checks. Base image tags still need digest pinning and image scanning for a controlled public release. ARM64 validation does not establish AMD64 cloud compatibility.

## Migration and rollback

This is a maintenance procedure, **not a zero-downtime guarantee**:

1. Show a maintenance page; pause intake and drain/stop workers.
2. Back up database plus the actual blob volume at a consistent point.
3. Build immutable image tags and run the one-shot migration.
4. Start services; check schema readiness and a synthetic workflow.
5. Reopen intake after checks pass.

Readiness verifies DB access, actual storage write/read and packaged Alembic head equality; schema mismatch returns 503. Prefer forward repair. Do not blindly downgrade: `e43a2f981207` permits multiple rubric labels on the same CV generation; restoring the old unique constraint fails if such labels exist. Preserve them and repair forward, or restore an explicitly accepted backup into a new isolated deployment. Align code, schema and storage snapshots.

## Backup/restore gaps — blocker for real candidate data

The existing backup/restore scripts stream database and blob archives through AES-256-CBC + PBKDF2, require a passphrase, and verify SHA-256 checksums. Restrict backup-directory access: the manifest is not an authenticated signature. They do **not** yet provide complete named-volume recovery:

- Scripts read PRIVATE_STORAGE_ROOT as a host directory. Export/import the actual named `storage_data` volume; a missing host directory currently becomes an empty archive. Do not accept that as a backup of real CVs.
- Database and blob snapshots are sequential; pause writers or implement consistent snapshots.
- Installed local pg_dump/psql take precedence over PG_DOCKER_CONTAINER. Verify the exact target.
- Migration/ledger CLI use local Python settings; they may target a different database from SQL restore unless DB/storage configuration is aligned. Build a container-native recovery wrapper.
- The deletion ledger lives in the backed-up database. A backup taken before a later deletion lacks that deletion. Replaying this older ledger cannot prevent resurrection.
- The ledger currently re-tombstones records; it does not independently prove restored physical blobs and child records were purged.
- Retention sweep marks database backup status by time. It does not physically delete backup objects or prove provider-side deletion. A scheduled maintenance service is not supplied.

Required drill: upload synthetic A → backup → delete A/prove local purge → restore the earlier snapshot into an isolated DB/volume → import a separately preserved latest deletion ledger → purge restored files, sanitized text, evidence, labels and identity → prove they cannot be accessed. Preserve dated results. G6/SEC-11 remain pending until this succeeds.

## Public ingress and monitoring

Before public access configure and test TLS, exact APP_ORIGIN, Secure cookies, login throttling (e.g. 5 attempts/minute per client with a small burst), per-account protection, upload body limits including multipart overhead above the 10 MiB file limit, timeouts and trusted-proxy handling. Login has no built-in distributed limiter. Keep loopback ports and controlled access until ingress is validated.

`/api/v1/admin/readiness` is a public orchestration probe. Metrics and config diagnostic require ADMIN. Telemetry reports actual ready-queue age, job turnaround, active budget spent/reserved and job-lease health. Missing average queue-wait/worker-execution measurements return null. Job leases do not establish idle worker availability.

Initial alarms: oldest ready job >60s; expired running leases; failed/(succeeded+failed) jobs >5% for jobs created in the last 24h; spent+reserved over period cap or multiple active periods. Prices require dated verification and unknown provider outcomes require reconciliation. Add real worker heartbeats, scheduled maintenance and alert delivery before completing operations gates.


## Build các service dùng chung image

Backend, migrate và worker dùng chung image. Với Docker Compose/Bake có thể gặp tranh chấp tag khi build đồng thời cả ba. Build từng image một lần:

```sh
docker compose --env-file /path/to/deployment.env -f docker-compose.prod.yml build backend web
docker compose --env-file /path/to/deployment.env -f docker-compose.prod.yml up -d --no-build
```

Migration b419ad53ef82 thêm bản nháp riêng của reviewer; f91bc402de33 thêm enum COPILOT_SELECT. Downgrade không loại enum khỏi PostgreSQL; không chạy image cũ khi còn tác vụ Copilot đang xử lý. Migration vẫn cần backup và maintenance phù hợp trước triển khai pilot.
