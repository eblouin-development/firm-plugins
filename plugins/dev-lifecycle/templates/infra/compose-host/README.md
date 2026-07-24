<!--
block: infra/compose-host
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-24
provenance: manual
needs:
  - built + pushed app image(s) (backend/fastapi or backend/django prod target, plus any frontend/worker block images) in a registry this host can pull from; each app reads DATABASE_URL/JWT_SIGNING_KEY/SMTP_* from process env (secret_store.py, process-env-first)
  - a single Docker host you own (home server or VPS) with Docker Engine + the compose plugin, reachable for deploy either via a self-hosted GitHub Actions runner on/near the host OR SSH (key-based, ideally Tailscale SSH)
  - a domain's A/AAAA record pointed at the host (public-TLS default) OR a tailnet + Tailscale auth key (Tailscale variant) — not both required
  - Docker Compose (the `compose` plugin, v2 spec), Caddy ~2.11.x, Postgres 18.x (versions-pinned-to)
exposes:
  - a running stack on the host: Caddy terminating TLS (public ACME, or Tailscale Serve/Funnel in the documented variant), the app service(s), Postgres with a named volume + nightly backup job, optional Uptime Kuma monitoring
  - contract outputs (env-driven, not Terraform outputs): the public URL (https://$DOMAIN or https://<host>.<tailnet>.ts.net), DATABASE_URL (composed from POSTGRES_* in .env), the same app-secret env-var names infra/aws-fargate injects via valueFrom — so a project can point the exact same app image at either block unmodified
  - its co-located doc fragment: docs/fragment.md (Deployment + Secrets + Maintenance)
-->

# infra/compose-host

The secure-by-default single-Docker-host infrastructure block: "a home
server or VPS you own" — Tailscale optional, not assumed. A production
`docker-compose.yml` overlay (app services + Postgres + a TLS reverse proxy),
two deploy-path variants from GitHub Actions (self-hosted runner and SSH),
and the ops posture (backups, monitoring, auto-recovery) `references/infra/
home-infra.md` documents as the firm's default beta tier. Lives at
`templates/infra/compose-host/` in this repo; scaffolding materializes it
into a project's `infra/compose-host/`. Everything here is a default a
scaffolded project can and will diverge from — when a project has already
diverged, the project wins.

## Contents
- Composition contract
- Structure
- Networking: public-with-TLS (default) vs Tailscale (variant)
- Deploy path: self-hosted runner vs SSH
- Migrations on deploy
- Ops posture: backups, monitoring, auto-recovery
- Security posture (secure-by-default)
- Graduating to infra/aws-fargate
- Documentation

## Composition contract

### NEEDS
- **Built + pushed app image(s)** in a registry the host can pull from
  (GHCR, Docker Hub, a self-hosted registry — the block is registry-
  agnostic, unlike `infra/aws-fargate`'s ECR-specific contract). The
  hardened PROD target of `backend/fastapi/Dockerfile` or
  `backend/django/Dockerfile` (non-root, no `--reload`, `HEALTHCHECK`); each
  running container reads `DATABASE_URL`, `JWT_SIGNING_KEY`, and `SMTP_*`
  from process env — this block injects them via Compose's `env_file: .env`
  (see `.env.example`), the direct-process-env path `secret_store.py`'s
  own "process-env-first" contract already expects, so the app code needs
  zero changes versus `infra/aws-fargate`'s `valueFrom` injection.
- **A single Docker host you own**, reachable for deploy either via a
  self-hosted GitHub Actions runner installed on/near the host, or via SSH
  (key-based; ideally **Tailscale SSH** — `references/infra/tailscale.md`
  — never a shared password). No cloud account, no IAM, no OIDC.
- **A domain pointed at the host** (A/AAAA record) for the default public-
  TLS mode, **or** a tailnet + a Tailscale auth key for the documented
  Tailscale variant — pick one, not both.
- **Docker Compose (the `compose` plugin, v2 spec)** on the host; **Caddy
  ~2.11.x**, **Postgres 18.x** — per `references/compatibility-matrix.md`.

### EXPOSES
- **A running stack**: Caddy fronting the app with automatic TLS (public
  ACME by default; Tailscale Serve/Funnel in the variant), the app
  service(s) from the composed backend/frontend blocks, a durable Postgres
  with a named volume and a nightly `pg_dump` backup job, and (on by
  default) Uptime Kuma for basic uptime/alerting.
- **Contract outputs** (env-driven — this block has no Terraform state to
  read outputs from): the public URL (`https://$DOMAIN`, or the tailnet
  `https://<hostname>.<tailnet>.ts.net` URL in the Tailscale variant), and
  `DATABASE_URL`/`JWT_SIGNING_KEY`/`SMTP_*` composed the same way
  `infra/aws-fargate` names them — see "Graduating to infra/aws-fargate"
  for why that naming match is deliberate.
- **Its co-located doc fragment**: `docs/fragment.md` (Deployment runbook +
  Secrets rows + Maintenance), aggregated into the root README by
  `just docs-generate`.

## Structure

```
templates/infra/compose-host/
  docker-compose.prod.yml       # the production overlay: caddy, api, db, backup, uptime-kuma
  docker-compose.tailscale.yml  # optional overlay: swaps public TLS for Tailscale Serve/Funnel
  Caddyfile                     # public-TLS reverse proxy config (default)
  Caddyfile.tailscale           # reverse proxy config for the Tailscale overlay
  .env.example                  # every var the compose files read — no real values
  scripts/
    deploy-self-hosted-runner.sh  # variant A: runner already on/near the host
    deploy-ssh.sh                 # variant B: SSH rollout from a GitHub-hosted runner
    migrate.sh                    # migrations-on-deploy, run against the new image before rollout
    backup.sh                     # the backup service's cron target (pg_dump [+ off-box push])
    restore.sh                    # scheduled restore-test into a scratch DB
    host-setup-checklist.sh       # one-time host resilience checklist (home-infra.md)
  docs/fragment.md               # co-located doc fragment (Deployment/Secrets/Maintenance)
```

## Networking: public-with-TLS (default) vs Tailscale (variant)

**Default:** `docker-compose.prod.yml` + `Caddyfile` — Caddy listens on
public `80`/`443`, gets a Let's Encrypt cert automatically for `$DOMAIN`,
redirects HTTP→HTTPS, and reverse-proxies to the app services on an
**internal-only** Docker network (nothing else is published). This is the
right default for a bare VPS with no tailnet — "table stakes" per issue
#101 — and works identically on a home box with the domain's DNS pointed
at your public IP + port-forward.

**Variant: Tailscale Serve/Funnel.** Layer `docker-compose.tailscale.yml`
on top (`docker compose -f docker-compose.prod.yml -f
docker-compose.tailscale.yml up -d`) to drop the public port publish
entirely and front Caddy with a `tailscale` sidecar instead — **Serve**
publishes tailnet-only HTTPS with a MagicDNS name and a valid cert (the
default for beta/dev access for yourself), **Funnel** additionally exposes
an authenticated public URL only when something off-tailnet needs it (a
client preview, a cloud pipeline agent's smoke test) and gets turned back
off when done. See `references/infra/tailscale.md` and this block's
`Caddyfile.tailscale`. **Tailscale is opt-in, never assumed** — a project
with no tailnet uses the default public-TLS mode unmodified.

## Deploy path: self-hosted runner vs SSH

Both variants build + push the app image in CI first (`references/devops/
cicd.md`'s gated pipeline — lint/type/test/scan, then build+tag by git SHA,
then push), and both run migrations against the new image before rollout
(see "Migrations on deploy" below). They differ only in how the rollout
command reaches the host:

- **`scripts/deploy-self-hosted-runner.sh`** — the workflow job runs
  directly on a GitHub Actions **self-hosted runner** installed on (or
  already reachable from, over the tailnet) the host itself. No SSH hop, no
  exposed port; the runner's own registration is the trusted channel back
  to GitHub. Preferred when the host is already on a tailnet with a runner
  registered — `references/devops/cicd.md`'s "Agent-testable beta" pattern.
- **`scripts/deploy-ssh.sh`** — a GitHub-hosted runner `rsync`s the compose
  project to the host and runs the rollout over **SSH** (key from a GitHub
  Actions secret, ideally Tailscale SSH — ACL-controlled, no exposed `:22`
  — falling back to a normal SSH key + public `:22` for a VPS with no
  tailnet). Preferred when no self-hosted runner is registered.

Both scripts: pull the new image, run `migrate.sh` against it, `docker
compose up -d` (which only recreates services whose config/image actually
changed — Compose's own rolling-recreate, not a hand-rolled blue/green),
then prune old images (never volumes). **Rollback** is re-running either
script with the previous `IMAGE_TAG` — the previous image is still on the
host/registry until pruned past the 7-day window.

Both scripts require **`API_IMAGE_REPO`** (the registry repo with no tag,
e.g. `ghcr.io/org/app-api`) and **`IMAGE_TAG`** (the git SHA CI just built
and pushed) as env vars — set as CI job env/secrets, not in the host's
`.env` (see `.env.example`). Both fail fast (`:?`) if unset rather than
deploying an empty/unintended image reference.

## Migrations on deploy

Per `references/devops/deploy-operate.md`: migrations are an explicit,
ordered deploy step, never baked into the image's `CMD`.
`scripts/migrate.sh` runs the **new** image once as a throwaway `docker run`
against the compose project's `internal` network (so `db` resolves by
service name), executes `alembic upgrade head` / `manage.py migrate`, and
exits — only then does the caller roll the real `api` service over to that
image. This is the same ordering `infra/aws-fargate`'s `deploy.sh` documents
(a one-off task against the new image, before the service finishes
rolling), made concrete here because a single Docker host has no separate
"run a one-off task" primitive of its own.

## Ops posture: backups, monitoring, auto-recovery

Per `references/infra/home-infra.md` — this block's ops posture is that
doc's guidance made runnable:

- **Backups.** The `backup` service (`docker-compose.prod.yml`) crons
  `scripts/backup.sh` (default `03:00` daily, `BACKUP_CRON` in `.env`):
  `pg_dump` to a named volume, optional off-box push via `rclone` when
  `BACKUP_REMOTE` is set, 14-day local retention. `scripts/restore.sh`
  restores a dump into a scratch database on demand — **run it on a
  schedule, not just when disaster strikes**; an untested backup is a hope,
  not a backup.
- **Monitoring/alerting.** Uptime Kuma ships on by default (no compose
  profile gate — a plain `docker compose up -d` starts it) watching the
  app's health endpoint and Postgres reachability, with alert channels
  configured in its own UI on first boot. This is intentionally basic — a
  project with an existing observability stack (Sentry, Grafana) wires
  that in instead and can drop
  this service.
- **Auto-recovery after reboot.** Every service in `docker-compose.prod.yml`
  sets `restart: unless-stopped`, so a host reboot (or a container crash)
  brings the whole stack back with no manual intervention, **provided**
  Docker's own daemon is enabled at boot (`systemctl enable docker`, the
  distro default) — this is the software half. The other four failure
  modes `home-infra.md` names (sleep, power-loss auto-boot, OS-hang
  watchdog, Wake-on-LAN backstop) are host/BIOS-level, not something a
  compose file can set; `scripts/host-setup-checklist.sh` checks and
  reports on each (never silently applies a BIOS setting — nothing in
  software can, per that doc).

## Security posture (secure-by-default)

- **No datastore port published.** Postgres (`db`) and the backup sidecar
  sit on the `internal` Docker network only — never `ports:`-published.
  Reach the DB for a manual session via `docker compose exec` over
  SSH/Tailscale SSH into the host, never a public `5432`.
- **TLS everywhere by default**, not an opt-in: Caddy auto-provisions and
  renews a Let's Encrypt cert (public mode) or rides the tailnet's own
  MagicDNS cert (Tailscale mode); HTTP→HTTPS redirect and HSTS are in the
  shipped `Caddyfile`. Security headers (`X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, a scoped `Permissions-Policy`) are
  set on every response by default, per `references/security/
  secure-baseline.md`.
- **Secrets never in the image or in git.** Every credential
  (`POSTGRES_PASSWORD`, `JWT_SIGNING_KEY`, `SMTP_*`) is read from `.env` via
  Compose's `env_file:` — `.env.example` ships with placeholders only,
  `.env` itself is gitignored and provisioned on the host out-of-band, and
  `scripts/deploy-ssh.sh` deliberately **excludes** `.env` from its `rsync`
  so a routine app deploy can never overwrite the host's real secrets.
- **Least-privilege network topology.** Only `caddy` (and, in the Tailscale
  overlay, the `tailscale` sidecar it shares a netns with) sits on the
  `edge` network with a published port; every other service is
  `internal`-only.
- **Non-root, health-checked containers.** The app image is the same
  hardened PROD target `infra/aws-fargate` requires (non-root `USER`, no
  `--reload`, a `HEALTHCHECK`); this block's own `api` service healthcheck
  polls `/readyz` (not `/health`) so a task with a live process but an
  unreachable database is correctly treated as not-ready — same posture
  `references/wiring/infra-app.md` documents for the Fargate block.
- **Auth key hygiene (Tailscale variant only).** `.env.example` documents
  the auth key as ephemeral, reusable, and `tag:server`-scoped, and calls
  out disabling key expiry on this node in the admin console once joined —
  `references/infra/tailscale.md`'s single most common self-inflicted
  outage otherwise.

This block clears the `template-author` four bars: composition-contract
(above), documented (`docs/fragment.md` + this README), version-pinned
(`versions-pinned-to` -> compatibility matrix), and secure-by-default (this
section).

## Graduating to infra/aws-fargate

The composition contract is deliberately shaped to match
`infra/aws-fargate`'s: both blocks read the exact same app-secret env-var
names (`DATABASE_URL`, `JWT_SIGNING_KEY`, `SMTP_USERNAME`, `SMTP_PASSWORD`)
via `secret_store.py`'s process-env-first path, both gate on the same
`/readyz` health check, and both run migrations as an explicit one-off step
against the new image before rollout. A project that outgrows a single
host doesn't re-wire its **application** at all when it graduates — it
swaps the infra block: point CI's deploy step at `infra/aws-fargate`'s
`deploy.sh` instead of this block's `deploy-*.sh`, provision the Terraform
stack, and move `POSTGRES_*`/`JWT_SIGNING_KEY`/`SMTP_*` from this block's
`.env` into `infra/aws-fargate`'s Secrets Manager. The app image, the
migration command, and the health-check path all carry over unchanged.

## Documentation

Ships `docs/fragment.md` co-located with the block; `just docs-generate`
aggregates its `## Deployment` / `## Secrets` / `## Maintenance` sections
into the project root README. See
`references/authoring/documentation-standard.md`.
