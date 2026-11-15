# -*- coding: utf-8 -*-
"""Saved looks: everything a sound is drawn with, except the words.

The point of a favourite is that it survives the text. You spend a while
getting an impact right - the font, the fill, two outlines, the shake,
the warp settings - and then the next panel needs the same thing said
with a different sound. Saving the whole parameter set would carry the
caption and the dents you pushed into *that* one shape along with it, so
a favourite is the look with those taken out.

Qt-free, like the rest of the cores: a list of dicts, a few functions,
and JSON in and out. The panel only shows them.
"""
import json

from . import giongo as G

#: what belongs to the words, not to the look
WORD_KEYS = ("caption", "caption_pos")

#: what belongs to one particular shape: the letters you dragged, the
#: dents you pushed in, the outlines you reshaped by hand
SHAPE_KEYS = ("letters", "warps", "nodes")

#: more than this and the list stops being something you can look at
MAX = 24


def look_of(params):
    """The look alone, ready to drop onto any text."""
    p = dict(G.sanitize(params))
    for k in WORD_KEYS:
        p.pop(k, None)
    for k in SHAPE_KEYS:
        p.pop(k, None)
    return p


def names(favs):
    """What is saved, in the order it was saved."""
    return [f.get("name", "") for f in favs or []]


def add(favs, name, params):
    """Save this look under `name`, replacing one of the same name.

    Returns a new list; the one passed in is not touched.
    """
    name = (name or "").strip()
    if not name:
        return list(favs or [])
    out = [f for f in (favs or []) if f.get("name") != name]
    out.append({"name": name, "look": look_of(params)})
    return out[-MAX:]


def remove(favs, name):
    """Forget one favourite. Returns a new list."""
    return [f for f in (favs or []) if f.get("name") != name]


def find(favs, name):
    for f in favs or []:
        if f.get("name") == name:
            return f
    return None


def apply(params, fav):
    """`params` drawn the way `fav` says, with the words left alone.

    The caption stays, and so does anything done to the shape that is on
    screen: applying a look is not meant to undo an afternoon of
    dragging letters about.
    """
    if not fav:
        return G.sanitize(params)
    cur = G.sanitize(params)
    out = dict(cur)
    out.update(fav.get("look") or {})
    for k in WORD_KEYS + SHAPE_KEYS:
        if k in cur:
            out[k] = cur[k]
    return G.sanitize(out)


def to_json(favs):
    return json.dumps(favs or [], ensure_ascii=False, sort_keys=True)


def from_json(text):
    """Back from the settings file, with anything odd dropped."""
    try:
        got = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(got, list):
        return []
    out = []
    for f in got:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        look = f.get("look")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(look, dict):
            continue
        out.append({"name": name, "look": look_of(look)})
    return out[-MAX:]
