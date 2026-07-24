<!--
recipe: gdpr-data-rights
applies-to:
  - backend block: fastapi OR django (SingleUseTokenService, background-jobs, audit-logging, transactional-email all ship on both tracks)
  - frontend block: any web block (the cookie-consent gate) — mobile out of scope (no third-party trackers/cookies to gate in the same sense)
last-verified: 2026-07-24
provenance: manual
sources:
  - references/security/data-protection.md
  - references/security/payments-security.md
  - references/security/secure-baseline.md
  - references/recipes/audit-logging.md
  - references/recipes/background-jobs.md
  - references/recipes/data-export.md
  - references/recipes/transactional-email.md
  - templates/components/security/auth/_core.py
-->

# GDPR data-subject rights (export, erasure, cookie consent)

Wire the three data-subject-rights mechanics a GDPR-facing (or CCPA-adjacent) product needs — an authenticated "download my data" export, a right-to-erasure deletion pipeline, and a cookie-consent gate — entirely by composing pieces this kit already ships: `auth`'s `SingleUseTokenService`, the `background-jobs`/`transactional-email`/`audit-logging` recipes, and `db-mixins`' `SoftDeleteMixin`. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

**Not legal advice.** This recipe describes a set of engineering mechanics commonly required to *support* GDPR Articles 15 (access) and 17 (erasure) and ePrivacy/cookie-consent obligations — it is not a compliance certification, does not cover every jurisdiction's requirements (CCPA/CPRA, LGPD, etc. differ in detail), and does not substitute for review by counsel before a project relies on it to meet a real regulatory obligation.

## Contents
- What this wires
- Prerequisites
- Wire-up steps: subject access export
- Wire-up steps: right to erasure
- Wire-up steps: cookie consent
- Limitation: backups, replicas, and third-party processors (read before shipping erasure)
- Doc fragment

## What this wires
Applying this recipe gives a project three working mechanics:
1. An authenticated user can request a machine-readable export of their own data — synchronous for a small graph, asynchronous (background job + expiring emailed link) for a large one.
2. An authenticated, identity-verified user can request account erasure: a grace period during which the request is cancellable, then either a hard delete or an anonymize-in-place pass depending on what legal/audit/financial retention requires the row to survive.
3. A visiting user's cookie/tracker consent choice is captured as explicit state and gates every non-essential script/tracker from loading until consent is given.

It **composes existing pieces** — it invents no new infrastructure:
- **`templates/components/security/auth/_core.py`'s `SingleUseTokenService`** (`issue(user_id, purpose, ttl)` / `consume(raw, purpose)`) — the same hashed, single-use, purpose-scoped, expiring token primitive `AccountService` already uses for verify-email/reset-password links. This recipe reuses it twice: as the expiring download link for an async export, and as the identity-verification gate before an erasure request is accepted.
- **The `background-jobs` recipe** — large exports and the grace-period finalization/anonymization pass run as a Celery task (Django track) or are flagged as needing a project-added queue on the FastAPI track (that recipe's own "What the kit does not provide" section applies here unchanged — see step 3 under Export).
- **The `transactional-email` recipe**'s `EmailSender` seam — the export-ready notification and the erasure grace-period confirmation/cancellation emails go through the same fire-and-forget, non-raising `EmailMessage`/`EmailSender` seam as verify/reset mail, not a new email path.
- **The `audit-logging` recipe** — every export and every erasure-pipeline transition (`gdpr.export.requested`, `gdpr.export.completed`, `gdpr.erasure.requested`, `gdpr.erasure.grace_period_cancelled`, `gdpr.erasure.hard_deleted`, `gdpr.erasure.anonymized`) is an `audit_event(...)` call — this is exactly the "access to or export of restricted-tier data" and "privilege/role changes" audit-worthy case that recipe already names.
- **`templates/components/backend/db-mixins/`'s `SoftDeleteMixin`** — the grace-period state (`deleted_at` set, not yet purged) and the anonymize-in-place branch (row survives, PII fields overwritten) both build on the same mixin every model in the kit already has, rather than a bespoke `pending_erasure` flag.
- **The `data-export` recipe**'s streaming/authorization-scoping discipline — the same "reuse the caller's own authorization scope, never a client-supplied scope, audit and rate-limit bulk access" posture applies to a subject-access export, which is bulk access to one user's *entire* graph.
- **`references/security/payments-security.md`** and **Stripe's own retention** — a user's Stripe `customer`/`payment_intent`/`charge` IDs persisted per the `stripe-payments` recipe are financial records with their own legal retention window; this recipe's erasure pipeline anonymizes the app's copy of associated non-required fields rather than deleting the row, and does not attempt to delete anything from Stripe itself (see "Limitation" below).

## Prerequisites
- A backend block with the **`auth`** component vendored (`SingleUseTokenService`/`SingleUseTokenStore` ship with it regardless of whether verify-email/reset-password is in active use).
- The **`audit-logging`**, **`background-jobs`**, and **`transactional-email`** recipes already wired (this recipe adds GDPR-specific call sites to each; it does not re-establish any of the three).
- **`db-mixins`' `SoftDeleteMixin`** (or the Django track's equivalent soft-delete manager) on every model that participates in erasure.
- A model relationship graph already expressed via the ORM (SQLAlchemy `relationship()` / Django `ForeignKey` related managers) for every object the export/erasure walk needs to reach from the user row — this recipe walks *existing* relationships; it does not introduce a second, hand-maintained list of "what belongs to a user."
- A frontend web block, for the cookie-consent gate only (skip that section for a backend-only/mobile-only project — mobile apps don't carry third-party cookies in the same sense, though an equivalent app-tracking-consent gate is a project's own analogous addition, out of scope here).
- No new compatibility-matrix row: every piece this recipe wires already pins its own version via the recipes/components it composes.

