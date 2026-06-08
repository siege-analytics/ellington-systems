"""Port of `MastersStore.js` — the master-tag collector that feeds the
master_boost path of `score_candidate`.

The current scope is `collect_voicing_style_tags`, which is the ONLY JS
mechanism by which a master contributes to scoring per the Investigation
Fact Sheet (Entity 2, SEMANTIC disposition: "reads
`master.principles[*].voicingStyleTags` only — does NOT read
`master.works[*].systems[*]`"). Goal B's payload-kind dispatcher
operates on `systems[]` independently — that's in `dispatcher.py`
(future PR).

A consequence the Fact Sheet captures: for a `systems[]`-only master
(e.g. `benson`, which has 0 `principles[]`), this function returns
`[]` — meaning the JS scorer's master_boost is permanently 0 for such
masters. The Python port mirrors that behaviour deliberately.

`derive_tolerances_from_master` is a sibling helper that the JS engine
uses to merge `tolerance_hints` from a master's principles. Goal A does
not consume it (the spike's `tolerance_match` score component stays at
0.0), but porting it now keeps the JS↔Python parity story complete and
unblocks future tolerance-aware work without revisiting this module.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


def collect_voicing_style_tags(master: Mapping[str, Any] | None) -> list[str]:
    """Port of `collectVoicingStyleTags` at `MastersStore.js:127-141`.

    Walks `master.principles[*].voicingStyleTags`, dedupes by string
    equality, returns the resulting list in first-seen order.

    Returns an empty list for ``None``, missing ``principles``, or a
    master whose principles carry no tags.

    Args:
        master: a master entry from ``masters.json``, or ``None``.

    Returns:
        Deduped list of `voicingStyleTags` strings. Order matches JS
        (first-seen wins).
    """
    if not master or "principles" not in master or master["principles"] is None:
        return []
    seen: dict[str, bool] = {}
    out: list[str] = []
    for principle in master["principles"]:
        tags = principle.get("voicingStyleTags") or []
        for tag in tags:
            if tag not in seen:
                seen[tag] = True
                out.append(tag)
    return out


def derive_tolerances_from_master(
    master: Mapping[str, Any] | None,
    tighten_fn: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None,
) -> Mapping[str, Any] | None:
    """Port of `deriveTolerancesFromMaster` at `MastersStore.js:147-170`.

    Folds each principle's ``tolerance_hints`` together using a
    "stricter wins" tighten function (caller-provided per the JS API).
    Returns ``None`` if no principle declared any hints.

    Graceful-degrade path mirrors JS: if ``tighten_fn`` is missing,
    returns the *first* non-empty hints dict encountered — explicitly
    "better than nothing" per the JS source comment.
    """
    if not master or "principles" not in master or master["principles"] is None:
        return None

    if tighten_fn is None:
        # JS comment: "Caller forgot to pass the tightener; degrade
        # gracefully by returning the FIRST hint we find."
        for principle in master["principles"]:
            h0 = principle.get("tolerance_hints")
            if h0 and len(h0) > 0:
                return h0
        return None

    combined: Mapping[str, Any] | None = None
    for principle in master["principles"]:
        h = principle.get("tolerance_hints")
        if not h or len(h) == 0:
            continue
        if combined is None:
            # JS source spreads the dict — match its observable effect.
            combined = dict(h)
        else:
            combined = tighten_fn(combined, h)
    return combined


__all__ = ["collect_voicing_style_tags", "derive_tolerances_from_master"]
