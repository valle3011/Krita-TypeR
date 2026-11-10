# -*- coding: utf-8 -*-
"""Your own lettering as a letter style.

Images of drawn letters - single files, a folder, or a ZIP - are traced
into outlines once, at import, and from then on they are ordinary
`giongo_nodes` contours in the glyph's own em. Everything the rest of
the tab can do then applies to them: fill, outlines, shadow, the path,
liquify, point editing.

The tracing is Qt's work, not ours: the mask becomes a `QRegion`, which
merges its runs into rectangles for us, and that region becomes a path.
What is left to do is to walk the staircase it gives back and drop the
points that say nothing (Ramer-Douglas-Peucker), then hand the result to
`giongo_nodes`.

A file is the letter its name is: ``ド.png`` is the lettering for
ド. Anything whose name is not exactly one character is skipped and
reported, rather than guessed at.
"""
import json
import math
import os
import zipfile

from ._qt import (QImage, QRegion, QBitmap, QPainterPath, Qt, QTransform,
                  QPointF)
from . import giongo_nodes as N

#: what a traced glyph is scaled into: the em box `giongo_render` uses
#: (`_REF` there; a test holds the two together)
REF = 200.0

#: how much of that em a traced letter fills. A font's kana fills about
#: this much of it (\u30c9 in MS Gothic: 170 of 200), so a drawing traced
#: to the same share sits where a letter of the font would.
INK = 0.85

#: tracing happens at this size at most - a drawn letter needs no more,
#: and every pixel costs
MAX_SIDE = 320

#: sets that have been loaded this session: name -> {"path", "glyphs"}
_sets = {}

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif",
             ".tiff")


# --- tracing one image ----------------------------------------------------

