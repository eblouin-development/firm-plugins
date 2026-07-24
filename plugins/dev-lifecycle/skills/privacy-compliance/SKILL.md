---
name: "privacy-compliance"
description: "Run a whole-project privacy and regulatory-compliance posture audit — data inventory (what personal data exists, where it lives, how long it's kept), lawful-basis/consent posture, DSAR readiness (do export and erasure paths actually work?), cookie/tracker inventory, processor list, and breach-notification readiness — grounded in current regulation text fetched at audit time, never recalled. Delivers an inline, evidence-cited report and, after one confirmation, files findings as pipeline-ready GitHub issues. Use this skill WHENEVER the user asks about privacy or regulatory compliance as a whole: \"are we GDPR compliant\", \"privacy audit\", \"do we handle CCPA/CPRA right\", \"can a user actually get their data deleted\", \"do we have a cookie banner problem\", \"what personal data do we even collect\", \"are we ready for a DSAR\", \"privacy posture review\". This is explicitly NOT legal advice — it flags what needs a lawyer rather than issuing compliance verdicts. Distinct from security-audit (security, not regulatory/rights posture), code-review (per-diff, not whole-project), and the data skill (which only bans PII in seed/fixture data)."
---

# Privacy compliance

A point-in-time, evidence-based audit of the project's privacy and data-rights posture: what personal data it holds, on what legal footing, and whether the mechanics required by that footing (access, erasure, consent, breach response) actually exist and work. Same pattern as `security-audit` — inline report first, filed issues only after confirmation — but a different axis: security asks "can this be broken into," this asks "is this collection and processing lawful and rights-respecting, and can we prove it."

## Core rules

