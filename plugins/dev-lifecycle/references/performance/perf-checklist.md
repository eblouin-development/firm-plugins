<!--
library: perf-checklist
versions-covered: "Core Web Vitals (2024 INP revision), n/a for backend checks"
last-verified: 2026-07-24
provenance: manual
sources:
  - https://web.dev/articles/vitals
-->

# Performance review checklist

Audit every enumerated surface against these checks. Only flag issues with a measured number or located code path behind them — no speculative findings padded for volume.

## Backend

- **N+1 queries** — a query issued once per row instead of once per request. Evidence: the loop/call site (`file:line`) plus the query count observed (log the queries for one representative request, or read the ORM's lazy-loading config).
- **Missing indexes** — `EXPLAIN`/`EXPLAIN ANALYZE` on the queries backing hot endpoints; flag sequential scans on tables past a few thousand rows, or sorts/joins not using an available index.
- **Unbounded queries** — list endpoints without pagination or a hard limit; a query that returns unboundedly with table growth is a latent incident.
- **Payload bloat** — response serializers returning full model objects (including relations, internal fields) where the client uses a fraction of it. Evidence: measured response size for a representative request vs. what the frontend actually consumes.
- **Synchronous slow work on the request path** — external API calls, file/image processing, or large serialization done inline instead of queued to a background worker.
- **Cache absence on read-heavy, rarely-changing data** — no cache layer where read:write ratio and data volatility would justify one. Note this only where write-invalidation is achievable — don't recommend a cache that would introduce staleness bugs without saying so.

## Frontend

- **Bundle size** — total and per-route JS/CSS shipped, from a bundler analyzer (`webpack-bundle-analyzer`, `vite-bundle-visualizer`, `source-map-explorer`) or the build output's own size report. Flag the largest contributors, not just the total.
- **Code splitting** — routes/heavy components (charting, editors, PDF viewers) loaded eagerly in the main bundle when they could be dynamically imported.
- **Core Web Vitals** (lab data — see the performance-audit skill's workflow step 4 for how to gather it):
  - **LCP** (largest contentful paint) — target under 2.5s. Common causes: render-blocking resources, slow server response, unoptimized hero image/font.
  - **CLS** (cumulative layout shift) — target under 0.1. Common causes: images/embeds without reserved dimensions, web fonts causing reflow, content injected above existing content.
  - **INP** (interaction to next paint) — target under 200ms. Common causes: long tasks blocking the main thread, expensive event handlers, large re-renders on interaction.
  - These are also SEO ranking signals — cross-link the `seo` skill for the search/crawlability treatment; this audit's concern is the user-experience and rendering-performance angle.
- **Render waterfalls** — sequential network requests visible in a waterfall (devtools Network tab or Lighthouse trace) that could run in parallel; render-blocking `<script>`/`<link>` in `<head>` without `defer`/`async`/preload.
- **Image & font delivery** — unsized/unoptimized images, missing `loading="lazy"` below the fold, fonts without `font-display: swap` (or equivalent), no modern format (WebP/AVIF) where supported.

## Cross-cutting

- **No measurement at all** — if a surface has never been profiled/measured (no APM, no Lighthouse run, no query logging), say so explicitly rather than guessing at severity. An unmeasured surface is a scope gap, not a clean bill of health.
- **Regression risk** — no CI budget/gate on bundle size or key query performance, so a regression ships silently. This is a process gap worth flagging even when current numbers are fine.
