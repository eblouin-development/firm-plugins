<!--
recipe: seo-meta-sitemap
applies-to:
  - frontend/nextjs: full support — Metadata API (static + generateMetadata), sitemap.ts, robots.ts, JSON-LD via a server component
  - frontend/vite-spa: partial, honestly capped — CSR-only; ships a static robots.txt/sitemap.xml plus a documented react-helmet-async path for per-route <head> tags, with the SPA's real indexability limits stated rather than papered over
  - backend/django: full support — server-rendered <head> per view/template, a sitemap.xml view backed by django.contrib.sitemaps, robots.txt as a plain view
last-verified: 2026-07-24
provenance: manual
sources:
  - https://nextjs.org/docs/app/getting-started/metadata-and-og-images
  - https://nextjs.org/docs/app/api-reference/functions/generate-metadata
  - https://nextjs.org/docs/app/api-reference/file-conventions/metadata/sitemap
  - https://nextjs.org/docs/app/api-reference/file-conventions/metadata/robots
  - https://docs.djangoproject.com/en/5.2/ref/contrib/sitemaps/
  - https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
  - https://developers.google.com/search/docs/crawling-indexing/robots/intro
  - https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data
  - https://schema.org/docs/schemas.html
  - https://ogp.me/
  - https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics
  - plugins/dev-lifecycle/skills/seo/SKILL.md
-->

# SEO: per-route metadata, sitemap, robots.txt, OG/JSON-LD

Wires per-route `<title>`/meta-description/canonical, a generated `sitemap.xml`, a `robots.txt`, Open Graph/Twitter Card tags, and JSON-LD structured data into a public-facing frontend or the Django server-rendered path — the metadata and indexability layer the `seo` skill's implementation mode governs. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps: `frontend/nextjs`
- Wire-up steps: `backend/django`
- Wire-up steps: `frontend/vite-spa` (honest limits)
- Verification
- Doc fragment

## What this wires

Applying this recipe gives a project's public routes the metadata search engines and social platforms actually read: a unique title/description/canonical per indexable route, a `sitemap.xml` generated from the real route source (never hand-maintained), a `robots.txt` that allows what should be crawled and references the sitemap, Open Graph/Twitter Card tags on shareable pages, and JSON-LD structured data on the content types that support a real rich-result type (Article/BlogPosting, Organization/WebSite, BreadcrumbList).

It **composes existing pieces** rather than inventing a metadata system:
- **`frontend/nextjs`** already establishes the per-route `export const metadata: Metadata` convention (`app/page.tsx`, `app/layout.tsx`'s title template) — this recipe extends that same convention to every public route and adds the two file-convention exports (`app/sitemap.ts`, `app/robots.ts`) Next's Metadata API expects, plus a JSON-LD pattern for content routes.
- **`backend/django`**'s existing public blog surface (`core/urls.py`'s `blog/posts` / `blog/posts/<str:slug>`, `core/views.py`'s `PublicBlogPostListView`/`PublicBlogPostDetailView`) is the concrete route set this recipe wires metadata onto — a `sitemap.xml` view built from `django.contrib.sitemaps`, a `robots.txt` view, and server-rendered `<head>` tags on the templates that render those routes.
- **`frontend/vite-spa`** has no server render at all (confirmed by its own README: "React 19 + Vite 8 + TypeScript 6" client-rendered SPA, no SSR/SSG story) — this recipe does not pretend otherwise. It wires the static assets a CSR app can still ship (`public/robots.txt`, a build-time-generated `sitemap.xml` from the route table) and documents the `react-helmet-async` path for per-route `<title>`/meta tags, while stating plainly that Google's JS-rendering pipeline processes CSR content on a delayed second wave (per Google's own JavaScript SEO basics) and social-media crawlers (which typically do NOT execute JS at all) will see none of it — see that section for what a project should actually do about it.

## Prerequisites

