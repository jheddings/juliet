"""Verify version information looks reasonable."""

import re

from juliet import __version__


def test_version_exists():
    assert __version__


def test_version_is_valid_string():
    assert re.match(r"[0-9]+(\.[0-9])+", __version__)