## Wire-up steps: subject access export

1. **Walk the user's object graph via existing relationships, not a hand-maintained field list.** Write one `export_user_data(user_id) -> dict` per project (not per recipe — this is inherently project-specific, since the object graph is the project's own schema) that starts at the user row and recursively serializes every relationship that belongs to that user — orders, posts, uploaded-file records, consent history (see the cookie-consent section), audit-log entries *about* the user as `actor` (identifiers only — see the audit-logging recipe's own "ids-only" rule; the export's own copy of an audit entry still only shows `action`/`resource`/`outcome`/`ts`, never a second user's data). Reuse the same ORM relationship attributes/related-name managers the domain code already defines — a second, drifting definition of "what belongs to this user" is the same structural risk `data-export`'s recipe calls out for authorization scoping, applied here to *completeness* instead.

2. **Serialize to a machine-readable format — JSON is the default.** One JSON object per export, nested by relationship, with ISO-8601 timestamps and no binary blobs inlined (reference an uploaded file by its S3 object key/URL per the `file-upload-s3` recipe, don't inline the bytes). This is the "machine-readable" requirement Article 15/20 exports are typically read as needing — a human-readable companion (rendered HTML/PDF) is a project addition, not required by this recipe.

3. **Branch small vs. large synchronously vs. async, using the `background-jobs` recipe for the latter.** A rough row-count/size threshold on the walked graph decides: below it, serialize and return the JSON directly from the request (still authenticated, still one `audit_event` call). At or above it, dispatch a Celery task (Django track — `export_user_data_task.delay(user_id)`, per the `background-jobs` recipe's own wire-up) that builds the export, uploads it (reuse the `file-upload-s3` recipe's presigned-URL pattern if the export artifact lands in the project's private uploads bucket, or writes it to encrypted local/blob storage the app already has) and, on completion, mints a `SingleUseTokenService.issue(user_id, purpose="gdpr_export", ttl=<hours, e.g. 24-72h>)` token, builds a download link against `FRONTEND_BASE_URL` (the same pattern `AccountService.request_password_reset` uses to build its own link), and sends it via the `transactional-email` recipe's `EmailSender` — never inlining the export itself in the email body. The FastAPI track's own honest gap from the `background-jobs` recipe applies unchanged: without a real task queue vendored for FastAPI, a large synchronous export on that track is a project addition (arq or similar), not something this recipe invents.

4. **The download endpoint consumes the single-use token exactly like `AccountService.reset_password` consumes its own** — `SingleUseTokenService.consume(raw_token, purpose="gdpr_export")` returns the `user_id` on success and raises the same `InvalidSingleUseToken` on reuse/expiry/wrong-purpose; a consumed or expired link is a dead end, not a retryable one (require a fresh export request instead of a token refresh — this token authenticates *possession of the email*, not an ongoing session).

5. **Audit every export.** `audit_event("gdpr.export.requested", actor=f"user:{user_id}", resource=f"export:user:{user_id}", outcome="success")` at request time and `audit_event("gdpr.export.completed", ..., outcome="success", row_count=...)` at completion — the same shape `data-export`'s recipe already establishes for bulk access to restricted-tier data, applied to a user exporting their own full graph.

## Wire-up steps: right to erasure

1. **Gate the request behind verified identity — never accept a bare "delete my account" call on an already-authenticated session alone.** Require a fresh credential check: either a re-entered current password (`AuthService`'s existing login/`PasswordService.verify` path, called again inline) or an emailed confirmation link built the same way as the export's download link — `SingleUseTokenService.issue(user_id, purpose="gdpr_erasure_confirm", ttl=<short, e.g. 1h>)`, sent via `transactional-email`, consumed via `SingleUseTokenService.consume(raw, purpose="gdpr_erasure_confirm")`. This mirrors `AccountService.reset_password`'s posture exactly: possession of a live session is not sufficient proof of intent for an irreversible action.

2. **On confirmed request, enter a grace period — soft-delete, don't purge immediately.** Set the record's `deleted_at` via `SoftDeleteMixin.mark_deleted()` (or the project's own equivalent) rather than issuing a hard `DELETE` at request time. Send a confirmation email (via `transactional-email`) stating the grace-period end date and a cancellation link (a third `SingleUseTokenService` purpose, e.g. `"gdpr_erasure_cancel"`, or a plain authenticated "cancel" action if the account is still otherwise usable during the grace period — a project decision). `audit_event("gdpr.erasure.requested", actor=f"user:{user_id}", resource=f"user:{user_id}", outcome="success", grace_period_ends=...)`.

3. **A grace-period cancellation clears `deleted_at` and stops there** — `audit_event("gdpr.erasure.grace_period_cancelled", ...)`, no further pipeline steps run.

4. **At grace-period end, a scheduled background job (per the `background-jobs` recipe's periodic-task wire-up — `django-celery-beat` on the Django track) finalizes the erasure**, branching per record **by retention requirement, not by table name convention**:
   - **Hard-delete**: rows with no independent legal/audit/financial retention requirement and no other row's referential integrity depending on them surviving (profile fields, preferences, session/device records, uploaded files with no retention hold) — an actual `DELETE`, not a second soft-delete layer. Per `references/security/data-protection.md`'s "Retention & deletion" section: "a soft delete that never hard-deletes is not deletion" — the grace period is the *only* soft-delete stage; finalization must be a real delete for this branch.
   - **Anonymize-in-place**: rows the audit-logging trail or financial retention requires to survive with their referential shape intact — see step 5 below for exactly which rows this covers and why. Overwrite PII fields (name, email, address, free-text fields that might carry PII) with a fixed anonymized sentinel (e.g. `"erased-user-<uuid>"`, a non-routable placeholder email) while leaving the row's id, foreign keys, and non-PII structural/aggregate fields (an order's `total_amount`, a subscription's `status` history) intact. This is a **project-specific step per table** — there is no generic "anonymize any row" helper in the kit; write one anonymization function per model that needs this branch, reviewed against exactly which columns are PII for that model.
   - Every finalized row's action is audited: `audit_event("gdpr.erasure.hard_deleted", actor="system", resource=f"user:{user_id}:<table>", outcome="success")` or `audit_event("gdpr.erasure.anonymized", ..., outcome="success")` per table/record group, not just once per user — this is what lets a future audit answer "what actually happened to this row," which a single top-level "user erased" event cannot.

5. **Cross-reference `audit-logging` and Stripe/`payments-security.md` for exactly what must NOT be hard-deleted:**
   - **The audit log itself is never touched by erasure — and structurally doesn't need to be.** The `audit-logging` recipe's own design already stores `actor`/`resource` as bare identifiers (`f"user:{user_id}"`), never a PII payload — see that recipe's "ids-only rule is the whole point." Anonymizing or deleting the `users` row does not require rewriting historical audit-log rows that merely *reference* the now-anonymized user id; the audit trail's completeness ("who did what, when") survives the user's own PII being gone, by construction, not by a special-case exemption carved out here.
   - **Financial/payment records tied to a Stripe `customer`/`payment_intent`/`charge` id (per the `stripe-payments` recipe) are anonymize-in-place, never hard-deleted**, for as long as the project's own tax/accounting retention window (commonly several years, jurisdiction-dependent — a legal/finance decision, not one this recipe makes) requires the transaction record to exist. Anonymize the app's own copy of any PII field on that record (a billing name/address duplicated locally); the Stripe object IDs themselves remain, since they're opaque identifiers, not PII, and remaining necessary for reconciliation (per the `stripe-payments` recipe's own "Reconcile periodically" step) and for any legally-required financial reporting.

## Wire-up steps: cookie consent

1. **Model consent as explicit state, not an implicit "no complaint = consent."** A `ConsentRecord` (persisted for a signed-in user; a first-party cookie/`localStorage` entry for an anonymous visitor, migrated to the DB record on login) carries: a per-category boolean or tri-state (`essential` — not user-choosable, always on; `functional`, `analytics`, `marketing` — each independently choosable), the timestamp consent was given/changed, and the version of the cookie/privacy policy the choice was made against (so a policy change can invalidate stale consent and re-prompt, rather than silently keeping an outdated choice authoritative).

2. **Gate every non-essential script/tracker behind the consent state — load nothing non-essential by default.** The secure-by-default posture is opt-in, not opt-out: analytics/marketing scripts (and any third-party tracker) do not load, do not set a cookie, and do not fire an event until the relevant category's consent bit is `true`. Essential cookies (session/CSRF per the `auth` component's own double-submit-cookie transport) are never gated — they're not the category this recipe's consent model covers.

3. **Wire the gate as a React context/provider in the web block, the same shape `@repo/web-shared`'s `AuthProvider` already uses** — the kit ships no dedicated consent-management catalog component today (an honest gap, same posture as `background-jobs`'s FastAPI-task-queue gap and `file-upload-s3`'s missing Terraform module): a project adds a `ConsentProvider`/`useConsent()` alongside `AuthProvider` in its own frontend code (or, if this pattern recurs across enough projects, a future `template-author` pass could promote it into `templates/components/frontend/`). Each non-essential script/tracker's initialization call is wrapped in `if (consent.analytics) { ... }` (or deferred until the provider signals a category flipped true) rather than always running and merely hiding a banner over it — a banner that doesn't actually block the script is not a consent gate.

4. **Pairs with a future analytics recipe's own consent note — not shipped yet.** The kit's recipe catalog has no `analytics.md` today; when one is authored, its own wire-up should gate initialization behind this recipe's consent state (`consent.analytics === true`) rather than loading unconditionally. Flagging this forward reference explicitly rather than presenting an analytics recipe as already wired to it.

5. **Persist and audit consent changes for a signed-in user** (not every anonymous cookie-banner click — that would be excessive for a low-stakes UI preference): a `ConsentRecord` write on login-time migration from the anonymous cookie, and on any explicit change via account settings, is enough; this does not need an `audit_event` call (it's not a privileged/restricted-data action in the `audit-logging` recipe's own sense) unless the project's own compliance posture wants every consent change traceable — a project-specific choice, not a default requirement here.

## Limitation: backups, replicas, and third-party processors (read before shipping erasure)

**This is a documented limitation, not solved by this recipe — treat every point below as an operational and legal decision the project must make explicitly, not a gap to silently ignore:**

- **Backups and snapshots.** Per `references/security/data-protection.md`'s own "Backups" section, RDS automated backups/snapshots are a full, encrypted copy of the data at the time they were taken — this recipe's hard-delete/anonymize pass touches the *live* database only. A pre-erasure backup still contains the original PII until that backup itself ages out of its own retention window and is naturally purged. **Do not attempt to selectively edit individual rows inside an existing backup** — that's not how point-in-time snapshots work, and trying breaks their integrity as a restore target. The honest posture (commonly the position GDPR guidance itself takes on this exact tension) is: erasure is applied going forward, backups roll off on their own retention schedule, and that rolling-off window is disclosed in the project's privacy policy as part of "how long we retain your data even after an erasure request."
- **Read replicas.** A hard-delete/anonymize write on the primary propagates to replicas on ordinary replication lag (seconds, typically) — not instantaneous, and not itself a gap this recipe needs to solve, but worth confirming: don't serve a replica-backed read path (a reporting replica, a cache warmed from a replica) as if it's guaranteed erasure-consistent within the same request that finalized the erasure.
- **Third-party processors.** Any vendor the project sends user data to as a data processor — the transactional-email provider's own logs, an analytics/marketing tool the cookie-consent gate permitted before a user later withdrew consent or requested erasure, Stripe (see the erasure section's "Stripe/payments-security.md" step above — financial records legally retained, not erasable on request), an error-tracking/APM vendor that may have captured a stack trace containing a PII value — each retains data per **its own** retention policy and the project's Data Processing Agreement (DPA) with it, not per this app's own database. This recipe does not, and structurally cannot, reach into a third party's systems. A project with real GDPR exposure needs an inventory of every processor a user's data reaches (the DPA list) and a documented process — largely manual, vendor by vendor — for requesting deletion from each where the DPA provides for it. That inventory and process is **out of scope for this recipe** and is exactly the kind of posture question the `privacy-compliance` audit skill (added alongside this recipe, auditing the mechanics this recipe implements) is meant to check for on an ongoing basis — this recipe builds the mechanics; that skill audits whether they're actually in place and complete.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### GDPR data-subject rights (export, erasure, cookie consent)
- **Setup:** An authenticated "download my data" endpoint walks the user's object graph via existing model relationships and returns JSON — synchronously for a small graph, or via a background job + an expiring, single-use emailed download link (`SingleUseTokenService`, purpose `gdpr_export`) for a large one. Erasure requires a fresh identity check (password re-entry or an emailed confirmation link, purpose `gdpr_erasure_confirm`), then a grace period (soft-delete via `SoftDeleteMixin`, cancellable), then a scheduled job finalizes each record either as a hard delete or an anonymize-in-place pass — audit-log rows and Stripe-linked financial records are anonymized, never hard-deleted, per their own legal retention windows. Every step is audited (`gdpr.export.*`/`gdpr.erasure.*`). Cookie consent is explicit opt-in per category (essential/functional/analytics/marketing); non-essential scripts/trackers are wrapped so they never initialize until the relevant category's consent bit is true.
- **Secrets:** none new — reuses `FRONTEND_BASE_URL`, `SMTP_*`, and the existing single-use-token/background-job/audit-logging wiring.
- **Maintenance:** Backups/snapshots retain pre-erasure data until they age out of their own retention window (not selectively edited — disclosed in the privacy policy); third-party processors (email, analytics, Stripe, error tracking) retain data per their own DPA, not this app's DB — keep a processor inventory and a deletion-request process for each, out of this recipe's scope. Re-review anonymization field lists whenever a model gains a new PII column. **Not legal advice** — review against counsel before relying on this to meet a real regulatory obligation. See the `privacy-compliance` audit skill for the ongoing posture check this recipe's mechanics feed.
```

---
<!--
Recipe authored via the `recipe-author` skill (closes #98). Composes the
auth component's SingleUseTokenService (verify/reset-password's own
primitive, reused for export links and erasure identity-verification), the
background-jobs/transactional-email/audit-logging recipes' existing wire-up
shapes, db-mixins' SoftDeleteMixin for the grace period, and
payments-security.md/the stripe-payments recipe for the financial-retention
branch of erasure — no new infrastructure invented. The backups/replicas/
third-party-processors section is an explicit documented limitation per the
issue's acceptance criterion, not hand-waved. Cross-links the
`privacy-compliance` audit skill (added in parallel) as the audit
counterpart to this recipe's mechanics. No analytics recipe exists in the
kit yet — flagged as a forward reference in the cookie-consent section
rather than presented as already wired.
-->
