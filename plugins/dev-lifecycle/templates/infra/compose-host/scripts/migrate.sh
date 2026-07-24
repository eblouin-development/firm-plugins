#!/usr/bin/env bash
# Migrations on deploy, per references/devops/deploy-operate.md: an
# explicit, ordered step run against the NEW image, before that image
# starts serving traffic — never baked into the prod image's CMD (same
# posture as infra/aws-fargate's deploy.sh step 4, made concrete here
# because a single Docker host has no separate "run a one-off task"
# primitive — this runs the new image once, migrates, exits, and only THEN
# does the caller roll `api` over to it).
#
# Usage: scripts/migrate.sh <api-image-ref>
set -euo pipefail

IMAGE="${1:?usage: migrate.sh <api-image-ref>}"
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Running migrations via a one-off container from ${IMAGE}"
# --env-file reads the same DATABASE_URL the real `api` service will use;
# --network attaches to the compose project's `internal` network so `db`
# resolves by service name. Adjust the migrate command for the project's
# backend track (alembic for FastAPI, manage.py for Django).
docker run --rm \
  --env-file "${COMPOSE_DIR}/.env" \
  --network "$(basename "${COMPOSE_DIR}")_internal" \
  "${IMAGE}" \
  sh -c 'alembic upgrade head || python manage.py migrate'

echo "==> Migrations applied."
