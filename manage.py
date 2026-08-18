#!/usr/bin/env python
"""Ellington web management entrypoint. Requires the [web] extra."""
import os
import sys


def main() -> None:
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "ellington_web.ellington_web.settings"
    )
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - installation guard
        raise ImportError(
            "Django is not installed. Install with `pip install -e '.[web]'`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
