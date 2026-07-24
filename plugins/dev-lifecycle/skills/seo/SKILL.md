---
name: "seo"
description: "Technical and on-page SEO for client sites — an audit mode (read-only, patterned after security-audit: crawlability, meta/canonical/robots, structured data validity, Core Web Vitals implications, rendering-strategy tradeoffs, index coverage) and an implementation mode (metadata conventions, sitemap/robots generation, redirects/canonicals, OG/Twitter cards, JSON-LD, image/alt discipline) that the build skills follow. Use this skill WHENEVER the work touches how a site is found, crawled, or ranked: \"SEO\", \"meta tags\", \"sitemap\", \"robots.txt\", \"why isn't this ranking\", \"why isn't this indexed\", \"structured data\", \"schema markup\", \"OG tags\", \"canonical URL\", \"is this page SEO-friendly\". Also trigger when scaffolding or building a public-facing page and the rendering choice (SSR/SSG vs CSR) has SEO consequences. Hands content strategy and keyword copy to copywriting, and performance work beyond metadata to frontend/devops — this skill owns the metadata and indexability layer, not the words or the raw speed."
---

# SEO

Technical and on-page SEO for client sites: whether a page can be crawled, indexed, and correctly represented in search results and social shares. Two modes, same domain: **audit** (read-only, patterned after `security-audit` — assess what's there, credit what's handled, find what's not) and **implementation** (the conventions the build skills follow when metadata, sitemaps, or structured data are part of the work). Neither mode writes keyword-targeted copy or chases raw page-speed — those are other skills' jobs (see Boundaries).

## Core rules

- **Ground every claim in current search-engine documentation, never recall.** Google's ranking systems, Search Console behavior, and structured-data requirements change often enough that training-data memory is a liability here. Before asserting how Google/Bing treats a tag, a status code, or a markup type, check current docs — Google Search Central (`developers.google.com/search`), Bing Webmaster docs, and `schema.org`/validator.schema.org for structured-data types — and cite what was checked. If a claim can't be grounded because docs weren't reachable, say so rather than asserting from memory.
- **No black-hat tactics, ever.** No cloaking, no doorway pages, no hidden text/links, no keyword stuffing, no PBNs/link schemes, no AI-generated content dressed as original reporting, no sneaky redirects. If a request would trade a search penalty for a short-term ranking gain, decline it and explain the risk — a manual action or algorithmic demotion costs far more than the gain.
- **Evidence or it didn't happen (audit mode).** Every audit claim — handled or finding — cites the actual page/file/response that was inspected (`file:line`, a URL and the status code/header returned, a validator result). No speculative findings padded for volume.
- **Rendering strategy is a first-class finding, not an aside.** CSR-only pages that need to rank are a structural problem no amount of meta-tag polish fixes — call this out explicitly when it applies, and route the fix (SSR/SSG adoption) to `frontend` since it's an architecture change, not metadata.
- **Scale to what's actually public.** Don't audit or optimize authenticated app screens for search indexability — they shouldn't be indexed at all (verify they're correctly excluded, per `noindex`/robots/auth-gating). Focus on the surfaces search engines actually see: marketing pages, blog/content, product/listing pages, docs.
- **Token-efficient breadth.** Enumerate routes from the router/sitemap/CMS rather than reading the whole tree; read the specific spans (a page's `<head>`, a route's metadata export, `robots.txt`, `sitemap.xml`) that decide handled vs. open. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Boundaries

- **Content strategy, keyword research, and on-page copy → `copywriting`.** This skill says *where* a title tag or meta description needs to exist and what constraints it must satisfy (length, uniqueness, one H1); it does not write the words. Hand off the actual copywriting to `copywriting`, which also runs the humanizer/ruthless-edit quality pass.
- **Performance work beyond metadata → `frontend` (Core Web Vitals fixes: bundle size, image optimization pipelines, lazy loading, render-blocking resources) or `devops` (CDN/caching/edge config, TTFB at the infra layer).** Audit mode reports Core Web Vitals *implications* and flags what's slow; it doesn't own the fix. Implementation mode's own scope stops at metadata, structured data, sitemap/robots, and redirects/canonicals.
- **Rendering-strategy architecture decisions (SPA vs SSR vs SSG, which frontend block to scaffold) → `frontend`/`scaffolding`.** This skill identifies the SEO consequence of a rendering choice and recommends a direction; the actual framework/architecture change is built by the build skills.
- **This skill does not run ranking/traffic analytics or paid-search work** (Google Ads, keyword-bid strategy) — out of scope entirely; point elsewhere if asked.

