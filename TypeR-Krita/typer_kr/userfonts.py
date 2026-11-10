# -*- coding: utf-8 -*-
"""Font files loaded by hand, for fonts that are not installed.

Qt can take a font file for the lifetime of the program
(``QFontDatabase.addApplicationFont``), which is exactly what a
scanlator needs for the one display face that came with a chapter and
has no business in the system font folder.

What is remembered is the *paths*, not the fonts: they are loaded again
at the next start, and a file that has moved away is reported rather
than silently missing.

Qt-light on purpose - it needs the font database and nothing else - so
the list handling below can still be tested without a window.
"""
import json
import os

from ._qt import QFontDatabase

#: path -> (font id, [family, ...]) for everything loaded this session
_loaded = {}

#: what could not be loaded this session: path -> why
_failed = {}

#: Qt takes these; .woff and .woff2 are web formats it does not read
EXTENSIONS = (".ttf", ".otf", ".ttc", ".otc")


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def load(path):
    """Register one font file. Returns the families it brought.

    Loading the same file twice is free: Qt would hand out a second id
    for the same families, so the first one is kept.
    """
    key = _norm(path)
    if key in _loaded:
        return list(_loaded[key][1])
    if not os.path.isfile(path):
        _failed[key] = "not there"
        return []
    try:
        fid = QFontDatabase.addApplicationFont(path)
    except Exception as exc:                        # noqa: BLE001
        _failed[key] = str(exc)
        return []
    if fid < 0:
        _failed[key] = "Qt could not read it"
        return []
    try:
        fams = list(QFontDatabase.applicationFontFamilies(fid) or [])
    except Exception:                               # noqa: BLE001
        fams = []
    if not fams:
        _failed[key] = "no families in the file"
        return []
    _failed.pop(key, None)
    _loaded[key] = (fid, fams)
    return list(fams)


def load_all(paths):
    """Load a list of files. Returns (families, paths that failed)."""
    fams = []
    bad = []
    for p in paths or []:
        got = load(p)
        if got:
            fams += [f for f in got if f not in fams]
        else:
            bad.append(p)
    return fams, bad


def forget(path):
    """Take one file back out again."""
    key = _norm(path)
    hit = _loaded.pop(key, None)
    if hit is None:
        return False
    try:
        QFontDatabase.removeApplicationFont(hit[0])
    except Exception:                               # noqa: BLE001
        pass
    return True


def paths():
    """Every file loaded this session, in a stable order."""
    return sorted(_loaded.keys())


def families():
    """Every family those files brought."""
    out = []
    for _key in paths():
        for f in _loaded[_key][1]:
            if f not in out:
                out.append(f)
    return out


def families_of(path):
    return list(_loaded.get(_norm(path), (0, []))[1])


def failures():
    """path -> why, for the files that would not load."""
    return dict(_failed)


def is_font_file(path):
    return os.path.splitext(path or "")[1].lower() in EXTENSIONS


# --- what is remembered between sessions ----------------------------------

def to_json(paths_in=None):
    return json.dumps(sorted(paths_in if paths_in is not None else paths()))


def from_json(raw):
    """The remembered list, as paths. Rubbish gives an empty list."""
    try:
        got = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(got, list):
        return []
    return [p for p in got if isinstance(p, str) and p.strip()]
