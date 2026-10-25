# -*- coding: utf-8 -*-
"""SUPERSEDED by make_strokes.py, which takes the lines from KanjiVG and
the Hershey fonts instead. Those know the strokes and the order they
are written in; thinning an outline does not, and that is what made a
letter come apart at every crossing. Kept only to show how the first
attempt worked.

Work out the centre lines of a font's glyphs, once, offline.

    py -3.13 tools/make_centrelines.py            # write the data file
    py -3.13 tools/make_centrelines.py --check    # report, write nothing

Brush lettering draws a stroke *along* a letter rather than filling its
outline, so it needs the line through the middle of each stroke. That cannot
be read out of a font - it has to be worked out from the shape - and working
it out needs numpy and a thinning pass, neither of which exists inside Krita.
So it happens here, and the plugin ships the answer.

**Which font.** Noto Sans JP Light, under the SIL Open Font License 1.1: thin,
even strokes, and it carries Latin as well as kana, so a word in either
alphabet comes out in one hand. The licence travels with the data file.

**How.** Each glyph is drawn large, thinned to a one-pixel skeleton, and that
skeleton is walked into polylines. Three things that look like details decide
whether the result is usable, each of them measured rather than reasoned:

* Ends and junctions are told apart by the number of ink runs around a pixel,
  not by how many neighbours it has. Counting neighbours broke ド into 157
  pieces.
* The redundant diagonals go before anything is walked. On a slanted stroke a
  skeleton pixel touches four others - the one before, the one after and both
  their diagonal partners - and every walk through that leaves edges behind
  which then start lines of their own. Dropping them took a K from 67 strokes
  to 3.
* A speck with no neighbours - the dot of an i, a dakuten mark - never enters
  a walk at all, because a walk needs a step to take. It is kept as a stroke
  of no length.

Needs numpy; Pillow only for --preview.
"""
import argparse
import io
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "TypeR-Krita", "typer_kr", "strokelines.txt")
LICENCE = os.path.join(ROOT, "TypeR-Krita", "typer_kr", "strokelines-LICENSE.txt")

FONT = "Noto Sans JP Light"
#: the grid the points are stored in: 1000 units to the em, y downwards from
#: the baseline, which is what the renderer works in
EM = 1000
#: how large a glyph is drawn before it is thinned. Large enough that a thin
#: stroke is several pixels wide, small enough to stay quick.
RENDER_PX = 256
#: how far a point may be moved when the line is simplified, in grid units
SIMPLIFY = 5.0


def glyph_set():
    """The characters worth carrying: kana, Latin, digits, punctuation.

    Kanji are left out on purpose - there are thousands, and a sound effect
    is written in kana. A letter that is not in here falls back to the
    ordinary outline lettering.
    """
    chars = []
    chars += [chr(c) for c in range(0x3041, 0x3097)]       # hiragana
    chars += [chr(c) for c in range(0x30A1, 0x30FB)]       # katakana
    chars += list("ーヽヾ゛゜々")
    chars += [chr(c) for c in range(0x30, 0x3A)]           # 0-9
    chars += [chr(c) for c in range(0x41, 0x5B)]           # A-Z
    chars += [chr(c) for c in range(0x61, 0x7B)]           # a-z
    chars += list("ÄÖÜäöüß")
    chars += list("!?.,:;'\"()[]{}<>+-*/=&%#@~_|^")
    chars += list("！？。、・…「」『』（）ー〜：；")
    seen = set()
    out = []
    for c in chars:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


# --------------------------------------------------------------------------
# the thinning and tracing, lifted from the measurements that proved them
# --------------------------------------------------------------------------

