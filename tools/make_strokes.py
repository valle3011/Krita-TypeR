# -*- coding: utf-8 -*-
"""Centre lines with the strokes in the order a hand writes them.

This replaces `make_centrelines.py`, which thinned the outlines of a font
down to a skeleton. Skeletonising works, but it knows nothing about strokes:
it cuts a letter apart at every crossing, so an あ came out as eleven pieces
instead of three, and it has no idea which end of a piece was written first,
so a brush landed heavy at the wrong end as often as not.

Two sources know the answer already:

* **KanjiVG** draws every kana as separate paths in writing order, the way
  the character is taught. CC BY-SA 3.0, so the data file we generate from
  it carries that licence too - see `strokelines-LICENSE.txt`.
* **The Hershey fonts** are single-stroke Latin from the start: no outlines
  to thin, just the lines themselves, likewise in writing order.

Neither carries the few Japanese punctuation marks that are nothing but
straight lines (the corner brackets, the wave dash, the ellipsis), so those
are written out by hand below; they are too simple to be anyone's work.

The output is the same file the old tool wrote, and the reader
(`typer_kr/strokefont.py`) is unchanged:

    <code point> <advance> <stroke>|<stroke>|...

Letters have to keep the place they had, or a line that mixes brush
lettering with ordinary outline lettering would come out stepped. So the two
sources are not scaled by some tidy number: each is fitted onto the file the
old tool produced, by least squares over the glyphs they share, and the
metrics line is left exactly as it was.

Usage:

    python make_strokes.py --kanjivg kanjivg-YYYYMMDD.xml.gz \\
                           --hershey futural.jhf \\
                           --old ../typer_kr/strokelines.txt \\
                           --out ../typer_kr/strokelines.txt

    KanjiVG : https://github.com/KanjiVG/kanjivg/releases (the .xml.gz)
    Hershey : futural.jhf, the Simplex Roman, from any of the usual
              distributions of the Hershey data
"""
from __future__ import print_function

import argparse
import gzip
import io
import math
import os
import re
import sys

EM = 1000
#: the box a full-width letter sits in, as the outline font had it. Kept
#: as it was so stroke lettering and outline lettering line up.
METRICS = (1160, 289)

#: how far a flattened curve may stray, in source units
FLATNESS = 0.4
#: how far the written-out line may stray from the flattened one, in em units
SIMPLIFY = 5.0
#: a closed loop no wider than this (in em units) is a dot, not a stroke
DOT_SIZE = 95.0

#: full-width marks drawn with the Latin shape, centred in a full-width box
WIDE = {0xFF1F: "?", 0xFF08: "(", 0xFF09: ")", 0xFF1A: ":", 0xFF1B: ";"}
#: a vowel plus the two marks over it
UMLAUT = {0xC4: "A", 0xD6: "O", 0xDC: "U", 0xE4: "a", 0xF6: "o", 0xFC: "u"}

#: Neither source has an eszett, so it is drawn here, in the frame Hershey
#: uses: x from the left edge of the letter, y down, baseline at 9, the
#: capitals at -12, the waist at -5. One stroke, the way it is written: up
#: the stem, over the top, in at the waist, round the bowl.
HAND_LATIN = {
    0xDF: (11.0, [[(1, 9), (1, -7), (2, -10), (4, -12), (6, -12), (8, -11),
                   (9, -9), (9, -6), (7, -3), (5, -1), (7, 0), (9, 2),
                   (10, 4), (10, 7), (8, 9), (5, 9), (3, 8)]]),
}


# --------------------------------------------------------------- KanjiVG ---
_PATH = re.compile(r'<path\b[^>]*\bd="([^"]+)"')
_GLYPH = re.compile(r'<kanji id="kvg:kanji_([0-9a-f]+)"')
_TOKEN = re.compile(r'[MmCcSsLlZz]|[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?')


def _cubic(p0, p1, p2, p3, out):
    """Walk a cubic as short straight pieces, fine enough to look curved."""
    span = (abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])
            + abs(p2[0] - p1[0]) + abs(p2[1] - p1[1])
            + abs(p3[0] - p2[0]) + abs(p3[1] - p2[1]))
    n = max(2, min(48, int(math.ceil(span / max(0.05, FLATNESS)))))
    for i in range(1, n + 1):
        t = i / float(n)
        u = 1.0 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t * t * t * p3[1]))


