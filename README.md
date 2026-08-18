# ellington-systems

Engine and supporting services for **Ellington** — a multi-format practice and feedback platform for guitarists.

Ellington ingests existing chart formats (iReal Pro, Band-in-a-Box, MuseScore, GuitarPro), records the user's performance against them, isolates the user's track from the backing, transcribes it to MIDI, compares it to the chart's intent, and produces personalised coaching that respects the player's physical and cognitive context — including motor-rehab and stroke-recovery scenarios.

The engine analyses both axes:

- **Harmonic** — voicing choice, chord-tone substitution, voice-leading, master voicing styles
- **Melodic** — single-line phrasing, target-tone selection, linear language, master melodic styles

This repository hosts the Python implementation. The systems-with-three-layers data model — masters, principles, works, payload kinds — is the same one curated by [`siege-analytics/musescore4-chord-library-plugin`](https://github.com/siege-analytics/musescore4-chord-library-plugin). Ellington is a derived product: it consumes that plugin's masters corpus as its source of truth, runs the schema-designed runtime against it, and adds the audio, ingestion, comparison, and coaching layers the plugin doesn't cover.

## Status

Pre-spike. The first deliverable is a feasibility spike for the engine port: see [issue #1](https://github.com/siege-analytics/ellington-systems/issues/1). No installable artifact yet.

## Tuning scope

Tuning-agnostic from day one. 6-string standard, 7-string (Van Eps high-A or low-A/B), baritone, custom — the engine discovers string count and pitches from the request. No 6-string assumptions anywhere.

## Repository conventions

- **`main`** — protected, curated stable subset. PR-only. Promoted from `develop` once an artifact is genuinely stable.
- **`develop`** — default branch, origin of all work. Feature branches are cut from here.
- Branch naming: `feat/<issue>-<slug>`, `fix/<issue>-<slug>`, `docs/<issue>-<slug>`.
- Every commit references its driving issue.

## Web layer (roster + pedagogue confirmations)

Ellington ships an optional Django app that renders master roster pages
(bio, granularity-bucket distribution, book list) and hosts the pedagogue
confirmation workflow over the s5 usage-note classifications.

```bash
pip install -e '.[web,dev]'
python manage.py migrate
python manage.py load_corpus data/corpus/
python manage.py createsuperuser
python manage.py runserver
```

`load_corpus` expects three files (produced by the
musescore4-chord-library-plugin pipeline):

- `granularity_index.json`
- `masters.jsonl`
- `usage_notes.jsonl`

Pedagogues review notes at `/confirm/<master-slug>/`. Only users with a
linked `Pedagogue` profile (create one in the Django admin) may submit
verdicts.

## License

Apache 2.0. See [LICENSE](LICENSE).
