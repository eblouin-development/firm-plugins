#!/usr/bin/env bash
# Deploy variant B: SSH-based rollout from a GitHub-hosted runner (no
# self-hosted runner registered on the host). Preferred for a VPS with no
# tailnet, or when you don't want a persistent runner process on the box.
#
# The GitHub Actions job runs THIS script with SSH_HOST/SSH_USER pointed at
# the target and an SSH private key injected from a GitHub Actions secret
# (never committed) — ideally over Tailscale SSH (tailscale.md "SSH": ACL-
# controlled, no exposed public SSH port) rather than a bare public :22.
# Falls back to a normal SSH key + public :22 for a VPS with no tailnet, per
# the issue's "Tailscale optional, not assumed."
#
# Requires: ssh, rsync (or the repo already checked out at COMPOSE_DIR on
# the remote host, pulled by a lightweight `git pull` instead of rsync).
set -euo pipefail

SSH_HOST="${SSH_HOST:?set SSH_HOST (e.g. a MagicDNS name, or a public VPS hostname/IP)}"
SSH_USER="${SSH_USER:?set SSH_USER}"
REMOTE_DIR="${REMOTE_DIR:?set REMOTE_DIR — the compose projects path on the host}"
IMAGE_TAG="${IMAGE_TAG:?set IMAGE_TAG to the git SHA that was just built + pushed}"
API_IMAGE_REPO="${API_IMAGE_REPO:?set API_IMAGE_REPO to the registry repo, e.g. ghcr.io/org/app-api}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

echo "==> Syncing compose files to ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}"
rsync -az --delete \
  --exclude ".env" \
  "$(dirname "${BASH_SOURCE[0]}")/../" "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"
# .env is excluded deliberately — it's provisioned once on the host by hand
# (or by a separate, audited config-management step), never overwritten by
# a routine app deploy (secrets-management.md: real .env never touches CI).

echo "==> Remote: pull + migrate + roll out (IMAGE_TAG=${IMAGE_TAG})"
# shellcheck disable=SC2087
ssh "${SSH_OPTS[@]}" "${SSH_USER}@${SSH_HOST}" bash -s <<REMOTE
  set -euo pipefail
  cd "${REMOTE_DIR}"
  export API_IMAGE="${API_IMAGE_REPO}:${IMAGE_TAG}"
  docker compose -f docker-compose.prod.yml pull api
  ./scripts/migrate.sh "\${API_IMAGE}"
  docker compose -f docker-compose.prod.yml up -d --remove-orphans
  docker image prune -f --filter "until=168h" >/dev/null
REMOTE

echo "==> Deploy of image tag ${IMAGE_TAG} to ${SSH_HOST} complete. Rollback: re-run with the previous IMAGE_TAG."