def svg_points(d):
    """One SVG path as a list of points. KanjiVG uses M/m, C/c, S/s only."""
    toks = _TOKEN.findall(d)
    pts, cur, start, prev_c2, cmd = [], (0.0, 0.0), (0.0, 0.0), None, None
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                if pts and pts[-1] != start:
                    pts.append(start)
                cur, prev_c2 = start, None
                continue
        if i >= len(toks) or toks[i].isalpha():
            continue
        rel = cmd.islower()
        base = cur if rel else (0.0, 0.0)
        up = cmd.upper()
        if up == "M":
            cur = (base[0] + float(toks[i]), base[1] + float(toks[i + 1]))
            i += 2
            start = cur
            pts.append(cur)
            cmd = "l" if rel else "L"          # as SVG says: M then implicit L
            prev_c2 = None
        elif up == "L":
            cur = (base[0] + float(toks[i]), base[1] + float(toks[i + 1]))
            i += 2
            pts.append(cur)
            prev_c2 = None
        elif up in ("C", "S"):
            if up == "C":
                c1 = (base[0] + float(toks[i]), base[1] + float(toks[i + 1]))
                c2 = (base[0] + float(toks[i + 2]),
                      base[1] + float(toks[i + 3]))
                end = (base[0] + float(toks[i + 4]),
                       base[1] + float(toks[i + 5]))
                i += 6
            else:
                c1 = cur if prev_c2 is None else (2 * cur[0] - prev_c2[0],
                                                  2 * cur[1] - prev_c2[1])
                c2 = (base[0] + float(toks[i]), base[1] + float(toks[i + 1]))
                end = (base[0] + float(toks[i + 2]),
                       base[1] + float(toks[i + 3]))
                i += 4
            if not pts:
                pts.append(cur)
            _cubic(cur, c1, c2, end, pts)
            cur, prev_c2 = end, c2
        else:                                   # nothing else occurs in the
            i += 1                              # data; skip rather than guess
    return pts


def read_kanjivg(path, wanted):
    """{code point: [stroke, ...]} in the 109-unit frame KanjiVG draws in."""
    out = {}
    cur = None
    opener = gzip.open if path.endswith(".gz") else io.open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            m = _GLYPH.search(line)
            if m:
                code = int(m.group(1), 16)
                cur = out.setdefault(code, []) if code in wanted else None
                continue
            if cur is None:
                continue
            m = _PATH.search(line)
            if m:
                pts = svg_points(m.group(1))
                if len(pts) >= 2:
                    cur.append(pts)
    return dict((c, s) for (c, s) in out.items() if s)


# --------------------------------------------------------------- Hershey ---
def read_hershey(path):
    """{character: (left, right, [stroke, ...])}, ASCII from the space up.

    The .jhf line is a glyph number, a vertex count, then coordinate pairs
    one character each, offset from 'R'. The first pair is not a point: it
    is the left and right edge of the letter's advance. ' R' lifts the pen.
    """
    out = {}
    code = 0x20
    for line in io.open(path, encoding="latin-1"):
        line = line.rstrip("\r\n")
        if len(line) < 10:
            continue
        body = line[8:]
        left = ord(body[0]) - ord("R")
        right = ord(body[1]) - ord("R")
        strokes, cur = [], []
        for i in range(2, len(body) - 1, 2):
            pair = body[i:i + 2]
            if pair == " R":
                if len(cur) >= 2:
                    strokes.append(cur)
                cur = []
                continue
            cur.append((float(ord(pair[0]) - ord("R")),
                        float(ord(pair[1]) - ord("R"))))
        if len(cur) >= 2:
            strokes.append(cur)
        out[chr(code)] = (float(left), float(right), strokes)
        code += 1
    return out


# ------------------------------------------------------------ hand-drawn ---
#: The marks that are nothing but straight lines, in the same frame as
#: KanjiVG: a 109 box, x right, y down from the top.
HAND = {
    0x300C: [[(74, 18), (26, 18), (26, 56)]],                 # LEFT CORNER
    0x300D: [[(83, 53), (83, 91), (35, 91)]],                 # RIGHT CORNER
    0x300E: [[(74, 14), (18, 14), (18, 56)],                  # WHITE CORNER
             [(74, 25), (29, 25), (29, 56)]],
    0x300F: [[(80, 53), (80, 95), (35, 95)],
             [(91, 53), (91, 84), (35, 84)]],
    0x301C: [[(12, 64), (28, 48), (44, 48), (65, 70), (81, 70), (97, 54)]],
    0x2026: [[(18, 78), (18, 78)], [(55, 78), (55, 78)],      # three dots
             [(92, 78), (92, 78)]],
}


