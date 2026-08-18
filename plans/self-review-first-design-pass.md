# Self-Review: feat/first-design-pass

Working as: software engineer, tech lead

Covers the first-pass design system: `static/ellington/ellington.css`, `static/ellington/logo.svg`, rewritten `base.html`, refined `master_list.html` + `master_detail.html` + `redeem_invite.html`, `STATICFILES_DIRS` setting. Closes F3 from the roster PR's self-review.

## Assumptions

Domain(s): software engineering
Geospatial cross-cut: no
Goal source: Dheeraj's pushback on 2026-07-08 that the shipped web pages had no design/branding, captured in `plans/design-note-first-design-pass.md#source`.
Plan reference: plans/design-note-first-design-pass.md
Pre-author-inventory: NONE
Trivial-against-state: No pre-existing design system, CSS file, or brand identity to inventory. The prior state was 20 lines of inline CSS in `base.html`. `grep -rn "class=" src/ellington_web/*/templates/` before this diff returned a handful of ad-hoc classes (`.distribution`, `.badge`, `.pending`, `.verdict-form`) — all preserved and now defined in the new stylesheet. `git diff develop..HEAD -- src/ellington_systems/` returns empty; engine code untouched.
Investigate-artifact: TRIVIAL
Pre-mortem-artifact: TRIVIAL
Hostile-review-artifact: plans/hostile-review-first-design-pass.md
Project-contribution: Closes F3 (design pass) from #17's self-review. Produces a coherent visual layer over the roster and confirmation pages that can be shown to an external guitar teacher without embarrassment. Introduces a scholarly-editorial identity (ivory paper / navy ink / brass accents / serif body) aligned with Ellington's positioning as a jazz-pedagogy tool rather than a generic SaaS product.

## Trivial-investigation declaration

Applies to both Investigate-artifact: TRIVIAL and Pre-mortem-artifact: TRIVIAL above.

Category: Additive presentation-layer changes. Zero DB writes, zero new endpoints, zero changes to auth or authorization, zero changes to the engine library. One new setting (`STATICFILES_DIRS`) that lists exactly one directory.
Cannot produce error: Because (a) the diff adds only CSS + SVG + template class attributes + one setting; nothing in it can raise an unhandled exception in a request path, (b) all existing tests assert on the concrete text strings that page templates render — the design pass preserves every asserted string, verified by re-running the full webapp suite (24 pass) after each template change, (c) `{% static %}` is Django's supported tag and returns a stable URL regardless of `STATIC_URL` value, (d) the engine library is byte-identical to develop.
Evidence: `git diff develop..HEAD --stat` shows changes under `src/ellington_web/*/templates/`, `src/ellington_web/ellington_web/templates/base.html`, `src/ellington_web/ellington_web/settings.py` (one line), `src/ellington_web/ellington_web/static/ellington/` (new dir with 2 files), `plans/` (3 new files). Full test suite: `python -m pytest` → `215 passed, 9 skipped in 1.18s`. Contrast-ratio math for all text-on-background pairs is enumerated in `plans/hostile-review-first-design-pass.md#5-contrast--accessibility-regressions`; every ratio passes WCAG AA.
Falsification: Would be falsified if any existing test failed, if the pages rendered with visible layout breakage, or if the WCAG AA contrast floor was breached anywhere. None hold: 215/215 tests pass; manual `runserver` check of `/masters/`, `/masters/ted-greene/`, `/masters/martin-taylor/`, and a confirmation review page renders correctly with the new palette; contrast ratios documented and passing.

## Peer review (Junior's checklist -- mechanics, correctness, craft floor)

Shelves engaged: writing-code:1 (no speculative abstraction — one stylesheet, no framework), writing-code:5 (no premature optimization — no build step, no CSS preprocessor), writing-tests:1 (existing tests still assert on the strings that matter), writing-claims:1 (grep-verified claims below), writing-claims:3 (contrast ratios computed with named color values, not vibes).

**writing-code:1 — Stylesheet scope discipline.** Checked.
- One CSS file, one SVG, hand-written. No Sass, no PostCSS, no Tailwind, no Bootstrap.
- No CSS class is defined that is not used by an existing template. Verified via `grep -oE '"[a-z-]+"' src/ellington_web/*/templates/**/*.html` cross-referenced with the class selectors in `ellington.css`.
- No CSS reset beyond `* { box-sizing: border-box; }` + `html, body { margin/padding: 0 }`. Retains sensible defaults from user agent for lists, blockquotes, etc., which are then styled specifically.

