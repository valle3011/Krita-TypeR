# -*- coding: utf-8 -*-
"""Write the repository's VERSION file from the plugin's own constant.

The docker checks for a newer TypeR by fetching this file (see
typer_kr/update_check.py). The project publishes no releases or tags, so there
is nothing in the GitHub API to read instead - and a six-byte file is a smaller
thing to fetch than any API response anyway.

Generated rather than edited, because a version marker that can disagree with
the plugin it describes is worse than none: it would announce updates that do
not exist, or stay quiet about ones that do. Run it after syncing the plugin,
before committing.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "TypeR-Krita", "typer_kr", "typer_kr.py")
TARGET = os.path.join(ROOT, "VERSION")

_VERSION = re.compile(r'^VERSION\s*=\s*"([^"]+)"', re.M)


def plugin_version(path=SOURCE):
    """The VERSION constant of the published plugin."""
    text = io.open(path, encoding="utf-8").read()
    match = _VERSION.search(text)
    if not match:
        raise SystemExit("no VERSION constant found in %s" % path)
    return match.group(1)


def main():
    version = plugin_version()
    # a bare version and a newline: update_check.py reads the first line and
    # nothing else, so there is no format to get wrong later
    io.open(TARGET, "w", encoding="ascii", newline="\n").write(version + "\n")
    print("VERSION -> %s" % version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
