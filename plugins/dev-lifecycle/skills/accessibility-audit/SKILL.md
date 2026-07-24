---
name: "accessibility-audit"
description: "Run a thorough, whole-project WCAG 2.2 AA accessibility audit — fingerprint the UI surfaces, map semantics/landmarks, keyboard paths, focus management, contrast (against the design-system tokens), forms/errors, and media alternatives, credit what's already handled with evidence, run automated checks (axe) plus the manual checks automation can't do, deliver an inline audit report, and (after one confirmation) file each finding as a scoped, pipeline-ready GitHub issue. Use this skill WHENEVER the user asks for an accessibility assessment of a project as a whole: \"accessibility audit\", \"a11y audit\", \"is this WCAG compliant\", \"can screen reader users use this\", \"check our contrast/keyboard support\", \"are we ADA compliant\", \"audit this for accessibility\". This is the whole-codebase, point-in-time audit — distinct from `frontend`/`mobile`/`design-system` (which build accessibility in as they ship) and `code-review` (which checks one diff as it ships). Strictly read-only: it never fixes markup or styles and never runs exploits — remediation flows through the filed issues into the normal plan → PR → review pipeline."
---

# Accessibility audit

A point-in-time, evidence-based WCAG 2.2 AA assessment of the whole project. `frontend`, `mobile`, and `design-system` build accessibility in as UI ships; this skill audits the accumulated whole — what's already accessible (credited, with evidence), and what's open (rated, reported, and filed as buildable issues). The deliverables are an inline audit report and, after the user confirms, one scoped issue per finding so remediation runs through the normal plan → PR → review → merge pipeline.

## Core rules

- **Read-only, always.** Never modify markup, styles, or config, and never run anything that mutates state. The only actions are reading code, running an automated scanner (axe) against a locally-rendered or static build in a read-only pass, and grepping/reading config. This makes the audit safe on any repo, including guest repos (`onboarding`).
- **Evidence or it didn't happen.** Every claim — handled *or* finding — cites `file:line` (component/template/screen) and the WCAG success-criterion number, per `${CLAUDE_PLUGIN_ROOT}/references/accessibility/wcag-checklist.md`. No speculative findings padded for volume; no soft-pedaling a real barrier to be agreeable.
- **Credit what's handled.** Half the audit's value is telling the user what they *don't* need to worry about. "Handled" means the control is located and confirmed wired in — a landmark that's actually present, a label that's actually associated, a contrast pair that actually computes to a pass — not presumed from the framework or component library.
- **Scale to the application type.** Fingerprint first, then assess only the surfaces that apply. A CLI tool or headless API doesn't get audited for contrast; a component library without app screens gets audited component-by-component rather than flow-by-flow.
- **No silent gaps.** If axe isn't installed, a surface couldn't be rendered to scan, or a flow needs a screen reader walk that wasn't possible in this environment, the report says so explicitly. A report that hides its own blind spots is worse than none.
- **Report first, one confirmation, then issues.** The user sees the full findings inline before anything is written to the repo. Never file issues before that confirmation.
- **Token-efficient breadth.** Whole-project scope does not mean whole-tree reads: enumerate surfaces from the route table, screen/page list, and component inventory, then read the specific spans that decide handled vs open. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Severity scale

🔴 **Blocker** — a user relying on assistive tech or keyboard cannot complete a core task at all (unreachable control, keyboard trap, unlabeled required input on checkout/auth). 🟠 **Serious** — the task is completable but significantly harder or error-prone (poor focus order, ambiguous error text, sub-AA contrast on body text). 🟡 **Moderate** — a real WCAG AA failure with a workaround or narrow reach (missing skip link, non-ideal heading order). ⚪ **Minor** — hardening / best-practice, not a conformance failure (missing `aria-label` on a redundant icon that has adjacent visible text). ✅ **Handled** — control present and verified. Rate by user impact × how many people it blocks, not by which WCAG bucket looks more official.

## Workflow

### 1. Fingerprint the application
Establish what kind of UI is being audited: surface type(s) — web frontend (SPA/server-rendered), mobile app (React Native/Expo), component/design-system library, marketing site; most projects are more than one. Identify the framework and its accessibility primitives (semantic HTML vs. custom component kit, RN's `accessibilityRole`/`accessibilityLabel`), whether a design-system token doc exists (`design-system` skill's output — theme file, tokens, or `docs/design-system.md`), and whether the project has any existing a11y tooling (`eslint-plugin-jsx-a11y`, `axe-core`, RN's built-in accessibility checks). State which sections of `${CLAUDE_PLUGIN_ROOT}/references/accessibility/wcag-checklist.md` apply. This fingerprint scopes everything that follows.

### 2. Enumerate the surfaces
Build the audit's checklist from the route table / screen list / page directory and the component inventory — located by search, not by reading the tree. For each: what it's for, whether it's a primary user flow (auth, checkout, core task) or secondary, and which WCAG categories apply (a static content page doesn't need a forms check; a settings screen does). This enumeration doubles as the report's surface map.

