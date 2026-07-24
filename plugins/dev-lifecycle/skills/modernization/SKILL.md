---
name: "modernization"
description: "Migrate an EXISTING repository you OWN onto the monorepo starter kit — assess the legacy app against the kit's catalog (keep/wrap/replace per part, honest about what has no counterpart), plan a staged strangler-fig migration filed as a GitHub epic + stage issues, then orchestrate each stage through the normal plan → PR → review → human-merge pipeline while verifying parity (tests green before and after every stage). Use this skill WHENEVER the user wants to bring an old or legacy app onto the firm's kit without a rewrite: \"modernize this repo\", \"migrate this app onto the starter kit\", \"move this onto the monorepo template\", \"strangler-fig this codebase\", \"adopt the kit in our existing app\". This is the third leg of the intake triangle: `onboarding` conforms to an existing repo as-is and composes nothing; `scaffolding` composes the kit but only for new/empty repos; `modernization` is the only path that moves an existing OWNED app's code onto the kit, and only incrementally — it never hand-builds a stage itself, it hands each one to the normal build pipeline."
---

# Modernization

Move an existing app you own onto the monorepo starter kit without ever breaking it. The app must run at every stage — there is no cutover weekend, no big-bang rewrite, no branch that sits unmerged for months drifting from `main`. This skill's job is narrow and specific: assess the legacy app against the kit's catalog, turn that assessment into an ordered sequence of small, reversible stages, and then drive each stage through the pipeline that already exists — `planning` scopes it, a build skill implements it, `code-review` takes it to merge-ready, a human merges it. Modernization orchestrates; it does not build.

The temptation with any "let's modernize this" effort is to treat it as license to rewrite everything the new way. Resist that. Some parts of a legacy app map cleanly onto a kit block or catalog component and should move. Some parts have no kit counterpart at all — a bespoke reporting engine, a quirky integration, a data model shaped by years of real usage — and those stay exactly as they are, with the seam to the kit documented so the next person knows why that boundary exists. A part earns migration by mapping to something the kit already ships better; nothing gets rewritten just because a newer pattern exists.

## Core rules

- **Owned repos only.** This skill migrates code — that requires committing infrastructure and opening PRs against the default branch. If ownership isn't confirmed, this isn't your skill: hand off to `onboarding` (guest mode), which conforms to the repo as-is and commits nothing.
- **Strangler-fig, not big-bang.** The app must be deployable and correct after every single stage, not just at the end. If a stage can't stand on its own — the app broken or half-wired in between — split it further until it can.
- **One stage, one PR.** Never migrate more than one stage per PR. A stage that turns out bigger than one reviewable PR gets split into further stages, not squeezed into one.
- **Verify parity, don't assume it.** Before a stage starts, capture what "working" means (the existing test suite, plus any manual checks the legacy app relies on). After the stage's PR is built, confirm the same tests are green and behavior hasn't drifted. A migration that trades a passing suite for a faster rewrite has failed at the one thing it promised.
- **Map honestly.** Every part of the legacy app gets a keep, wrap, or replace verdict against the kit's catalog — never a default "replace." A clean kit counterpart earns "replace." Something close but not quite earns "wrap" (adapt it to the kit's contract without a rewrite). Something with no kit shape at all earns "keep," with the seam written down.
- **Orchestrate, don't hand-build.** This skill never writes the migration code itself. Each stage is scoped by `planning`, built by the relevant build skill (`backend`, `frontend`, etc.), and reviewed by `code-review`, exactly as any other piece of work would be. What this skill owns is the assessment, the staging, the sequencing, and the parity check around each stage.

## Workflow

### 1. Assess

Inventory the legacy app before proposing anything:
- **Stack and versions** — languages, frameworks, package manager, runtime versions, from manifests/lockfiles rather than reading the tree (see `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`).
- **Structure** — how the app is laid out (monolith, loose services, a single package), where the boundaries between concerns already are.
- **Test coverage and deploy story** — what tests exist and how they're run, how the app currently ships (CI, manual, none). This becomes the parity baseline every later stage is checked against.

