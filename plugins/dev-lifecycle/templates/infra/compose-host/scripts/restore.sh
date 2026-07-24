#!/bin/sh
# Restore a scripts/backup.sh dump into a SCRATCH database — never directly
# over the live `db` service. Run this on a schedule (not just when disaster
# strikes) to prove the backup is actually restorable, per home-infra.md.
#
# Usage: scripts/restore.sh <path-to-dump.sql.gz> [scratch-db-name]
set -eu

DUMP="${1:?usage: restore.sh <dump.sql.gz> [scratch-db-name]}"
SCRATCH_DB="${2:-restore_check}"

echo "==> creating scratch database ${SCRATCH_DB}"
docker compose exec -T db psql -U "${POSTGRES_USER}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${SCRATCH_DB};" \
  -c "CREATE DATABASE ${SCRATCH_DB};"

echo "==> restoring ${DUMP} into ${SCRATCH_DB}"
gunzip -c "${DUMP}" | docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${SCRATCH_DB}"

echo "==> restore check passed: ${DUMP} is restorable."
echo "    (scratch DB '${SCRATCH_DB}' left in place for inspection — drop it manually when done)"
