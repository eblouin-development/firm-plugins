#!/usr/bin/env bash
# Deploy variant A: a self-hosted GitHub Actions runner installed ON THIS
# HOST (or reachable to it over the tailnet — cicd.md/home-infra.md's
# "already on the tailnet" pattern). The workflow job runs THIS script
# directly on the target machine — no SSH hop, no exposed port, because the
# runner process itself already has a trusted, authenticated connection back
# to GitHub. Preferred when the host is already on the tailnet with a
# runner registered (references/devops/cicd.md, references/infra/tailscale.md
# "Working from the road").
#
# This is the target of `just deploy <env>` when the project's runner
# variant is chosen — see docs/fragment.md "Deployment".
#
# Requires: docker compose v2, this repo checked out at COMPOSE_DIR (the
# runner's own workspace, or a fixed deploy path), a populated .env.
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
IMAGE_TAG="${IMAGE_TAG:?set IMAGE_TAG to the git SHA that was just built + pushed}"
COMPOSE_FILES=(-f "${COMPOSE_DIR}/docker-compose.prod.yml")
[ "${USE_TAILSCALE_OVERLAY:-0}" = "1" ] && COMPOSE_FILES+=(-f "${COMPOSE_DIR}/docker-compose.tailscale.yml")

cd "${COMPOSE_DIR}"
echo "==> Pulling image tag ${IMAGE_TAG}"
API_IMAGE="${API_IMAGE_REPO}:${IMAGE_TAG}" docker compose "${COMPOSE_FILES[@]}" pull api

echo "==> Running migrations against the new image (one-off, before rollout)"
"${COMPOSE_DIR}/scripts/migrate.sh" "${API_IMAGE_REPO}:${IMAGE_TAG}"

echo "==> Rolling out (docker compose up -d recreates only changed services)"
API_IMAGE="${API_IMAGE_REPO}:${IMAGE_TAG}" docker compose "${COMPOSE_FILES[@]}" up -d --remove-orphans

echo "==> Pruning old images (keep restart resilience: never prune volumes)"
docker image prune -f --filter "until=168h" >/dev/null

echo "==> Deploy of image tag ${IMAGE_TAG} complete. Rollback: re-run with the previous IMAGE_TAG."