Map each significant part — the repo shape/tooling, cross-cutting concerns (settings, error handling, auth, security headers), and each functional area — against the kit's catalog (`${CLAUDE_PLUGIN_ROOT}/templates/` blocks and components, `${CLAUDE_PLUGIN_ROOT}/references/recipes/`). Give each part one verdict:
- **Replace** — a kit block/component/recipe covers this cleanly; migrating onto it is a net win.
- **Wrap** — close but not exact; adapt the existing code to the kit's contract (e.g., its composition `needs`/`exposes`) rather than rewriting it from scratch.
- **Keep** — no kit counterpart, or the existing implementation is genuinely better suited to this app. Document the seam: what it is, why it stays, and how it interfaces with whatever kit pieces surround it.

Present the inventory and verdicts before proposing stages — this is the evidence the staging plan rests on.

### 2. Plan

Turn the verdicts into an ordered set of stages using strangler-fig sequencing: the app works at the end of every stage, and each stage is small enough to land as one PR. The default order, highest leverage first:
1. **Repo shape and tooling** — adopt the kit's workspace layout, package manager, `justfile` task surface, and CI shell around the existing code, without touching app logic yet. This is what makes every later stage cheaper.
2. **Cross-cutting components** — settings/config, error envelope, security baseline, and similar catalog components that many later stages will depend on.
3. **Block-by-block adoption** — one functional area at a time, following the keep/wrap/replace verdicts from step 1. Order by risk and leverage: low-risk, high-leverage wins first; anything touching auth or data migrations gets its own stage, sequenced deliberately, never bundled with unrelated changes.

File this as a GitHub epic + stage sub-issues using the **existing `product-planning`/`planning` machinery** — don't reinvent issue filing here. Concretely: run (or hand off to) `product-planning`'s step 4 to record the epic (vision = "migrate `<app>` onto the starter kit", the staged roadmap as a checklist, one milestone per stage), then `planning` per stage to flesh out each stage's own implementation plan and file it as a sub-issue linked back with the `Epic: #<n>` marker and its number on the epic's checklist line — the same mechanics `epic-checkoff` already relies on. This is what makes epic-checkoff work for a migration exactly as it does for a greenfield roadmap.

### 3. Execute

Advance one stage at a time. For each stage:
1. **Capture the parity baseline** — run the existing test suite (and any manual checks noted in the assessment) and confirm it's green before the stage starts. If it isn't already green, that's a pre-existing issue to flag, not something to fold into this stage's diff.
2. **Hand the stage to the pipeline** — the stage's issue goes through the normal loop: `planning` (if not already fully scoped), a build skill implements it as commits on a branch, `code-review` takes it to merge-ready. Modernization does not write the migration code itself.
3. **Verify parity after** — the same tests (plus the stage's own new coverage) must be green on the resulting PR. If a stage is genuinely unable to preserve behavior 1:1 (a deliberate, agreed-on change), that must be called out explicitly in the PR, not discovered later as an accidental regression.
4. **One PR per stage, then stop and hand back to the human merge gate** — same as any other pipeline PR, per `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`. Move to the next stage only after this one has merged.

### 4. Hand off

After each stage merges, report which stage completed, that parity held, and what the epic's remaining stages are. When the epic's checklist is fully ticked, summarize the full migration: what moved onto the kit, what was deliberately kept as-is and why (the documented seams), and the app's current state relative to the kit's conventions.

## What this skill does NOT do
- Migrate a repo you don't own — that's `onboarding` (guest mode), which leaves no footprint and composes nothing.
- Scaffold a brand-new or empty repo — that's `scaffolding`; modernization exists specifically for an app with real code and history already in it.
- Rewrite a part of the app for its own sake. A part with no clean kit mapping stays as-is with the seam documented, not forced onto the kit.
- Migrate more than one stage in a single PR, or start a new stage before the current one has merged and held parity.
- Hand-build any stage itself — every stage's implementation runs through `planning` and the build skills, exactly like any other pipeline work.
- Kick off a build or file anything without going through the existing `product-planning`/`planning` issue-filing machinery.
