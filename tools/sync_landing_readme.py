# -*- coding: utf-8 -*-
"""Rebuild the landing README from the plugin one, keeping only what must differ.

Hand-merging the two is what let them drift apart in both directions in the
first place, and patching one section at a time only moves the drift around. So
the landing page is derived instead: it IS the plugin README, with the two
places whose instructions are relative to the repo root - the installation
section and the command that runs the tests - swapped for its own.

Idempotent: it reads the landing page's own installation section back out of the
file it rewrites, so running it again after any change to the plugin README
keeps the two in step.
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING = os.path.join(ROOT, "README.md")
PLUGIN = os.path.join(ROOT, "TypeR-Krita", "README.md")

INST_START = "## Installation"
INST_END = "---\n\n## The docker: tabs"

OLD_TESTS = ("Run the whole suite (no real Krita needed; PyQt is only used by "
             "the integration\npart):")
NEW_TESTS = ("Run the whole suite from the `TypeR-Krita` folder (no real Krita "
             "needed; PyQt is\nonly used by the integration part):")


def section(text, start, end):
    """The slice from `start` up to (not including) `end`."""
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[a:b]


landing = io.open(LANDING, encoding="utf-8").read()
plugin = io.open(PLUGIN, encoding="utf-8").read()

out = plugin.replace(section(plugin, INST_START, INST_END),
                     section(landing, INST_START, INST_END), 1)

assert OLD_TESTS in out, "the tests line moved - check the plugin README"
out = out.replace(OLD_TESTS, NEW_TESTS, 1)

io.open(LANDING, "w", encoding="utf-8", newline="\n").write(out)
print("landing README rebuilt from the plugin one")
