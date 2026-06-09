"""Corpus loaders for `masters.json` and `voicings.json`.

Until the plugin's Apache 2.0 LICENSE PR (musescore4-chord-library-plugin#403)
merges, ellington-systems does NOT vendor the corpus. Loaders read
from a live plugin clone pointed at by the `ELLINGTON_PLUGIN_PATH`
environment variable. Once #403 lands, a follow-up PR will vendor the
corpus under `data/plugin-snapshot/` and the loaders will switch to
that path.

Both files use a top-level wrapper shape per the Investigation Fact
Sheet (Entity 3 + Entity 4):

- `masters.json` → ``{"masters": [...], "schemaNote": ..., "version": ...}``
- `voicings.json` → ``{"voicings": [...]}``

The loaders unwrap and validate against the Pydantic models in
``models.py``. Validation failures are surfaced as ``ValueError`` with
the validation chain attached.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Voicing


@dataclass(frozen=True)
class Corpus:
    """Snapshot of the masters and voicings corpus at engine bootstrap.

    Both fields are immutable post-construction; the engine never
    writes back to the plugin. ``masters`` is a list of raw dicts
    rather than Pydantic models because the corpus's per-master shape
    is heterogeneous (some have ``systems[]``, some don't; some have
    zero ``principles[]``) and we read into it via key lookups, not
    via a fixed model surface.

    ``voicings`` is a list of validated ``Voicing`` instances.

    ``masters_by_id`` is built once for O(1) lookup during
    ``Engine.rank``.
    """

    masters: list[dict[str, Any]]
    voicings: list[Voicing]
    masters_by_id: dict[str, dict[str, Any]]

    @classmethod
    def from_plugin_clone(cls, plugin_path: str | Path) -> Corpus:
        """Load a corpus snapshot from a local plugin clone.

        Args:
            plugin_path: filesystem path to the plugin repository root
                (the directory containing ``plugin/data/``).

        Raises:
            FileNotFoundError: if either JSON file is missing.
            ValueError: if either file fails wrapper-shape or model
                validation.
        """
        root = Path(plugin_path)
        masters_path = root / "plugin" / "data" / "masters.json"
        voicings_path = root / "plugin" / "data" / "voicings.json"

        if not masters_path.is_file():
            raise FileNotFoundError(f"masters.json not found at {masters_path}")
        if not voicings_path.is_file():
            raise FileNotFoundError(f"voicings.json not found at {voicings_path}")

        masters_doc = json.loads(masters_path.read_text())
        voicings_doc = json.loads(voicings_path.read_text())

        if not isinstance(masters_doc, dict) or "masters" not in masters_doc:
            raise ValueError(
                f"masters.json must be a wrapper object with a 'masters' key; "
                f"found keys={list(masters_doc.keys()) if isinstance(masters_doc, dict) else type(masters_doc).__name__}"
            )
        if not isinstance(voicings_doc, dict) or "voicings" not in voicings_doc:
            raise ValueError(
                f"voicings.json must be a wrapper object with a 'voicings' key; "
                f"found keys={list(voicings_doc.keys()) if isinstance(voicings_doc, dict) else type(voicings_doc).__name__}"
            )

        masters_list = masters_doc["masters"]
        voicings_raw = voicings_doc["voicings"]

        voicings = [Voicing.model_validate(v) for v in voicings_raw]
        masters_by_id = {m["id"]: m for m in masters_list if "id" in m}

        return cls(
            masters=masters_list,
            voicings=voicings,
            masters_by_id=masters_by_id,
        )

    @classmethod
    def from_env(cls, env_var: str = "ELLINGTON_PLUGIN_PATH") -> Corpus:
        """Convenience: load from the path in ``ELLINGTON_PLUGIN_PATH``.

        Raises ``RuntimeError`` if the env var is unset or empty.
        """
        path = os.environ.get(env_var)
        if not path:
            raise RuntimeError(
                f"{env_var} is not set; cannot locate plugin corpus. "
                f"Set the variable to a local plugin clone path, or wait for "
                f"plugin LICENSE PR #403 to land and vendoring to happen."
            )
        return cls.from_plugin_clone(path)


def parse_chord_symbol(symbol: str) -> tuple[str, str]:
    """Split a chord symbol like ``"Cmaj7"`` or ``"F#m7b5"`` into
    ``(root, quality)``.

    Spike-grade parser — assumes the root is one of A-G followed by an
    optional ``b`` or ``#``, and the rest is the quality. Returns
    ``("", symbol)`` if no recognisable root prefix is found, so the
    caller can detect malformed input by checking the empty root.

    Examples:
        ``"Cmaj7"`` → ``("C", "maj7")``
        ``"Bbm7b5"`` → ``("Bb", "m7b5")``
        ``"F#13b9"`` → ``("F#", "13b9")``
        ``"xunknown"`` → ``("", "xunknown")``
    """
    if not symbol:
        return ("", "")
    head = symbol[0]
    if head not in "ABCDEFG":
        return ("", symbol)
    if len(symbol) >= 2 and symbol[1] in "b#":
        return (symbol[0:2], symbol[2:])
    return (symbol[0:1], symbol[1:])


__all__ = ["Corpus", "parse_chord_symbol"]
