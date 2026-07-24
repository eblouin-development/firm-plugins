---
name: "repo-audit"
description: "Run a whole-repository, all-dimensions analysis in one pass — security, performance, accessibility, privacy, SEO, code quality, and dependency health — by fingerprinting the repo, fanning out across the applicable specialist audit skills as subagents, and rolling their findings into a single prioritized, actionable report. Can target ANY repository available in the session, including a guest repo added via `add_repo`. Use this skill WHENEVER the user wants a full picture of a project's health rather than one dimension of it: \"audit this whole repo\", \"give me a full health check on this project\", \"what's wrong with this codebase overall\", \"run every audit on this\", \"is this repo in good shape\", \"assess this project before we take it over\", \"full analysis pass on this before launch\". It also offers to drive a live frontend URL with Playwright for a real accessibility/SEO/Core-Web-Vitals/console-error pass when one is available, and degrades cleanly to static-only otherwise. This is the capstone across the individual `*-audit` skills — distinct from `code-review` (one diff), any single `*-audit` skill (one dimension), and `walkthrough` (comprehension, not findings). Strictly read-only: it never fixes code and never probes a live system beyond passive checks — remediation flows through filed issues, and even those are gated on one confirmation."
---

# Repo audit

A whole-repository, all-dimensions analysis, delivered as one report. Where each `*-audit` skill goes deep on a single dimension and `code-review` guards a single diff, `repo-audit` is the conductor: it fingerprints the repository, fans out across every dimension that applies, and rolls the results into one prioritized picture of where the project stands. It mirrors `coding-session`'s orchestration pattern — a lean conducting thread that dispatches subagents and collects their verdicts — but for read-only analysis instead of a build.

## Core rules

