---
name: "performance-audit"
description: "Run a thorough, whole-app performance audit — fingerprint the application, map every applicable performance surface (backend query plans/N+1s/indexes/payload sizes, frontend bundle size/Core Web Vitals/render waterfalls), credit what's already fast with evidence, identify slow paths, run a safe load-test methodology for honest capacity numbers, deliver an inline audit report, and (after one confirmation) file each finding as a scoped, pipeline-ready GitHub issue. Use this skill WHENEVER the user asks for a performance assessment of a project as a whole: \"performance audit\", \"is this app fast enough\", \"find the bottlenecks\", \"why is this slow overall\", \"can we handle N users\", \"capacity check\", \"speed up the app\" (whole-project framing, not one PR). This is the whole-codebase, point-in-time audit — distinct from code-review (which checks one diff's performance as it ships) and debugging (which chases one already-observed slow case). Strictly read-only and non-destructive: it never fixes code and never load-tests a live/production system — remediation flows through the filed issues into the normal plan → PR → review pipeline, built by the backend/frontend skills."
---

# Performance audit

A point-in-time, evidence-based performance assessment of the whole application. `code-review` checks each diff's performance as it ships; `debugging` chases a single already-observed slow case; this skill audits the accumulated whole — what's fast (credited, with evidence), what's slow (rated, reported, and filed as buildable issues), and what capacity the app actually has under load. The deliverables are an inline audit report and, after the user confirms, one scoped issue per finding so remediation runs through the normal plan → PR → review → merge pipeline.

## Core rules

- **Read-only, always.** Never modify code or config, never fix a slow query or split a bundle directly. The only mutating action this skill takes anywhere is a **safe, scoped load test against a non-production environment** the user has confirmed is safe to hit — see `${CLAUDE_PLUGIN_ROOT}/references/performance/load-testing.md`. Everything else is measurement: profilers, query plans, bundle analyzers, read-only greps and config reads.
- **Evidence or it didn't happen.** Every claim — handled *or* finding — cites `file:line`, a measured number (latency, query count, bundle size, `EXPLAIN` output), or both. No speculative findings padded for volume; no soft-pedaling a real bottleneck to be agreeable.
- **Credit what's fast.** Half the audit's value is telling the user what they *don't* need to worry about. "Handled" is held to the evidence standard in `${CLAUDE_PLUGIN_ROOT}/references/performance/perf-surfaces.md` — a measured number or a located, confirmed-wired control, not presumed from the framework.
- **Scale to the application.** Fingerprint first, then assess only the surfaces that apply. A CLI tool doesn't get audited for Core Web Vitals; an API-only backend doesn't get a bundle-size finding.
- **No silent gaps.** If a surface was never profiled, a tool isn't installed, or load testing couldn't run safely, the report says so explicitly. A capacity number presented without its caveats is worse than no number.
- **Honest capacity numbers.** A load test measures one environment under one request mix on one day — it is an estimate, not a guarantee. Report it that way, per `${CLAUDE_PLUGIN_ROOT}/references/performance/load-testing.md`.
- **Token-efficient breadth.** Whole-app scope does not mean whole-tree reads: enumerate surfaces from routes, schema, and build manifests, then read/measure the specific spans that decide handled vs. slow. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Severity scale

🔴 **Critical** — actively degrades every user now, or the app falls over under normal (not peak) load. 🟠 **High** — a clearly measurable bottleneck (multi-second query, multi-megabyte bundle, N+1 on a hot path) with real user impact. 🟡 **Medium** — a slow path with limited reach, or a missing defense-in-depth layer (no cache, no CI budget gate). ⚪ **Low** — hardening/optimization opportunity, not currently painful. ✅ **Handled** — measured and within a defensible budget, or a control present and verified. Rate by measured impact × how many requests/users hit the path, not by how large a number sounds in isolation.

## Workflow

### 1. Fingerprint the application

Establish what's being audited: layers present (backend/API, database, frontend, background workers, build pipeline — most apps are several); stack and versions (from manifests/lockfiles); the routes and pages that matter most (highest traffic, or the ones the user names); data volume (rows in the largest tables — order of magnitude matters more than an exact count); and deployment context (single instance? autoscaled? CDN in front of the frontend?). State which sections of `${CLAUDE_PLUGIN_ROOT}/references/performance/perf-surfaces.md` apply. This fingerprint scopes everything that follows.

### 2. Enumerate the performance surfaces

Instantiate the applicable taxonomy sections against *this* project: the actual hot endpoints, the largest/most-queried tables, the frontend's routes and bundle entry points, background jobs — located by search and manifest reading, not by reading the tree. The enumeration doubles as the report's surface map and the audit's checklist.