def _mask(img, threshold=128):
    """A 1-bit image: 1 where there is ink.

    An image with an alpha channel is ink where it is opaque; one
    without is ink where it is dark, which is what a photographed or
    scanned lettering looks like.
    """
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    if w > MAX_SIDE or h > MAX_SIDE:
        img = img.scaled(min(w, MAX_SIDE), min(h, MAX_SIDE),
                         Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        w, h = img.width(), img.height()
    has_alpha = False
    for y in range(0, h, max(1, h // 24)):
        for x in range(0, w, max(1, w // 24)):
            if (img.pixel(x, y) >> 24) & 0xff < 250:
                has_alpha = True
                break
        if has_alpha:
            break
    # a QBitmap's region is its colour0 pixels, which is index 1 in a
    # mono image's default colour table - measured, not assumed: with it
    # the other way round the region came back as the whole canvas
    out = QImage(w, h, QImage.Format.Format_Mono)
    out.fill(1)
    for y in range(h):
        for x in range(w):
            px = img.pixel(x, y)
            a = (px >> 24) & 0xff
            if has_alpha:
                ink = a >= threshold
            else:
                lum = ((px >> 16 & 0xff) * 299 + (px >> 8 & 0xff) * 587
                       + (px & 0xff) * 114) // 1000
                ink = a >= 128 and lum < threshold
            if ink:
                out.setPixel(x, y, 0)
    return out


def _rdp(pts, tol):
    """Ramer-Douglas-Peucker: the same line with the dull points gone."""
    if len(pts) < 3:
        return list(pts)
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    span = math.hypot(dx, dy)
    worst = -1.0
    at = 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        if span < 1e-9:
            d = math.hypot(px - ax, py - ay)
        else:
            d = abs(dy * px - dx * py + bx * ay - by * ax) / span
        if d > worst:
            worst, at = d, i
    if worst <= tol:
        return [pts[0], pts[-1]]
    return _rdp(pts[:at + 1], tol)[:-1] + _rdp(pts[at:], tol)


def _smooth_ring(ring):
    """Give every point handles from its neighbours.

    Off by default: measured against four glyphs traced from a drawing
    of themselves, smoothing pulls thin strokes inward and costs ten
    points of agreement (98.6 % -> 88 %). It is kept for lettering that
    is meant to look drawn rather than exact.
    """
    n = len(ring)
    for i, nd in enumerate(ring):
        prv = ring[(i - 1) % n]
        nxt = ring[(i + 1) % n]
        hx, hy = (nxt[0] - prv[0]) / 6.0, (nxt[1] - prv[1]) / 6.0
        nd[2], nd[3] = -hx, -hy
        nd[4], nd[5] = hx, hy
        nd[6] = 1
    return ring


def trace_image(img, threshold=128, tol=0.5, smooth=False):
    """One image -> contours in the em box, centred, REF tall."""
    if img is None or img.isNull():
        return []
    mask = _mask(img, threshold)
    region = QRegion(QBitmap.fromImage(mask))
    if region.isEmpty():
        return []
    path = QPainterPath()
    path.addRegion(region)
    path = path.simplified()
    rect = path.boundingRect()
    if rect.width() <= 0 or rect.height() <= 0:
        return []
    k = REF * INK / max(rect.width(), rect.height())
    tr = QTransform()
    tr.scale(k, k)
    tr.translate(-rect.center().x(), -rect.center().y())
    contours = []
    for poly in path.toSubpathPolygons():
        pts = [(p.x(), p.y()) for p in poly]
        if len(pts) > 2 and pts[0] == pts[-1]:
            pts.pop()
        pts = _rdp(pts, tol)
        if len(pts) < 3:
            continue
        ring = []
        for x, y in pts:
            q = tr.map(QPointF(x, y))
            ring.append(N.node(q.x(), q.y()))
        if smooth:
            _smooth_ring(ring)
        contours.append(ring)
    return N.sanitize_contours(contours)


# --- a whole set ----------------------------------------------------------

def _char_of(name):
    """The letter a file is for, or "" if its name does not say."""
    stem = os.path.splitext(os.path.basename(name))[0].strip()
    return stem if len(stem) == 1 else ""


def sources(paths):
    """[(letter, QImage, where)] from files, folders and ZIPs.

    Returns (items, skipped) - skipped is [(where, why)], so an import
    can say what it did not take.
    """
    items = []
    skipped = []
    for p in paths or []:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                sub = os.path.join(p, name)
                if os.path.isfile(sub):
                    _take_file(sub, items, skipped)
        elif zipfile.is_zipfile(p):
            try:
                with zipfile.ZipFile(p) as z:
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        ch = _char_of(info.filename)
                        if not ch:
                            skipped.append((info.filename, "name"))
                            continue
                        img = QImage()
                        if not img.loadFromData(z.read(info)):
                            skipped.append((info.filename, "image"))
                            continue
                        items.append((ch, img, info.filename))
            except (OSError, zipfile.BadZipFile) as exc:
                skipped.append((p, str(exc)))
        elif os.path.isfile(p):
            _take_file(p, items, skipped)
        else:
            skipped.append((p, "not there"))
    return items, skipped


def _take_file(path, items, skipped):
    if os.path.splitext(path)[1].lower() not in IMAGE_EXT:
        return
    ch = _char_of(path)
    if not ch:
        skipped.append((path, "name"))
        return
    img = QImage(path)
    if img.isNull():
        skipped.append((path, "image"))
        return
    items.append((ch, img, path))


def build_set(name, paths, threshold=128, tol=0.5, smooth=False):
    """Trace everything those paths hold. Returns (set dict, skipped)."""
    items, skipped = sources(paths)
    glyphs = {}
    for ch, img, where in items:
        cs = trace_image(img, threshold, tol, smooth)
        if cs:
            glyphs[ch] = cs
        else:
            skipped.append((where, "nothing to trace"))
    return {"name": name or "lettering", "glyphs": glyphs}, skipped


def save_set(data, path):
    """Write a set beside the images it came from."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    return path


def load_set(path):
    """Read a set back. Returns None if the file is not one."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("glyphs"), dict):
        return None
    glyphs = {}
    for ch, cs in data["glyphs"].items():
        if isinstance(ch, str) and len(ch) == 1:
            ring = N.sanitize_contours(cs)
            if ring:
                glyphs[ch] = ring
    return {"name": str(data.get("name") or
                        os.path.splitext(os.path.basename(path))[0]),
            "glyphs": glyphs}


# --- what the renderer asks ------------------------------------------------

def register(data, path=""):
    """Make a set available to the renderer under its name."""
    if not data or not data.get("glyphs"):
        return ""
    name = data["name"]
    _sets[name] = {"path": path, "glyphs": data["glyphs"]}
    return name


def forget(name):
    _sets.pop(name, None)


def names():
    return sorted(_sets.keys())


def path_of(name):
    return (_sets.get(name) or {}).get("path", "")


def letters(name):
    """Which characters a set can draw."""
    return sorted((_sets.get(name) or {}).get("glyphs", {}).keys())


def glyph_of(name, ch):
    """The contours for one character, or None if the set has no such
    letter - then the font draws it as usual."""
    if not name:
        return None
    got = (_sets.get(name) or {}).get("glyphs", {}).get(ch)
    return got or None


def fingerprint(name, ch):
    """Enough to tell one traced letter from another, for a cache key."""
    cs = glyph_of(name, ch)
    return "" if not cs else "%s/%s/%d" % (name, ch, N.count(cs))