- **Read-only, always.** This skill never modifies code or config, never fixes a finding, and never runs exploits, load, or anything state-mutating against a live system — live-frontend checks are passive (page loads, DOM inspection, network timing), never form submissions, auth attempts, or write actions. Every lane it dispatches inherits this constraint from its own skill.
- **Fingerprint before fanning out.** Detect what the repo actually is before deciding what to run — see Workflow step 1. An audit that runs every lane regardless of relevance wastes tokens and buries the report in N/A sections; an audit that silently skips a lane that *did* apply hides risk. Neither is acceptable.
- **No silent omission.** The report states which lanes ran, which were skipped, and why, in one place — see Workflow step 4's scope section. This is inherited from `security-audit`'s "no silent gaps" rule, extended from one dimension to all of them.
- **Orchestrate, don't reimplement.** Each dimension already has an owner — `security-audit`, `performance-audit`, `accessibility-audit`, `privacy-compliance`, `seo` (audit mode), `dependency-maintenance`, and `code-review` for cross-codebase quality/DRYness. This skill's job is fingerprinting, briefing, dispatch, and synthesis — not re-deriving OWASP checklists or WCAG criteria inline. Depth lives in the lane skill; breadth and prioritization live here.
- **Token-efficient breadth.** Whole-repo, all-dimension scope is the most token-hungry shape this plugin runs — spawn each lane as its own subagent with a focused brief so its reading dies with it, per `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`. The conducting thread holds the fingerprint, the lane briefs, and the collected verdicts — never the underlying file reads.
- **Guest repos work read-only.** A repo added via `add_repo` (per `onboarding`'s guest mode) can be fully audited — every lane here is read-only by construction. Only step 6 (filing issues) needs a writable repo, and that's gated on confirmation regardless.
- **Report first, one confirmation, then issues.** Same contract as `security-audit`: the user sees the whole report before anything is written back to any repo.

## Workflow

### 1. Fingerprint the repo

Before dispatching anything, establish what's being audited — this scopes every lane that follows:

- **Target.** Which repo (this session's own, or one named/added via `add_repo`)? If it's a guest repo, confirm read-only mode explicitly with the user up front so there's no ambiguity about issue-filing later.
- **Shape.** Frontend present? Backend/API present? Mobile app? CLI/library only? Infra/IaC? Most repos are several at once. This directly gates lane applicability (step 2).
- **Stack.** Languages, frameworks, package managers — from manifests, not assumption. Each lane subagent needs this in its brief so it doesn't re-derive it.
- **Scale signal.** Rough size (file count, LOC, or `git log` age/activity) — informs how much breadth each lane subagent should budget for, and whether this repo is a one-pass or a "warn the user this is big" case.

### 2. Decide which lanes apply

Map the fingerprint to lanes, and don't run a lane that plainly doesn't fit:

| Lane | Skill | Runs when… |
|---|---|---|
| Security | `security-audit` | Always — every repo has *some* attack surface (even a CLI has supply-chain and secrets exposure). |
| Code quality / DRYness | `code-review` | Always — brief it for whole-codebase quality, not a diff (see step 3's note on this lane). |
| Dependencies | `dependency-maintenance` | Always — any repo with a manifest (`package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, …). Skip only if genuinely dependency-free. |
| Performance | `performance-audit` | Repo has a backend and/or a frontend to profile. Skip for a pure library/CLI with no runtime service surface — note why. |
| Accessibility | `accessibility-audit` | Repo has a UI surface (web frontend, server-rendered templates, mobile). Skip for a headless API/CLI/library. |
| Privacy/compliance | `privacy-compliance` | Repo handles personal data in any form (user accounts, forms, analytics, cookies). Skip for a repo with no user data surface (e.g. an internal CLI tool) — note why. |
| SEO | `seo` (audit mode) | Repo serves public, indexable web pages. Skip for internal tools, APIs, or authenticated-only apps. |

State this table, filled in for the actual repo, as part of the report's scope section (step 4) — this *is* the "no silent omission" contract from Core rules.

### 3. Dispatch each applicable lane as a subagent

For each lane that applies, spawn a subagent briefed to invoke that lane's skill against this repo, in read-only/report-only mode (no issue-filing from inside the lane — this orchestrator files, once, at the end). Dispatch under the same worker-cadence discipline `coding-session` uses for build steps — background dispatch with a right-sized watchdog, not a blocking wait (`${CLAUDE_PLUGIN_ROOT}/shared/worker-cadence.md`).

Brief each subagent with: the repo/path (and guest-mode note if applicable), the fingerprint facts relevant to its lane, and an explicit instruction to **stop at its own report** — return findings to the conductor, not file anything itself. Ask it to return: findings (severity, evidence, remediation sketch — matching that lane's own severity scale), what it credited as already handled, and what it couldn't assess and why.

One lane needs a slightly different brief than its solo invocation:

- **`code-review` for whole-codebase quality.** `code-review`'s native unit is a diff. Brief this subagent explicitly to assess the codebase as a whole for correctness risk, DRYness/duplication, and structural quality — not to review a specific change — and to report findings in the same evidence-cited, file:line style the other lanes use.
- **`dependency-maintenance` for audit-only.** `dependency-maintenance` is a remediation skill by charter — it can plan and apply upgrades and fix CVEs. Brief this subagent to inventory outdated/vulnerable packages and report only — no upgrades applied, so the lane holds this skill's read-only guarantee like every other.

Independent lanes can run concurrently since they only read the repo. If the whole-repo scale signal from step 1 flagged the repo as large, consider batching lanes (e.g. security + deps first, then the rest) rather than firing all seven subagents at once, to keep the conductor's watchdog manageable.

### 4. Offer the live-frontend check

If step 1 found a frontend, **offer** to check the live site directly (don't assume — ask): "Do you have a working URL — a deployed site or a local dev server — I can drive with a browser for a real check?"

- **If given a URL:** use Playwright/Chromium (available in-session) to drive it, passively, and produce:
  - An `axe-core` accessibility pass against the rendered page (distinct from `accessibility-audit`'s own axe pass, which runs against a local dev build/static render — this one is the deployed page, real fonts/CDN/CSP and all).
  - Rendered `<head>`: meta description, OG/Twitter tags, canonical, and structured data (JSON-LD) as the browser actually sees them post-render — this catches CSR pages where the static source has none of this but the rendered DOM does (or vice versa).
  - Core Web Vitals / Lighthouse-style signals available from the browser (LCP, CLS, TTFB-equivalent, main-thread timing) — label these as approximate, single-run signals, not a lab-grade Lighthouse report.
  - A broken-link and console-error sweep of the page(s) checked.
  - Fold these into the accessibility and SEO sections of the report, each finding tagged **[live]**.
- **If no URL is given (or no frontend at all):** say so plainly in the report's scope section and proceed static-only. Every finding from the `accessibility-audit` and `seo` lanes in that case is implicitly static — tag them **[static]** in the report so the two sources are never conflated.

This check is the orchestrator's own addition — it is not a lane subagent, since it needs the live browser session in the conducting context. Keep it scoped to what the user offers access to; never guess at or scan a URL the user didn't provide.

### 5. Synthesize the report

Collect every lane's findings and the live-check results (if run) into **one** report, in this shape:

1. **Executive summary** — overall project health in a few sentences, finding counts by severity across all dimensions combined.
2. **Repo profile & scope** — the fingerprint (step 1), the lane table with run/skipped-and-why (step 2), and live vs. static-only status for the frontend check (step 4).
3. **Findings by dimension** — one subsection per lane that ran, each internally severity-ranked, each finding with evidence (`file:line`, or the live URL + what was observed for live-check findings), impact, and a concrete recommended fix. Preserve each lane's own severity scale rather than inventing a new one — a `security-audit` 🔴 and a `performance-audit` finding are rated on different axes and shouldn't be silently flattened into one.
4. **What's already handled** — the credited controls/practices each lane reported, so the user knows what *not* to worry about. This is worth as much as the findings list.
5. **Prioritized "do this next"** — a single cross-dimension ordered list, not per-lane lists stapled together. Weigh true severity and blast radius over which lane produced the finding (a 🟠 security finding usually outranks a ⚪ SEO one regardless of section order), and call out dependencies between fixes.

Present this inline. Offer — don't default to — a published artifact version for a shareable copy, same as any other audit deliverable in this plugin.

### 6. Confirm, then file issues

After the user sees the full report, offer (one confirmation) to file the confirmed findings as scoped, pipeline-ready GitHub issues, mirroring `security-audit`'s pattern:

- Only proceed if the target repo is writable (not a guest repo in read-only mode — if it is, say so and stop here; the user can still take the report to a repo they can write to).
- An umbrella issue **"Repo audit YYYY-MM-DD"** with the executive summary and a dimension-grouped task list (`- [ ]`) of the findings.
- One issue per high-severity finding across any dimension; related lower-severity findings grouped by theme within their dimension, to avoid issue spam — each in `planning`'s issue format (goal / context / steps / acceptance criteria) so it's directly buildable, labeled by dimension (`security`, `performance`, `accessibility`, `privacy`, `seo`, `quality`, `dependencies` as applicable) plus severity, registered as a native sub-issue of the umbrella.
- **Do not tag `@claude`** on any filed issue — the user picks which findings to kick off, same rationale as `security-audit`.
- If the target is a public repo and any security finding is detailed enough to be a disclosure risk, apply `security-audit`'s public-repo disclosure guard before filing that one.

### 7. Hand off

Share the report (and artifact link if published), the umbrella and finding-issue links if filed, the single highest-priority next step, and confirm nothing in the repo was modified — including on a guest repo, where this is the whole point of having run it.

## What this skill does NOT do

- Fix, patch, or refactor anything — every fix flows through a filed issue into the normal `planning` → build → `code-review` → merge pipeline.
- Run exploits, load tests, credential attacks, or any mutating/write action against a live site — the live-frontend check in step 4 is strictly passive browsing.
- Re-implement a lane's own methodology — it dispatches `security-audit`, `performance-audit`, `accessibility-audit`, `privacy-compliance`, `seo`, `dependency-maintenance`, and `code-review`, and trusts each to own its depth.
- Review a single diff or PR — that's `code-review`'s job; this skill is whole-repository and point-in-time.
- Explain how code works without judging it — that's `walkthrough`; this skill always produces findings, not just comprehension.
- File any issue before the user has seen the full report and confirmed, or file into a repo that isn't writable.
- Guess at or scan a live URL the user didn't explicitly provide.
