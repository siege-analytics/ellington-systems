# Ellington audio pipeline: research + architecture plan

Working as: software engineer, tech lead
Status: **plan doc, not implementation**. No code lands with this.
Purpose: give Dheeraj a concrete map of the audio side of Ellington so that when we start building it we're not making architectural decisions under deadline pressure. The pedagogue-facing web layer (roster + confirmations + invite flow + design pass) is orthogonal to this and continues in parallel.

## What Ellington's audio pipeline is supposed to do

From the repo `README.md`:

> Ellington ingests existing chart formats (iReal Pro, Band-in-a-Box, MuseScore, GuitarPro), records the user's performance against them, isolates the user's track from the backing, transcribes it to MIDI, compares it to the chart's intent, and produces personalised coaching that respects the player's physical and cognitive context — including motor-rehab and stroke-recovery scenarios.

That's five distinct stages, plus a sixth (coaching) that consumes the output. Each stage has real technical decisions.

## Stage-by-stage decomposition

### 1. Chart ingest

**Input:** a chart file uploaded by the user (or referenced from a URL). Supported formats:

| Format | Extension | Notes |
|---|---|---|
| iReal Pro | `.html` or `.txt` payload; iRealPro URL scheme | Text-based, easy to parse. Community `python-ireal-pro` libraries exist. |
| Band-in-a-Box | `.SGU`, `.MGU`, `.SG*` | Proprietary binary. `libbb` / community parsers exist but coverage is partial. |
| MuseScore | `.mscz` (zip of MusicXML) | Standard. `music21` parses MusicXML natively. |
| GuitarPro | `.gp`, `.gpx`, `.gp3-.gp7` | Multiple format generations. `PyGuitarPro` covers `.gp3-.gp5`; `.gpx`/`.gp7` need `guitarpro` (Rust binding) or a custom parser. |

**Design decision:** normalize all four into a single internal representation. Options:
- (a) **MusicXML as the canonical intermediate.** `music21` reads MusicXML directly, converts many other formats to it, and gives us an object model we can query. Trade-off: MusicXML is verbose and doesn't cover iReal's chord-shorthand grammar perfectly.
- (b) **Our own `ChartDoc` pydantic model.** Fine-grained control, but we own the mapping from every input format. More engineering, better fit.

**Recommendation:** (b) — a `ChartDoc` pydantic model with (bars, chords, section markers, tempo, key, time signature, form). Use `music21` as one of several parsers that emit `ChartDoc`. Reason: Ellington's engine already speaks pydantic; forcing MusicXML through the stack would create a second lingua franca.

**Falsifiable premise:** users mostly bring iReal + MuseScore charts. If real usage is 80% GP, we should invest more in GP parsing.

**Follow-up ticket outline:** three sub-tickets, one per non-MuseScore parser + one for `ChartDoc` schema.

### 2. Performance recording

**Input:** user records themselves playing against the chart backing.

**Design decisions:**
- **Where does the recording happen?** Three options: (a) in-browser via `MediaRecorder` API, (b) in a native/mobile app, (c) upload of a file recorded elsewhere.
- **Latency compensation.** If the user hears the backing through headphones and plays into a mic, we know the mic's arrival time relative to the backing. If they play on speakers, we get feedback + we need to source-separate. If they play a direct-input electric guitar into an interface, no separation needed.

**Recommendation:** ship (c) first — upload existing recordings paired with the chart. It's the smallest surface, unblocks the whole transcription/comparison chain, and gives us data to test the rest of the pipeline. Add (a) after the transcription stage is working end-to-end. Punt (b) until there's a signal a native app is worth the multi-month investment.

**Falsifiable premise:** users have existing recordings they want feedback on. If they only want to record inside Ellington, (c) is a waste. Mitigation: (c) is a week of work, not a month.

### 3. Source separation

**Input:** stereo/mono mix of backing + user's guitar.
**Output:** isolated user-guitar stem.

**Design decisions:**
- **Model choice.** Demucs (Meta) is the current SotA for source separation and has a `guitars` model in the community fork. Spleeter (Deezer) is older, faster, and worse at guitar. htdemucs is the current best-in-class.
- **Runtime.** Demucs runs on GPU comfortably (0.5x realtime on an M-series Mac; faster on CUDA). CPU-only is 3-10x realtime, tolerable for async jobs but not for interactive.
- **Where do we run it?** (a) On the user's device (WASM / Core ML / MPS — complex, portable), (b) on a server (simple, needs a GPU box or model-inference API).

