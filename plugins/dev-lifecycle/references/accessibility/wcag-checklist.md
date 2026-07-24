<!--
library: wcag-checklist
versions-covered: "WCAG 2.2 (AA), WAI-ARIA 1.2"
last-verified: 2026-07-24
provenance: manual
sources:
  - https://www.w3.org/TR/WCAG22/
  - https://www.w3.org/WAI/WCAG22/quickref/
  - https://www.w3.org/WAI/ARIA/apg/
-->

# WCAG 2.2 AA checklist (by surface)

Loaded by the `accessibility-audit` skill after it fingerprints the application. For each surface: the success criteria to check, and what evidence of a pass looks like. Cite the WCAG success-criterion number (e.g. "1.4.3") alongside `file:line` evidence — it's what makes a finding buildable and lets the user cross-reference the spec directly.

## Contents
- Semantics & landmarks
- Keyboard paths
- Focus management
- Contrast (text, UI components, non-text)
- Forms & errors
- Media alternatives
- Motion, timing & input
- What automation (axe) catches vs. what needs a human

## Semantics & landmarks

- **Document structure** (1.3.1) — one `<main>`, `<nav>`, `<header>`/`<footer>` used correctly; landmark regions don't overlap or nest wrongly. Evidence: rendered DOM or template markup.
- **Heading hierarchy** (1.3.1, 2.4.6) — one `<h1>` per page/screen, no skipped levels, headings describe the section that follows.
- **Native elements over ARIA** — `<button>` not `<div onClick>`, `<a href>` not a styled span; ARIA only fills gaps native HTML doesn't cover (WAI-ARIA "First Rule").
- **Roles, states, and properties correct** (4.1.2) — custom widgets (tabs, menus, dialogs, comboboxes) expose the right `role`, `aria-*` state, and follow the APG pattern for that widget; no ARIA that contradicts the underlying element.
- **Name, role, value programmatically determinable** (4.1.2) — every interactive element has an accessible name (visible label, `aria-label`, or `aria-labelledby`) a screen reader announces.
- **Language of page/parts** (3.1.1, 3.1.2) — `lang` attribute set and correct; `lang` on substrings in a different language.
- **Status messages** (4.1.3) — async updates (toasts, form results, cart counts) use `aria-live`/`role="status"`/`role="alert"` so screen reader users get them without a focus change.

## Keyboard paths

- **Keyboard operable** (2.1.1) — every interactive element (including custom widgets) reachable and operable via keyboard alone; no mouse-only handlers (`onMouseOver` with no `onFocus` equivalent).
- **No keyboard trap** (2.1.2) — modals, menus, and widgets can be exited with keyboard (typically `Esc`, and `Tab` cycles within then releases).
- **Tab order matches visual/reading order** (2.4.3) — no `tabindex` values that scramble sequence; positive `tabindex` is a finding, not a style choice.
- **Skip link** (2.4.1) — a "skip to main content" link (or equivalent landmark navigation) exists for pages with repeated nav/header blocks.
- **Character key shortcuts** (2.1.4) — single-key shortcuts are remappable/disableable or only active on focus, so they don't clash with assistive tech.
- **Target size** (2.5.8) — interactive targets ≥24×24 CSS px (or adequate spacing) except inline text links.

## Focus management

- **Visible focus indicator** (2.4.7, 2.4.11) — every focusable element shows a visible focus state (not `outline: none` without a replacement); indicator not obscured by sticky headers/overlays.
- **Focus moves with the UI** — opening a modal/drawer moves focus into it (usually to the first focusable element or the dialog itself); closing it returns focus to the trigger.
- **Focus order stays logical after DOM changes** (2.4.3) — dynamically inserted content (toasts, infinite scroll, route changes) doesn't strand focus or reset it to `<body>`.
- **Route changes announce** — SPA navigation moves focus to the new view's heading or announces the change, since there's no full page load to reset assistive tech context.

