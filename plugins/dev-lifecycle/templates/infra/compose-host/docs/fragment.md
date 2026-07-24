<!-- fragment: block:infra/compose-host -->

## Deployment

Provisioned by the `infra/compose-host` Docker Compose block — a production
overlay (`infra/compose-host/docker-compose.prod.yml`) run directly on a
single Docker host you own (home server or VPS). No cloud account, no
Terraform state; `.env` on the host is the entire config surface.

First-time setup on the host:

```bash
cd infra/compose-host
cp .env.example .env            # fill in real values — never commit this file
./scripts/host-setup-checklist.sh   # verify reboot/auto-recovery posture
docker compose -f docker-compose.prod.yml up -d
```

App deploy (what `just deploy <env>` runs, once wired to the project's
chosen variant):

1. **CI gates + build + push** — the usual lint/type/test/scan pipeline,
   then the app image is built and pushed to a registry (GHCR, Docker Hub,
   or equivalent) tagged with the git SHA.
2. **Roll out**, via one of two variants:
   - `scripts/deploy-self-hosted-runner.sh` — runs directly on a
     self-hosted GitHub Actions runner installed on/near the host.
   - `scripts/deploy-ssh.sh` — a GitHub-hosted runner `rsync`s the compose
     project and rolls out over SSH (ideally Tailscale SSH).
3. **Migrations on deploy**: `scripts/migrate.sh` runs `alembic upgrade
   head` / `manage.py migrate` as a one-off container against the NEW image
   BEFORE the `api` service is recreated — the prod image CMD does not
   migrate.
4. **`docker compose up -d`** recreates only the services whose image/config
   changed. **Rollback**: re-run the same deploy script with the previous
   `IMAGE_TAG`.

Networking defaults to plain public-with-TLS (Caddy, automatic Let's
Encrypt). For a Tailscale Serve/Funnel deploy instead, layer
`docker-compose.tailscale.yml` on top — see the block's README "Networking".

## Secrets

| `DATABASE_URL` | infra/compose-host (backend) | Composed in `.env` from `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`; injected into the `api` service via `env_file`. Generate a real password (`openssl rand -hex 24`), never the `.env.example` placeholder. |
| `JWT_SIGNING_KEY` | infra/compose-host (backend auth) | Generate once (`openssl rand -hex 32`), store only in the host's `.env`. Rotating it invalidates live tokens — plan a window. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | infra/compose-host (backend email) | Set the real relay values in `.env` out-of-band; `SMTP_HOST`/`EMAIL_FROM` are non-secret config in the same file. |
| `TS_AUTHKEY` | infra/compose-host (Tailscale variant only) | Tailscale admin console -> Settings -> Keys: an ephemeral, reusable, `tag:server`-scoped key. Disable key expiry on this node once joined. |
| `BACKUP_REMOTE` / rclone config | infra/compose-host (backups) | The off-box destination for `scripts/backup.sh`'s optional push (a second host, or an S3-compatible bucket) — provide rclone credentials via a mounted, gitignored config file, never baked into the image. |

## Maintenance

- **Restore-test on a schedule**, not just when disaster strikes:
  `scripts/restore.sh <dump.sql.gz>` restores into a scratch database —
  see the block's README "Ops posture".
- **Host resilience**: `scripts/host-setup-checklist.sh` re-run after any OS
  reinstall or new host provision — checks sleep/suspend masking, the
  systemd watchdog, `kernel.panic`, `tailscaled` enablement, and
  unattended-upgrades; BIOS power-loss auto-boot and Wake-on-LAN are called
  out as manual, software-can't-set steps.
- **Monitoring**: Uptime Kuma (`docker compose --profile monitoring up -d`)
  watches the app's health endpoint and Postgres reachability — configure
  alert channels in its own UI on first boot.
- **Updates & patching**: `unattended-upgrades` (or the distro equivalent)
  for the host OS; re-pull base images (`postgres:18-bookworm`,
  `caddy:2.11-alpine`) on a cadence and redeploy to pick up patches.
- **Cost watch**: none beyond the host itself — this block is the
  zero-hosting-cost tier by design. When traffic/availability requirements
  outgrow one host, see the README's "Graduating to infra/aws-fargate".
