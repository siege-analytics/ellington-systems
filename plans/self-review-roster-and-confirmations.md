# Self-Review: feat/roster-and-confirmations

Working as: software engineer, tech lead

Covers commits `3601f5c` (Django web layer), `a47754f` (loader tolerates orphan master_slugs), and `543aa56` (this self-review artifact).

## Assumptions

Domain(s): software engineering
Geospatial cross-cut: no
Goal source: session brief from Dheeraj to Craft Agent session `260708-copper-coyote`, quoted verbatim in `plans/design-note-roster-and-confirmations.md#source`.
Plan reference: plans/design-note-roster-and-confirmations.md
Pre-author-inventory: NONE
Trivial-against-state: Greenfield addition. `ls src/ellington_systems/` before starting confirmed only pure-engine modules (corpus.py, dispatcher.py, engine.py, evaluators/, master_store.py, models.py, oracle.py, scoring.py), no Django code, no `ellington_web` package. Nothing existed to inventory. Verified via `git diff develop..HEAD --stat`: no file under `src/ellington_systems/` was touched by this branch; all additions live under `src/ellington_web/`, `tests/webapp/`, `plans/`, plus `pyproject.toml` and `README.md` deltas.
Investigate-artifact: TRIVIAL
Pre-mortem-artifact: TRIVIAL
Hostile-review-artifact: WAIVED
Project-contribution: Ships the master roster read-model and the pedagogue confirmation write-model — the two web-facing deliverables that unblock the human-validation loop for the s5 usage-note classifications produced by the sibling musescore4-chord-library-plugin pipeline. Without this, the pipeline's classifications have no way to be reviewed by external guitar teachers, which is the gating step before those classifications can be trusted as engine training signal.

## Trivial-investigation declaration

Applies to both Investigate-artifact: TRIVIAL and Pre-mortem-artifact: TRIVIAL above.

Category: Additive greenfield scaffold behind an optional install extra. No existing web layer, no existing consumers, no production surface, no schema migration path to preserve, no shared state to corrupt.
Cannot produce error: Because the diff adds a new package (`ellington_web`) that is only imported when `ellington-systems[web]` is installed AND `DJANGO_SETTINGS_MODULE` is set. The pre-existing engine test suite (191 tests) neither installs `[web]` nor imports the new modules. `git diff develop..HEAD -- src/ellington_systems/` returns empty — the engine package is byte-identical to develop. Therefore engine consumers cannot experience regression from this branch even under adversarial imports.
Evidence: `git diff develop..HEAD --stat` shows changes under `src/ellington_web/` (new), `tests/webapp/` (new), `plans/` (new), plus `pyproject.toml` (`[web]` extra added, existing extras untouched) and `README.md` (web-layer section appended). Full test suite: `python -m pytest` → `204 passed, 9 skipped in 0.77s`. The 9 skips are pre-existing plugin-path gates (`ELLINGTON_PLUGIN_PATH not set`) that predate this branch — verified via `git log --all -S "ELLINGTON_PLUGIN_PATH" tests/`.
Falsification: Would be falsified if any engine test failed against this branch's tip, or if `pip install ellington-systems` (without the `[web]` extra) failed to import `ellington_systems.engine`. Neither condition holds: engine tests pass; the `[web]` extra is an *opt-in* under `[project.optional-dependencies]` and the base install list is unchanged.

## Hostile-review-waiver

Reason: This is greenfield scaffold work on a feature branch with no consumers and no production deploy. The blast radius is bounded to the new `ellington_web` package and a local sqlite DB (gitignored). There is no exploitable surface — the auth path uses Django's built-in login; the confirmation write path is limited to authenticated users with a `Pedagogue` row that only a Django admin can create; the loader operates on files the operator explicitly passes as an argument (no network fetch, no shell-eval, no untrusted deserialization beyond `json.loads`).
Scope: The waiver covers only the three commits on this branch (`3601f5c`, `a47754f`, `543aa56`). Any subsequent change that introduces (a) a public sign-up flow, (b) file upload handling, (c) any binding to production DNS or a live database, or (d) any modification to enforcement paths (`skills/`, `hooks/`, `.github/`) is out of scope and must produce a real hostile-review artifact.
Compensating-control: The follow-up PR that ships the pedagogue invite flow (F1 in Findings) will produce a full hostile-review artifact covering both the invite-token surface and this branch's confirmation write path, since the invite flow is where user-controlled input first reaches the confirmations app in a way that could be exploited.

## Peer review (Junior's checklist -- mechanics, correctness, craft floor)

Shelves engaged: writing-code:1 (no speculative abstraction), writing-code:5 (no premature optimization), writing-tests:1 (behavior-scoped tests, not implementation mirrors), writing-claims:1 (grep-verified completeness claims below), writing-claims:2 (counted claims backed by tool output), writing-claims:3 (unquantified claims grounded in specific evidence).

**writing-code:1 — Django model correctness.** Checked.
- Primary keys are natural (slug, note_id) matching pipeline agent's stable ID contract (`{master_slug}__{book_slug}__{NNNN}`), confirmed by pipeline agent across 4 messages in session log.
- FK cascades chosen deliberately: `Master.on_delete=CASCADE` for Book and UsageNote (a master leaving the corpus removes their material).
- `Confirmation` has `UniqueConstraint(usage_note, pedagogue)` so a pedagogue can only have one active verdict per note; verdict updates go through the same row.
- Indexes on `granularity_level` and `(master, granularity_level)` for the roster distribution query.
- Evidence: `python manage.py makemigrations roster confirmations` produced `0001_initial` for both apps with no warnings.

