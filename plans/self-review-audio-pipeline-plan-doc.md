# Self-Review: docs/audio-pipeline-plan-doc

Working as: software engineer, tech lead

Covers one new plan file, `plans/audio-pipeline-plan.md`, a research + architecture plan for the Ellington audio pipeline (chart ingest → recording → separation → transcription → comparison → coaching), plus this artifact. This revision follows an independent review of the first draft (head `491dcaea`) and reconciles the plan with epic ellington-systems#12 and ellington-web#60/#70/#71/#232/#243. No executable code changes.

## Assumptions

Domain(s): software engineering
Geospatial cross-cut: no
Goal source: the owner's 2026-07-08 pushback flagging "test workflow for uploading tracks and parsing them" as a real gap, and the owner's later decision (relayed 2026-11-04) to revise this PR before merge after the review of the first draft.
Plan reference: plans/audio-pipeline-plan.md (this artifact reviews *that* doc; there is no separate design note for a plan doc)
Pre-author-inventory: NONE
Trivial-against-state: Docs-only diff. The branch changes `plans/audio-pipeline-plan.md` and `plans/self-review-audio-pipeline-plan-doc.md` only. No `.py`, `.sh`, `.js`, `.ts`, `.sql`, or executable file is touched.
Investigate-artifact: TRIVIAL
Pre-mortem-artifact: TRIVIAL
Hostile-review-artifact: WAIVED
Project-contribution: Provides a map of the audio side of Ellington reconciled with what is already recorded in epic #12 and the `ellington-web` issues, so that continued work does not duplicate or contradict it. Enumerates the six stages (chart ingest, recording, separation, transcription, comparison, coaching), states for each what is recorded versus open, corrects the description of `Engine.rank()` to match the code, and replaces the first draft's four "blocking questions" with the real blocking set (layout confirmation, chart schema, rehab scope, corpus availability) while keeping multi-track upload and LLM budget as deferrable. It records decisions already made with quotes and does not answer any open question.

## Trivial-investigation declaration

Applies to both Investigate-artifact: TRIVIAL and Pre-mortem-artifact: TRIVIAL above.

Category: Prose-only planning document. No code, no schema, no config, no infrastructure.
Cannot produce error: Because a markdown file under `plans/` is not loaded by any code path in the repo. `grep -rn "audio-pipeline-plan" src tests` over the extracted head returns zero matches.
Evidence: the test suite was run at the pre-revision head `491dcaea` (the revision changes only the two `plans/` files): `207 passed, 9 skipped` (interpreter `~/.pyenv/versions/default_31111/bin/python` 3.11.11, pytest 8.4.2; command `python -m pytest -p no:cacheprovider -o pythonpath=src -o addopts= -rs` from the extracted tarball). All 9 skips are `ELLINGTON_PLUGIN_PATH not set; skipping plugin-data test`. The first draft's "215 passed, 9 skipped" was wrong for the committed tree: two test files (`tests/webapp/test_roster_views.py`, 3 tests, and `tests/webapp/test_confirmation_flow.py`, 5 tests) exist only in the author's local clone and are not in git, which accounts for the 8 missing tests. A ticket for that is being filed and has no number yet. The suite was not re-run after this revision because no file the suite loads was changed.
Falsification: Would be falsified if adding or editing a markdown file under `plans/` changed the suite result. Not re-run; the claim rests on the grep above.

## Peer review (Junior's checklist -- mechanics, correctness, craft floor)

Shelves engaged: writing-prose:1 (claims grounded in specific tools / prices / model names, not vibes), writing-claims:2 (countable claims verified), writing-claims:3 (unquantified claims grounded or marked UNVERIFIED).

**writing-prose:1 — Grounded claims.** Checked.
- Each recorded decision is quoted with its issue number or document; each is labelled "recorded" with the owner's ratification UNVERIFIED, because the quoted comments are posted under the owner's account but the threads do not show the owner's own answer.
- Open questions are restated precisely and are not answered.

**writing-claims:2 — Countable claims verified.** Checked.
- Test count: 207 passed, 9 skipped, measured (see declaration above); the first draft's 215 is corrected.
- Code references re-checked by grep against the extracted head `491dcaea`: `Engine.rank(self, request: EngineRequest)` at `src/ellington_systems/engine.py:237`; `melody_target=-1`, `bass_target=-1`, `ref=None` at `engine.py:288-290`; `EngineRequest` at `models.py:22`, `RankedVoicing` at `models.py:110`, `Voicing` at `models.py:234` with `dots` (253) and `fingering` (271); `Corpus.from_plugin_clone` at `corpus.py:54` and `from_env` at `corpus.py:102`.
- Issue and PR references re-checked with `gh`: ellington-systems#12 exists (EPIC: Ellington web application on the GeoDjango Simple Template); ellington-systems PRs #17, #18, #19 exist; ellington-web PRs #74, #234, #245, #270, #279, #281, #288 are MERGED (with mergedAt dates as stated in the plan), and #242, #247, #249, #251, #253, #254 are CLOSED with mergedAt null; the plan states each of those states as checked; plugin PR #403 is MERGED (2026-06-08) and PR #595 is MERGED (2026-06-25). Issues #4, #5, #57, #60, #70, #71, #86, #232, #243 in ellington-web were fetched with bodies and comments before quoting; the long bodies and comments of #57 and #243 were truncated at 2,000-4,500 characters in the fetch, so quotes from them come only from the portions read.
- File paths re-checked with `gh api`: `ellington-web/app/ellington_web/ingest/charts_common/normalize.py`, `.../ingest/irealpro/parser.py`, `.../apps/styles/comparator.py` exist; `.../apps/engine_rules/` contains `firing.py`, `slicer.py`, `alignment.py`; `docker/requirements.txt` contains `celery[redis]` and `pyRealParser==0.1.0`.
- Package claims re-checked against the PyPI JSON endpoint on 2026-11-04: `pyRealParser`, `PyGuitarPro`, `basic-pitch`, `demucs`, `django-q2` exist (HTTP 200); `python-ireal-pro`, `libbb`, `guitarpro` returned HTTP 404 and are described in the plan as not found / UNVERIFIED. Which merged PR delivered each file under `apps/audio/` on `ellington-web` `develop` was not traced and is marked UNVERIFIED in the plan.

