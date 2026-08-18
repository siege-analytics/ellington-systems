# Self-Review: docs/audio-pipeline-plan-doc

Working as: software engineer, tech lead

Covers one new file: `plans/audio-pipeline-plan.md`, a research + architecture plan for the Ellington audio pipeline (chart ingest → recording → separation → transcription → comparison → coaching). No executable code changes.

## Assumptions

Domain(s): software engineering
Geospatial cross-cut: no
Goal source: Dheeraj's pushback on 2026-07-08 flagging "test workflow for uploading tracks and parsing them" as a real gap — enumerated as follow-up in my four-priority reply, promoted to explicit ordering when Dheeraj said "pick and go" via saved feedback preference.
Plan reference: plans/audio-pipeline-plan.md (this artifact reviews *that* doc; there is no separate design note for a plan doc)
Pre-author-inventory: NONE
Trivial-against-state: Docs-only diff. `git diff develop..HEAD --stat` shows one new file, `plans/audio-pipeline-plan.md`, plus this artifact. No `.py`, `.sh`, `.js`, `.ts`, `.sql`, or executable file is touched.
Investigate-artifact: TRIVIAL
Pre-mortem-artifact: TRIVIAL
Hostile-review-artifact: WAIVED
Project-contribution: Provides a concrete map of the audio side of Ellington so that when we start building it we're not making architectural decisions under deadline pressure. Enumerates six stages (chart ingest, recording, separation, transcription, comparison, coaching), names specific libraries (Basic Pitch, htdemucs, music21, PyGuitarPro, django-q2) with trade-offs, gives cost estimates at 1k-recordings/month volume (~$5-10/month marginal), sequences seven implementation slices with time estimates, and enumerates four genuinely-blocking decisions Dheeraj needs to make (deploy target, motor-rehab v1 vs v2, multi-track uploads, LLM coaching budget).

## Trivial-investigation declaration

Applies to both Investigate-artifact: TRIVIAL and Pre-mortem-artifact: TRIVIAL above.

Category: Prose-only planning document. No code, no schema, no config, no infrastructure.
Cannot produce error: Because a markdown file under `plans/` is not loaded by any code path in the repo. `grep -rn "audio-pipeline-plan" src/ tests/` returns zero matches. The file exists only for human consumption.
Evidence: `git diff develop..HEAD --stat` shows `plans/audio-pipeline-plan.md` and `plans/self-review-audio-pipeline-plan-doc.md` as the only changes. `python -m pytest` still passes 215 tests + 9 skips against the branch — same as develop.
Falsification: Would be falsified if adding a markdown file to `plans/` broke something. Sanity check: `pytest` passes.

## Peer review (Junior's checklist -- mechanics, correctness, craft floor)

Shelves engaged: writing-prose:1 (claims grounded in specific tools / prices / model names, not vibes), writing-claims:2 (cost estimates cite actual per-inference rates, sequencing cites specific slice sizes), writing-claims:3 (model choices name specific alternatives with trade-offs).

**writing-prose:1 — Grounded claims.** Checked.
- Every model recommendation names the specific library (Basic Pitch, htdemucs, music21, PyGuitarPro, django-q2) and the specific trade-off that led to picking it.
- Cost estimates use concrete per-inference rates from published Replicate pricing (2026 rates for demucs / basic-pitch models) rather than "cheap" / "not too much."
- Sequencing gives per-slice time estimates (2-3 days, 1 week, etc.) that reflect actual scope of the described work.
- Each stage has a "Falsifiable premise" section naming what evidence would invalidate the recommendation.

**writing-claims:2 — Countable claims verified.** Checked.
- "215 tests still pass" verified: `python -m pytest 2>&1 | tail -3` shows `215 passed, 9 skipped`.
- "Zero new files touched outside `plans/`" verified: `git diff develop..HEAD --stat` shows only two `plans/` files.
- Cost totals ($5-10/month at 1k recordings) computed inline in the doc — reader can check the arithmetic.

**writing-claims:3 — Unquantified claims grounded.** Checked.
- "htdemucs is current best-in-class for source separation" — grounded in the public MDX challenge leaderboards; not asserted without a reference model to check against.
- "Basic Pitch is production-ready" — grounded in Spotify's public deployment and the MIT license, not vibes.
- "Django admin is a staff tool, not pedagogue-facing" — grounded in the previous PR's model where only staff can create Pedagogue accounts.

## Lead review (Lead's adversarial pass -- did the Junior actually solve this?)

**software engineering domain:**

- *Approach fit:* A plan doc, not a spike, is the right first artifact for a multi-week body of work. The alternative (start coding immediately) would repeat the "engine spike" pattern — fine for a bounded feasibility test, wrong for a pipeline with six independent stages that each need library selection.
- *Affirmative standard: the doc gives Dheeraj enough to decide "go / no-go / different direction."* Holds. The four blocking decisions are named explicitly and separated from the rest. If Dheeraj answers those four, the rest is proceed-with-defaults.
- *Affirmative standard: the doc does NOT commit us to code that would need to be undone.* Holds. Zero code changes. Every recommendation is qualified as "recommendation" or "current best guess" with a falsifiability clause.

**tech lead domain:**

- *Approach fit:* Sequencing (steps 1-4 to end-to-end demo in ~3 weeks; steps 5-7 as enhancements) is a defensible chunking. Each slice has independent value.
- *Sequencing assumption:* Plan doc after web-layer PRs, not before, was the right order because the web layer was mostly built already (roster + confirmations + invite + design) and shipping those made pedagogue outreach possible in parallel with audio-pipeline planning.

**Dismissals from peer review:**
- "No benchmark data on Basic Pitch guitar accuracy in the doc." — dismissed. The plan doc explicitly lists a prototype benchmark as a follow-up artifact needed *before* implementing step 2. Doing the benchmark inside the plan doc would be over-scoped for a research document.

## Findings

| ID | Priority | Description | Resolution |
|----|----------|-------------|------------|
| F12 | P3 | Cost estimates use 2026 Replicate rates. They will drift. | Reader-obvious; the doc says "order of magnitude" not "commit." |
| F13 | P2 | Four decisions genuinely block Dheeraj to answer. This is the point of the doc, but if he doesn't answer, we stall. | By-design. The saved `feedback_pick_and_execute.md` rule doesn't apply here — these are aesthetic / budget / scope decisions I cannot infer. |

Zero P1 findings.

Self-Review author: Craft Agent (session `260708-copper-coyote`)
