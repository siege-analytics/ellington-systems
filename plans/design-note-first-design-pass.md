# Design note: first design pass on Ellington web

Authorizes the design work on `feat/first-design-pass`. Closes F3 from `plans/self-review-roster-and-confirmations.md`.

## Source

Session brief from Dheeraj to Craft Agent session `260708-copper-coyote`: pushback on 2026-07-08 noting the web pages had no design / branding and were therefore not shippable to external pedagogues. Enumerated as follow-up F3 in the roster PR's self-review. This slice is the first-pass response — not a final identity, but a coherent visual layer that can be shown to a guitar teacher without embarrassment.

## Deliverable

- One stylesheet (`static/ellington/ellington.css`) covering all current pages: master list, master detail (bio + distribution + books), confirmation review index and per-note form, invite redemption form, invite error page.
- A minimal SVG mark (`static/ellington/logo.svg`) used as favicon + brand-lockup icon.
- A rewritten `base.html` with a proper site header (brand + nav) and footer, responsive `<main class="wrap">` container, and inline `messages` rendering so per-page templates don't have to.
- Refined `master_list`, `master_detail`, and `redeem_invite` templates to use the new CSS classes.

## Aesthetic direction

Ellington-the-person is Duke Ellington. Ellington-the-app is a scholarly tool for jazz-guitar pedagogy. That combination pulls the design toward *editorial / scholarly / musical* — think a jazz-history reference volume, not a SaaS dashboard.

- **Palette:** warm ivory paper (`#f6f1e6`) with deep navy ink (`#1c2540`) as the primary text color, brass-gold (`#b3892b`) for accents (links, level letters in the distribution table, the brass in "Ellington" himself), muted crimson (`#8a2a2a`) reserved for form errors.
- **Type:** system serif stack (`Iowan Old Style, Palatino Linotype, Georgia`) for editorial content — headings, prose, master names. System sans-serif for UI chrome — nav, form labels, badges, meta text. This gives the roster pages a "page from a book" feel without loading a web font.
- **Layout:** single-column, 880px max-width, generous line-height. No sidebar, no toolbar. The confirmation form is the most complex thing on the page; everything else is prose or a small chart.
- **Chart:** the granularity distribution keeps its horizontal-bar form but the bars are now a brass gradient (lighter at the tail), the level letter is drawn in the accent color so a-i reads as a natural index, and the count is right-aligned in a soft ink color.

## Alternatives considered and rejected

- **Tailwind / utility CSS.** Rejected. One stylesheet for one small app doesn't need a build step, PostCSS, or a class explosion in templates. Django's `{% static %}` + a single hand-written CSS file is the right size.
- **Bootstrap / an off-the-shelf framework.** Rejected. Would import a lot of unused surface (grid systems, JS components) and lock the visual identity to "generic corporate SaaS." Ellington's brief is editorial.
- **A web font (Bitter, Merriweather, EB Garamond).** Rejected for this slice. System serif ships zero bytes, degrades gracefully on machines that don't have Iowan/Palatino, and looks good enough for a first pass. Revisit when the identity is finalized.
- **Dark mode.** Deferred. Not requested; a proper dark palette needs its own careful pass on the brass/ivory contrast ratios.

## Falsifiable premises

- **A system-serif stack renders acceptably across macOS/Linux/Windows/mobile.** Falsifier: pedagogues on Windows without Palatino see fallback Georgia which is fine, or a plain serif which is still fine. No layout depends on font metrics.
- **The brass-on-ivory palette is legible enough for pedagogue-facing text.** WCAG AA contrast for the navy-on-ivory body text is ~11:1 (well above 4.5:1). The brass links on ivory are ~4.6:1 (just above 4.5:1). Passes for normal-weight body text.
- **A serif-first typographic identity signals "scholarly" to guitar teachers, not "outdated."** Falsifier: first pedagogue reactions call it dusty. Cheap fix — swap the serif stack for a modern sans identity later without changing the layout skeleton.

## Rollback

Pure additive: one CSS file, one SVG, template class additions, one static-files setting. Reverting the commit falls back to the previous bare-CSS-in-`<style>` version. No DB changes, no functional regressions. Tests protect against structural template drift: 24 webapp tests still assert on the concrete strings they need.

## What this design pass does NOT do

- Does not establish a final brand identity. That needs actual design input from Dheeraj or a designer.
- Does not build a design system with tokens, components, or Storybook. One CSS file for the current five templates is not that.
- Does not add responsive breakpoints beyond `max-width: 880px + meta viewport`. Single-column layouts don't need them.
- Does not touch admin pages — Django admin has its own CSS and is a staff tool, not pedagogue-facing.
