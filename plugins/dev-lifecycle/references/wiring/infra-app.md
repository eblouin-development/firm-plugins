<!--
wiring: infra-app
covers: backend/web/admin app templates <-> infra/aws-fargate (secret_store env-first -> Secrets Manager valueFrom, /readyz healthchecks, the deploy runbook)
last-verified: 2026-07-23
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
sources:
  - https://12factor.net/config
  - https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html
  - references/infra/aws.md
  - references/security/secrets-management.md
-->

# Infra, app-side

**How a backend and its frontends become the running things `infra/aws-fargate` actually provisions** — 12-factor env/config, migrations run as a deploy step rather than baked into a container's startup command, `/readyz` as the thing an orchestrator actually polls, and the deploy runbook that ties OIDC → ECR → Terraform → migrate → ECS together. This is a wiring reference: it stitches together pieces that each have their own canon doc, and is **subordinate to the project's existing conventions** — when they conflict, the project wins.

The pieces:
- **App containers** — `templates/backend/fastapi/Dockerfile` / `templates/backend/django/Dockerfile`, and (when the frontend is the Next.js variant) `templates/frontend/nextjs/Dockerfile` and `templates/frontend/nextjs-admin/Dockerfile`.
- **Infra** — `templates/infra/aws-fargate/` (Terraform, seven reusable modules under `modules/`, one environment root per `envs/<env>/`).
- **The deploy entrypoint** — `just deploy <env>` (`templates/monorepo/justfile`) → `templates/infra/aws-fargate/scripts/deploy.sh`.

## Contents
- 12-factor env: `secret_store` meets `valueFrom`
- Healthchecks: `/readyz` as the thing that's actually polled
- Migrations on deploy, not in the image
- `apps/web` AND `apps/admin` are container services
- The deploy runbook
- Wiring checklist
- Related canon

## 12-factor env: `secret_store` meets `valueFrom`
The backend's `secret_store.py` (`templates/components/security/secrets-loading/secret_store.py`, vendored into `templates/backend/fastapi/app/core/security/secret_store/secret_store.py` and `templates/backend/django/core/contract/secret_store.py`) resolves every secret **process-env first**, with an optional AWS Secrets Manager fallback (`boto3`, lazily imported) only when `SECRETS_BACKEND=aws-secrets-manager` is explicitly set. On Fargate, that fallback layer is normally never exercised: `templates/infra/aws-fargate/modules/ecs-fargate-service/main.tf`'s task definition maps each configured secret straight into the container's **process environment** via ECS's own `secrets`/`valueFrom` mechanism —

```hcl
# main.tf — one entry per name in var.app_secret_arns
secrets = [for name, arn in var.app_secret_arns : { name = name, valueFrom = arn }]
```

— so `DATABASE_URL`, `JWT_SIGNING_KEY`, `SMTP_USERNAME`, `SMTP_PASSWORD` (`envs/dev/main.tf`'s `local.app_secret_arns`, composed from the `secrets` and `rds` modules' outputs) arrive at the container as ordinary env vars, resolved by ECS itself from Secrets Manager **before** the app process starts. Nothing sensitive ever sits in the task's plain `environment` block or is baked into the image — only non-secret config (`var.app_environment`) goes there. The practical result: `secret_store.py`'s env-first layer is *the* layer that actually fires in production on this infra block; its Secrets Manager fallback exists for a deployment target that doesn't inject secrets this way (a bare EC2 box, a non-ECS container host), not for Fargate itself. This is 12-factor config in the literal sense (`https://12factor.net/config` — config, including secrets, lives in the environment, never in code or a committed file) end to end: `.env.example` locally (`references/security/secrets-management.md`), `valueFrom`-injected env in Fargate.

## Healthchecks: `/readyz` as the thing that's actually polled
The backend exposes two probes, deliberately distinct (`templates/backend/fastapi/app/api/routers/health.py`, mirrored in the Django block):

- **`/health`** — liveness: touches nothing but the process itself, answers even with the database down.
- **`/readyz`** — readiness: runs a real `SELECT 1` through the DB session; a broken DB connection returns 503 with a plain `ReadinessStatus` body (deliberately **not** the `ErrorEnvelope` shape — `ErrorCode` has no `service_unavailable` member, and this is a status orchestrators poll by code, not by parsing a body).

`templates/infra/aws-fargate/modules/ecs-fargate-service/variables.tf`'s `health_check_path` variable **defaults to `/readyz`** — the ALB target group's health check polls readiness, not liveness, so a task with a live process but an unreachable database is correctly pulled out of rotation rather than kept serving traffic it can't actually fulfill. The container image's own `HEALTHCHECK` (both Dockerfiles) polls the same `/readyz` path directly (stdlib `urllib.request`, no `curl`/`wget` in the slim base image) for any orchestrator that honors a container-level healthcheck instead of (or in addition to) the ALB's own target-group check.

## Migrations on deploy, not in the image
Neither Dockerfile's production `CMD` runs a migration — `templates/backend/fastapi/Dockerfile`'s prod stage runs bare `uvicorn app.main:app`, no `--reload`, with an explicit comment that migrations are "a separate deploy step... not baked into this CMD." `templates/infra/aws-fargate/scripts/deploy.sh`'s step 4 is the acknowledged placeholder for that step: it echoes the intended command (`alembic upgrade head` for FastAPI / `manage.py migrate` for Django) run as a one-off ECS task against the **newly-pushed image**, before the service finishes rolling — but does not itself invoke it. A project wiring this block for real needs to replace that echo with an actual `aws ecs run-task` (or equivalent) invocation before relying on `just deploy` to migrate anything.

