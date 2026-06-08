# Vendored plugin snapshot

This directory will hold a frozen snapshot of the
[musescore4-chord-library-plugin](https://github.com/siege-analytics/musescore4-chord-library-plugin)
data corpus and schemas at SHA
`628ed30fbb03bbf015f167ce8962edef8c0e5273` (tip of `develop` at the moment
the feasibility spike was scoped — see ticket [#1](https://github.com/siege-analytics/ellington-systems/issues/1)).

## Status: empty pending plugin LICENSE

Vendoring is deferred until the plugin's Apache 2.0 LICENSE PR
([musescore4-chord-library-plugin#403](https://github.com/siege-analytics/musescore4-chord-library-plugin/pull/403)) merges.
At plugin SHA `628ed30`, the plugin source carries no LICENSE file. Copying
unlicensed content into Ellington would be on weak legal ground.

Until then, tests that need plugin data read from a live local clone via
the `ELLINGTON_PLUGIN_PATH` environment variable. See
`tests/conftest.py:plugin_clone_path`.

## Once #403 merges

This directory will be populated with:

- `masters.json` — at SHA `628ed30`
- `voicings.json` — at SHA `628ed30`
- `schema/masters.schema.json` — at SHA `628ed30`
- `schema/voicings.schema.json` — at SHA `628ed30`
- `NOTICE` — attribution per Apache 2.0 §4 requirements

Vendoring is a separate PR. The engine's bootstrap path will switch from
the env-var lookup to loading from this directory.