def zhang_suen(img, np):
    """Thin a boolean image to a one-pixel skeleton."""
    im = img.copy()
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            P = np.pad(im, 1)
            p2 = P[:-2, 1:-1]; p3 = P[:-2, 2:]
            p4 = P[1:-1, 2:];  p5 = P[2:, 2:]
            p6 = P[2:, 1:-1];  p7 = P[2:, :-2]
            p8 = P[1:-1, :-2]; p9 = P[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            B = sum(n.astype(np.uint8) for n in nb)
            seq = nb + [p2]
            A = sum(((~seq[i]) & seq[i + 1]).astype(np.uint8)
                    for i in range(8))
            if step == 0:
                c1, c2 = p2 & p4 & p6, p4 & p6 & p8
            else:
                c1, c2 = p2 & p4 & p8, p2 & p6 & p8
            kill = im & (B >= 2) & (B <= 6) & (A == 1) & (~c1) & (~c2)
            if kill.any():
                im = im & ~kill
                changed = True
    return im


def neighbours(y, x):
    return ((y - 1, x - 1), (y - 1, x), (y - 1, x + 1),
            (y, x + 1), (y + 1, x + 1), (y + 1, x),
            (y + 1, x - 1), (y, x - 1))


def build_graph(pts):
    """Adjacency with the redundant diagonals taken out."""
    adj = dict((p, set(q for q in neighbours(*p) if q in pts)) for p in pts)
    for p in pts:
        for q in list(adj[p]):
            if abs(p[0] - q[0]) + abs(p[1] - q[1]) != 2:
                continue
            if adj[p] & adj[q]:
                adj[p].discard(q)
                adj[q].discard(p)
    return adj


def trace(skel, np):
    pts = set((int(y), int(x)) for y, x in zip(*np.nonzero(skel)))
    adj = build_graph(pts)
    deg = dict((p, len(adj[p])) for p in pts)
    seen = set()
    lines = []

    def walk(a, b):
        line = [a, b]
        seen.add(frozenset((a, b)))
        prev, cur = a, b
        while deg.get(cur, 0) == 2:
            nxt = [q for q in adj[cur] if q != prev]
            if not nxt:
                break
            nxt = nxt[0]
            key = frozenset((cur, nxt))
            if key in seen:
                break
            seen.add(key)
            line.append(nxt)
            prev, cur = cur, nxt
        return line

    for n in sorted(p for p in pts if deg[p] != 2):
        for q in sorted(adj[n]):
            if frozenset((n, q)) not in seen:
                lines.append(walk(n, q))
    for p in sorted(pts):                      # closed loops have no node
        if deg[p] == 2:
            for q in sorted(adj[p]):
                if frozenset((p, q)) not in seen:
                    lines.append(walk(p, q))
    for p in sorted(pts):                      # the dot of an i
        if deg[p] == 0:
            lines.append([p, p])
    return lines


def blob_centres(bits, skel, np):
    """The middle of every ink blob that the thinning left nothing of.

    Returns them as strokes of no length, in pixel coordinates, so they
    travel the same path as every other stroke.
    """
    ink = int(bits.sum())
    if ink == 0:
        return []
    # an ordinary glyph keeps roughly a sixth of its ink as skeleton; far
    # less than that means something has been eaten
    if int(skel.sum()) * 40 >= ink:
        return []
    pts = set((int(y), int(x)) for y, x in zip(*np.nonzero(bits)))
    alive = set((int(y), int(x)) for y, x in zip(*np.nonzero(skel)))
    out = []
    seen = set()
    for p in sorted(pts):
        if p in seen:
            continue
        stack = [p]
        seen.add(p)
        comp = []
        while stack:
            c = stack.pop()
            comp.append(c)
            for q in neighbours(*c):
                if q in pts and q not in seen:
                    seen.add(q)
                    stack.append(q)
        if any(c in alive for c in comp):
            continue                        # this blob did keep a skeleton
        cy = sum(c[0] for c in comp) / float(len(comp))
        cx = sum(c[1] for c in comp) / float(len(comp))
        centre = (int(round(cy)), int(round(cx)))
        out.append([centre, centre])
    return out


def _dir(line, at_start, look=6):
    pts = line[:look] if at_start else line[-look:][::-1]
    (y0, x0), (y1, x1) = pts[0], pts[-1]
    dy, dx = y1 - y0, x1 - x0
    n = (dy * dy + dx * dx) ** 0.5
    return (0.0, 0.0) if n < 1e-9 else (dy / n, dx / n)


def link_through_junctions(lines, max_turn=0.55):
    """Join ends that meet and carry on, so a stroke crosses a junction."""
    lines = [list(l) for l in lines if l]
    changed = True
    while changed:
        changed = False
        ends = {}
        for i, line in enumerate(lines):
            if line is None or len(line) < 2:
                continue
            ends.setdefault(line[0], []).append((i, True))
            ends.setdefault(line[-1], []).append((i, False))
        best = None
        for _p, incident in ends.items():
            for a in range(len(incident)):
                for b in range(a + 1, len(incident)):
                    ia, sa = incident[a]
                    ib, sb = incident[b]
                    if ia == ib or lines[ia] is None or lines[ib] is None:
                        continue
                    da, db = _dir(lines[ia], sa), _dir(lines[ib], sb)
                    cost = 1.0 + (da[0] * db[0] + da[1] * db[1])
                    if cost <= max_turn and (best is None or cost < best[0]):
                        best = (cost, ia, sa, ib, sb)
        if best is not None:
            _c, ia, sa, ib, sb = best
            la = lines[ia][::-1] if sa else lines[ia]
            lb = lines[ib] if sb else lines[ib][::-1]
            lines[ia] = la + lb[1:]
            lines[ib] = None
            changed = True
    return [l for l in lines if l]


def prune_spurs(lines, min_len):
    """Drop the hairs a skeleton grows at the end of a wide stroke.

    Only a line that hangs free at exactly one end: two free ends means a
    stroke standing on its own, however short - a dakuten tick, the dot of
    an i.
    """
    ends = {}
    for line in lines:
        for p in (line[0], line[-1]):
            ends[p] = ends.get(p, 0) + 1
    out = []
    for line in lines:
        free = sum(1 for p in (line[0], line[-1]) if ends.get(p, 0) == 1)
        if free == 1 and len(line) < min_len:
            continue
        out.append(line)
    return out or lines


def rdp(points, eps):
    """Douglas-Peucker: drop the points that carry nothing."""
    if len(points) < 3:
        return list(points)
    (y0, x0), (y1, x1) = points[0], points[-1]
    dy, dx = y1 - y0, x1 - x0
    n = (dy * dy + dx * dx) ** 0.5
    worst, at = -1.0, 0
    for i in range(1, len(points) - 1):
        py, px = points[i]
        if n < 1e-9:
            d = ((py - y0) ** 2 + (px - x0) ** 2) ** 0.5
        else:
            d = abs(dy * (px - x0) - dx * (py - y0)) / n
        if d > worst:
            worst, at = d, i
    if worst > eps:
        return rdp(points[:at + 1], eps)[:-1] + rdp(points[at:], eps)
    return [points[0], points[-1]]

# --------------------------------------------------------------------------
# from a glyph to lines in em units
# --------------------------------------------------------------------------

def glyph_lines(ch, qt, np, font, metrics):
    """(advance, [stroke, ...]) for one character, in em units.

    The glyph is drawn at its real size with the baseline at y=0, so the
    points come back in the same frame the renderer lays text out in: x to
    the right from the pen position, y downwards from the baseline.
    """
    QImage, QPainter, QPainterPath, QColor, Qt = qt
    path = QPainterPath()
    path.addText(0.0, 0.0, font, ch)
    rect = path.boundingRect()
    advance = metrics.horizontalAdvance(ch) * EM / float(RENDER_PX)
    if rect.width() <= 0.2 or rect.height() <= 0.2:
        return advance, []                      # a space, or an empty glyph

    margin = 6
    w = int(rect.width()) + 2 * margin + 2
    h = int(rect.height()) + 2 * margin + 2
    img = QImage(w, h, QImage.Format_Grayscale8)
    img.fill(255)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.translate(margin - rect.x(), margin - rect.y())
    p.fillPath(path, QColor(0, 0, 0))
    p.end()

    buf = img.constBits()
    buf.setsize(img.byteCount())
    arr = np.frombuffer(bytes(buf), np.uint8).reshape(h, img.bytesPerLine())
    bits = arr[:, :w] < 128
    if not bits.any():
        return advance, []

    skel = zhang_suen(bits, np)
    lines = trace(skel, np)
    lines = prune_spurs(lines, min_len=max(3, RENDER_PX // 40))
    lines = link_through_junctions(lines)
    lines += blob_centres(bits, skel, np)

    k = EM / float(RENDER_PX)
    out = []
    for line in lines:
        simple = rdp(line, max(1.0, SIMPLIFY / k))
        if len(simple) < 2:
            continue
        pts = []
        for (py, px) in simple:
            x = (px - margin + rect.x()) * k
            y = (py - margin + rect.y()) * k
            pts.append((int(round(x)), int(round(y))))
        # a stroke that got simplified into one spot is a dot, and keeps
        # both of its points so the brush can tell
        out.append(pts)
    return advance, out


def write_file(rows, path, font_name, ascent=880, descent=120):
    """One line per glyph, ASCII only.

    The character is written as its code point rather than itself, so the
    data file cannot be damaged by anything mis-reading an encoding - this
    project has lost non-ASCII text to a tool's round trip before.
    """
    lines = ["# giongo stroke centre lines v1",
             "# source font: %s" % font_name,
             "# licence: SIL Open Font License 1.1 - see %s"
             % os.path.basename(LICENCE),
             "# units: %d per em, x right from the pen, y down from the "
             "baseline" % EM,
             # the renderer centres a letter on its em box, so it needs the
             # same ascent and descent the outline lettering uses
             "# metrics: ascent %d descent %d" % (int(round(ascent)),
                                                  int(round(descent))),
             "# glyph: <code point> <advance> <stroke>|<stroke>, "
             "each stroke 'x,y x,y ...'",
             "# glyphs: %d" % len(rows)]
    for (ch, advance, strokes) in rows:
        body = "|".join(" ".join("%d,%d" % (x, y) for (x, y) in st)
                        for st in strokes)
        lines.append("%04X %d %s" % (ord(ch), int(round(advance)), body))
    io.open(path, "w", encoding="ascii", newline="\n").write(
        "\n".join(lines) + "\n")


def write_licence(path, font_name):
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        "Stroke centre lines in strokelines.txt\n"
        "=====================================\n\n"
        "These are derived from the outlines of %s, which is licensed under\n"
        "the SIL Open Font License, Version 1.1. The data carries no glyph\n"
        "outlines; it is a set of polylines through the middle of each\n"
        "stroke, worked out by tools/make_centrelines.py.\n\n"
        "The full licence text ships with the font and is available at\n"
        "https://openfontlicense.org/ and with the Noto fonts at\n"
        "https://github.com/notofonts/noto-cjk\n\n"
        "Font name and attribution are kept here so that the origin of the\n"
        "data stays visible even though the font itself is not included.\n"
        % font_name)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--font", default=FONT)
    ap.add_argument("--check", action="store_true",
                    help="report what would come out, write nothing")
    ap.add_argument("--only", default="",
                    help="just these characters, for a quick look")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    try:
        import numpy as np
    except ImportError:
        raise SystemExit("needs numpy: this runs outside Krita, not in it")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import (QImage, QPainter, QPainterPath, QColor, QFont,
                             QFontMetricsF, QFontDatabase)
    from PyQt5.QtCore import Qt

    app = QApplication.instance() or QApplication(sys.argv[:1])
    if args.font not in QFontDatabase().families():
        raise SystemExit("font not installed here: %s" % args.font)
    font = QFont(args.font)
    font.setPixelSize(RENDER_PX)
    metrics = QFontMetricsF(font)
    qt = (QImage, QPainter, QPainterPath, QColor, Qt)

    chars = list(args.only) if args.only else glyph_set()
    rows = []
    empty = []
    total_pts = 0
    for ch in chars:
        advance, strokes = glyph_lines(ch, qt, np, font, metrics)
        if not strokes and not ch.isspace():
            empty.append(ch)
        rows.append((ch, advance, strokes))
        total_pts += sum(len(s) for s in strokes)

    print("font     : %s" % args.font)
    print("glyphs   : %d" % len(rows))
    print("points   : %d (%.1f per glyph)"
          % (total_pts, total_pts / float(len(rows) or 1)))
    strokes_per = [len(s) for (_c, _a, s) in rows if s]
    if strokes_per:
        strokes_per.sort()
        print("strokes  : fewest %d, middle %d, most %d"
              % (strokes_per[0], strokes_per[len(strokes_per) // 2],
                 strokes_per[-1]))
    if empty:
        print("no lines : %d (%s)"
              % (len(empty), " ".join(empty[:12])))

    if args.check:
        print("\ncheck only, nothing written")
        return 0

    k = EM / float(RENDER_PX)
    write_file(rows, OUT, args.font,
               ascent=metrics.ascent() * k, descent=metrics.descent() * k)
    write_licence(LICENCE, args.font)
    size = os.path.getsize(OUT)
    print("\nwrote %s (%.1f KB)" % (OUT, size / 1024.0))
    print("wrote %s" % LICENCE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