- **This is not legal advice, and the report says so up front and often.** The skill never concludes "we are compliant" or "we are non-compliant" — those are legal conclusions for a lawyer, informed by facts this audit surfaces but doesn't own. Every finding is framed as a gap against a cited regulatory text or a missing technical mechanism, with a explicit call-out of what needs counsel to close (a scoping question, a jurisdictional call, a risk-acceptance decision). Findings that hinge on interpretation ("is this a legitimate interest or do we need consent") are flagged **"needs legal review"**, not resolved.
- **Regulation text is fetched at audit time, never recalled.** Privacy law changes — new state laws, amended guidance, updated enforcement priorities — and training-data recall goes stale silently with no way to tell the user it's stale. Before assessing any surface against a specific obligation (GDPR Art. 6 lawful basis, CCPA/CPRA opt-out mechanics, a state law's DSAR timeline, etc.), fetch the current text or an authoritative current summary (official regulator sites, e.g. `gdpr.eu`, a state AG's CCPA page, `oag.ca.gov`) via web search/fetch and cite what was actually pulled. If a fetch fails or the jurisdiction is ambiguous, say so explicitly rather than falling back to memory — this is the one rule in this skill that overrides "work efficiently."
- **Evidence or it didn't happen.** Every claim — a data field found, a DSAR path confirmed working, a cookie set without consent — cites `file:line` or the concrete artifact (a request/response, a cookie name from a page load, a processor's name from config/package manifests). No speculative findings padded for volume.
- **Credit what's handled.** If export and erasure paths exist and actually delete data (not just soft-delete), if a consent banner genuinely gates trackers, if a processor list and DPAs are documented — say so with evidence. Half the value is telling the user what they don't need to worry about.
- **Read-only, always.** Never modify code or config, never submit a real DSAR against a live system, never accept/reject a cookie banner to probe it beyond what a normal read of the page/network calls reveals. Only non-mutating inspection: reading code, config, request/response shapes, and public regulation text.
- **Scale to what the project actually does.** A backend-only API with no cookies doesn't get a cookie audit; a project that collects no personal data at all gets a short report saying so, with evidence for why (no user model, no analytics, no forms) — don't manufacture findings to look thorough.
- **No silent gaps.** If a surface couldn't be assessed (no way to verify a third-party processor's actual data handling, a jurisdiction's law wasn't found), the report says so in scope, not silently omits it.
- **Public-repo disclosure guard.** Check repository visibility before filing. A detailed issue naming exactly which personal-data fields lack a lawful basis, or exactly how erasure is broken, is sensitive on a public repo — warn the user and default to redacted issues (finding title + severity + pointer, detail stays in the inline report) unless they explicitly ask for full detail filed.
- **Token-efficient breadth.** Enumerate data surfaces from models, routes, and config rather than reading the whole tree; see `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Workflow

### 1. Fingerprint the project's data footprint
Establish: does this project collect/process personal data at all (user accounts, forms, analytics, uploads)? Which jurisdictions plausibly apply (deployment region, stated user base, `.eu`/`.com` cues, any privacy policy already in the repo or linked from it) — ask the user if genuinely unclear rather than guessing a jurisdiction that changes which laws apply. Note payment or health data specifically (higher-obligation categories). This scopes which regulation texts get pulled in step 3.

### 2. Enumerate the data surfaces
Locate, by search rather than full-tree reads:
- **Data inventory** — models/tables/fields holding personal data, log statements that might capture it, upload/storage paths, analytics/tracking calls, and any retention/TTL logic (or its absence).
- **Consent & tracker surface** — anything setting cookies or loading a tracking/analytics script, and any consent-banner implementation.
- **DSAR mechanics** — existing export and delete-account/erasure endpoints or admin tooling. This is the surface the **GDPR data-rights recipe** exists to wire up (self-serve export/erasure flows) — check whether that recipe's mechanics are present and actually functional, not just a stubbed route.
- **Processor list** — third-party services receiving personal data: analytics, email/SMS providers, payment processors, hosting/CDN, error tracking. Found via config, env vars, package manifests, and integration code.
- **Breach-notification readiness** — any documented incident-response process, and whether logging/access records are sufficient to reconstruct who accessed what (a prerequisite for notifying correctly, not a notification process itself).

This enumeration doubles as the report's data-surface map.

### 3. Pull current regulation text, then assess each surface
For each applicable jurisdiction from step 1, fetch the current obligations relevant to what was found in step 2 — lawful basis and consent requirements, DSAR response-time and scope requirements, cookie/consent rules, breach-notification triggers and timelines — from an authoritative current source, and cite it. Then classify each surface: ✅ **handled** (mechanism present and evidenced), 🔴/🟠/🟡/⚪ **finding** (missing or broken mechanism, or a posture gap), **needs legal review** (facts are clear but the compliance conclusion requires a lawyer's judgment), or N/A (with a one-line reason). Cross-reference `${CLAUDE_PLUGIN_ROOT}/references/security/data-protection.md` for the *technical* how-it's-protected side (encryption, retention automation, access logging) where a finding overlaps it — that doc is the engineering baseline this audit's rights/lawfulness findings sit on top of, not a substitute for the regulatory read.

### 4. Deliver the inline report
Present in the conversation, in this shape:
1. **Not legal advice** — one line, first, every time. This report identifies facts and gaps; a lawyer determines compliance.
2. **Executive summary** — data footprint in 3–5 sentences, finding counts by severity, jurisdictions assessed.
3. **Scope** — what was assessed, what regulation text was fetched (with sources/dates), and what was skipped or couldn't be verified.
4. **Data surface map** — the enumeration from step 2.
5. **What's handled** — credited mechanisms with evidence.
6. **Findings** — severity order (🔴 critical: no lawful basis for data collected / no working erasure path for a jurisdiction requiring one; 🟠 high: partial or unverified DSAR mechanics, trackers firing pre-consent; 🟡 medium: missing processor documentation, thin breach-response readiness; ⚪ low: hardening/documentation gaps) plus a separate **needs legal review** list for anything hinging on legal interpretation.
7. **Remediation roadmap** — findings ordered by risk, noting which ones the GDPR data-rights recipe would resolve directly (DSAR/export/erasure gaps) versus which need other build work or legal sign-off first.

### 5. Confirm, then file the issues
After the user confirms (and the visibility check from Core rules passes):
- An umbrella issue **"Privacy compliance audit YYYY-MM-DD"** — posture summary, jurisdictions assessed, and a severity-ordered task list (`- [ ]`) of findings, labeled `privacy`.
- **One issue per 🔴/🟠 finding; related 🟡/⚪ findings grouped by theme**, in the `planning` skill's issue format (goal / context / steps / acceptance criteria) so each is directly buildable — pointing at the GDPR data-rights recipe by name where a finding is exactly what that recipe wires up. Labeled `privacy` plus severity, registered as a native sub-issue of the umbrella. Findings marked **needs legal review** are filed as-is (not resolved into a build task) with that label so they route to a human decision, not a build agent.
- **Do not tag `@claude`** on any of them — the user decides what to kick off and when legal sign-off is needed first.

### 6. Hand off
Share the umbrella and finding-issue links, the single highest-priority next step, which findings need a lawyer before any build work starts, and confirm nothing in the repo was modified.

## What this skill does NOT do

- Give a legal compliance verdict ("we are/aren't GDPR compliant") — it surfaces facts and gaps; findings that require legal judgment are flagged **needs legal review**, not resolved.
- Assess or harden security controls (auth, injection, secrets, infra) — that's `security-audit`; this skill only pulls in `data-protection.md` where a technical control underpins a rights/lawfulness finding.
- Review a single diff as it ships — that's `code-review`'s job, every PR; this is the whole-project, point-in-time sweep.
- Police seed/fixture data for PII — that's the `data` skill's narrow build-time rule; this is the regulatory posture of production data handling.
- Build or fix anything — export/erasure mechanics are implemented via the GDPR data-rights recipe and other build skills through the normal plan → PR → review pipeline; this skill only diagnoses.
- Submit a real DSAR, accept/reject cookie consent to probe behavior, or otherwise act against a live system — inspection only.
- Rely on memorized regulation text — every legal obligation cited is fetched and sourced at audit time.
- File issues before the user has seen the report and confirmed, or file full sensitive detail on a public repo without explicit go-ahead.