### 3. Assess each surface
For each enumerated surface, read the deciding markup/styles and classify against `${CLAUDE_PLUGIN_ROOT}/references/accessibility/wcag-checklist.md`'s six categories (semantics/landmarks, keyboard paths, focus management, contrast, forms/errors, media alternatives): ✅ Handled (evidence cited), 🔴/🟠/🟡/⚪ finding (impact, evidence, WCAG criterion, remediation sketch), or N/A (one line why). For contrast, check computed values against the design-system's token pairings where they exist; fall back to computed hex values and cite them directly when no token doc exists — and note the gap as a `design-system` follow-up, not an accessibility finding.

### 4. Run automated checks (read-only)
- **axe:** run `axe-core` (via its CLI, `@axe-core/cli`, or a Playwright/Puppeteer integration already in the project) against a local dev build or static render, read-only — no state-mutating interactions beyond page loads. Fold violations in by surface.
- **Static lint:** if `eslint-plugin-jsx-a11y` (or RN equivalent) is configured, its existing lint output is another automated source — don't newly install or reconfigure it as part of the audit.
- **Manual walk:** for each primary flow, do the checks automation can't — tab through the flow keyboard-only and confirm order/visibility/traps; confirm focus lands correctly on modal open/close and route change; read forms and errors for whether the *content* (not just presence) is meaningful. Note in the report which surfaces got a manual walk and which didn't (and why, e.g. requires auth state that couldn't be reached read-only).

Record every check that was skipped and why — these go in the report's scope section.

### 5. Deliver the inline audit report
Present in the conversation, in this shape:
1. **Executive summary** — overall conformance posture in 3–5 sentences, finding counts by severity.
2. **App profile & scope** — the fingerprint, what was assessed, and *what was skipped*.
3. **Surface map** — the enumeration from step 2.
4. **What's handled** — credited controls with evidence.
5. **Findings** — severity order; each with impact, evidence (`file:line`), WCAG success-criterion number, and a remediation sketch.
6. **Remediation roadmap** — findings ordered by user impact and by dependency between fixes (fix the keyboard trap before polishing its focus ring).

### 6. Confirm, then file the issues
After the user confirms:
- An umbrella issue **"Accessibility audit YYYY-MM-DD"** — posture summary and a severity-ordered task list (`- [ ]`) of the findings, labeled `accessibility`.
- **One issue per 🔴/🟠 finding; related 🟡/⚪ findings grouped by theme** (e.g. all missing-alt-text instances as one issue) to avoid issue spam. Each in the `planning` skill's issue format (goal / context / steps / acceptance criteria) so it is directly buildable, labeled `accessibility` plus severity, registered as a native sub-issue of the umbrella, with its number on the umbrella's checklist line so the epic reconciles when it closes.
- **Do not tag `@claude` on any of them.** An audit can produce a dozen issues; auto-triggering that many builds is chaos. The user picks which to kick off — or asks to tag specific blockers, one at a time.

### 7. Hand off
The report stands delivered; share the umbrella and finding-issue links, the single highest-priority next step, and confirm nothing in the repo was modified.

## Boundaries

- **vs. `security-audit`:** that skill covers exploitable security vulnerabilities (auth, injection, exposed secrets); this skill covers whether people — including those using assistive tech — can actually use the product. No overlap; a security audit and an accessibility audit of the same project produce disjoint findings.
- **vs. `code-review`:** that skill checks one diff's accessibility as it ships (a PR-sized gate, run on every change); this skill is the whole-project, point-in-time sweep that catches what accumulated before the gate existed or slipped through it.
- **vs. `frontend` / `mobile` / `design-system`:** those skills build accessibility in from the start (semantic HTML, `accessibilityRole`/labels, token-level contrast) and are where every filed finding gets fixed. This skill never edits markup, styles, or components — it only finds and files.

## What this skill does NOT do

- Modify markup, styles, config, or apply any fix — remediation goes through the filed issues into the pipeline.
- Run anything beyond read-only page loads and existing lint/scan tooling — no fuzzing, no destructive interaction, nothing against a production environment without the user's own read-only access already in place.
- File issues before the user has seen the report and confirmed.
- Tag `@claude` on finding issues — the user controls build kickoff.
- Replace the accessibility work already built into `frontend`/`mobile`/`design-system`, or the `code-review` gate that checks each diff — this is the whole-project sweep those lanes don't cover.
- Manufacture findings to look thorough, hide its own blind spots, or bury a real barrier.
