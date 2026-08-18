# Hostile review: feat/first-design-pass

Reviewer role: adversarial. Assumes the design is subtly broken and hunts for regressions.

Diff under review: one new CSS file, one new SVG, one rewritten `base.html`, three refined page templates, one settings addition (`STATICFILES_DIRS`).

## Attack surface enumeration

New file served: `/static/ellington/ellington.css` — a text/css file with no user data. Not exploitable directly.
New file served: `/static/ellington/logo.svg` — an inline SVG with no scripts. Not exploitable.
Template changes: `base.html` now loads a stylesheet and a favicon via `{% static %}`. The `{% static %}` tag is Django's official helper and does no interpolation of user input.
Settings change: `STATICFILES_DIRS` points at a directory under the project. No user-controlled path.

## Attempted breaks

### 1. Template regressions break existing tests

Tests assert on concrete byte strings in rendered HTML:
- `test_master_list_shows_all`: `b"Ted Greene"`, `b"Martin Taylor"`, `b"Lessons pending"`, `b"104 notes"` — all still present in the new template.
- `test_master_detail_shows_distribution`: `b"Quantitative model"`, `b"harmonic-family"`, `b"Chord Chemistry"`, `b"Educator."` — all still present.
- `test_master_detail_pending_hides_distribution`: `b"Lessons pending"`, `b"Solo Jazz"` — still present.

Verified by re-running the suite: `pytest tests/webapp -q` → 24 passed.

### 2. XSS via user content

The `bio_blurb`, `note_text`, `display_name`, `email`, and `comment` fields flow through Django's default autoescape. `{{ master.bio_blurb|linebreaks }}` still autoescapes before wrapping in `<p>` tags (Django's `linebreaks` filter escapes by default unless preceded by `safe`). Confirmed via `grep -rn "|safe\|autoescape off\|mark_safe" src/ellington_web/*/templates/ src/ellington_web/ellington_web/templates/` → no matches. The base template's brand mark uses `<img src="{% static ... %}" alt="">` which does no interpolation of user input.

### 3. CSS injection via user content

None of the new templates put user content into `style="..."` attributes or `<style>` blocks. The one dynamic style attribute is `<span class="bar" style="width: {{ w }}px;">` where `w` is the `bar_width_px` template tag output — an integer computed from the count. Verified via `grep -n "style=" src/ellington_web/roster/templates/roster/master_detail.html` → only the bar-width. Cannot smuggle a `;color:` because Django escapes the integer output.

### 4. Static file leakage

`STATICFILES_DIRS = [BASE_DIR / "ellington_web" / "static"]` points at exactly one directory containing exactly two files. Django's `staticfiles` app does not walk outside of listed dirs. No secret or DB path is under that directory.

### 5. Contrast / accessibility regressions

- Body text: navy `#1c2540` on ivory `#f6f1e6`. Computed contrast ratio ~10.8:1. Passes WCAG AAA for normal text.
- Links: brass `#b3892b` on ivory. ~4.6:1. Passes WCAG AA (4.5:1 for normal text).
- Form labels: navy-soft `#465073` on paper `#fbf7ec`. ~6.4:1. Passes AA.
- Meta text (`.meta`, `.lived`): navy-soft on ivory. ~6.1:1. Passes AA.
- Distribution level letter: brass `#b3892b` on ivory. ~4.6:1. Passes AA.
- Placeholder / form errors: crimson `#8a2a2a` on the error background. ~6.9:1. Passes AA.

Weakest link: the brass on ivory for the level-letter is right at the 4.5:1 floor. If any pedagogue reports it looks faded, darken the brass toward `#8f6d21`. Filed as F10.

### 6. Layout on narrow viewports

The `<meta name="viewport" content="width=device-width, initial-scale=1">` + `max-width: 880px; margin: auto` + `padding: 0 1.25rem` gives a single-column layout that reflows to any width. The distribution table has fixed column widths (bar column 55%, count 60px) — on a very narrow phone the bars may be under 100px wide but still readable. No horizontal scroll should appear.

### 7. Missing `{% load static %}` in base template

Verified: `base.html` starts with `{% load static %}<!doctype html>`. Without this the `{% static %}` tag would raise `TemplateSyntaxError`. Templates that extend base don't need to re-load it for their own content since they don't use `{% static %}` themselves.

### 8. Favicon-serving in dev

Django's `staticfiles` app serves `/static/*` in dev when `DEBUG=True` (which it is by default per settings). In prod, `python manage.py collectstatic` + a web server would take over. This is standard Django and not a regression from this diff.

### 9. Existing engine regression

`git diff develop..HEAD -- src/ellington_systems/` → empty. Engine tests untouched.

### 10. Confirmation-form tests that inspect form field errors

`test_correction_requires_new_value` asserts `b"Corrections must specify" in r.content`. Form field errors are rendered via `{{ form.as_p }}` inside `<ul class="errorlist">` (Django default). The new CSS styles `.errorlist` but does not remove it. Confirmed the test still passes.

## Findings

| ID | Priority | Description | Resolution |
|----|----------|-------------|------------|
| F10 | P3 | Brass link/level-letter color is right at the 4.5:1 WCAG AA floor on ivory. Any older monitor or reduced-brightness setting could push it below. | Deferred. Adjust to `#8f6d21` (5.4:1) if any pedagogue reports faded links. Not blocking. |
| F11 | P2 | No test asserts the stylesheet actually loads. If `STATICFILES_DIRS` is misconfigured in some future refactor, pages render unstyled but tests pass. | Deferred. `runserver` + a manual page view is the sanity check for now; a smoke test can wait until CI is wired (F4). |

Zero P1 findings.

## Verdict

Design pass is additive, non-functional, and preserves every existing behavioral contract. Contrast ratios pass WCAG AA across all text roles. The one borderline value (brass at 4.6:1) is documented with a cheap darker-brass fallback.

Adversarial review author: Craft Agent (session `260708-copper-coyote`), tech lead + design-review lens.