## `apps/web` AND `apps/admin` are container services
`infra/aws-fargate` as shipped provisions exactly **one** `ecs-fargate-service` module instance (the backend API) and **one** `static-site` module instance (a CloudFront-fronted private S3 bucket) — see `envs/dev/main.tf`. Which of those two shapes a given frontend needs depends on which frontend template it is:

- **`templates/frontend/vite-spa/`** builds a genuinely static bundle (`apps/web/dist/`) — the shipped `static-site` module and `deploy.sh`'s `aws s3 sync`/CloudFront-invalidate step are built for exactly this app.
- **`templates/frontend/nextjs/`** (`apps/web`) and **`templates/frontend/nextjs-admin/`** (`apps/admin`) are **not** static — both need a Node runtime in production (`next start` serving `.next/standalone`, because `next.config.ts`'s dev rewrites/headers are server features with no static-hosting equivalent). Both blocks' own READMEs state this plainly: "that makes `apps/web` a container service for infra purposes, not an S3/CloudFront static upload." `apps/admin` is explicitly a **second, separate deployable** — its own subdomain, its own container, never bundled into `apps/web`'s image or JS bundle — following the same shape as the backend API, not the static-site module.

Provisioning a project that uses the Next.js web + admin combination therefore means instantiating the `ecs-fargate-service` module (`templates/infra/aws-fargate/modules/ecs-fargate-service/`) **again per app** — once for the backend, once for `apps/web`, once for `apps/admin` — each with its own `container_port` (backend 8000, `apps/web` 3000, `apps/admin` 3001 per their Dockerfiles) and its own target group. **This is not wired in `envs/dev/main.tf` today** — the shipped root module composes a single `ecs` instance and a single `static_site` instance, matched to the vite-spa + one-backend composition; a project using the Next.js variants needs to add the second/third `ecs-fargate-service` module block itself (and correspondingly extend `deploy.sh`'s build/push/rollout steps, which as shipped only build+push one app image and only sync one static bucket).

## The deploy runbook
`just deploy <env>` (`templates/monorepo/justfile`) shells out to `infra/aws-fargate/scripts/deploy.sh <env>`, which runs, in order:

1. **Read the stack's Terraform outputs** (`ecr_repository_url`, `ecs_cluster_name`, `ecs_service_name`, `cloudfront_distribution_id`, `static_bucket_name`) — the stack must already have been `apply`'d once.
2. **Build + push the app image** to ECR, tagged with the git SHA (`IMAGE_TAG`, overridable) — the ECR repo is scan-on-push and immutable-tag.
3. **`terraform apply -var="app_image_tag=<sha>"`** — the one Terraform call in the runbook, pointing the ECS task definition at the freshly-pushed image.
4. **Sync the static site** (if `apps/web/dist` exists) to the private S3 bucket, then invalidate CloudFront.
5. **Migrations** — currently an echoed placeholder (see "Migrations on deploy" above), not an executed step.
6. **Roll the service** — `aws ecs update-service --force-new-deployment`.

Credentials for all of this come from **GitHub OIDC** exclusively (`aws-actions/configure-aws-credentials` with `role-to-assume: <deploy_role_arn>`, the least-privilege role `templates/infra/aws-fargate/modules/oidc-deploy-role/` provisions) — never long-lived AWS keys. `terraform validate`/`plan` run credential-free in CI (`skip_credentials_validation`/`skip_requesting_account_id`/`skip_metadata_api_check` on the provider, `account_id` as a plain variable rather than an `aws_caller_identity` lookup); only `apply` (inside `deploy.sh`, or a manual first-time apply) needs the real OIDC-assumed role.

## Wiring checklist
1. **Backend** — the hardened prod Dockerfile target (non-root, no `--reload`, `HEALTHCHECK` on `/readyz`) built and pushed to the provisioned ECR repo.
2. **Secrets** — `DATABASE_URL`/`JWT_SIGNING_KEY`/`SMTP_*` provisioned by the `secrets`/`rds` Terraform modules and mapped into `local.app_secret_arns`; confirm the app reads each by the exact env var name the task's `secrets` block injects.
3. **Health check** — leave `health_check_path` at its `/readyz` default (or point it at whatever readiness path the project's backend actually exposes, if it diverged).
4. **Frontend shape** — vite-spa → the `static-site` module as shipped; Next.js `apps/web`/`apps/admin` → add an `ecs-fargate-service` module instance per app (not shipped by default) and extend `deploy.sh` to build/push/roll each.
5. **Migrations** — replace `deploy.sh`'s step-4 echo with a real one-off ECS task run before declaring the runbook production-ready.
6. **CI identity** — confirm the deploy workflow assumes `deploy_role_arn` via OIDC, never a stored `AWS_SECRET_ACCESS_KEY`.

## Related canon
- `templates/infra/aws-fargate/README.md` — the block's full composition contract, structure, and security posture (secure-by-default bars, checkov skips).
- `templates/infra/aws-fargate/docs/fragment.md` — the Deployment/Secrets/Maintenance fragment aggregated into a scaffolded project's root README.
- `templates/components/security/secrets-loading/README.md` — `secret_store.py`'s env-first/Secrets-Manager-fallback contract in full.
- `templates/frontend/nextjs/README.md` / `templates/frontend/nextjs-admin/README.md` — each app's own "Deployment" section (the container-service statement this doc cites).
- `references/infra/aws.md`, `references/infra/terraform.md` — the general AWS/Terraform conventions this block implements.
- `references/security/secrets-management.md` — the local/CI/prod secrets posture this doc's env-first section sits alongside.
