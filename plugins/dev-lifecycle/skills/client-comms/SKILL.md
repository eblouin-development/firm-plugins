---
name: "client-comms"
description: "Write client-facing communication about a project's real state — status reports, demo write-ups, plain-language release notes, and project handoff/offboarding packages. Use this skill WHENEVER the audience is the client rather than the team: \"status update for the client\", \"write the release notes\", \"summarize this sprint for the client\", \"demo write-up for the preview link\", \"hand this project off\", \"offboard this client\", \"what do we tell the client about progress\", or preparing a handover package (docs, access transfer, revocation) at the end of an engagement. It grounds every claim in the real record — merged PRs, closed issues, epic state — and never invents progress. This is client-facing writing — for in-product UI copy use `copywriting`, and for technical docs (READMEs, API refs, technical changelogs) use `documentation`."
---

# Client Comms

Write the words a client reads about their project: what shipped, what's next, what's new, and — at the end — what they're getting back. This is the outward-facing counterpart to `documentation` (which writes for engineers) and `copywriting` (which writes for end users inside the product). The reader here is a client: often non-technical, paying for the work, and deciding whether to trust the update.

The failure mode of client comms isn't being too blunt — it's being *wrong*: a status report that quietly rounds up, a release note that overclaims, a handoff that leaves the client unsure what they actually own. Trust with a client is built on the update matching reality every time, including the times reality is behind schedule.

## Core rules

- **Ground every claim in the record.** Status reports and release notes are built from merged PRs, closed issues, and epic/milestone state — not from memory or from what was *supposed* to happen. If you can't point to the issue or PR, don't claim the work. Pull the real state (`gh`/GitHub MCP) before writing a word.
- **Never inflate progress.** No "nearly done" for something still in review, no burying a slipped date, no silent scope changes. If something's behind or blocked, say so plainly along with what it takes to unblock it — clients plan around what you tell them.
- **Translate, don't dumb down.** The client doesn't need "refactored the auth middleware to use dependency injection" — they need "logins are more reliable now." Strip jargon, commit hashes, and file paths; keep the substance.
- **Match the register to the deliverable.** A status report is a briefing (shipped / next / needs a decision / risks). A demo write-up is a guided tour. Release notes are a highlight reel. A handoff is a legal-adjacent inventory — precise, complete, no surprises later.
- **Quality pass, always.** Run the draft through `humanizer` (kill hedging and AI tells) and `ruthless-edit` (cut anything not earning its place), exactly as `copywriting` does. A client update that reads like a template erodes the same trust it's meant to build.
- **Confirm before any handoff mutates anything.** Producing the handoff *package* (docs, checklists) is safe to draft freely. Actually transferring access or revoking the firm's own credentials is a real, often irreversible action — never execute it without the user explicitly confirming the specific change first. Same rule as the infra skills' confirm-before-mutate.
- **Never hand over a secret.** Handoff documents *that* credentials exist, where they live, and how to rotate them — never the credential value itself.

## Workflow

### 1. Identify the deliverable and pull the real record
Which of the four below, and for what period/milestone/release. Then gather ground truth before drafting anything:
- Merged PRs and closed issues since the last update (`gh pr list --state merged`, `gh issue list --state closed`, or the GitHub MCP equivalents), scoped to the relevant date range or milestone.
- Epic/milestone state for the "what's next" and "what's blocked" sections.
- The technical changelog, if release notes are the ask — it's the source, not something to re-derive from git log.

Work from this scoped set of PRs/issues, not the whole repo history — see `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

### 2. Write to the deliverable

**Status report** — periodic progress summary for a non-technical stakeholder:
- *Shipped since last update* — plain-language description of each merged item, each one linked to its issue/PR.
- *In progress / next* — what's actively being worked, grounded in open issues, not aspiration.
- *Decisions needed from the client* — anything blocked on their input, stated as a specific question, not a vague FYI.
- *Risks / timeline* — honest note on anything at risk of slipping, with why and what it takes to fix. Silence here is the most common way status reports mislead.

**Demo write-up** — accompanies a preview/beta link:
- What's live at the link, in the order a first-time viewer should look at it.
- What to try, framed as actions ("click X to see Y"), not a feature list.
- What's intentionally not finished yet, so rough edges don't read as bugs.
- How to leave feedback.

**Client release notes** — derived from the technical changelog (keep-a-changelog or equivalent):
- Group by user-visible impact (new, improved, fixed), not by technical category.
- One line per item, plain language, no commit hashes, no internal file/module names, no jargon left unexplained.
- If a changelog entry has no user-visible effect (internal refactor, dependency bump, dev tooling), leave it out — a release note is for the client, not a mirror of `CHANGELOG.md`.

**Handoff / offboarding** — the closing package when a project transfers to the client:
- *Docs handover* — an aggregated, client-readable README/runbook (what the system is, how to run/deploy it, where things live) plus a credentials/secrets *inventory*: what secrets exist, what they're for, where they're stored, how to rotate them — names and locations only, never values.
- *Access-transfer checklist* — every repo, cloud account, domain/DNS, and third-party service (billing, analytics, email, etc.) the client needs to end up owning, with the concrete transfer step for each (e.g., "transfer GitHub repo ownership to `<org>`", "add client as billing admin on `<provider>`").
- *Revocation checklist* — every credential and access grant the firm itself holds that should be removed once the client confirms they've taken over: collaborator access, API keys issued to the firm, service accounts, deploy keys.
- Draft all three as documents freely. Before running any actual access change or revocation, list the specific actions and get explicit confirmation from the user — then execute only the confirmed ones.

### 3. Quality pass
Run `humanizer` and `ruthless-edit` on the draft: cut hedging, throat-clearing, and anything that sounds like a template filled in rather than someone reporting real work. Read it as the client would — if a claim would raise an eyebrow ("wait, is that actually true?"), verify it against the record again or cut it.

### 4. Hand off
Deliver the artifact and state what it's grounded in (the PR/issue range, milestone, or changelog version it was built from) so the client-facing claims are auditable later. For a handoff package, list any access-transfer or revocation actions that still need explicit confirmation before they're executed.

## How this works with the other skills
- **documentation** owns the technical changelog and internal docs; this skill translates the changelog into client release notes and aggregates docs into a handover package — it doesn't originate technical content.
- **copywriting** owns in-product UI copy for end users; this skill owns comms *about* the project, sent outside the product.
- **planning / product-planning / coding-session** produce the epics, issues, and PRs this skill reports on — it reads their output, it doesn't create work items.
- **infrastructure / devops** hold the actual access and deploy mechanics; a handoff's access-transfer and revocation steps are executed there, under the same confirm-before-mutate rule, once this skill has drafted the checklist.

## What this skill does NOT do
- Send or deliver anything itself — no email, no Slack, no posting. It produces the written artifact; a human or another tool sends it.
- Write in-product UI copy (`copywriting`) or technical documentation (`documentation`).
- Execute any access transfer or credential revocation without the user's explicit confirmation of that specific change.
- Hand over credential values, ever — only that they exist, where, and how to rotate them.
- Invent progress, dates, or client-facing claims not backed by real repo state.
