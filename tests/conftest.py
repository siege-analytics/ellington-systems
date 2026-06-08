"""Pytest configuration shared across the test suite."""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def plugin_clone_path() -> str:
    """Path to a local musescore4-chord-library-plugin clone.

    Until the plugin's LICENSE PR (plugin #403) merges, ellington-systems
    does NOT vendor the corpus. Tests that need real plugin data read
    from `ELLINGTON_PLUGIN_PATH` instead. Tests requiring this fixture
    are marked `requires_plugin`; if the env var is missing, the test
    is skipped (not failed) so CI doesn't need the plugin to pass.
    """

    path = os.environ.get("ELLINGTON_PLUGIN_PATH")
    if not path:
        pytest.skip("ELLINGTON_PLUGIN_PATH not set; skipping plugin-data test")
    if not os.path.isdir(path):
        pytest.skip(f"ELLINGTON_PLUGIN_PATH={path} is not a directory; skipping")
    return path
