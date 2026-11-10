# -*- coding: utf-8 -*-
"""What to send when something goes wrong.

A bug report is only useful if it says which version, which Krita, which
Qt, and what the plugin was doing. Asking a person to find all that is
asking them not to report it at all, so the plugin writes it itself: a
button gathers the report, and from there it goes to the clipboard, to a
file, or straight into a prefilled issue.

Qt-free, so the report can be built and tested without a window. The
caller passes in what only it knows (versions, the settings in play).

Nothing here is sent anywhere on its own: the person sees the text and
decides. Nothing is collected that they are not shown.
"""
import datetime
import json
import os
import platform
import sys
import traceback

PROJECT_URL = "https://github.com/valle3011/Krita-TypeR"
ISSUE_URL = PROJECT_URL + "/issues/new"

#: how much of the report fits in a URL. GitHub accepts a long query but
#: browsers and servers start cutting around here, so the rest is left
#: for the clipboard.
MAX_URL = 6000

#: the last things that went wrong, newest last
_EVENTS = []
MAX_EVENTS = 12


def record(where, exc=None, detail=""):
    """Note that something went wrong, for the next report.

    `where` is what was being done ("insert", "preview", ...). An
    exception is kept with its last few frames; a plain note is kept as
    it is. Never raises: a broken report must not break what it reports
    about.
    """
    try:
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        text = ""
        if exc is not None:
            text = "".join(traceback.format_exception_only(
                type(exc), exc)).strip()
            tb = getattr(exc, "__traceback__", None)
            if tb is not None:
                frames = traceback.format_tb(tb)[-3:]
                text += "\n" + "".join(frames).rstrip()
        if detail:
            text = (text + "\n" + detail).strip()
        _EVENTS.append((stamp, str(where), text))
        del _EVENTS[:-MAX_EVENTS]
    except Exception:                               # noqa: BLE001
        pass


def events():
    return list(_EVENTS)


def clear():
    del _EVENTS[:]


def _safe(value, cut=400):
    try:
        text = str(value)
    except Exception:                               # noqa: BLE001
        return "?"
    return text if len(text) <= cut else text[:cut] + "…"


def build(info=None, settings=None, what=""):
    """The report, as Markdown.

    `info` is {label: value} the caller knows (TypeR version, Krita, Qt).
    `settings` is a dict that is written as JSON - the tab's parameters,
    so a look at them shows what was set when it went wrong.
    """
    info = dict(info or {})
    lines = ["### What happened", "",
             what.strip() or "_(say what you did and what you expected)_",
             "", "### Where", ""]
    for key in sorted(info):
        lines.append("- **%s**: %s" % (key, _safe(info[key])))
    lines.append("- **Python**: %s" % platform.python_version())
    lines.append("- **System**: %s" % _safe(platform.platform()))
    if _EVENTS:
        lines += ["", "### What the plugin noticed", "", "```"]
        for stamp, where, text in _EVENTS:
            lines.append("%s  %s" % (stamp, where))
            for row in (text or "").splitlines():
                lines.append("    " + row)
        lines.append("```")
    if settings:
        try:
            blob = json.dumps(settings, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            blob = "(settings could not be written)"
        lines += ["", "### Settings in play", "", "```json",
                  blob if len(blob) < 4000 else blob[:4000] + " …", "```"]
    lines += ["", "_Written by TypeR's report button; check it over before "
              "sending._"]
    return "\n".join(lines)


def _quote(text):
    """Percent-encode for a URL query, stdlib only."""
    try:
        from urllib.parse import quote
    except ImportError:                             # pragma: no cover
        from urllib import quote                    # noqa: F401
    return quote(text, safe="")


def issue_url(body, title="Problem in TypeR"):
    """A link that opens a new issue with the report already in it.

    Trimmed to what a URL carries: the person is told the rest is on the
    clipboard rather than finding half a report in the browser.
    """
    body = body or ""
    room = MAX_URL - len(ISSUE_URL) - len(_quote(title)) - 40
    cut = body
    while len(_quote(cut)) > room and len(cut) > 200:
        cut = cut[:int(len(cut) * 0.8)]
    if cut != body:
        cut = cut.rstrip() + "\n\n_(cut to fit the link - the full report "
        cut += "is on the clipboard)_"
    return "%s?title=%s&body=%s" % (ISSUE_URL, _quote(title), _quote(cut))


def save(text, folder, name=None):
    """Write the report beside whatever folder the caller offers."""
    name = name or ("typer-report-%s.md"
                    % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def hook_excepthook():
    """Catch what nobody caught, so it is in the next report too."""
    previous = sys.excepthook

    def catcher(kind, value, tb):
        try:
            value.__traceback__ = tb
            record("unhandled", value)
        finally:
            previous(kind, value, tb)

    sys.excepthook = catcher
    return previous