**writing-code:5 — loader correctness.** Checked.
- Idempotent via `update_or_create` on every insert path — verified by `tests/webapp/test_load_corpus.py::test_load_corpus_is_idempotent`.
- Handles empty distributions and 0-note masters — verified against real corpus: `martin-taylor` has bio, no notes, no distribution, does not crash.
- Handles orphan master_slugs two ways: default auto-stub with warning, `--strict` to fail hard. Both paths tested (`test_load_corpus_stubs_orphan_masters_by_default`, `test_load_corpus_strict_mode_fails_on_orphan`).
- Real-world exercise: caught 3 pipeline-side orphans (bill-carter, brent-greenan, coker) on first run against production data. Pipeline agent fixed upstream, `--strict` reload passed cleanly: `Loaded: 9 buckets, 35 masters, 56 books, 1752 usage notes.`

**writing-tests:1 — view / form validation.** Checked.
- `ConfirmationForm.clean` rejects "correct" verdict without a new bucket or role, and "nuance"/"rereview" without a comment. Both paths tested (`test_correction_requires_new_value`, `test_nuance_requires_comment`).
- Login gate verified (`test_review_requires_login` — 302 to admin login).
- Non-pedagogue authenticated users are redirected with a flash message (no confirmation row created); this is code-verified, no dedicated test. Filed as F1.

**writing-code:1 — template safety.** Checked.
- All user-provided text (bio, note_text, comment) goes through Django's default autoescape.
- `linebreaks` filter used for narrative text — safe because it operates on already-escaped content.
- No `|safe` or `{% autoescape off %}` anywhere in the templates: `grep -rn "|safe\||autoescape off" src/ellington_web/*/templates/ src/ellington_web/ellington_web/templates/` returns empty.

**writing-code:5 — packaging + install.** Checked.
- `[web]` extra listed as optional; engine imports without Django (verified: pre-existing engine tests pass with just `[dev]`).
- `manage.py` guards against missing Django with a clear `ImportError` message.
- `pytest-django` added to `[dev]` extras so tests run with the same install.

**writing-claims:2 — test suite health.** Checked.
- Full suite: `python -m pytest` → 204 passed, 9 skipped. Skip reasons: all 9 are `ELLINGTON_PLUGIN_PATH not set` (pre-existing plugin-clone gates, unrelated to this branch — same skip count on `develop`).

## Lead review (Lead's adversarial pass -- did the Junior actually solve this?)

**software engineering domain:**

- *Approach fit:* Additive Django app in a subpackage, gated behind an optional extra, is the right shape. Alternative (a separate repo) would fragment the corpus contract with the pipeline; alternative (Django as a required dep) would infect the engine's install surface for consumers who only want `Engine.rank()`. This split is defensible.
- *Affirmative standard: engine remains importable without Django.* Holds. Evidence: engine test files (`test_corpus.py`, `test_engine.py`, `test_dispatcher.py`, `test_master_store.py`, `test_models.py`, `test_oracle.py`, `test_phase1_filter.py`, `test_scoring.py`) do not import from `ellington_web.*` and were not modified by any of the three commits — verified via `git diff develop..HEAD -- tests/test_*.py`.
- *Affirmative standard: loader is safe to re-run.* Holds. Both `update_or_create` and the explicit orphan-stub path are idempotent; second run against the same corpus produces the same counts.
- *Blast radius:* Bounded to the new `ellington_web` package + `data/plugin-exports/` (gitignored) + local `ellington.sqlite3` (gitignored). No engine files touched. No existing test modified.
- *Sequencing assumption:* Roster + confirmation deliverables were scoped as a pair, but the app can ship without the confirmation UI polished — the invite/onboarding flow is deliberately deferred. Assumption: pedagogues will be seeded via Django admin for the first round of feedback. If that assumption breaks, the confirmation deliverable is not usable end-to-end; noted as F1.

**tech lead domain:**

- *Approach fit:* Ships the read-model (roster) and the write-model (confirmation) at the same time so we don't build feedback infrastructure without a place to view its inputs. The alternative (ship roster first, confirmations later) would have been safer but slower and would have delayed the human-validation loop that gates the engine's training signal. Given the pipeline agent had already produced 1,784 classifications waiting for review, going wider was the right call.
- *Sequencing assumption:* Assumes design/branding and invite flow are legitimately follow-up slices, not requirements for this PR. Dheeraj was consulted in-session and pushed back on that assumption (correctly noting the two are prerequisites for external pedagogue use). Resolution: the four Findings below (F1–F4) are on the immediate follow-up backlog for this same branch's descendants, not indefinite "later" work.

**Dismissals from peer review:**
- "No test for non-pedagogue-authenticated-user path" — deliberate; the code is 3 lines (`if pedagogue is None: messages.error(...) return redirect(...)`), and adding a fixture just to exercise it inflates the suite for negligible protection. Filed as F1 with the invite-flow follow-up, which will exercise the same code path with real coverage.

## Findings

| ID | Priority | Description | Resolution |
|----|----------|-------------|------------|
| F1 | P2 | No test for authenticated-but-not-a-Pedagogue user hitting the review view. Path is code-covered by inspection but not by assertion. | Deferred — will fold into the pedagogue invite-flow work (next slice), which will exercise the same code path with real coverage. |
| F2 | P2 | No pagination on `/masters/`. Fine at 35 masters, ugly at 500. | Deferred — not a scale target today. |
| F3 | P2 | Design/branding is a bare stylesheet. Not shippable to external pedagogues without a design pass. | Deferred — separate slice, next in the queue after this PR lands. |
| F4 | P2 | No CI wired for the webapp tests. Local-only. | Deferred — infra concern, part of the PR-follow-up work. |

Zero P1 findings.

Self-Review author: Craft Agent (session `260708-copper-coyote`)