# ---------------------------------------------------------------- fitting ---
def read_old(path):
    """The file the old tool wrote: {code point: (advance, [stroke, ...])}."""
    out = {}
    for line in io.open(path, encoding="ascii"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        bits = line.split(" ", 2)
        if len(bits) < 3:
            continue
        strokes = []
        for chunk in bits[2].split("|"):
            pts = [tuple(float(v) for v in p.split(","))
                   for p in chunk.split()]
            if len(pts) >= 2:
                strokes.append(pts)
        out[int(bits[0], 16)] = (int(bits[1]), strokes)
    return out


def _box(strokes):
    xs = [x for s in strokes for (x, _y) in s]
    ys = [y for s in strokes for (_x, y) in s]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _fit(pairs):
    """Least squares k, b for dst = k * src + b."""
    n = float(len(pairs))
    sx = sum(a for (a, _b) in pairs)
    sy = sum(b for (_a, b) in pairs)
    sxx = sum(a * a for (a, _b) in pairs)
    sxy = sum(a * b for (a, b) in pairs)
    den = n * sxx - sx * sx
    if abs(den) < 1e-9:
        return 1.0, 0.0
    k = (n * sxy - sx * sy) / den
    return k, (sy - k * sx) / n


def fit_source(new, old, note):
    """Scale and shift one source onto the frame the old file used.

    Both the left and the right edge of every shared letter, and both the
    top and the bottom, go into the fit, so a letter ends up the size it
    was as well as in the place it was.
    """
    xs, ys = [], []
    for code, strokes in new.items():
        if code not in old:
            continue
        a, b = _box(strokes), _box(old[code][1])
        if not a or not b:
            continue
        xs.extend([(a[0], b[0]), (a[2], b[2])])
        ys.extend([(a[1], b[1]), (a[3], b[3])])
    if len(xs) < 8:
        raise SystemExit("too few shared glyphs to fit %s" % note)
    kx, bx = _fit(xs)
    ky, by = _fit(ys)
    err = max(abs(ky * a + by - b) for (a, b) in ys)
    print("  %-8s %4d glyphs  x: %.4f*s%+.1f  y: %.4f*s%+.1f  "
          "worst y error %.0f/1000em" % (note, len(xs) // 2, kx, bx, ky, by,
                                         err))
    return (kx, bx, ky, by)


# ----------------------------------------------------------------- output ---
def rdp(pts, tol):
    """Douglas-Peucker: drop the points that say nothing."""
    if len(pts) < 3:
        return list(pts)
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    den = math.hypot(dx, dy)
    worst, at = -1.0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        if den < 1e-9:
            d = math.hypot(x - x0, y - y0)
        else:
            d = abs(dy * x - dx * y + x1 * y0 - y1 * x0) / den
        if d > worst:
            worst, at = d, i
    if worst <= tol:
        return [pts[0], pts[-1]]
    return rdp(pts[:at + 1], tol)[:-1] + rdp(pts[at:], tol)


def tidy(strokes):
    """Round to whole em units, drop repeats, turn tiny loops into dots."""
    out = []
    for st in strokes:
        box = _box([st])
        closed = math.hypot(st[0][0] - st[-1][0], st[0][1] - st[-1][1]) < 12.0
        if closed and max(box[2] - box[0], box[3] - box[1]) < DOT_SIZE:
            cx = (box[0] + box[2]) / 2.0
            cy = (box[1] + box[3]) / 2.0
            out.append([(int(round(cx)), int(round(cy)))] * 2)
            continue
        pts = rdp(st, SIMPLIFY)
        got = []
        for p in pts:
            q = (int(round(p[0])), int(round(p[1])))
            if not got or q != got[-1]:
                got.append(q)
        if len(got) == 1:
            got = got * 2
        if len(got) >= 2:
            out.append(got)
    return out


def place(strokes, k, bx, by, ky=None):
    ky = k if ky is None else ky
    return [[(x * k + bx, y * ky + by) for (x, y) in st] for st in strokes]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kanjivg", required=True)
    ap.add_argument("--hershey", required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    old = read_old(args.old)
    print("old file: %d glyphs" % len(old))

    # kana, the iteration mark, and the two marks KanjiVG draws itself
    wanted = set(range(0x3041, 0x3100))
    wanted |= set([0x3005, 0x3001, 0x3002, 0xFF01])
    kvg = read_kanjivg(args.kanjivg, wanted)
    kvg.update(dict((c, [[(float(x), float(y)) for (x, y) in s] for s in v])
                    for (c, v) in HAND.items()))
    print("KanjiVG: %d glyphs" % len(kvg))

    her = read_hershey(args.hershey)
    print("Hershey: %d glyphs" % len(her))

    print("fitted onto the old frame:")
    kx, bx, ky, by = fit_source(kvg, old, "KanjiVG")
    # Hershey is measured from its own left edge, so it is already where the
    # pen is; only the size and the height above the baseline are fitted.
    pen = {}
    for ch, (left, right, strokes) in her.items():
        code = ord(ch)
        if strokes:
            pen[code] = [[(x - left, y) for (x, y) in st] for st in strokes]
    hx, hbx, hy, hby = fit_source(pen, old, "Hershey")

    glyphs = {}
    for code, strokes in kvg.items():
        glyphs[code] = (EM, tidy(place(strokes, kx, bx, by, ky)))
    for code, strokes in pen.items():
        left, right, _s = her[chr(code)]
        adv = int(round((right - left) * hx))
        glyphs[code] = (adv, tidy(place(strokes, hx, hbx, hby, hy)))
    for code, (width, strokes) in sorted(HAND_LATIN.items()):
        glyphs[code] = (int(round(width * hx)),
                        tidy(place([[(float(x), float(y)) for (x, y) in st]
                                    for st in strokes],
                                   hx, hbx, hby, hy)))

    # A vowel with the two marks over it. They are short ticks rather than
    # dots: a brush writing quickly flicks them, and a round blob at the
    # brush's own width would be bigger than the letter can carry.
    for code, base in sorted(UMLAUT.items()):
        src = glyphs.get(ord(base))
        if not src:
            continue
        adv, strokes = src
        top = min(y for st in strokes for (_x, y) in st)
        mid = sum(x for st in strokes for (x, _y) in st) / float(
            sum(len(st) for st in strokes))
        gap, high = EM * 0.15, top - EM * 0.14
        tick = (EM * 0.035, EM * 0.085)
        marks = [[(int(round(mid + d - tick[0])), int(round(high))),
                  (int(round(mid + d + tick[0])),
                   int(round(high + tick[1])))] for d in (-gap, gap)]
        glyphs[code] = (adv, list(strokes) + marks)
    for code, base in sorted(WIDE.items()):
        src = glyphs.get(ord(base))
        if not src:
            continue
        adv, strokes = src
        shift = (EM - adv) / 2.0
        glyphs[code] = (EM, [[(int(round(x + shift)), y) for (x, y) in st]
                             for st in strokes])

    write_file(args.out, glyphs)
    return 0


def write_file(path, glyphs):
    lines = ["# giongo stroke centre lines v2",
             "# sources: KanjiVG (kana, Japanese marks) CC BY-SA 3.0,",
             "#          Hershey simplex (Latin) - see "
             "strokelines-LICENSE.txt",
             "# units: 1000 per em, x right from the pen, y down from "
             "the baseline",
             "# metrics: ascent %d descent %d" % METRICS,
             "# glyph: <code point> <advance> <stroke>|<stroke>, each "
             "stroke 'x,y x,y ...'",
             "# glyphs: %d" % len(glyphs)]
    n_s = n_p = 0
    for code in sorted(glyphs):
        adv, strokes = glyphs[code]
        if not strokes:
            continue
        n_s += len(strokes)
        n_p += sum(len(st) for st in strokes)
        body = "|".join(" ".join("%d,%d" % (x, y) for (x, y) in st)
                        for st in strokes)
        lines.append("%04X %d %s" % (code, adv, body))
    text = "\n".join(lines) + "\n"
    with io.open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(text)
    print("wrote %s: %d glyphs, %d strokes, %d points, %.1f KB"
          % (os.path.basename(path), len(glyphs), n_s, n_p,
             len(text) / 1024.0))


if __name__ == "__main__":
    sys.exit(main())
