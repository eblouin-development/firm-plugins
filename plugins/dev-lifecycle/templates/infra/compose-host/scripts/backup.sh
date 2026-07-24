#!/bin/sh
# Postgres backup job run on BACKUP_CRON's schedule by the `backup` service
# in docker-compose.prod.yml (cron -> this script, inside the `postgres`
# image so `pg_dump` always matches the server version). Dumps to a local
# named volume, then — if BACKUP_REMOTE is set — pushes off-box, per
# home-infra.md "Backups": "back up off-box... and test the restore, an
# untested backup is a hope, not a backup."
set -eu

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/backups/${POSTGRES_DB}-${STAMP}.sql.gz"

echo "==> pg_dump ${POSTGRES_DB} -> ${OUT}"
pg_dump -h db -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${OUT}"

# Off-box push (optional, recommended). Requires rclone configured with a
# remote named to match BACKUP_REMOTE's scheme, or swap for `scp`/`rsync` to
# a second host you control. Not wired by default — set BACKUP_REMOTE and
# provide the rclone config/credentials via a mounted, gitignored file, never
# baked into the image.
if [ -n "${BACKUP_REMOTE:-}" ] && command -v rclone >/dev/null 2>&1; then
  echo "==> pushing to ${BACKUP_REMOTE}"
  rclone copy "${OUT}" "${BACKUP_REMOTE}"
fi

# Retention: keep the last 14 local daily dumps; off-box retention is the
# remote's own policy (e.g. bucket lifecycle rules).
find /backups -name "${POSTGRES_DB}-*.sql.gz" -mtime +14 -delete

echo "==> backup complete: ${OUT}"
echo "    Restore test reminder: run 'scripts/restore.sh <dump-file>' against"
echo "    a scratch DB on a schedule — an untested backup is not a backup."