**writing-claims:3 — Unquantified claims grounded.** Checked.
- The first draft's "htdemucs is current best-in-class", "Basic Pitch is production-ready", and the cost rates cited no source in the plan. The plan now states the cost figures are unsourced assumptions and removes the unsourced superlatives; model choices are described through the recorded issues instead.
- The first draft's time estimates are withdrawn as ungrounded.
- A line in the first draft's self-review about "Django admin is a staff tool" did not describe this PR (it came from a different change's review) and is removed.

## Lead review (Lead's adversarial pass -- did the Junior actually solve this?)

**software engineering domain:**

- *Approach fit:* A plan doc is still the right artifact for a multi-week body of work, but only if it agrees with the recorded work. The first draft did not; the reconciliation in this revision is the substantive change. Where the sources disagree with each other (for example separation sequencing in #60 versus #232, or LLM runtime in #5 versus PLAN.md), the plan shows both and does not pick.
- *Affirmative standard: the doc gives the owner enough to decide "go / no-go / different direction."* Holds only for the listed open questions; the plan makes no decision on the owner's behalf.
- *Affirmative standard: the doc does NOT commit us to code that would need to be undone.* Holds. Zero code changes. Where the plan proposes something (a voicing-rank comparison as possible v2 evidence) it is labelled a proposal.

**tech lead domain:**

- *Approach fit:* The sequencing table now maps first-draft slices onto existing issues and PRs instead of presenting a fresh schedule.
- *Residual risk:* Recorded decisions are quoted from issues whose authorship cannot be confirmed from GitHub alone. The plan marks this; the owner is the only one who can ratify.

**Dismissals from peer review:**
- "No benchmark data on pitch-engine guitar accuracy in the doc." — dismissed. The plan lists a prototype benchmark as a follow-up artifact; doing it inside a plan doc would be over-scoped.

## Verification performed on this revision

- Every issue number, PR number, file path and package name added or changed in `plans/audio-pipeline-plan.md` was checked in the same work cycle as listed under writing-claims:2.
- Markdown tables were re-read for broken cells (literal pipes inside quoted text are escaped).
- The revised files were diffed against the versions at head `491dcaea`; the diff touches only these two files.
- Added propagation-deferred frontmatter to satisfy the ticket-propagation guard (claude-configs-public#251, the reference the guard's own message gives); no comments were posted on the cited issues.
- Second revision: every pull request cited in the plan was re-checked with `gh pr view` (state and mergedAt) before the wording was changed; the `apps/audio/` file list and the pYIN docstring in `apps/audio/pitch.py` were confirmed with `gh api` on `ellington-web` `develop`; "canonical" and "ratified" were re-read in the plan and kept only inside quotes or as the open question; the same-name package sentence was checked against `src/ellington_web/` here and `app/ellington_web/` in `ellington-web`.
- Not done: no tests were run after the revision (docs-only); which merged PR delivered each file in `apps/audio/` was not traced; the sources behind the quoted "recorded" decisions were not re-read after the quoting pass beyond the issue fetches done for this revision.

## Findings

| ID | Priority | Description | Resolution |
|----|----------|-------------|------------|
| F1 | P2 | First draft claimed `python-ireal-pro`, `libbb`, and a Rust `guitarpro` package without verification. | Checked against PyPI on 2026-11-04: those names return 404 and are now marked not found / UNVERIFIED; the package actually used (`pyRealParser`) is named. |
| F2 | P3 | Cost estimates cite no source; also, under the recorded layout (owned GPU nodes, local LLM) a pay-per-inference model may not apply. | Marked as unsourced assumptions (UNVERIFIED) in the plan. |
| F3 | P3 | First draft's findings table started at F12 with no F1-F11. | Renumbered F1 onward. |
| F4 | P2 | First draft's self-review ended with an authorship attribution line. | Removed. |
| F5 | P2 | Plan did not relate the audio app to the existing `ellington_web` Django app in this repo. | Plan now states the layout is open pending confirmation and that this repo's web layer is the pedagogue layer, not the audio app. |
| F6 | P3 | Branch is one commit behind `develop` (PR #19). | Not addressed here by instruction; no sync was done. |
| F7 | P3 | No driving issue named. | Plan header names ellington-systems#12 (sub-epic 2). |
| F8 | P2 | Two test files exist only in a local clone. | Out of scope of this PR; ticket being filed, no number yet. |
| F9 | P1 | First draft conflicted with recorded work (chart schema, queue, deploy, comparator, LLM runtime). | Reconciled in the plan; items that remain genuinely open are listed under "Decisions". |
| F10 | P2 | Plan cited ellington-web PRs #242, #247, #249, #251, #253, #254 as the built comparator chain; all six are CLOSED, not merged. | Plan now states each as CLOSED, points to the code on `ellington-web` `develop` under `apps/audio/` and to MERGED #270, #279, #281, #288. |
| F11 | P3 | "canonical" (chart schema) and "ratified" (#243) read as plain fact while the chart schema and ratification are open. | Reworded to "existing" and to a sourced statement with Dheeraj's ratification UNVERIFIED. |

No P1 findings remain open in this artifact. Remaining open items are decisions for the owner, listed in the plan.