**Recommendation:** server-side htdemucs on a modest GPU (or the Replicate / RunPod inference APIs while volume is low), with a background job queue. Users upload, the recording gets separated in the background, results appear when done. Skip separation entirely for direct-input recordings (Ellington asks the user during upload).

**Falsifiable premise:** htdemucs is good enough for guitar to serve the transcription stage. If it leaves too much drum bleed on the guitar stem, transcription accuracy drops. Test: pull 20 recordings across genres and measure transcription error rate with and without separation.

### 4. Transcription

**Input:** isolated guitar stem (mono audio).
**Output:** MIDI or note-event stream (pitch, onset, offset, velocity).

**Design decisions:**
- **Model.** For polyphonic guitar transcription: Basic Pitch (Spotify, MIT license, fast, decent). MT3 (Google, better quality, heavier, TensorFlow-2 model). Onsets & Frames (older, piano-specific, don't use). A guitar-specific model like `hFT-Transformer` for guitar tablature exists in academic prototypes.
- **Tablature vs MIDI?** Guitar-specific value: if we know it's a guitar, we can output fret+string not just pitch. Basic Pitch does not; MT3 does not; the academic guitar-transformer does but is not production-ready.

**Recommendation:** Basic Pitch as the first transcriber. Fast (0.3x realtime CPU), production-ready, decent guitar performance. Output: MIDI note events. Fret+string inference is a v2 problem — from MIDI pitch + tempo + physically-plausible-position constraints we can infer plausible fingerings (that's the direction the engine already understands via `RankedVoicing`).

**Falsifiable premise:** Basic Pitch's guitar accuracy is good enough that the coaching stage can produce useful feedback. Test: transcribe 20 recordings with known ground truth (multi-tracked studio takes), measure onset F1 and pitch accuracy.

### 5. Comparison

**Input:** transcribed performance note-events + `ChartDoc` (the intent).
**Output:** a structured diff — timing errors (rushed / dragged), pitch errors (wrong chord tone, wrong voicing), rhythmic errors (missing / extra notes), voicing choices (which voicings from the chart's `RankedVoicing` set did the user actually play).

**Design decision:** this is where the engine library the spike built (`Engine.rank()`, `RankedVoicing`) becomes load-bearing. Given a bar's chord symbol and the user's played notes, `Engine.rank()` produces the ordered set of "master voicings" for that chord. We compare user's played pitches to the top-N voicings; the match / near-miss / miss verdict is the comparison output.

**No new library needed** — this stage is native Python against the engine.

**Falsifiable premise:** the engine's `RankedVoicing` output actually covers the voicings guitarists play. If the top-20 misses common voicings, we need to widen the engine's search or add a "user voicing was outside the ranked set — here's what it approximates" branch.

### 6. Coaching output

**Input:** the comparison diff.
**Output:** actionable feedback to the user, respecting their physical/cognitive context.

**Design decisions:**
- **Voice.** Coaching text should reflect the master voicing style of whichever master's approach the user is being coached against. E.g. Ted Greene coaching should reference chord-melody density; Joe Pass coaching should reference walking-bass integration.
- **Motor-rehab/stroke-recovery context.** README explicitly calls this out. In practice: the coaching tone should be encouraging, chunked, achievable-next-step focused; it should never require a full-hand voicing when the user's context indicates limited mobility. This is a data-model thing (user profile with capability flags) + a coaching-generation constraint (LLM prompt or template).
- **LLM vs template.** Templated coaching is deterministic, cheap, and shippable this quarter. LLM coaching is richer but non-deterministic and needs safeguards (jailbreak, hallucinated advice). Ship templated first; add LLM per-master-voice as v2.

## Cross-cutting architecture concerns

### Storage

- **Uploads (chart file + recording).** Object store (S3-compatible). Local dev: MinIO or plain filesystem. Prod: DreamHost bucket (source already active) or S3.
- **Intermediate artifacts (separated stems, MIDI).** Same store. Named by upload-hash for idempotency.
- **DB.** SQLite in dev / Postgres in prod. Schema additions: `Recording`, `Chart`, `PerformanceRun` (foreign keys to both, plus separation + transcription + comparison outputs). All engine-independent — the audio side is its own Django app.

### Job queue

- Separation and transcription are async (seconds to minutes each).
- Options: Celery + Redis (heavy but standard), django-q2 (lighter, fine for our volume), or plain background tasks via `Threading` (no, don't).
- **Recommendation:** django-q2 for v1. Volume is low, ops surface is minimal.

### Deploy target

- Currently: no deploy exists.
- Web layer is trivially deployable anywhere Python + SQLite/Postgres run. DreamHost is the active source; siegeanalytics.com WordPress is separate.
- Audio pipeline needs a GPU or a cloud inference API. Options:
  - Rent a GPU box (RunPod, Lambda Labs, ~$0.30/hr while queue is busy)
  - Use inference-as-a-service (Replicate, Modal, per-request pricing)
  - Local Mac Studio if this stays personal/small
- **Recommendation:** Replicate for demucs + basic-pitch until monthly cost exceeds $200, then reconsider.

### Cost estimates (order of magnitude)

Assumptions: 100 users, each uploads 10 recordings/month, each recording is 3 min.

- Separation: 100 * 10 * 3 * $0.001/min inference = **$3/month** at Replicate rates for demucs.
- Transcription: 100 * 10 * 3 * $0.0005/min = **$1.50/month** for Basic Pitch.
- Object storage: ~30GB/month uploads @ $0.023/GB = **$0.70/month** on S3.
- Django hosting: existing.
- Total marginal: **~$5-10/month** at 1k recordings/month.

Reasonable at any scale I can envision short-term. This is not a cost-constrained architecture.

## Security surface introduced by audio pipeline

- **File upload endpoint.** New attack vector: malicious files (huge sizes, embedded exploits in audio decoders, path-traversal in stored filenames). Mitigations: enforce size limit; use `magic` / mime-type check + extension check for chart files; store uploads under uuid names, never user-supplied names; use `ffmpeg` in a subprocess with fixed args; drop the raw upload once separated / transcribed.
- **User-supplied audio triggers downstream ML model inference.** Model inference itself is not exploitable in the classical sense, but a crafted audio file could cause OOM or long inference. Mitigations: cap duration (say 15 min), cap file size, run inference in a resource-bounded subprocess / container.
- **Coaching output.** If LLM coaching lands, prompt-injection via user-supplied "notes about my playing" text is real. Mitigations: content-length limits, output moderation, user-controlled disclaimer.

Each of these is a hostile-review-worthy concern at implementation time.

## Sequencing

Recommend building in this order — each slice is shippable and unblocks the next:

1. **Upload + storage** (2-3 days). Django model for `Chart` + `Recording`, upload views, object-store wiring. No processing yet — pedagogues can upload and view. Slice-alone value: manual review of user submissions.
2. **Transcription only, direct-input recordings only** (1 week). Skip separation. Basic Pitch on the raw recording. Store MIDI. Manual QA of results across 10-20 real guitar recordings.
3. **Comparison** (1 week). Wire transcribed MIDI to the existing engine's `Engine.rank()` and produce the structured diff. Store the diff. No coaching output yet — just "here are the discrepancies as data."
4. **Templated coaching output** (1 week). Given a diff + a target master's style, produce text feedback via templates. This is what a user sees.
5. **Source separation for mic'd recordings** (1 week). Add demucs step; enable users to upload full-mix recordings, not just direct-input.
6. **LLM coaching per master voice** (2+ weeks, later). v2. Requires prompt engineering per master + safety scaffolding.
7. **In-browser recording** (2 weeks, later). Only after we know users want it.

Total to a full end-to-end demo (steps 1-4): ~3 weeks of focused work. Steps 5-7 are enhancements.

## What decisions this doc DEFERS to Dheeraj

Genuinely blocking questions I cannot decide alone:

1. **Deploy target.** Where does Ellington-web actually live in production? DreamHost + a GPU box elsewhere? Modal for everything? This affects the object-store choice and the job-queue choice.
2. **Motor-rehab/stroke-recovery scope.** The README calls this out prominently. Is it a v1 feature (informs data model now) or a v2 feature (design around it later)? This changes whether `UserProfile` needs capability flags in the initial schema.
3. **Whether to accept multi-track / DAW-project uploads.** A Logic project or Reaper project has stems already separated. If we accept those we can skip separation entirely for pro users. Nice-to-have or scope creep?
4. **LLM budget.** If templated coaching feels flat, LLM coaching is the natural next step. Are you willing to spend, say, $50/month on Claude API for coaching output? Cheap either way at low volume.

Everything else in this doc I can proceed with defaults for.

## Follow-up artifacts this doc does NOT include

- Per-stage design notes (`ChartDoc` schema, `Recording` model, comparison-diff schema) — one per implementation slice
- Per-stage hostile-review artifacts — one per implementation slice
- Per-stage pre-mortems — one per implementation slice
- A prototype benchmark of Basic Pitch on 20 real guitar recordings — needed before committing to it as the transcription primitive

These are enumerated so that when we start implementing, the discipline artifacts are pre-scoped rather than invented under time pressure.