## Contrast (text, UI components, non-text)

Check against the project's design-system tokens, not eyeballed values — if `design-system`'s token doc/theme file defines pairings, cite the token names; if it doesn't, cite the computed hex values.

- **Text contrast** (1.4.3) — normal text ≥4.5:1, large text (≥18pt / ≥14pt bold) ≥3:1 against its background.
- **Non-text/UI component contrast** (1.4.11) — icons, input borders, focus indicators, and other meaningful graphical objects ≥3:1 against adjacent color(s).
- **Color not the only signal** (1.4.1) — error/success/required-field state also uses text, icon, or pattern, not color alone.
- **Text resize / reflow** (1.4.4, 1.4.10) — content usable at 200% zoom and at 320px width without horizontal scrolling or clipped content.
- **Text spacing** (1.4.12) — no clipping/overlap when a user overrides line-height, letter/word spacing, paragraph spacing to the WCAG minimums.

## Forms & errors

- **Labels on every input** (1.3.1, 4.1.2) — visible `<label for>` (placeholder text alone is not a label); grouped controls (radio/checkbox sets) wrapped in `<fieldset>`/`<legend>`.
- **Instructions before errors** (3.3.2) — required fields and format expectations (e.g. date format) stated before submission, not only revealed on failure.
- **Error identification** (3.3.1) — invalid fields identified in text (not color alone), programmatically associated via `aria-describedby`, and the error text says what's wrong.
- **Error suggestion** (3.3.3) — where the fix is knowable, the message suggests it ("Email must contain @", not just "Invalid").
- **Error prevention on legal/financial/data-altering actions** (3.3.4) — confirm, allow review/undo, or allow correction before an irreversible submit.
- **Redundant entry** (3.3.7) — information the user already supplied in the same flow isn't demanded again (or is auto-populated).
- **Accessible authentication** (3.3.8) — no cognitive-function test (e.g. transcribing a CAPTCHA image) required for login without an alternative.

## Media alternatives

- **Images** (1.1.1) — informative images have descriptive `alt`; decorative images have `alt=""` or are CSS backgrounds; complex images (charts) have a text alternative nearby.
- **Prerecorded audio/video** (1.2.1–1.2.5) — captions on video with audio; audio-only content has a transcript; prerecorded video has audio description where visual-only info matters.
- **Live captions** (1.2.4) — live video/audio content has real-time captions if the project ships any.
- **Icon-only controls** — accessible name via `aria-label`/`sr-only` text, not relying on a tooltip alone.

## Motion, timing & input

- **Reduced motion respected** (2.3.3) — decorative animation honors `prefers-reduced-motion`; nothing flashes >3×/second (2.3.1).
- **Pausable/adjustable timing** (2.2.1, 2.2.2) — session timeouts and auto-advancing content (carousels, auto-refresh) can be paused, extended, or disabled.
- **Pointer gestures have simple alternatives** (2.5.1, 2.5.2) — drag/multi-touch/path-based gestures have a single-pointer equivalent; accidental activation is preventable (down-event doesn't fire the action where a cancel affordance is expected).
- **Orientation not locked** (1.3.4) — content works in both portrait and landscape unless the orientation is essential.

## What automation (axe) catches vs. what needs a human

Automated tools (axe-core, and its CLI/CI wrappers) reliably find missing alt text, missing form labels, contrast failures on static text, invalid ARIA usage, and missing landmarks/headings — roughly a third of WCAG success criteria, and they produce zero false positives on what they *do* flag. They cannot judge: whether tab order and focus movement make sense, whether an `alt` text or error message is actually meaningful (only that one exists), whether a custom widget's keyboard interaction matches its APG pattern, whether captions are accurate, or whether reduced-motion/timing behavior is correct. Treat an axe pass as a floor, never a ceiling — always pair it with the manual keyboard-and-screen-reader walk for interactive flows.
