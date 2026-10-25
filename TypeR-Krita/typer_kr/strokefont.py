# -*- coding: utf-8 -*-
"""The centre lines of the letters, read back in.

Brush lettering draws a stroke along the middle of a letter, so it needs
the line through that middle - and it needs to know which end of the line
was written first, or the brush lands heavy at the wrong end.

Both come from sources that know: KanjiVG draws every kana as separate
paths in writing order, and the Hershey fonts are single-stroke Latin to
begin with. `tools/make_strokes.py` fits them onto one frame, once,
outside Krita; the answer ships as `strokelines.txt` beside this file, and
`strokelines-LICENSE.txt` says whose work it is.

The file is plain ASCII and one line per glyph, the character written as its
code point: this project has twice lost non-ASCII text to a tool that
re-encoded it on the way through, and a data file that cannot be damaged
that way is worth the four extra characters per line.

    <code point> <advance> <stroke>|<stroke>|...
    each stroke: "x,y x,y x,y ..."  in 1000ths of an em,
    x to the right from the pen position, y downwards from the baseline.

A stroke whose two points are the same is a dot - the tittle of an i, a
dakuten mark, a full stop - and the brush draws it as a blob rather than as
a line of no length.
"""
import io
import os

#: where the generated file sits
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "strokelines.txt")
#: the grid the points are stored in
EM = 1000

_cache = {}
_metrics = {}
#: what to assume when the file says nothing - the proportions of an
#: ordinary Japanese face, so a letter still sits near the right height
FALLBACK_METRICS = (880.0, 120.0)


def load(path=None):
    """{code point: (advance, [[(x, y), ...], ...])}, read once and kept.

    A missing or damaged file is not an error worth stopping for: brush
    lettering simply has nothing to offer then, and the ordinary outline
    lettering carries on. The caller asks `has()` first.
    """
    key = path or DATA
    if key in _cache:
        return _cache[key]
    glyphs = {}
    try:
        with io.open(key, encoding="ascii") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("# metrics:"):
                    bits = line.split()
                    try:
                        _metrics[key] = (float(bits[3]), float(bits[5]))
                    except (IndexError, ValueError):
                        pass
                    continue
                if not line or line.startswith("#"):
                    continue
                parts = line.split(" ", 2)
                if len(parts) < 2:
                    continue
                try:
                    code = int(parts[0], 16)
                    advance = int(parts[1])
                except ValueError:
                    continue
                strokes = []
                body = parts[2] if len(parts) > 2 else ""
                for chunk in body.split("|"):
                    pts = []
                    for pair in chunk.split():
                        try:
                            x, y = pair.split(",")
                            pts.append((int(x), int(y)))
                        except ValueError:
                            pts = []
                            break
                    if len(pts) >= 2:
                        strokes.append(pts)
                glyphs[code] = (advance, strokes)
    except (OSError, UnicodeDecodeError):
        glyphs = {}
    _metrics.setdefault(key, FALLBACK_METRICS)
    _cache[key] = glyphs
    return glyphs


def metrics(path=None):
    """(ascent, descent) in em units, as the source font had them.

    The renderer centres a letter on its em box - that is what makes ッ sit
    low and ー sit mid-height - so stroke lettering has to be centred on the
    same box as the outline lettering, or the two would not share a line.
    """
    key = path or DATA
    if key not in _metrics:
        load(key)
    return _metrics.get(key, FALLBACK_METRICS)


def has(ch, path=None):
    """Is there a centre line for this character?"""
    return bool(ch) and ord(ch[0]) in load(path)


def glyph(ch, path=None):
    """(advance, strokes) in em units, or None."""
    return load(path).get(ord(ch[0])) if ch else None


def coverage(text, path=None):
    """How much of `text` can be drawn with a brush, 0..1.

    Spaces and line breaks do not count - they need no lettering - so a line
    of pure kana reports 1.0 even though it is full of them.
    """
    letters = [c for c in (text or "") if not c.isspace()]
    if not letters:
        return 1.0
    known = sum(1 for c in letters if ord(c) in load(path))
    return known / float(len(letters))


def missing(text, path=None):
    """The characters of `text` that have no centre line, in order, once each."""
    out = []
    seen = set()
    for c in text or "":
        if c.isspace() or c in seen:
            continue
        seen.add(c)
        if ord(c) not in load(path):
            out.append(c)
    return out


def scaled(ch, size, path=None):
    """The strokes of one character at `size` pixels to the em.

    Returns (advance, [[(x, y), ...], ...]) with the same frame the font
    metrics use, so a caller can place it exactly where a glyph would sit.
    """
    got = glyph(ch, path)
    if not got:
        return None
    advance, strokes = got
    k = size / float(EM)
    return (advance * k,
            [[(x * k, y * k) for (x, y) in st] for st in strokes])


def is_dot(stroke):
    """A stroke of no length: a tittle, a dakuten mark, a full stop."""
    return len(stroke) >= 2 and stroke[0] == stroke[-1] and len(set(stroke)) == 1


def info(path=None):
    """(glyph count, stroke count, point count) - for the Setup tab."""
    glyphs = load(path)
    strokes = sum(len(s) for (_a, s) in glyphs.values())
    points = sum(len(p) for (_a, s) in glyphs.values() for p in s)
    return len(glyphs), strokes, points