## Audit mode

Read-only, point-in-time technical + on-page SEO assessment. Never modify code or config, never submit anything to Search Console/Bing Webmaster Tools, never fetch a live competitor site more aggressively than a normal crawl.

### 1. Fingerprint the site
Identify the rendering strategy per route group (SSR/SSG vs CSR — check the frontend block: `frontend/nextjs`'s App Router pages default to server-rendered; `frontend/vite-spa` is CSR-only, `backend/django` server-rendered templates render fully on request), which routes are meant to be public/indexable vs authenticated/excluded, and the CMS/content source if any. This scopes what follows — a CSR-only SPA's audit leads with the rendering-strategy finding before any meta-tag detail matters.

### 2. Enumerate the surfaces
Instantiate this checklist against the actual routes (from the router/sitemap, not by reading the whole tree):
- **Crawlability:** `robots.txt` present and not accidentally blocking public routes; no stray `noindex` on pages meant to rank; internal links use real `<a href>` (or framework equivalents Google can traverse), not JS-only navigation with no crawlable fallback.
- **Indexability signals:** canonical tags present and self-referential (or correctly pointing at the preferred URL for near-duplicate content); no conflicting signals (e.g., a page both submitted in `sitemap.xml` and `noindex`ed).
- **Meta/head correctness:** unique, appropriately-lengthed `<title>` and meta description per route; single `<h1>`; `lang` attribute set; viewport meta present.
- **Structured data:** JSON-LD present where it adds value (Organization/WebSite on the home page, Article/BlogPosting on posts, Product on listings, BreadcrumbList where applicable) and **valid** — check against `schema.org`'s current type definitions and, where reachable, Google's Rich Results Test guidance for what it actually surfaces as a rich result vs. what's merely valid markup.
- **Social sharing:** Open Graph (`og:title`, `og:description`, `og:image`, `og:url`) and Twitter Card tags present and populated with real values, not placeholders.
- **Sitemap:** `sitemap.xml` exists, is reachable, lists the actual public routes (not stale, not missing new ones, not including `noindex`d/authenticated routes), and is referenced from `robots.txt`.
- **Core Web Vitals implications:** note what's measurable from the code/config (render-blocking resources, unoptimized `<img>` without dimensions/lazy-loading, large unsplit JS bundles on a page meant to rank) as a *finding to route elsewhere* (see Boundaries) — this skill doesn't fix it, it flags that it affects rankability.
- **Index coverage (if Search Console/Bing Webmaster access is available):** actual indexed-vs-submitted counts and any reported crawl errors; if no access, say so explicitly rather than skipping the section silently.

### 3. Assess each surface
For each, classify: ✅ Handled (evidence cited — the file/response inspected), 🔴/🟠/🟡/⚪ finding (impact on rankability/indexability, evidence, remediation sketch, and which skill owns the fix if not this one), or N/A (one line why, e.g. "route is authenticated, correctly excluded"). Severity is about rankability/indexability impact, not aesthetics: 🔴 a public page that can't be indexed at all or is accidentally `noindex`ed; 🟠 broken/missing structured data on a type that drives real rich-result value, or a CSR-only page that needs to rank; 🟡 missing OG/Twitter tags, thin meta descriptions, sitemap drift; ⚪ hardening opportunities (breadcrumb schema not yet added, alt-text gaps on non-critical images).

### 4. No silent gaps
State plainly what wasn't checked — no Search Console access, a route behind auth that couldn't be crawled as a real visitor, a validator that wasn't reachable — in the report's scope section.

### 5. Deliver the inline report
1. **Executive summary** — overall indexability/rankability posture in 3–5 sentences, finding counts by severity.
2. **Site profile & scope** — rendering strategy per route group, what was assessed, what was skipped.
3. **Surface map** — the enumeration from step 2.
4. **What's handled** — credited, with evidence.
5. **Findings** — severity order, each with impact, evidence, remediation sketch, and the owning skill if it's not this one.
6. **Roadmap** — ordered by rankability impact and by dependency (fix a hard `noindex` block before polishing structured data on the same page).

Audit mode does not file GitHub issues itself unless the user asks — this is a lighter, faster loop than `security-audit`'s umbrella-issue pipeline since SEO findings are typically metadata-scoped and clear individually; if the user wants findings tracked, file them in the `planning` skill's issue format (goal / context / steps / acceptance criteria), one per finding or grouped by page/theme, without kicking off a build unless the user says to start one via a `coding-session`.

## Implementation mode

Guidance the build skills (`frontend`, `backend`) follow whenever a feature involves per-route metadata, sitemap/robots generation, structured data, or social cards. Implementation mode doesn't build the feature itself — it hands the build skill the conventions; the concrete per-block wiring (Next.js Metadata API, Django server-rendered templates, the vite-spa SPA caveats) is `references/recipes/seo-meta-sitemap.md`.

- **Metadata conventions:** every indexable route gets a unique `<title>` (~50–60 characters is the commonly cited safe range before truncation, verify current guidance rather than treating that as gospel) and meta description (~150–160 characters), a self-referential canonical unless intentionally pointing elsewhere, and exactly one `<h1>`.
- **Sitemap generation:** `sitemap.xml` is generated from the actual route source (the router/CMS), not hand-maintained — hand-maintained sitemaps drift. Exclude authenticated/`noindex`d routes. Reference from `robots.txt`.
- **Robots.txt:** allow what should be crawled, disallow authenticated/internal routes, reference the sitemap. Never disallow the whole site by accident (a common staging-environment leak into production).
- **Redirects/canonicals:** a permanent URL change is a 301, not a client-side-only redirect a crawler may not follow; canonical tags resolve duplicate-content ambiguity (query-param variants, trailing-slash variants) rather than leaving multiple URLs competing for the same content.
- **OG/Twitter cards:** every shareable page gets real `og:title`/`og:description`/`og:image`/`og:url` and Twitter Card equivalents — populated from the page's actual content/metadata source, not static placeholders that go stale.
- **JSON-LD:** add structured data where it maps to a real Google-supported rich-result type for the content (Article, Product, BreadcrumbList, Organization/WebSite) — grounded in schema.org's current type definitions, not invented properties. Validate before considering it done.
- **Image/alt discipline:** every content-bearing `<img>` gets meaningful `alt` text (empty `alt=""` only for genuinely decorative images); explicit `width`/`height` (or their framework equivalent) to avoid layout shift, which is itself a Core Web Vitals signal.
- **Rendering strategy honesty:** when a build touches a CSR-only surface (`frontend/vite-spa`) that needs to rank, say so plainly rather than layering meta tags onto a page search engines may render incompletely or on a delay — see the recipe's vite-spa section for what's actually achievable there (prerendering options) versus what isn't.

## What this skill does NOT do

- Write keyword-targeted or marketing copy — that's `copywriting`.
- Fix Core Web Vitals at the code/infra level (bundle splitting, image pipelines, CDN/caching) — flags the SEO impact, routes the fix to `frontend`/`devops`.
- Decide or build the rendering-strategy architecture (SPA vs SSR vs SSG) — identifies the SEO consequence, hands the build to `frontend`/`scaffolding`.
- Use any black-hat tactic, or help a request that trades a search penalty for short-term ranking gain.
- Assert how a search engine behaves from memory — every such claim is grounded in current documentation, checked in the session.
- Submit anything to Search Console/Bing Webmaster Tools or crawl third-party sites aggressively during an audit — read-only against the project's own code/config/reachable public pages.