**writing-code:5 — Template preservation of test contracts.** Checked.
- Every string asserted by the existing 24 webapp tests is preserved. Cross-referenced test assertions with rendered template output. All 24 pass.
- Header nav still resolves `{% url 'roster:master_list' %}` and (when authenticated) exposes a sign-out link that uses Django's built-in logout URL.

**writing-tests:1 — No new tests needed.** Justified.
- Design changes are aesthetic and structural, not functional. Every functional path still returns the same responses with the same asserted content.
- A "does the stylesheet load" smoke test would only cover the case where `STATICFILES_DIRS` gets misconfigured — deferred as F11 pending CI wiring.

**writing-code:1 — Static file setup.** Checked.
- `STATICFILES_DIRS` lists exactly one directory under the project source tree.
- `{% load static %}` present at the top of `base.html`.
- `STATIC_URL` unchanged from Django default.
- No `collectstatic` needed in dev; production deployment (when it exists) will need it — noted in the design note but not part of this PR.

**writing-claims:1 — Untouched-engine claim.** Verified.
- `git diff develop..HEAD -- src/ellington_systems/` → empty. Engine module is byte-identical.
- `git diff develop..HEAD -- tests/test_*.py` → empty. Engine tests untouched.
- `pytest tests/` (excluding webapp) → 191 pass, 9 skip. Same numbers as develop.

**writing-claims:3 — Contrast-ratio claims.** Verified.
- Ratios computed against WCAG AA formula, enumerated in `plans/hostile-review-first-design-pass.md#5-contrast--accessibility-regressions`.
- Weakest pair (brass on ivory) is 4.6:1 — right above the 4.5:1 floor. Documented as F10 with a darker-brass fallback if reports come in.

## Lead review (Lead's adversarial pass -- did the Junior actually solve this?)

**software engineering domain:**

- *Approach fit:* One hand-written CSS file + one SVG + Django's `{% static %}` is exactly the right size for the current five templates. Any framework or build tooling would be over-scoped. If the app grows past ~15 templates or needs tokens for a design system, revisit — but that's not today.
- *Affirmative standard: F3 (design pass) is closed.* Holds. The pages now have a coherent typographic identity, a palette that matches Ellington's positioning, a header with a brand mark, a footer with attribution, form styling that treats errors consistently, and a chart that reads as an intentional visual (brass gradient) rather than an afterthought (raw blue rectangle).
- *Affirmative standard: no functional regressions.* Holds. 215 tests pass. Existing behavior preserved.
- *Blast radius:* Presentation layer only. No DB, no auth, no engine.
- *Sequencing assumption:* Audio-pipeline plan doc (next slice) is independent of design.

**tech lead domain:**

- *Approach fit:* This is a *first pass*, not a final identity. That's the right call given no design input has been solicited from Dheeraj yet and the audience (external pedagogues) has not seen anything. It's coherent enough to show without embarrassment; it's simple enough to throw away if Dheeraj wants a different direction.
- *Sequencing assumption:* Design pass before audio-pipeline plan doc is the right order because it unblocks pedagogue outreach (which drives the confirmation feedback loop). Audio pipeline is a bigger, longer piece of work that does not gate anything else in the near term.

**Dismissals from peer review:**
- "No web font, might look dusty on Windows." — dismissed for now. System serif ships zero bytes and looks fine on macOS/Linux; Windows falls back to Georgia which is also fine. Revisit if any pedagogue complains.
- "No dark mode." — dismissed. Would require a second pass on brass/ivory contrast; premature until requested.

## Findings

| ID | Priority | Description | Resolution |
|----|----------|-------------|------------|
| F10 | P3 | Brass color at 4.6:1 contrast is right at the WCAG AA floor for links / level-letters. | Deferred with a documented darker-brass fallback (`#8f6d21`). |
| F11 | P2 | No automated smoke test that the stylesheet actually loads. | Deferred until CI is wired (F4). Manual `runserver` check for now. |

Zero P1 findings.

Self-Review author: Craft Agent (session `260708-copper-coyote`)
