<!--
recipe: analytics
applies-to:
  - backend block: fastapi OR django (an AnalyticsSink Protocol mirroring the auth component's EmailSender pattern — NEW, not yet in the kit; see "What the kit does not provide")
  - frontend block: nextjs OR vite-spa (a consent-gated web-analytics snippet + a thin client that posts events to the backend sink)
  - mobile block: expo (a thin client that posts events to the backend sink — no client-side web-analytics snippet on mobile)
last-verified: 2026-07-24
provenance: manual
sources:
  - https://plausible.io/docs
  - https://plausible.io/docs/events-api
  - https://umami.is/docs
  - references/backend/fastapi.md
  - references/backend/django.md
  - references/security/data-protection.md
  - references/security/secure-baseline.md
  - templates/components/security/auth/_core.py
  - references/recipes/background-jobs.md
  - references/recipes/transactional-email.md
-->

# Analytics & event tracking

Wire product analytics — a typed event taxonomy, server-side event capture through one `AnalyticsSink` seam, and a privacy-respecting default for page-view web analytics — so events survive ad-blockers and stay consistent across web and mobile instead of depending solely on a client-side script. **This recipe describes ADDING a capability the kit does not ship today**: there is no `AnalyticsSink`, no event model, and no analytics wiring in any block as of this recipe's `last-verified` date (confirmed by inspection — grep the relevant blocks before trusting this claim to have not gone stale). Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- What the kit does not provide (read this first)
- Prerequisites
- The event taxonomy
- Wire-up steps (backend: `AnalyticsSink` + capture endpoint)
- Wire-up steps (web: nextjs / vite-spa)
- Wire-up steps (mobile: expo)
- Privacy, consent, and the web-analytics default
- Doc fragment

## What this wires
Applying this recipe gives a project one server-side event-capture seam — an `AnalyticsSink` Protocol, mirroring the auth component's `EmailSender` pattern (one abstraction, one production adapter, safe to call from a request path) — plus a minimal typed event taxonomy every event conforms to, wired from nextjs, vite-spa, and expo through to a chosen backend track (fastapi or django). A consent-gated, privacy-respecting web-analytics default (self-hosted/EU-hosted, page-view-only) covers the "how many people visited" question; the `AnalyticsSink` covers the "what did a known actor do" question — the two are deliberately separate paths, not one script doing both.

It **composes existing pieces** and is explicit about what it adds:
- **The existing auth component's `EmailSender` shape** (`templates/components/security/auth/_core.py`) is the pattern this recipe mirrors: a framework-neutral `Protocol` (`async def send(...)`/`async def capture(...)`), a dev-only synchronous adapter that just logs, and a real adapter that is fire-and-forget and non-raising. `AnalyticsSink` does not live in the auth component — it is new, project-level code this recipe adds — but it follows the exact same discipline.
- **The `background-jobs` recipe** — dispatching a captured event to whatever real analytics/warehouse backend a project chooses (a queue, a batched HTTP call to a self-hosted collector) is async work off the request path, the same way the transactional-email and push-notifications recipes dispatch their own network calls.
- **The `transactional-email` recipe's fire-and-forget, non-raising contract** — `AnalyticsSink.capture()` holds the identical shape: it must never block or raise into the request/interaction that triggered it.
- **`references/security/data-protection.md`'s data classification** — event `properties` are held to the same "no PII, no secrets" bar as a report or export from this skill's reporting lane.

## What the kit does not provide (read this first)
None of the following exist in this kit as of this recipe's `last-verified` date — the wire-up steps below are instructions for **adding** each of them, not for wiring an existing component:
- **No `AnalyticsSink` Protocol, no event model, no capture endpoint** in either `templates/backend/fastapi` or `templates/backend/django`.
- **No analytics/tracking script** in `templates/frontend/nextjs`, `templates/frontend/vite-spa`, or `templates/mobile/expo`.
- **No compatibility-matrix row** for any analytics provider (Plausible, Umami, PostHog, or otherwise) — this recipe recommends a self-hosted/EU-hosted, privacy-respecting default but does not vendor a specific provider's SDK; pin whatever the project picks against its current release at implementation time.
- **No consent-management mechanic** — the consent gate this recipe requires is a boolean check documented below, not a full consent-state model. `references/recipes/gdpr-data-rights.md` (added in parallel by a sibling issue, #98) is the recipe that will own a real consent-state model and cookie-consent UI; this recipe's gate is the minimum honest stand-in until that lands, and should be swapped for it once available rather than maintained as a second consent mechanism.

Don't cite any of the above as already wired. A build agent applying this recipe is doing net-new work across the chosen backend and every frontend/mobile block in play, not composing a pre-built analytics component.

## Prerequisites
- A backend block (`templates/backend/fastapi` or `templates/backend/django`) to host the `AnalyticsSink` and the capture endpoint.
- At least one of `templates/frontend/nextjs`, `templates/frontend/vite-spa`, or `templates/mobile/expo` to emit events from.
- If the project also wants page-view web analytics (distinct from the `AnalyticsSink`'s actor/event capture), a chosen provider reachable from the browser — self-hosted (Plausible CE, Umami) or an EU-hosted managed instance; see "Privacy, consent, and the web-analytics default."
- A decision on where captured events ultimately land: an `events` table in the project's existing Postgres database is the zero-new-infrastructure default this recipe assumes; a real warehouse/pipeline (ClickHouse, BigQuery, a streaming pipeline) is explicitly out of scope — that's the `infrastructure`/`devops` punt the `data` skill's boundary still makes, and it stays a deliberate future addition, not something this recipe backs into.

## The event taxonomy
Every event this recipe's seam captures conforms to one minimal, typed shape — the point is that events stay queryable (you can `WHERE name = 'checkout_completed'` and get a consistent `properties` shape back), not a free-form `dict` per call site:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AnalyticsEvent:
    """One product-analytics event. `properties` MUST NOT contain PII or
    secrets by default (see "Privacy, consent, and the web-analytics
    default") -- it holds only what's needed to answer a product
    question about this event, never a name/email/free-text field."""

    name: str                      # e.g. "checkout_completed" -- snake_case, past-tense verb phrases
    actor_id: str | None           # the acting user's opaque ID, or None for an anonymous/unauthenticated actor
    object_type: str | None        # e.g. "order", "post" -- what the event happened to, if anything
    object_id: str | None          # that object's ID
    properties: dict[str, Any] = field(default_factory=dict)   # small, typed, no-PII payload
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

- **`name`** is a closed-ish, snake_case, past-tense convention (`signup_completed`, `checkout_completed`, `item_viewed`) — not a free-form string per call site. Keep a single source list (a module-level `Literal`/enum, or at minimum a reviewed constants file) so `SELECT DISTINCT name FROM events` doesn't drift into near-duplicates (`checkoutComplete` vs `checkout_completed`).
- **`actor_id`** is the acting principal's opaque ID (the same ID `AccountService`/the auth component already mints) — never an email or a display name. `None` is a legitimate value for an anonymous pre-auth event (e.g. a landing-page CTA click), and must stay distinguishable from a missing/broken actor lookup — don't silently coerce `None` to a sentinel user.
- **`object_type`/`object_id`** name what the event acted on, when there is one — omit both (leave `None`) for an event with no natural object (`app_opened`).
- **`properties`** stays small and typed per event `name` (a plan tier, an item count, a currency amount) — never free text, never anything from `references/security/data-protection.md`'s PII/secret categories. See "Privacy, consent, and the web-analytics default" for the enforcement point.

## Wire-up steps (backend: `AnalyticsSink` + capture endpoint)
1. **Define the `AnalyticsSink` Protocol** in a framework-neutral module (mirroring where `EmailSender` lives relative to the auth component — a plain-Python core with no request/DB coupling):
   ```python
   from typing import Protocol

   class AnalyticsSink(Protocol):
       """The event-capture seam a feature calls to record an
       AnalyticsEvent. Implementations MUST NOT let capture latency or
       capture failure affect the caller -- same fire-and-forget,
       non-raising contract as EmailSender.send()."""

       async def capture(self, event: AnalyticsEvent) -> None: ...
   ```
2. **Ship exactly one dev-only implementation in the same module** — a `LoggingAnalyticsSink` that logs the event (structured, via the project's existing logger) instead of persisting it, the same role `ConsoleEmailSender` plays for email. A real implementation is application code, not part of this neutral core.
3. **Add the production adapter per backend track**, persisting to an `events` table built on the same `db-mixins`/`repository` catalog components every other model in the kit uses (`id`, `name`, `actor_id` nullable FK, `object_type`, `object_id`, `properties` as JSON/JSONB, `occurred_at`, indexed on `(name, occurred_at)` at minimum — add `(actor_id, occurred_at)` if per-actor timelines are a real query pattern):
   - **FastAPI**: an `async def capture(self, event)` that inserts via the repository, wrapped so the insert itself never raises into the caller — catch and log, per the pattern below.
   - **Django**: the same shape behind Django's ORM, dispatched the same way `DjangoEmailSender` dispatches (a bounded `ThreadPoolExecutor`, not `asyncio.create_task` — see the transactional-email recipe's step 4 for exactly why `asyncio.create_task` silently drops work under `async_to_sync`).
4. **Dispatch the actual persist off the request path** through the `background-jobs` recipe's task path (Celery `.delay()` on Django, `BackgroundTasks`/a task-queue path on FastAPI) once event volume matters — for low volume, a direct non-blocking insert is an acceptable starting point, but never an `await`ed round-trip that can slow or fail the request the event rode in on.
5. **Add one authenticated capture endpoint** (`POST /analytics/events` or similar) for web/mobile clients to call, gated the same way every other authenticated route is (`Depends(get_current_principal)` on FastAPI, the equivalent on Django) — but accept an **optional** principal, not a required one, since pre-auth events (landing-page interactions) are legitimate. Resolve `actor_id` from the authenticated principal server-side when present; never trust a client-supplied `actor_id` in the request body (the same anti-spoofing posture the push-notifications recipe applies to device-token registration).
6. **Validate `name` against the project's known taxonomy and cap `properties`' size/depth** before insert — reject an event whose `name` isn't in the project's reviewed list (or route unknowns to a quarantine table for review) and reject an oversized/deeply-nested `properties` payload, so a compromised or buggy client can't turn this endpoint into an unbounded write amplifier.
7. **Call `AnalyticsSink.capture()` from server-side code directly for events the client should never be trusted to report** (e.g. `checkout_completed` — a client-reported "I paid" event is trivially spoofable) — reserve the `POST /analytics/events` endpoint for events that are legitimately client-observed (a page view, a button click) and have no authoritative server-side moment to hook instead.

## Wire-up steps (web: nextjs / vite-spa)
1. **Add a thin `analyticsApi.ts`** following the same adapter shape `authApi.ts` already establishes in this kit's frontend blocks (and that the push-notifications recipe proposes `pushApi.ts` also follow) — a small wrapper over the generated `@repo/api-client` operation for `POST /analytics/events`, not a new HTTP client.
2. **Fire events from user interactions the client legitimately observes** (page views, clicks, form-started) — never for events with a server-side source of truth (see backend step 7).
3. **Gate every call behind the consent check** (see "Privacy, consent, and the web-analytics default") — no event, including a bare page view, fires before consent is granted, unless the project has classified that specific event as strictly necessary (rare — most product-analytics events are not).
4. **Debounce/batch high-frequency events client-side** (e.g. scroll-depth, hover) before they ever reach the capture endpoint — sending one event per interaction is wasteful and re-introduces the load-amplification concern backend step 6 already guards against.

## Wire-up steps (mobile: expo)
1. **Reuse the bearer-mode `@repo/api-client`** the way `pushApi.ts` does — no separate mobile analytics SDK, no separate transport; the same `POST /analytics/events` endpoint, called with the app's existing authenticated (or anonymous, pre-auth) client.
2. **No client-side web-analytics snippet on mobile** — the "Privacy, consent, and the web-analytics default" section below is a *web* page-view concern (a browser script); mobile app-open/screen-view events are ordinary `AnalyticsSink` events like any other, still consent-gated per the same rule.
3. **Respect the platform's own tracking-permission surface** where applicable (e.g. iOS App Tracking Transparency, if the project ever attributes events to a cross-app identifier) — out of scope for this recipe's own event taxonomy (which uses the app's own `actor_id`, not a cross-app ad identifier), but flag it explicitly if a future addition introduces one.

## Privacy, consent, and the web-analytics default
- **The recommended default is a self-hosted or EU-hosted, cookieless, page-view-only web-analytics tool** (e.g. Plausible or Umami, self-hosted; either provider's managed EU-hosted offering as the lower-effort alternative) over a third-party ad-network-affiliated analytics script. Tradeoffs, stated plainly:
  - **Gains**: no cross-site cookie, no IP storage by default (both providers hash/discard it), typically no cookie-consent banner *legally required* for the page-view tool itself in most EU readings (still confirm with counsel per-jurisdiction — this is not legal advice), smaller JS payload, no ad-tech data-sharing relationship.
  - **Costs**: fewer built-in feature-flag/session-replay/funnel capabilities than an ad-tech-affiliated suite; self-hosting is infrastructure the project now owns (or a managed EU tier's ongoing cost); less "everyone already knows this dashboard" familiarity for a new team member.
  - This tool answers **"how many people visited/which pages"** — it is deliberately separate from the `AnalyticsSink` seam above, which answers **"what did this known actor do."** Don't conflate the two into one script; the page-view tool never receives `actor_id` or any authenticated-user data.
- **Consent gate, explicitly documented**: adding *any* tracker — including a privacy-respecting one — has consent implications under GDPR/ePrivacy (EU) and similar regimes elsewhere. This recipe requires a simple boolean consent check gating both the web-analytics snippet's load and every `AnalyticsSink.capture()` call from a client (web step 3, mobile step 2) before either fires, with the sole exception of events the project has explicitly classified as strictly-necessary (rare for product analytics). **This is a minimum stand-in, not a full consent-management system** — `references/recipes/gdpr-data-rights.md` (issue #98, in progress alongside this recipe) is where the real consent-state model and cookie-consent UI will live; adopt that recipe's consent gate in place of this one once it ships, rather than running two.
- **No PII in event properties, by default, full stop.** `properties` never carries an email, name, free-text field, IP address, or precise geolocation — per `references/security/data-protection.md`'s classification. If a project genuinely needs one of those fields for a specific analysis, that is a deliberate, reviewed exception at the point of that event's definition (documented in the taxonomy's source-of-truth list), never an ambient default any call site can reach for.
- **This is not legal advice.** GDPR/ePrivacy/CCPA and similar regimes vary by jurisdiction and change; confirm the project's actual consent and retention obligations with counsel. This recipe documents the engineering mechanics (a consent gate exists, PII is excluded by default) — it does not certify compliance.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Analytics & event tracking
- **Setup:** Product-analytics events go through one `AnalyticsSink` seam (mirrors the auth component's `EmailSender` — fire-and-forget, non-raising) into an `events` table (`name`, `actor_id`, `object_type`, `object_id`, `properties`, `occurred_at`), captured either server-side directly (for events with an authoritative server moment) or via an authenticated `POST /analytics/events` endpoint (for client-observed events like page views/clicks). Web/mobile call it through a thin `analyticsApi.ts`/client adapter, same shape as `authApi.ts`. Page-view web analytics (distinct from `AnalyticsSink`) defaults to a self-hosted/EU-hosted, cookieless tool (Plausible/Umami) rather than an ad-tech-affiliated script.
- **Secrets:** none new for the `AnalyticsSink`/events-table path. If a self-hosted/EU-hosted web-analytics provider is added, its site ID/domain (not typically a secret) is project config, resolved the same way as other runtime config.
- **Consent & privacy:** every client-side event (web-analytics snippet load and any `AnalyticsSink.capture()` call from a browser/mobile client) is gated behind a consent check — see `references/recipes/gdpr-data-rights.md` for the full consent-state model once it ships; this recipe's gate is a minimum stand-in. `properties` never carries PII by default (`references/security/data-protection.md`'s classification governs exceptions). Not legal advice — confirm jurisdiction-specific obligations with counsel.
- **Maintenance:** This is a kit addition, not a pre-built component — the `AnalyticsSink` Protocol, the `events` table, both endpoints, and the taxonomy's source-of-truth list are project code following this recipe's shape. Keep the event-name list reviewed and closed-ish (reject/quarantine unknown names at the capture endpoint) so `events.name` doesn't drift into near-duplicates.
```

---
<!--
Recipe authored via the `recipe-author` skill for issue #97. Mirrors the
EmailSender Protocol/adapter shape from templates/components/security/auth/
_core.py explicitly rather than claiming a pre-existing AnalyticsSink (none
exists in the kit as of last-verified). Cross-links the GDPR/consent recipe
(issue #98, references/recipes/gdpr-data-rights.md) being authored in
parallel rather than inventing a second consent-management mechanic. Backend
persistence stays on the project's existing Postgres (an `events` table via
db-mixins/repository) — a real warehouse/pipeline is explicitly out of scope,
consistent with the data skill's (now-real) infrastructure/devops punt.
-->