- One of `frontend/nextjs`, `backend/django`, or `frontend/vite-spa` already scaffolded (this recipe's steps are block-specific — see the matching section below).
- Know which routes are meant to be public/indexable versus authenticated — this recipe only touches the public surface. Authenticated routes should already be excluded from indexing (see each section's exclusion step) rather than left to `noindex` as an afterthought.
- No new runtime dependency for `frontend/nextjs` or `backend/django` (both wire this from stack already present — Next's built-in Metadata API, Django's built-in `django.contrib.sitemaps`). `frontend/vite-spa` adds one new dependency (`react-helmet-async`) — pin it against current npm at implementation time; it has no entry on `references/compatibility-matrix.md` yet.
- Read `plugins/dev-lifecycle/skills/seo/SKILL.md`'s implementation-mode conventions before wiring — this recipe is the concrete per-block application of those conventions, not a restatement of them.

## Wire-up steps: `frontend/nextjs`

1. **Per-route metadata.** For a static route, export `const metadata: Metadata = { title, description, alternates: { canonical: "<absolute-or-relative-url>" } }` from that route's `page.tsx`, following `app/page.tsx`'s existing pattern. `app/layout.tsx`'s `title: { default, template: "%s · Web App" }` already composes with a child route's own `title` — don't duplicate the site name in every route's title, let the template do it. For a dynamic route (e.g. a blog post at `app/blog/[slug]/page.tsx`), use `generateMetadata({ params })` instead of a static export, fetching the post's real title/description/OG image from `@repo/api-client` server-side.

2. **`app/sitemap.ts`.** Add the file-convention sitemap Next serves at `/sitemap.xml` automatically:
   ```ts
   import type { MetadataRoute } from "next";

   export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
     const posts = await getPublishedPosts(); // via @repo/api-client, same source app routes render from
     return [
       { url: "https://example.com/", lastModified: new Date() },
       ...posts.map((p) => ({ url: `https://example.com/blog/${p.slug}`, lastModified: p.updatedAt })),
     ];
   }
   ```
   Generate the list from the same data source the routes themselves render from (the backend's public blog API) — never a hand-maintained array that drifts from the actual route set. Exclude the `(auth)` and `(app)` route groups entirely (login/register/dashboard/admin are never indexable).

3. **`app/robots.ts`.** The matching file-convention counterpart, served at `/robots.txt`:
   ```ts
   import type { MetadataRoute } from "next";

   export default function robots(): MetadataRoute.Robots {
     return {
       rules: { userAgent: "*", allow: "/", disallow: ["/dashboard", "/admin", "/login", "/register"] },
       sitemap: "https://example.com/sitemap.xml",
     };
   }
   ```
   This is a second, independent gate alongside step 2's exclusion — a route being absent from the sitemap doesn't stop a crawler discovering it via links; `robots.ts`'s `disallow` is the actual crawl-block.

4. **OG/Twitter cards.** Extend each public route's `metadata` export with `openGraph` and `twitter` fields, sourced from the same real content the page renders (not static placeholders):
   ```ts
   export const metadata: Metadata = {
     title: post.title,
     description: post.excerpt,
     openGraph: { title: post.title, description: post.excerpt, images: [post.ogImage], url: `https://example.com/blog/${post.slug}` },
     twitter: { card: "summary_large_image", title: post.title, description: post.excerpt, images: [post.ogImage] },
   };
   ```

5. **JSON-LD.** Render structured data as a `<script type="application/ld+json">` from a server component (no client JS needed — this is exactly the kind of static, server-rendered content `app/page.tsx`'s own SSR posture already favors):
   ```tsx
   <script
     type="application/ld+json"
     dangerouslySetInnerHTML={{
       __html: JSON.stringify({
         "@context": "https://schema.org",
         "@type": "BlogPosting",
         headline: post.title,
         datePublished: post.publishedAt,
         author: { "@type": "Organization", name: "Example" },
       }),
     }}
   />
   ```
   Use `dangerouslySetInnerHTML` here deliberately — it's the documented pattern for JSON-LD in React, and the payload is server-constructed from trusted fields (never raw user input dropped in unescaped). Validate the emitted markup against the current schema.org type definition for whichever `@type` is used before considering a route done.

## Wire-up steps: `backend/django`

1. **Sitemap via `django.contrib.sitemaps`.** Add `"django.contrib.sitemaps"` to `INSTALLED_APPS` in `config/settings.py`. In a new `core/sitemaps.py`, define a `Sitemap` subclass over the same queryset `PublicBlogPostListView` already filters (published, not soft-deleted, `published_at` not in the future — see `core/views.py`'s own module comment for that exact filter):
   ```python
   from django.contrib.sitemaps import Sitemap
   from core.views import _public_blog_post_queryset

   class BlogPostSitemap(Sitemap):
       changefreq = "weekly"
       priority = 0.6

       def items(self):
           return _public_blog_post_queryset()

       def lastmod(self, obj):
           return obj.updated_at

       def location(self, obj):
           return f"/blog/{obj.slug}"
   ```
   Reusing `_public_blog_post_queryset()` itself (not a fresh, re-derived filter) is what keeps the sitemap and `PublicBlogPostListView` from ever disagreeing about what's actually published — that helper's own docstring already documents it as "the ONE visibility predicate both public blog views share" (`status="published"`, not soft-deleted via `BlogPost.objects`'s default manager, `published_at` set and not in the future); a hand-rolled second filter here would be exactly the kind of drift step 1's "generated from the real route source" principle exists to prevent.

2. **Wire the sitemap URL.** In `config/urls.py`, add the sitemap view alongside the existing `path("", include("core.urls"))`:
   ```python
   from django.contrib.sitemaps.views import sitemap
   from core.sitemaps import BlogPostSitemap

   urlpatterns += [
       path("sitemap.xml", sitemap, {"sitemaps": {"blog": BlogPostSitemap()}}, name="sitemap"),
   ]
   ```
   This is a page/content route, not part of the DRF API contract — it sits at the same URLconf level as `/api/schema` (an additive path outside `core.urls`'s router, matching that file's own precedent).

3. **`robots.txt` as a plain view.** A `TemplateView` (or a trivial function view returning `HttpResponse(..., content_type="text/plain")`) rendering:
   ```
   User-agent: *
   Allow: /
   Disallow: /admin/
   Disallow: /api/
   Sitemap: https://example.com/sitemap.xml
   ```
   Note the `Disallow: /admin/` here is Django's convention for whatever admin/internal paths exist in this project — cross-check against the actual mounted paths (this block's own `admin/*` DRF routes are API endpoints, not pages, so they're not meant for indexing regardless; disallow them for crawl-budget hygiene, not because they'd otherwise rank).

4. **Server-rendered `<head>` per template.** For any server-rendered page template (this block's own routes are a DRF/JSON API today, not template-rendered HTML — if the project adds template-rendered public pages on top of this backend, e.g. a server-rendered blog view rather than the JSON API a frontend consumes), set `<title>{{ post.title }}</title>`, `<meta name="description" content="{{ post.excerpt }}">`, `<link rel="canonical" href="{{ request.build_absolute_uri }}">`, and the OG/Twitter equivalents directly in the template `<head>`, sourced from the view's real context data.

5. **JSON-LD.** Same pattern as the Next.js section — a `<script type="application/ld+json">` block in the template, populated from the view's context, validated against the current schema.org type definition.

## Wire-up steps: `frontend/vite-spa` (honest limits)

**State this plainly to whoever is applying this recipe:** `frontend/vite-spa` ships no server render — every route, public or not, serves the same `index.html` and hydrates client-side. Per Google's own JavaScript SEO documentation, Googlebot does render client-side JS, but on a **second, delayed rendering wave** after the initial crawl — a real but slower and less reliable path to indexing than server-rendered content. Non-Google crawlers and, critically, **social-media link-preview crawlers (Slack, Twitter/X, Facebook, iMessage) typically do not execute JavaScript at all** — an OG tag injected client-side via `react-helmet-async` will never be seen by those, producing a blank/broken share preview. This is a structural SPA limitation, not a configuration mistake to "fix" with more meta tags — the honest options, in order of how much they actually solve:

1. **Best: don't use the SPA for the public/marketing/content surface.** If SEO matters for specific routes, that's exactly `frontend/nextjs`'s reason to exist (see `skills/scaffolding/SKILL.md`'s own guidance: pick `nextjs` "when the product plan calls for server rendering, SEO-sensitive public pages"). This recipe doesn't force that migration, but says so rather than pretending the SPA can fully close the gap.
2. **Prerendering, if the SPA must stay.** Vite has no first-party SSG output; a project needing indexable/shareable SPA routes can add a build-time prerender step (e.g. running the built app through a headless-browser snapshot tool at build time to emit static HTML per route) — evaluate current tooling against `references/compatibility-matrix.md`'s Vite 8 pin before adopting one, since this is exactly the kind of vendor-churn surface the matrix exists to track; the kit does not ship a pinned prerender tool as of this recipe's `last-verified` date.
3. **What's still worth doing regardless:**
   - **`public/robots.txt`** — a static file, same content shape as the Django section's step 3, served as-is by Vite's static asset pipeline.
   - **Build-time-generated `public/sitemap.xml` (or a Vite plugin that emits one)** — generated from the app's route table at build time, not hand-maintained, even though the routes it lists won't get the SSR indexing benefit `nextjs` provides.
   - **`react-helmet-async`'s `<Helmet>`** per route for `<title>`/meta description — genuinely helps the delayed-JS-render path (option 1's Google-only, second-wave crawl) even though it does nothing for the non-JS social-preview crawlers noted above. Wrap the app root in `<HelmetProvider>` (main.tsx, alongside the existing `AuthProvider`/`QueryClientProvider` wiring) and call `<Helmet><title>...</title><meta name="description" content="..." /></Helmet>` per route component.
   - **OG/Twitter tags via `react-helmet-async` are still worth adding** for the crawlers that do execute JS, with the caveat from above stated to the project rather than silently omitted.

## Verification

- `sitemap.xml` is reachable at the expected URL and lists only intended-public routes (spot-check that an authenticated route never appears).
- `robots.txt` is reachable, does not accidentally `Disallow: /` the whole site, and its `Sitemap:` line matches the real sitemap URL.
- Each public route's rendered `<head>` (view source, not devtools' post-hydration DOM, to see what a non-JS crawler sees) has a unique `<title>`, a meta description, and a canonical link.
- JSON-LD blocks validate against the current schema.org type definition for their `@type`.
- OG tags render real content values, checked with an actual link-preview tool (not assumed from the code alone) — this is where the vite-spa gap is most visible if it applies.

## Doc fragment

```markdown
### SEO: per-route metadata, sitemap, robots.txt
- **Setup:** Public routes carry per-route title/description/canonical metadata (`frontend/nextjs`: the `Metadata`/`generateMetadata` exports and `app/sitemap.ts`/`app/robots.ts`; `backend/django`: `core/sitemaps.py` + the `sitemap.xml`/`robots.txt` views; `frontend/vite-spa`: `react-helmet-async` per route plus static `public/robots.txt`/generated `public/sitemap.xml`, with SPA indexing/social-preview limits called out — see `references/recipes/seo-meta-sitemap.md`). Sitemaps generate from the same data source the routes render from, never hand-maintained. OG/Twitter cards and JSON-LD (Article/BlogPosting, Organization/WebSite) are wired on shareable content routes.
- **Secrets:** none — this recipe adds no credential or backing service.
- **Maintenance:** Adding a new public content type means adding it to the sitemap source (the `Sitemap.items()` queryset on Django, the `sitemap.ts` data fetch on Next) in the same change that adds the route — a route that ships without its sitemap entry silently under-indexes. Re-validate JSON-LD against schema.org's current type definitions if a content model's fields change shape. The `frontend/vite-spa` path's limits are structural, not a bug to file — see the recipe's own honest-limits section before spending time trying to fully close that gap in-place.
```

---
<!--
Recipe authored via the `recipe-author` skill (issue #91). Wires the
frontend/nextjs Metadata API convention already established by app/page.tsx
and app/layout.tsx, the backend/django public blog surface already shipped
in core/urls.py / core/views.py, and states frontend/vite-spa's real SPA
indexing/social-preview limits rather than presenting a false parity with
the SSR blocks.
-->
