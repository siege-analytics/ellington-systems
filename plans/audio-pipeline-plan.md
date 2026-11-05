---
propagation-deferred: reference-only plan doc; no comments are posted on the cited issues by this change
---
# Ellington audio pipeline: research + architecture plan

Working as: software engineer, tech lead
Status: **plan doc, not implementation**. No code lands with this.
Driving issue: [ellington-systems#12](https://github.com/siege-analytics/ellington-systems/issues/12), sub-epic 2 ("Audio pipeline"). Related open work in `siege-analytics/ellington-web`: epic [#60](https://github.com/siege-analytics/ellington-web/issues/60) (practice-feedback loop), [#70](https://github.com/siege-analytics/ellington-web/issues/70) (PDF/OMR ingest), [#71](https://github.com/siege-analytics/ellington-web/issues/71) (per-axis scoring), [#86](https://github.com/siege-analytics/ellington-web/issues/86) (chord detection), [#232](https://github.com/siege-analytics/ellington-web/issues/232) (audio analysis epic), [#243](https://github.com/siege-analytics/ellington-web/issues/243) (comparison contract).
Purpose: give Dheeraj a concrete map of the audio side of Ellington, reconciled with work already recorded in those issues, so that when building continues nobody makes architectural decisions under deadline pressure.

## Revision note (this revision vs. the first draft at `491dcaea`)

The first draft was written as if the audio side were greenfield. This revision reconciles it with the issues above. Changes:
- Adds a "Relationship to existing work" section and rewrites the stages, cross-cutting concerns and sequencing to point at what is already recorded, with quotes.
- Retires the new `ChartDoc` model (the canonical chart representation already exists as Django models in `ellington-web`; see Stage 1).
- Replaces django-q2 with the Celery stack that already exists.
- Corrects the `Engine.rank()` description to match the code (Stage 5).
- Marks the cost figures as unsourced assumptions and the package claims as verified or UNVERIFIED.
- Replaces the "four blocking questions" with the real blocking set, keeps two of the original four as deferrable, and quotes decisions already recorded. It does not answer any question.

Conventions in this document: "recorded" means written in a GitHub issue or in `ellington-web/docs/PLAN.md`; every such item was posted under the `dheerajchand` account, but much of it does not show Dheeraj's own words answering, so Dheeraj's ratification is **UNVERIFIED** unless stated. "UNVERIFIED" means I could not check it.

## What Ellington's audio pipeline is supposed to do

From the repo `README.md`:

> Ellington ingests existing chart formats (iReal Pro, Band-in-a-Box, MuseScore, GuitarPro), records the user's performance against them, isolates the user's track from the backing, transcribes it to MIDI, compares it to the chart's intent, and produces personalised coaching that respects the player's physical and cognitive context — including motor-rehab and stroke-recovery scenarios.

That is five distinct stages, plus a sixth (coaching) that consumes the output. The pedagogue-facing web layer (roster + confirmations + invite flow + design pass) already in this repo (`src/ellington_web/`, PRs #17-#19) is orthogonal to the audio side.

## Relationship to existing work

Where the audio code lives is **recorded but not yet confirmed** (see "Decisions" below). Epic #12 comment of 2026-06-08 ("Decisions locked") says: "Repo layout | (A) — separate `siege-analytics/ellington-web` (app) + `siege-analytics/ellington-web-manifests` (k8s)". Under that layout this repository (`ellington-systems`) is the engine library and the audio application lives in `ellington-web`, where the sub-epic "sub-4: audio pipeline (Demucs stem-separation + Basic Pitch transcription + timeline diff)" is [ellington-web#4](https://github.com/siege-analytics/ellington-web/issues/4) and the later audio epic is #232. This plan is kept in `ellington-systems` as a design reference only. If Dheeraj chooses a different placement (epic #12 Open Question 1), the "Relationship" table below must be revised.

| Plan topic | Already recorded (quote) | Where | Effect on this plan |
|---|---|---|---|
| Chart schema | "apps/charts/ (exists) — Songbook → Song → Section → Measure → ChordEvent ... ChordEvents are the ground-truth timeline" | ellington-web#60 | No new `ChartDoc`. Epic #12 names the intended schema "Master Timeline" (see Stage 1). |
| Practice/recording models | "apps/practice/ (exists) — BackingTrack, PracticeSession, Recording, AudioStem, ChordDetection, PracticeSegment" | ellington-web#60 | No new `Recording` / `PerformanceRun` models. |
| Job queue | "Celery + Redis runs in the `ellington` namespace alongside the web pods." | ellington-web#4 | Use Celery, not django-q2. `docker/requirements.txt` in `ellington-web` lists `celery[redis]`. |
| Source separation | "Sub-4 Option B/C — Demucs source separation for mixed user uploads; **required for shipping**" | ellington-web#60 (Phase 5) | Agrees on htdemucs; sequencing differs (Stage 3). |
| Transcription | "Recommendation: ship with pYIN for v1 (no new heavy deps, librosa is already in requirements), document the monophonic limitation, file basic_pitch as the v2 upgrade" | ellington-web#232 | Basic Pitch is v2, not the first transcriber (Stage 4). |
| Chord detection | "Primary engine: madmom" | ellington-web#86 | Separate from note transcription (Stage 4). |
| Comparison | "Granularity-split: slice-level observation (deterministic audio facts) vs per-rule verdict (rules attach to observations)." | ellington-web#243 (ratified; see plugin PR #595 per that thread) | Comparator is firing-rule based; `Engine.rank()` is not the built path (Stage 5). |
| Scoring | "Per-axis scoring (not weighted aggregate)" and "No aggregate score in v1." | ellington-web#71 | Coaching input is per-axis (Stage 6). |
| LLM coach | "Deploy Llama 3.1 8B Instruct (4-bit / 8-bit quantized) via vLLM in the `ellington` namespace, GPU-node-pinned." | ellington-web#5 | Conflicts with a paid-API assumption in the first draft (Stage 6). |
| Deploy | "Domain \| `ellington.siegeanalytics.com`" and "GPU selector \| `node-role.kubernetes.io/gpu: \"true\"`" | ellington-systems#12 comment 2026-06-08 | "No deploy exists" in the first draft is wrong (Cross-cutting). |
| Uploaded-audio privacy | "User-uploaded `.mscz` / `.wav` / `.mid` \| Private to that user's account" | ellington-web#60 ("Audio-corpus legal posture (decided 2026-06-12)") | Added to the security section. |

## Stage-by-stage decomposition

### 1. Chart ingest

**Input:** a chart file uploaded by the user (or referenced from a URL).

| Format | Extension | Status and notes |
|---|---|---|
| iReal Pro | `.html` or `.txt` payload; iRealPro URL scheme | Implemented in `ellington-web`: ellington-web#232 says "`ingest/irealpro/parser.py` + `ingest/irealpro/importer.py` ... `pyRealParser` is in `docker/requirements.txt`." (`pyRealParser` exists on PyPI, checked 2026-11-04; the first draft's "`python-ireal-pro`" is not a PyPI package name I could find, HTTP 404.) |
| Band-in-a-Box | `.SGU`, `.MGU`, `.SG*` | Proprietary binary. ellington-web#232: ".SGU / .MGU are proprietary binary formats with no documented Python parser. Realistic path: users export from BIAB to MusicXML or MIDI before upload." (The first draft's "`libbb`" is not a PyPI package name I could find, HTTP 404; UNVERIFIED elsewhere.) |
| MuseScore | `.mscz` (zip of MusicXML) | Shipped: ellington-web#70 says "Phase 4-MS shipped on develop in PR #74 / commit 963107b". |
| GuitarPro | `.gp`, `.gpx`, `.gp3-.gp7` | `PyGuitarPro` exists on PyPI (checked 2026-11-04). The first draft's claim of a Rust-binding package named `guitarpro` for `.gpx`/`.gp7` is UNVERIFIED (no PyPI package of that name, HTTP 404). Whether GuitarPro ingest is planned in `ellington-web` is UNVERIFIED (I did not find an issue). |
| Scanned PDF | `.pdf` | Not in the first draft. ellington-web#70 integrates `omr-leadsheet` as the fourth ingest format; its Q3 decision is recorded as "Multi-page (album) from v1, not single-PDF." |

**Chart representation.** The first draft proposed a new `ChartDoc` pydantic model. That proposal is **withdrawn**. The canonical chart representation exists as Django models in `ellington-web` (`apps/charts`: Songbook → Song → Section → Measure → ChordEvent, per ellington-web#60), and ellington-web#86 refers to "the canonical chord layer shipped in Phase 4-MS (#73 / `ingest/charts_common/normalize.py`)". Epic #12 sub-epic 1 describes the intended schema as "**Master Timeline JSON schema + multi-format ingestion** ... Define the canonical `{measure, beat, target_harmonic, target_intervals, ...}` timeline". The relationship between "Master Timeline" and `apps/charts` (same thing, a serialization of it, or superseded) is **not stated in anything I read**. This is an open question for Dheeraj (see "Decisions").

**Falsifiable premise:** users mostly bring iReal + MuseScore charts. If real usage is mostly GP or PDF, invest accordingly.

### 2. Performance recording

**Input:** user records themselves playing against the chart backing.

**Recorded reality** (ellington-web#232): "Phone or GarageBand. Not DAW. Mixed mono with backing-from-speakers OR clean signal with backing-via-headphones." ellington-web#60: "either separate backing+player stems (the development path) or a mixed export (the realistic user path)".

**Recommendation (unchanged):** upload-first (a recorded file paired with a chart) is the smallest surface; in-browser `MediaRecorder` capture is later; a native app is not justified without a signal. This agrees with ellington-web#60 Phase 2 ("Practice-flow UI — upload recording, select song, tempo input → `PracticeSession` row").

**Falsifiable premise:** users have existing recordings they want feedback on. If they only want to record inside Ellington, upload-first is a waste.

### 3. Source separation

**Input:** stereo/mono mix of backing + user's guitar. **Output:** isolated user-guitar stem.

- **Model:** htdemucs, agreed in epic #12 ("Demucs HTDemucs stem-separation") and ellington-web#4 ("PIN to `node-role.kubernetes.io/gpu: \"true\"` via nodeSelector"). `demucs` exists on PyPI (checked 2026-11-04).
- **Where it runs:** the recorded layout is the cyberpower cluster's GPU nodes (epic #12 survey: "3 aegis (general-purpose) + 2 GPU nodes (cyberpower, magnum)"). The first draft's Replicate/RunPod/Modal options are not part of the recorded layout.
- **Sequencing differs between sources.** ellington-web#60 puts separation at Phase 5 and calls it "required for shipping". ellington-web#232 drops it from the first version: "Spectral subtraction dropped from v1", because "Canonical backing is deterministic; audio analysis is a **diff against known ground truth**", and it time-aligns the recording against a backing rendered from the chart. ellington-web#86 lists "Audio stem separation (Spleeter / Demucs)" as "deferred to Phase 3b-v2 followup". The plan therefore treats separation as a later enhancement, consistent with the first draft's own slice order.

**Falsifiable premise:** htdemucs is good enough for guitar to serve the next stage. Test: pull 20 recordings across genres and measure downstream error with and without separation.

### 4. Transcription and chord detection

**Input:** the (possibly separated) user signal. **Output:** note events and/or chord events aligned to the chart.

Three different recorded choices cover this stage:
- **Note-level pitch, version 1:** ellington-web#232: "Recommendation: ship with pYIN for v1 (no new heavy deps, librosa is already in requirements), document the monophonic limitation, file basic_pitch as the v2 upgrade once we have data on what real recordings look like."
- **Polyphonic transcription, version 2:** Basic Pitch (Spotify, MIT license; `basic-pitch` exists on PyPI, checked 2026-11-04). Epic #12 and ellington-web#4 name "Basic Pitch architecture" as the transcriber; ellington-web#232 and #243 reschedule it to v2.
- **Chord-level detection:** ellington-web#86: "Primary engine: madmom", fallback "librosa + chordino".

The first draft's recommendation of Basic Pitch as the first transcriber is **superseded** by the recorded v1 choice (pYIN). The fret/string inference idea (MIDI pitch + physically plausible positions) remains a v2+ idea; note that `RankedVoicing` carries no fret data (Stage 5), so this idea would use the corpus `Voicing.dots`, not `RankedVoicing`.

**Falsifiable premise:** the chosen engine's guitar accuracy is good enough for useful feedback. A prototype benchmark on 20 recordings with known ground truth is still needed before committing to any engine; it is not part of this PR.

### 5. Comparison

**Input:** detected performance events + the chart (ground truth). **Output:** a structured diff.

**What is recorded as built or ratified.** ellington-web#60: "The comparator (v0 already exists in `apps/styles/comparator.py`) produces a `CritiqueDraft`." ellington-web#232 workflow step 9: "Diff against per-beat firing-rule expectations from `engine_rules` (`firing.py`)". ellington-web#243 (ratified) defines `SliceObservation` (deterministic audio facts) and `RuleVerdict` (per-rule conformance). The PR chain for it (#247 contract dataclasses, #249 per-slice comparator, #251 verdict storage) is listed in #232; whether those PRs have merged is UNVERIFIED. ellington-web#71 scores six axes "independently per chord event, NEVER aggregated into a single number in v1."

**What `Engine.rank()` actually does** (checked against `src/ellington_systems/engine.py` and `models.py` at the pinned head):
- Signature: `Engine.rank(self, request: EngineRequest) -> EngineResponse` (`engine.py:237`). `EngineRequest` has `chord_symbol`, `tuning`, `master_id`, `category_filter`, `context` (`models.py:22`). There is **no input for played notes or pitches**.
- It scores candidate voicings for one chord symbol and tuning. Inside it, the score call passes `melody_target=-1`, `bass_target=-1`, `ref=None` (`engine.py:288-290`), meaning no melody or bass target constrains the ranking.
- `RankedVoicing` (`models.py:110`) carries `voicing_id`, `rank`, `score`, `payload_kind`, `score_components`, `applied_principles`. It has **no pitches, frets or fingering**. Pitches and frets live on the corpus `Voicing` record (`dots`, `notes`, `intervals`; `models.py:234`, `fingering` is an untyped `list[Any]`).
- Constructing an `Engine` requires a `Corpus` loaded from a plugin clone (`Corpus.from_plugin_clone`, `Corpus.from_env` reading `ELLINGTON_PLUGIN_PATH`; `corpus.py:54,102`). The plugin corpus is therefore a **deploy dependency** of anything that calls the engine (epic #12's body lists plugin PR #403, the Apache 2.0 licence PR, as a vendoring blocker "still" to merge; `gh pr view` on 2026-11-04 shows it MERGED on 2026-06-08, so that item in the epic body is stale).

**Consequence.** Comparing a performance to ranked voicings is **new work**, not "no new library needed" as the first draft said. It needs (a) a lookup from `voicing_id` to the corpus `Voicing` (pitches/frets), (b) a matcher from a set of played pitches to the nearest voicing (match / near-miss / miss), and (c) time alignment of detected events to chart slices. None of these exist in `ellington-systems`.

**Where it could fit (proposal, not a recorded decision).** ellington-web#243 reserves two v2 evidence variants, and ellington-web#232 lists "v2 voicing_match evidence" as outstanding. A voicing-rank comparison via `Engine.rank()` is a plausible basis for that v2 `voicing_match` evidence, alongside the built firing-rule comparator rather than replacing it. Whether to do that, and in which repository, is open (see "Decisions").

**Falsifiable premise:** the engine's ranked set covers the voicings guitarists play. If the top-N misses common voicings, widen the search or add a branch "played voicing was outside the ranked set; here is what it approximates".

### 6. Coaching output

**Input:** the comparison output (per-axis scores per ellington-web#71, verdicts per #243). **Output:** feedback respecting physical/cognitive context.

- **Templated / deterministic layer:** ellington-web#57 defines a typed reader, `coach_prose_fragments(selection, detected_voicings, candidate_function_roles)` returning a list of `CommentaryFragment`, that renders prose fragments from each Master's `usage_notes[]` with provenance. This is the recorded template-style layer; the first draft did not mention it.
- **LLM layer:** epic #12 sub-epic 4: "Deployable local LLM (Llama 3.1 8B or Mistral Nemo)". ellington-web#5: "Per-token cost is zero (local deployment); only latency budget matters." Epic #12 Open Question 4 is unanswered in that thread: "Local (deployable, predictable latency, no per-token cost — Llama 3.1 8B or Mistral Nemo on the same Mac mini / GPU box) vs commercial API (cheaper to start, harder to guarantee privacy for rehab-profile data)." `ellington-web/docs/PLAN.md` still says "llm coach worker (Phase 5: prose render via Anthropic API or local)". The first draft's assumption of a paid API is not the recorded direction. See "Decisions".
- **Motor-rehab / stroke-recovery context:** epic #12: "These are NOT UX afterthoughts. They drive frontend component choices, the LLM prompt-engineering layer, and the Master Timeline's `rehab_profile` extension." ellington-web#5 puts it per session: "per-session rehab_profile" and "`session.cognitive_load = HIGH`". The first draft put capability flags on a user profile; the recorded design is per session. Whether this is in the first data model is open (see "Decisions").
- **Voice:** the recorded design has the coach speak per Master ("Joe Pass would say…", ellington-web#71); this agrees with the first draft.

## Cross-cutting architecture concerns

### Storage

- **Uploads and intermediate artifacts.** Recorded: content-addressed files under Django `MEDIA_ROOT`; ellington-web#70: "Stored at `MEDIA_ROOT/pdf_upload/{sha256}.pdf`, content-addressed." The first draft's S3-compatible object store (MinIO locally, DreamHost bucket or S3 in production) is **not** recorded anywhere I read; it is an open design choice, not a decision, and nothing here depends on it for the next slices.
- **Data models.** No new `Recording` / `Chart` / `PerformanceRun` models. `apps/practice` (`BackingTrack`, `PracticeSession`, `Recording`, `AudioStem`, `ChordDetection`, `PracticeSegment`) and `apps/charts` exist in `ellington-web`; ellington-web#232 lists an "AudioVerdict storage model" (PR #251). The nearest equivalent of the first draft's `PerformanceRun` is `PracticeSession` plus its verdict rows; this mapping is my reading of the issue text, UNVERIFIED against the code.
- **Database.** Epic #12: "**PostGIS via PostgreSQL** — Postgres is the right relational store anyway". `ellington-web/docs/PLAN.md`: "PostGIS db ellington_web on default/db-postgis-master". SQLite remains only a local convenience in this engine repo.

### Job queue

- Separation, transcription and comparison are asynchronous. Celery with Redis already exists (`celery[redis]` in `ellington-web/docker/requirements.txt`; queues named in ellington-web#70: "NEW Celery queue 'omr-leadsheet' (separate from 'audio-analysis')"). The first draft's recommendation of django-q2 is **withdrawn**: adding it would create a second queue stack beside the existing Celery one. (`django-q2` exists on PyPI; that is not the issue.)

### Deploy target

- Recorded (epic #12 comments of 2026-06-08): a 5-node Kubernetes cluster ("3 aegis (general-purpose) + 2 GPU nodes (cyberpower, magnum)"), ArgoCD, Tekton, an internal registry at `cyberpower:32000`; layout "(A) — separate `siege-analytics/ellington-web` (app) + `siege-analytics/ellington-web-manifests` (k8s)"; domain `ellington.siegeanalytics.com`; "Auth (v1) | Django default; Authentik SSO deferred"; GPU pods pinned with `node-role.kubernetes.io/gpu: "true"`. Epic #12's later comment of 2026-06-09 reports "Sub-1 substrate live". Ratification of the "Decisions locked" table by Dheeraj is UNVERIFIED (the comment shows no visible reply; confirmation has been requested).
- The first draft said "Currently: no deploy exists" and recommended Replicate for demucs and basic-pitch. Both are **withdrawn**; the recorded deploy path uses the cluster's own GPU nodes.
- Not in the first draft: the plugin corpus is a deploy dependency of any engine call (Stage 5). Epic #12 says the web app "reads from a configured `ELLINGTON_PLUGIN_PATH`" (its stated reason, plugin PR #403, has since merged; whether another way of supplying the corpus has been decided is UNVERIFIED).

### Cost estimates (assumptions, UNVERIFIED)

The first draft gave "~$5-10/month marginal" at 1k recordings/month from per-minute rates ($0.001/min separation, $0.0005/min transcription, $0.023/GB storage). **None of those rates is sourced in this document**; treat them as unsourced assumptions. The arithmetic is internally consistent (100 users × 10 recordings × 3 min = 3,000 min; $3.00 + $1.50 + ~$0.70 ≈ $5.20), but the inputs are not verified, and under the recorded layout the GPU work runs on owned cluster nodes (and the LLM locally), so a pay-per-inference estimate may not apply at all. A real cost model, if wanted, is future work.

## Security surface introduced by audio pipeline

- **File upload endpoint.** New attack vector: malicious files (huge sizes, embedded exploits in audio decoders, path-traversal in stored filenames). Mitigations: enforce size limit; mime-type check + extension check for chart files; store uploads under uuid or content-hash names, never user-supplied names; run `ffmpeg` in a subprocess with fixed args.
- **User-supplied audio triggers downstream ML inference.** A crafted file could cause OOM or long inference. Mitigations: cap duration (say 15 min), cap file size, run inference in a resource-bounded subprocess / container. ellington-web#4 assumes "Audio upload size capped at 100MB".
- **Privacy of uploaded recordings.** Recorded posture (ellington-web#60, decided 2026-06-12): "User-uploaded `.mscz` / `.wav` / `.mid` | Private to that user's account | No [cross-user sharing]". The first draft did not cover this; implementation must honour it. Rehab-profile data adds a privacy concern when sent to an external API (epic #12 Open Question 4).
- **Coaching output.** If an LLM is used, prompt-injection via user-supplied "notes about my playing" text is real. Mitigations: content-length limits, output moderation, user-controlled disclaimer.

Each of these is a hostile-review-worthy concern at implementation time.

## Sequencing

The first draft's seven slices overlap work that is already queued. The table maps each slice to what is recorded; "status" is taken from issue text and is UNVERIFIED against merge state.

| First-draft slice | Already recorded | Residual work for this plan |
|---|---|---|
| 1. Upload + storage | ellington-web#60 Phase 2 (practice-flow UI) and #232 PR #245 "Form bank picker + render dispatch" | none beyond a check that it matches the privacy posture |
| 2. Transcription, direct-input only | #232 PR #242 "Pitch extraction pYIN v1"; #86 madmom chord detection | Basic Pitch is v2 (#240 v2) |
| 3. Comparison via `Engine.rank()` | #232 PRs #247, #249, #251, #253, #254 (firing-rule comparator chain) | voicing-rank evidence as a possible v2 `voicing_match` input (open, Stage 5) |
| 4. Templated coaching | #57 fragment reader contract; #71 per-axis scoring | not scheduled in what I read |
| 5. Source separation for mic'd recordings | #60 Phase 5; #86 deferred to 3b-v2 | later enhancement |
| 6. LLM coaching per master | epic #12 sub-epic 4; ellington-web#5 | runtime (local vs API) open |
| 7. In-browser recording | not found in what I read | later, only on demand |

First-draft time estimates ("2-3 days", "1 week", "~3 weeks to an end-to-end demo") are **withdrawn**: they were estimated without reference to the work above and should not be used for planning.

## Decisions

### A. Recorded decisions that bear on this plan (ratification UNVERIFIED unless noted)

| Topic | Quote | Source |
|---|---|---|
| Hosting layout, domain, GPU selection, v1 auth | "Repo layout \| (A) — separate `siege-analytics/ellington-web` (app) + `siege-analytics/ellington-web-manifests` (k8s)"; "Domain \| `ellington.siegeanalytics.com`"; "Auth (v1) \| Django default; Authentik SSO deferred" | ellington-systems#12 comment, 2026-06-08T20:52:40Z, https://github.com/siege-analytics/ellington-systems/issues/12#issuecomment-4653436377 |
| Stems versus mixed uploads | "C (mixed-stem source separation) is the product target; A (separate stems) is the dev stepping stone" | ellington-web `docs/PLAN.md` decision log, 2026-06-12 |
| Task layer for ingest | "Q1: Port to Python ... Celery integration is first-class" | ellington-web#70 comment, 2026-06-15T21:29:37Z, https://github.com/siege-analytics/ellington-web/issues/70#issuecomment-4712606705 |
| Comparison contract | "Ratified — porting to firing-spec §10" | ellington-web#243 comment, 2026-06-25T01:39:28Z, https://github.com/siege-analytics/ellington-web/issues/243#issuecomment-4795079873 |
| Chord detection engine | "Dheeraj-confirmed decision (2026-06-16):" followed by "Primary engine: madmom" | ellington-web#86 body |
| Note pitch, version 1 | "Recommendation: ship with pYIN for v1" | ellington-web#232 comment, 2026-06-25T01:26:50Z, https://github.com/siege-analytics/ellington-web/issues/232#issuecomment-4795025491 |

### B. Real blocking set (needs Dheeraj; this document answers none of these)

1. **Confirm or change the recorded layout (repo placement and deploy).** Question: is the "Decisions locked" table of 2026-06-08 (audio app in `ellington-web`, deployed on the cyberpower cluster) Dheeraj's decision, and does it still stand? Epic #12 Open Question 1 asks the same of repo placement. It decides where steps 1-4 are built and whether this document stays in `ellington-systems`.
2. **Canonical chart schema.** Question: for audio alignment, is the chart representation (a) the existing `ellington-web` `apps/charts` models, (b) a separate "Master Timeline" JSON schema as in epic #12 sub-epic 1, or (c) something new? No ruling found in any issue I read.
3. **Motor-rehab / stroke-recovery scope (original Q2), restated.** Question: is the per-session `rehab_profile` / `cognitive_load` design (ellington-web#5) part of the first data model that slice 1 creates, or added later? Recorded intent is only "first-class UX concerns"; no v1-or-later ruling found.
4. **Plugin corpus availability for deployment.** Question: how does a deployed comparator obtain the plugin corpus (today via `ELLINGTON_PLUGIN_PATH`; the licence PR #403 named in epic #12 has merged), given the engine cannot be constructed without it? Only relevant if a voicing-rank comparison is built (Stage 5): GitHub code search in `ellington-web` for `ellington_systems` and for `rank(` returned no hits on 2026-11-04 (search coverage is not guaranteed), which suggests the built firing-rule path does not call `Engine.rank()`.

### C. Deferrable (do not block steps through the first comparator)

- **Multi-track / DAW-project upload (original Q3).** Only affects the upload model and the separation step. Recorded so far: separate backing + player stems are accepted as a development path (ellington-web#60: "either separate backing+player stems (the development path) or a mixed export (the realistic user path)"). Native DAW project files (Logic/Reaper): no decision found. Question: accept them, or not?
- **LLM coaching: local model versus commercial API, and budget (original Q4).** Only affects the last coaching slice. Recorded: ellington-web#5 specifies a local Llama 3.1 8B via vLLM with zero per-token cost; epic #12 Open Question 4 is unanswered; `PLAN.md` says "Anthropic API or local". No dollar budget figure found. The first draft's "$50/month on Claude API" is withdrawn as a premise. Question: local or API for the coach, and if API, what budget?

Everything else in this document is either recorded above or has a default that can be revised without rework.

## Follow-up artifacts this doc does NOT include

- Per-stage design notes (comparison-diff schema if a voicing-rank comparison is built; any audio-specific models not already in `ellington-web`), one per implementation slice
- Per-stage hostile-review artifacts and pre-mortems, one per implementation slice
- A prototype benchmark of the chosen pitch engine on 20 real guitar recordings, needed before committing to it beyond v1
- A ticket for two test files that exist only in a local clone of this repo (`tests/webapp/test_roster_views.py` and `tests/webapp/test_confirmation_flow.py`, 8 tests); the ticket is being filed and has no number yet

These are enumerated so that when implementation starts, the discipline artifacts are pre-scoped rather than invented under time pressure.
