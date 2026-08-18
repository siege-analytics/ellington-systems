# Design note: master roster + pedagogue confirmation forms

Authorizes the work on `feat/roster-and-confirmations` (commits `3601f5c`, `a47754f`, `543aa56`).

## Source

The design source is the session brief from Dheeraj to Craft Agent session `260708-copper-coyote` on 2026-07-08. Two deliverables:

1. **Confirmation forms/quizzes for pedagogues** — forms that present the s5 usage_notes classifications (granularity levels, function_roles) to guitar teachers for validation. "Does this accurately describe what [master] teaches about [chord_quality]?" The pedagogue confirms, corrects, or adds nuance. Delivery target: lightweight Django view (Google Forms fallback if pedagogues resist logging in).

2. **Master roster pages** — a page per master that explains: who they are and their approach to jazz guitar; a quantitative model of their approach (the granularity bucket distribution); links to every lesson/book involving them.

## Approach chosen

Ship both as an **optional Django app** installed under `ellington-systems[web]`, layered on top of the pure engine library at `src/ellington_systems/`. The engine remains importable without Django. Data ingested from the sibling musescore4-chord-library-plugin pipeline (session `260703-pure-harbor`) via a `manage.py load_corpus` command against three JSON/JSONL files: `masters.jsonl`, `usage_notes.jsonl`, `granularity_index.json`.

Two Django apps:
- `ellington_web.roster` — `Master`, `Book`, `UsageNote`, `GranularityBucket` models; list + detail views; bucket-distribution bar chart.
- `ellington_web.confirmations` — `Pedagogue` (linked to auth user), `Confirmation` (confirm/correct/nuance/rereview verdict, unique per pedagogue+note); login-gated review views.

## Alternatives considered and rejected

- **Google Forms only:** rejected because the confirmations feed the engine long-term as a training signal; owning the data model is required.
- **Separate repo for the web layer:** rejected because it would fragment the corpus contract with the pipeline agent.
- **Django as a required (non-optional) dep:** rejected because it would infect the engine's install surface for consumers who only want `Engine.rank()`.

## Falsifiable premises

- The pipeline export shape (fields, slug conventions) is stable enough to bind Django models to it directly. **Falsifier:** pipeline emits new required fields the loader doesn't tolerate. Mitigated by making the loader tolerant of unknown JSON keys (they are ignored) and by writing 13 tests around the loader that will catch shape drift.
- Pedagogues will consent to Django-admin-seeded accounts for the first round of validation (no self-signup required in this slice). **Falsifier:** first pedagogue outreach in Q4 2026 hits resistance, forcing a magic-link invite flow. Mitigated by the invite flow being a scoped follow-up slice (F1 in the self-review Findings).
- Bucket distribution as a quantitative model is meaningful to guitar teachers. **Falsifier:** first pedagogue reviews come back saying the buckets themselves are the wrong shape. In that case the confirmation form is the correction channel — the design accommodates its own falsification.

## Rollback

Both apps are additive and gated behind the `[web]` extra. Rollback = revert the three commits; engine tests continue passing because they never imported `ellington_web.*`. Local DB (`ellington.sqlite3`) is gitignored. No production surface exists yet.
