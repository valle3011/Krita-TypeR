# -*- coding: utf-8 -*-
"""What there is to know about one font family (Qt-free core).

The favourites tab shows a font's name and a preview of it, which answers
"what does it look like" and nothing else. The two questions that actually
come up while typesetting are:

* **Is there more of this family?** A cut usually arrives as a family of its
  own - "Anime Ace" and "Anime Ace Bold" are two entries in Qt's list, not
  one family with two styles - so the only way to see what else is installed
  is to go looking by eye.
* **Am I using this anywhere?** Deleting a favourite is harmless, but
  uninstalling the font behind a preset is not, and nothing said which
  presets would lose their font.

Both are answered here, out of data the docker already holds, so the dialog
in ``fontprops_ui.py`` only has to lay it out. Matching goes through
``fontmatch`` rather than string equality: a preset saved as "CCWildWords"
and a family listed as "CC Wild Words" are the same font, and a tab that
said otherwise would be worse than no tab.
"""

try:
    from . import fontmatch
except (ImportError, ValueError):       # loaded as a plain file by the tests
    import fontmatch


def same_font(a, b):
    """Are these two spellings the same family?

    Spacing, punctuation and case differ freely between what a font file
    declares, what Qt lists and what was saved into a preset years ago.
    """
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    return a.lower() == b.lower() or fontmatch.squash(a) == fontmatch.squash(b)


def family_key(family):
    """The key that groups a family with its own cuts, or '' if there is none.

    "Anime Ace", "AnimeAce Bold" and "Anime Ace Italic" all key the same;
    "Anime Ace 2.0" does not, because the 2.0 is part of the name and not a
    cut, and the two really are different families.
    """
    base, _bold, _italic = fontmatch.split_cut(fontmatch.tokens(family or ""))
    return "".join(sorted(base))


def is_cut_word(word):
    """Is this word a cut name ('Bold', 'Light', 'Oblique') rather than a name?

    Asked of ``fontmatch`` instead of a list kept here, so the two never
    drift apart.
    """
    toks = fontmatch.tokens(word or "")
    if len(toks) != 1:
        return False
    return len(fontmatch.split_cut(["\x00"] + toks)[0]) == 1


def split_cut_name(family):
    """('Anime Ace', 'Bold Italic') - the family without its cut, and the cut.

    The original spelling is kept rather than rebuilt from tokens: a name is
    the user's to read, and "CCWildWords" should not come back as "cc wild
    words". A name made of nothing but cut words keeps its last word, so
    "Black" stays a family and does not dissolve into a cut.
    """
    name = (family or "").strip()
    if not name:
        return "", ""
    words = name.replace("-", " ").replace("_", " ").split()
    cut = []
    while len(words) > 1 and is_cut_word(words[-1]):
        cut.insert(0, words.pop())
    return " ".join(words), " ".join(cut)


def relatives(family, families):
    """Every installed family that is a cut of the same font, *family* included.

    Sorted so the plain cut comes first and the rest alphabetically, which is
    the order a list of cuts is read in.
    """
    name = (family or "").strip()
    if not name:
        return []
    key = family_key(name)
    out, seen = [], set()
    for f in list(families or []) + [name]:
        f = (f or "").strip()
        low = f.lower()
        if not f or low in seen:
            continue
        if same_font(f, name) or (key and family_key(f) == key):
            seen.add(low)
            out.append(f)
    out.sort(key=lambda f: (bool(split_cut_name(f)[1]), f.lower()))
    return out


def cuts_of(family, families):
    """[(family, cut)] for the whole family - '' as the cut of the plain one."""
    return [(f, split_cut_name(f)[1]) for f in relatives(family, families)]


def preset_uses(groups, wanted):
    """Which saved presets use one of the *wanted* spellings of a font.

    *groups* is the docker's ``{manga: {character: {preset: settings}}}``;
    the font of a preset is ``settings["font"]``. Returns
    ``[(manga, character, preset, font_as_saved)]``, sorted the way the
    preset tree reads: manga, then character, then preset.

    *wanted* may be one name or several - the dialog passes the whole family,
    so a font's Bold cut shows up under the plain one rather than looking
    unused.
    """
    names = [wanted] if isinstance(wanted, str) else list(wanted or [])
    names = [n for n in names if (n or "").strip()]
    if not isinstance(groups, dict) or not names:
        return []
    out = []
    for manga, chars in groups.items():
        if not isinstance(chars, dict):
            continue
        for char, presets in chars.items():
            if not isinstance(presets, dict):
                continue
            for preset, cfg in presets.items():
                font = ""
                if isinstance(cfg, dict):
                    font = str(cfg.get("font", "") or "")
                if font and any(same_font(font, n) for n in names):
                    out.append((str(manga), str(char), str(preset), font))
    out.sort(key=lambda r: (r[0].lower(), r[1].lower(), r[2].lower()))
    return out


def type_uses(type_fonts, wanted):
    """Which text types were given one of the *wanted* fonts.

    *type_fonts* is ``{label: family}`` - the docker resolves the labels,
    because only it knows what a custom type is called.
    """
    names = [wanted] if isinstance(wanted, str) else list(wanted or [])
    names = [n for n in names if (n or "").strip()]
    if not isinstance(type_fonts, dict) or not names:
        return []
    out = [(str(label), str(font)) for label, font in type_fonts.items()
           if font and any(same_font(str(font), n) for n in names)]
    out.sort(key=lambda r: r[0].lower())
    return out


def file_kind(path):
    """'TrueType', 'OpenType', … for a font file, by its extension."""
    ext = (path or "").rsplit(".", 1)[-1].lower() if "." in (path or "") else ""
    return {"ttf": "TrueType", "otf": "OpenType", "ttc": "TrueType collection",
            "otc": "OpenType collection", "woff": "WOFF", "woff2": "WOFF2",
            "pfb": "Type 1", "pfm": "Type 1", "fon": "Bitmap",
            "fnt": "Bitmap"}.get(ext, ext.upper() or "")


def human_size(n, group=",", point="."):
    """'21.6 KB (22,204 bytes)' - as a properties window writes it.

    *group* and *point* are the separators of the user's locale; the caller
    reads them off Qt, because a German Windows writes the same number as
    "21,6 KB (22.204 bytes)" and a dialog that did otherwise would be the
    one line on screen that looks imported.
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    bytes_ = "{:,}".format(n).replace(",", group or "")
    if n < 1024:
        return "%s bytes" % bytes_
    v = float(n)
    for unit in ("KB", "MB", "GB"):
        v /= 1024.0
        if v < 1024.0 or unit == "GB":
            return "%s %s (%s bytes)" % (("%.1f" % v).replace(".", point),
                                         unit, bytes_)
    return ""
