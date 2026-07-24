<!--
library: perf-surfaces
versions-covered: "n/a (methodology, not a versioned library)"
last-verified: 2026-07-24
provenance: manual
sources: []
-->

# Performance surface taxonomy (by application type)

Loaded by the `performance-audit` skill after it fingerprints the application. For each surface: where to look and what evidence of "handled" looks like. Most projects are several types at once (an API **and** a frontend **and** a build pipeline) — union the applicable sections. Per-surface checks (what specifically to measure/flag) live in `perf-checklist.md`; this doc is the map of *where to look*.

## Contents
- Backend / API service
- Database layer
- Frontend (SPA or server-rendered)
- Background workers / scheduled jobs
- Build & deploy pipeline
- The evidence standard for "handled"

## Backend / API service

- **Request lifecycle** — each hot endpoint's handler: what it queries, calls, and serializes before responding. Handled: p50/p95 latency known (APM, logs, or measured locally) and within a stated budget.
- **Payload sizes** — response bodies for list/collection endpoints: pagination present, over-fetching absent (are unused fields returned?), compression enabled (gzip/brotli at the proxy or app layer).
- **Caching** — response/query caching where reads dominate writes: cache headers, CDN, in-memory/Redis cache, and correct invalidation (a cache that's never invalidated is a correctness bug, not a perf win).
- **Blocking work on the request path** — synchronous calls to external services, unbounded loops, CPU-heavy work (image processing, large serialization) done inline instead of offloaded to a worker.
- **Connection pooling** — DB/HTTP client pools sized and reused, not opened per request.

## Database layer

- **Query plans** — `EXPLAIN`/`EXPLAIN ANALYZE` on the queries backing hot endpoints: sequential scans on large tables, missing or unused indexes, sort/hash operations spilling to disk.
- **N+1 queries** — a loop issuing one query per iteration instead of a single batched/joined query. Look at ORM call sites in list-rendering and serialization code (`.all()` inside a loop, lazy-loaded relations accessed per-row).
- **Index coverage** — foreign keys, columns in `WHERE`/`JOIN`/`ORDER BY` on large tables. Handled: index exists and the query plan actually uses it (an unused index is dead weight, not a fix).
- **Migrations & table growth** — tables large enough that a naive migration (adding a column with a default, a new index) would lock or block; whether migrations are written to run online.
- **Transaction scope** — transactions held open across slow external calls, long-running transactions that hold locks.

## Frontend (SPA or server-rendered)

- **Bundle size & composition** — total JS shipped to first paint, largest dependencies (bundle analyzer output or manifest inspection), code-splitting / lazy-loading of routes and heavy components, tree-shaking working (no whole-library imports where a named import would do).
- **Core Web Vitals** — LCP (largest contentful paint), CLS (cumulative layout shift), INP (interaction to next paint). These overlap with search ranking factors — see the `seo` skill for the ranking/crawlability angle; this audit covers them as a user-experience and rendering-performance surface.
- **Render waterfalls** — sequential (rather than parallel) data fetching, render-blocking scripts/styles in `<head>`, images without explicit dimensions (CLS), fonts without `font-display` (invisible/flash-of-text).
- **Asset delivery** — image formats/sizing (served at display resolution, modern formats), lazy-loading below the fold, CDN/cache headers on static assets.
- **Client-side data fetching** — over-fetching, missing request deduplication/caching (React Query/SWR-style or equivalent), waterfalled fetches that could run in parallel.

## Background workers / scheduled jobs

- **Queue depth & throughput** — whether job processing keeps pace with enqueue rate; evidence from queue metrics/dashboards where available, otherwise flagged as unmeasured.
- **Job runtime** — individual job duration against its queue's expected cadence; jobs that risk timing out or backing up the queue.
- **Concurrency & resource contention** — worker pool sizing relative to DB connection limits and downstream rate limits.

## Build & deploy pipeline

- **Build time** — CI build/test duration as a proxy for developer iteration speed and deploy latency; not a user-facing metric but relevant to the audit's "capacity" framing.
- **Asset pipeline** — minification, compression, and cache-busting actually wired into the production build (not just available as an option).

## The evidence standard for "handled"

A surface is ✅ Handled only with concrete evidence: a measured number (latency, bundle size, query plan output) or a located, confirmed-wired control (`file:line` for the caching middleware, the index migration, the code-split boundary). "The framework probably handles this" is not evidence. Credit partial coverage honestly ("caching on `/products` but not `/search`") — the gap is the finding, the coverage is still credited.

---
<!--
Authoring rules for this reference:
- This is a *where-to-look* map, not a metrics checklist — per-surface checks and thresholds live in perf-checklist.md.
- Keep sections keyed to application types so the performance-audit skill can load/apply only what the fingerprint says.
- Update `last-verified` whenever revised; the freshness audit reads the header above.
-->