### 3. Assess each surface

For each enumerated surface, read/measure the deciding evidence and classify: ✅ Handled (measured number or located control cited), 🔴/🟠/🟡/⚪ finding (impact, evidence, remediation sketch), or N/A (one line why). Use `${CLAUDE_PLUGIN_ROOT}/references/performance/perf-checklist.md` as the per-surface check list — N+1s, missing indexes, payload sizes on the backend; bundle size, Core Web Vitals, render waterfalls on the frontend.

For Core Web Vitals (LCP, CLS, INP) specifically: these are also search-ranking signals. Note the overlap and point to the `seo` skill by name for the crawlability/ranking treatment — this audit's angle is user-experience and rendering performance, not search visibility.

### 4. Run mechanical measurements (read-only)

- **Backend:** query plans (`EXPLAIN`/`EXPLAIN ANALYZE`) for the queries backing hot endpoints; a request-count check for suspected N+1s (log or count queries for one representative request); measured response sizes for list/collection endpoints.
- **Frontend:** a bundler analyzer or the build's own size report for bundle composition; Lighthouse (or equivalent) for lab Core Web Vitals; a devtools/trace waterfall for render-blocking and sequential-fetch patterns.
- **Load test:** only against local or a dedicated staging environment the user confirms is safe to target — never production or a shared environment without explicit sign-off, and never a third-party/partner endpoint. Follow `${CLAUDE_PLUGIN_ROOT}/references/performance/load-testing.md` for the ramp methodology and how to report the resulting capacity number honestly, with its caveats. If no safe environment or tooling is available, skip this step and say so.

Record every measurement that was skipped and why — these go in the report's scope section.

### 5. Deliver the inline audit report

Present in the conversation, in this shape:
1. **Executive summary** — overall performance posture in 3–5 sentences, finding counts by severity.
2. **App profile & scope** — the fingerprint, what was measured, and *what was skipped*.
3. **Performance surface map** — the enumeration from step 2.
4. **What's fast** — credited surfaces with evidence (measured numbers or located controls).
5. **Findings** — severity order; each with impact, evidence (`file:line` or measured number), and a remediation sketch (the direction, not the implementation — that's the build skills' job).
6. **Capacity estimate** — the load-test results if run, framed as an estimate with its caveats, or a plain statement that no safe load test could be run.
7. **Remediation roadmap** — findings ordered by risk and by dependency between fixes (add the missing index before load-testing the endpoint it backs).

### 6. Confirm, then file the issues

After the user confirms:
- An umbrella issue **"Performance audit YYYY-MM-DD"** — posture summary and a severity-ordered task list (`- [ ]`) of the findings, labeled `performance`.
- **One issue per 🔴/🟠 finding; related 🟡/⚪ findings grouped by theme** to avoid issue spam. Each in the `planning` skill's issue format (goal / current state & context / step-by-step breakdown / acceptance criteria) so it is directly buildable by the `backend` or `frontend` skill, labeled `performance` plus severity, registered as a native sub-issue of the umbrella, with its number on the umbrella's checklist line so the epic reconciles when it closes.
- **Do not kick off a build on any of them.** An audit can produce a dozen issues; auto-triggering that many builds is chaos. The user picks which to build via a `coding-session` — or asks to start with the criticals, one at a time.

### 7. Hand off

The report stands delivered; share the umbrella and finding-issue links, the single highest-priority next step, and confirm nothing in the repo was modified and no live/production system was load-tested.

## What this skill does NOT do

- Modify code or config, or apply any fix — remediation goes through the filed issues into the pipeline, built by `backend`/`frontend`/the relevant build skill.
- Load-test production or any shared environment without explicit sign-off, or load-test a third-party/partner endpoint.
- File issues before the user has seen the report and confirmed.
- Kick off a build on finding issues — the user controls build kickoff.
- Replace the `code-review` performance dimension (per-diff, every PR) or `debugging` (root-causing one already-observed slow case).
- Replace `security-audit` — that skill assesses security posture (vulnerabilities, attack surface); this one assesses performance posture (speed, capacity). A surface that's both slow and insecure (e.g. an unbounded endpoint that's also a DoS vector) gets a performance finding here and a security finding there, filed independently.
- Own SEO ranking or crawlability — Core Web Vitals findings note the overlap and point to the `seo` skill by name; this audit's lane is user-experience and rendering performance.
- Present a load-test number as a guaranteed ceiling rather than an environment-specific estimate, or manufacture findings to look thorough.
