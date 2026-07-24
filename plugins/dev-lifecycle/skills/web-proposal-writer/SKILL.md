---
name: "web-proposal-writer"
description: "Write the persuasive, client-facing sales proposal for a website/app build — problem framing in the client's language, the recommended approach, what's included and excluded, timeline, investment framing, and a clear next step. Use this skill WHENEVER the work is winning the client's yes on a build: \"write the proposal for this client\", \"turn this into something I can send the client\", \"pitch this website build\", \"turn our quote into a proposal I can send\", \"make this sound compelling for the client\", \"proposal for the redesign we quoted\". It takes an approved or draft technical-proposal plus client context as input and runs a humanizer + ruthless-edit pass, same as copywriting. This is the external sales pitch — for the internal engineering decision (stack, architecture, cost/timeline honestly estimated) use technical-proposal instead, and for in-product UI/microcopy use copywriting instead. Produces markdown with optional docx export."
---

# Web proposal writer

Turn an engineering decision into a client's yes. `technical-proposal` answers *should we build this and how* for an internal audience; this skill takes that answer and makes the case to the person paying for it — in their language, around their priorities, ending in a clear next step. It's persuasion built on real substance, not marketing built on nothing: every claim it makes has to trace back to the technical proposal or stated client facts.

## Core rules

- **Persuade with what's true.** The proposal's job is to make the real plan compelling, not to invent a better one. Reframe, prioritize, and simplify for the client; never claim a capability, timeline, or outcome the technical proposal doesn't support.
- **Never fabricate social proof.** No invented testimonials, client logos, case-study numbers, or "trusted by" claims. If the firm has real proof points, use them; otherwise leave an explicit placeholder (e.g. `[case study: similar project, link]`) and flag it — a placeholder that's obviously a placeholder beats a number that looks real but isn't.
- **Don't re-decide the engineering.** Stack, architecture, and the cost/timeline math are `technical-proposal`'s job. This skill translates and frames those decisions; it doesn't second-guess or re-derive them. If something looks wrong, flag it back rather than silently changing it.
- **Speak the client's language, not the build's.** Lead with the client's problem and outcome, not framework names and layer diagrams. Technical detail earns its place only where it answers a client concern (security, scale, ownership of the code).
- **It's a proposal, not a contract.** No binding terms, liability language, payment schedules, or legal SOW content — that's a separate document a human (or a legal-review flow) produces. This skill stops at "here's what we'd do and what it takes to start."
- **It doesn't send anything.** Deliver the document; the human decides when and how it reaches the client.
- **Quality pass is mandatory.** Run `humanizer` and `ruthless-edit` before calling it done, same as `copywriting` — a proposal that reads like an AI wrote it undercuts the pitch it's making.

## Workflow

### 1. Gather inputs
Two things this skill needs before it can write anything:
- **The technical substance**: an approved or draft `technical-proposal` (stack, architecture rationale, cost/timeline range, risks). If none exists yet, say so and hand off to `technical-proposal` first — don't improvise engineering decisions to fill the gap.
- **Client context**: who's reading this (technical buyer vs. non-technical decision-maker), what they care about (speed to launch, cost ceiling, brand, risk aversion), budget sensitivity, and who else needs to sign off. Ask for what's missing rather than guessing at a client's priorities.

### 2. Frame the problem in the client's terms
Restate their problem and goal the way *they'd* describe it — the business outcome, not the technical one. This section earns the rest of the read; get it right before moving on.

### 3. Present the approach
Translate the technical proposal's recommendation into a client-facing narrative: what we'd build and why it's the right fit for them, in plain language. Offer options or tiers where they genuinely help the decision (e.g. a phased MVP vs. full scope) — don't force tiers where the honest answer is one path.

### 4. Scope it clearly
Say plainly what's included and what's explicitly not, so there's no ambiguity later. Vague scope is where trust erodes after signing, not before.

### 5. Timeline and investment
Translate the technical proposal's estimate into a client-readable timeline (milestones, not engineering sprints) and an investment framing — anchored to the value delivered, not just a number floating alone. Use the ranges and assumptions from the technical proposal; never sharpen a range into false precision or invent a number it didn't produce.

### 6. Social proof and credibility
Include real proof points if given (past work, testimonials, credentials). If none are supplied, use an explicit, clearly-marked placeholder — never a plausible-sounding fake.

### 7. Next steps
End with one clear, low-friction next action (a call, a signed kickoff, a question to answer) — not a vague "let us know."

### 8. Quality pass
Run `humanizer` (kill AI tells, hedging, and inflated language — this skill is especially prone to promotional puffery, so watch for it) and `ruthless-edit` (cut anything not earning its place). A persuasive document that's also bloated persuades less.

### 9. Deliver
Produce the proposal as markdown. If the client needs a polished document, use the `docx` skill to export it — don't hand-roll document formatting. State any placeholders or assumptions carried over from the technical proposal so the human can fill or confirm them before sending.

## What this skill does NOT do
- Decide or revise the stack, architecture, or engineering cost/timeline math — that's `technical-proposal`; this skill translates its output, it doesn't re-derive it.
- Fabricate testimonials, metrics, client logos, or capabilities not backed by the technical proposal or real client-supplied facts.
- Produce contracts, SOWs, or other legally binding terms.
- Send or deliver the proposal to the client — that's a human decision and action.
- Write general in-product UI or marketing copy unrelated to a specific client pitch — that's `copywriting`.

## Handoff
Comes from `technical-proposal` once a build is recommended and the engineering substance is settled. If the pitch surfaces a client question that changes the technical scope, send it back to `technical-proposal` rather than resolving it here.

**Where you sit in the chain:** discovery → technical-proposal → web-proposal-writer → product-planning → planning.
