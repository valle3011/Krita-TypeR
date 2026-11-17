# -*- coding: utf-8 -*-
"""A bin for presets that went away, so a slip is not the end of them.

Deleting a preset used to be one click with no question and no way
back: the entry left the table and the table went to the settings file
the same instant. Four of them were lost that way, and the only reason
they came back at all was an export the user happened to have made
three weeks earlier.

The idea here is deliberately dull. Nothing watches the delete button;
instead, **every** time the preset table is about to be written, it is
compared with the one that was written last, and whatever is no longer
in it is put in the bin with its settings and the time. One hook, and
it catches the lot: the delete action, an import that overwrote a
group, a reset, a rename that went wrong, and whatever else is added
later and forgets to tell the bin about itself.

Qt-free and pure, like the other cores: tables and lists in, tables and
lists out. The docker only shows them.
"""
import json
import time

#: how many deleted presets are kept. A bin, not an archive - the
#: export is the archive.
MAX = 60

#: a bin bigger than this is not written back: a settings file is not a
#: database, and a preset that large means something upstream is wrong
#: rather than that somebody has a lot of presets.
MAX_CHARS = 400000


def count(groups):
    """How many presets a table holds."""
    total = 0
    for chars in (groups or {}).values():
        if not isinstance(chars, dict):
            continue
        for presets in chars.values():
            if isinstance(presets, dict):
                total += len(presets)
    return total


def entries(groups):
    """{(manga, char, name): settings} out of a table."""
    out = {}
    for manga, chars in (groups or {}).items():
        if not isinstance(chars, dict):
            continue
        for ch, presets in chars.items():
            if not isinstance(presets, dict):
                continue
            for name, cfg in presets.items():
                if isinstance(cfg, dict):
                    out[(str(manga), str(ch), str(name))] = cfg
    return out


def removed(before, after):
    """What `before` had and `after` has not, newest table wins.

    A preset whose settings merely changed is not removed - only one
    that is no longer there under that name at all.
    """
    old, new = entries(before), entries(after)
    return [(k, old[k]) for k in old if k not in new]


def drop(trash, before, after, at=None):
    """Put whatever `after` lost into the bin. Returns the new bin.

    The same preset deleted twice keeps one entry, the newer one: a bin
    that fills up with repeats of one name pushes out the entries that
    mattered.
    """
    gone = removed(before, after)
    if not gone:
        return list(trash or [])
    when = float(at if at is not None else time.time())
    out = [dict(item) for item in (trash or [])]
    for (manga, ch, name), cfg in gone:
        out = [it for it in out
               if (it.get("manga"), it.get("char"), it.get("name"))
               != (manga, ch, name)]
        out.append({"at": when, "manga": manga, "char": ch, "name": name,
                    "data": json.loads(json.dumps(cfg))})
    out.sort(key=lambda it: it.get("at", 0.0))
    return out[-MAX:]


def restore(groups, item, overwrite=False):
    """Put one binned preset back. Returns (table, what happened).

    "what happened" is "ok", "exists" (something of that name is there
    now and `overwrite` was not asked for) or "bad".
    """
    if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
        return groups, "bad"
    manga, ch, name = (str(item.get("manga", "")), str(item.get("char", "")),
                       str(item.get("name", "")))
    if not name:
        return groups, "bad"
    out = json.loads(json.dumps(groups or {}))
    dst = out.setdefault(manga, {}).setdefault(ch, {})
    if name in dst and not overwrite:
        return groups, "exists"
    dst[name] = json.loads(json.dumps(item["data"]))
    return out, "ok"


def forget(trash, item):
    """Take one entry out of the bin. Returns the new bin."""
    key = (item.get("manga"), item.get("char"), item.get("name"),
           item.get("at")) if isinstance(item, dict) else None
    return [it for it in (trash or [])
            if (it.get("manga"), it.get("char"), it.get("name"),
                it.get("at")) != key]


def to_json(trash):
    text = json.dumps(trash or [], ensure_ascii=False)
    return text if len(text) <= MAX_CHARS else "[]"


def from_json(text):
    """Back from the settings file, with anything odd dropped.

    A settings file is edited by people and synced between machines, so
    everything here is checked rather than trusted.
    """
    try:
        got = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(got, list):
        return []
    out = []
    for item in got:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("data"), dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        try:
            at = float(item.get("at") or 0.0)
        except (TypeError, ValueError):
            at = 0.0
        out.append({"at": at,
                    "manga": str(item.get("manga") or ""),
                    "char": str(item.get("char") or ""),
                    "name": name,
                    "data": item["data"],
                    })
    out.sort(key=lambda it: it.get("at", 0.0))
    return out[-MAX:]


def newest_first(trash):
    """The bin as it is shown: what went last, first."""
    return sorted(trash or [], key=lambda it: it.get("at", 0.0), reverse=True)
