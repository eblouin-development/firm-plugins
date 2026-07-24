---
name: "discovery"
description: "Turn a vague client brief into concrete, client-confirmable requirements — generate a client-interview guide to prep for a call, then synthesize raw notes/transcripts into a requirements document that keeps STATED FACTS separate from ASSUMPTIONS in an explicit assumption log. Use this skill WHENEVER a new client engagement is starting and what they actually need isn't nailed down yet: \"new client lead\", \"prep for the kickoff call\", \"turn these meeting notes into requirements\", \"we have a call with a prospect next week\", \"here's the brief, what should we ask them\", \"write up what we learned from the client call\". This is the step before technical-proposal — it elicits and structures what the client needs, it does NOT decide stack or architecture (technical-proposal), does NOT estimate cost or timeline, and does NOT write persuasive copy. Distinct from planning, which scopes an already-understood change in an existing codebase — discovery is for when the codebase doesn't exist yet and the requirements themselves are still fuzzy."
---

# Discovery

Before anyone can propose a stack or a timeline, someone has to work out what the client actually needs — and a vague brief ("we need a website that does X-ish") isn't that. This skill owns the step before both `technical-proposal` and `planning`: turning a brief into a client-interview guide, then turning what comes back from that call into a requirements document precise enough to build a technical proposal from.

## Core rules

- **Elicit and structure — don't decide.** This skill's job ends at "here's what the client needs, clearly written down." It does not choose a stack or architecture (`technical-proposal`'s job), does not estimate cost or timeline, and does not write persuasive client-facing copy (`web-proposal-writer`'s job). If a question drifts into "so what should we build this with," note it as a question for `technical-proposal` and keep moving.
- **Separate what was said from what was inferred, always.** Every fact in the requirements document is either something the client stated (or a document/transcript shows) or an assumption made to fill a gap — and it must be visibly labeled which. Silently inventing a requirement to make the document feel complete is the single failure mode this skill exists to prevent.
- **An assumption is not a guess to hide — it's a question to surface.** When the brief or notes don't cover something the build will need to know (a must-have vs. a nice-to-have, who the users are, a constraint), write the most reasonable assumption and flag it for the client to confirm rather than leaving a blank or quietly deciding. The assumption log is the deliverable's safety net.
- **This is for a client engagement, not an internal change.** `planning` scopes a change to a codebase that already exists and whose stakeholders already share context. Discovery is for when there's no codebase yet and the person who wants the thing built hasn't yet said precisely what "it" is.
- **Work from what's given; ask rather than pad.** If the brief is thin, say what's missing and ask for it (or propose the assumption) instead of manufacturing detail to look thorough.

## Workflow

### 1. Prepare — build the interview guide
Starting from whatever brief exists (an email, a one-liner, a referral note), generate a client-interview guide to run the kickoff/discovery call. Cover:
- **Goals** — what outcome the client is actually after, and how they'd know it worked.
- **Users** — who uses the thing, and how that differs from who's paying for it.
- **Must-haves vs. nice-to-haves** — get the client to rank, don't assume everything mentioned is equally critical.
- **Content & data sources** — what content exists already, what needs creating, where data lives or comes from.
- **Integrations** — other systems this needs to talk to (payments, CRM, existing site, third-party APIs).
- **Constraints** — budget band, timeline pressure, hosting preferences/requirements, compliance or regulatory needs.
- **Success measures** — how the client will judge whether this worked, post-launch.

Organize the guide as questions grouped by these topics, flagged by priority (the questions that most change scope or feasibility first) so a rushed call still gets the load-bearing answers. If the brief already answers something, don't ask it again — note it as already known and move to what's still open.

### 2. Synthesize — turn notes into requirements
Once call notes, a transcript, or follow-up emails come back, turn them into a requirements document. This is the core deliverable. Structure:
- **User roles** — who interacts with the system and how (distinct roles, not just "users").
- **Core flows** — the primary things each role needs to be able to do, described as flows, not features — what happens, not how it's built.
- **In scope / out of scope** — an explicit list of both. What's excluded is as load-bearing as what's included; write it down so it isn't re-litigated later.
- **Open questions** — anything the notes didn't resolve, aimed at the client for follow-up.
- **Assumption log** — every assumption made to fill a gap, each one paired with what was actually stated (or "nothing stated — inferred from X") and what happens if the assumption turns out wrong. Format each entry so a client can scan it and reply "confirmed" or "actually, no."

Keep every claim traceable: if a requirement can't be pointed back to something the client said (in the brief, the notes, or a direct quote) or flagged as an assumption, it doesn't belong in the document.

### 3. Hand off
The requirements document is `technical-proposal`'s input — it reads user roles, flows, and scope to recommend a stack and estimate cost/timeline honestly. Deliver the document with the assumption log called out up front, so whoever picks it up next knows which parts are solid and which still need client confirmation before they get load-bearing.

**Where you sit in the chain:** discovery → technical-proposal → web-proposal-writer → product-planning → planning.

## What this skill does NOT do
- Decide or recommend a stack, architecture, or technical approach — that's `technical-proposal`.
- Estimate cost or timeline — that's `technical-proposal`, once the requirements are settled.
- Write persuasive, client-facing sales copy — that's `web-proposal-writer`, once there's a technical proposal to translate.
- Invent a requirement to fill a gap without flagging it as an assumption in the log.
- Scope a change to an existing codebase — that's `planning`; discovery is for a client engagement before a codebase or a settled understanding exists.
