# -*- coding: utf-8 -*-
"""Draw Giongo lettering: placements from :mod:`giongo` → filled outlines.

Everything is built as glyph *outlines* (QPainterPath), never as live text,
for two reasons: a letter can then be sheared, stretched and thickened like
any shape, and the vector result does not depend on Krita's text engine
having the font — the SVG carries the shapes themselves.

The drawing is first collected as a *scene*: a list of layers back to front,
each one path with one paint. The same scene is then painted into a QImage
(preview, paint layer, PNG) or written out as SVG (vector layer, .svg file),
so the two can never drift apart.

Layer order, back to front:
    afterimages → shadow / 3D extrusion → trembling copies →
    outlines (outer → inner) → fill
With outline mode "letter" every letter gets its own stack, so the nearer
letter's outline cuts into the one behind; with "merged" the outlines of all
letters are drawn first and the word reads as one block.
"""
import math
import os
import random

from ._qt import (
    QPainterPath, QPainterPathStroker, QTransform, QFont, QFontMetricsF,
    QImage, QPainter, QColor, QBrush, QPen, QLinearGradient, QPointF,
    QBuffer, QIODevice,
    QRectF, Qt,
)
from . import giongo as G
from . import strokefont as SF
from . import giongo_brush as BR
from . import giongo_warp as W
from . import giongo_nodes as N
from . import giongo_trace as TR

_REF = 200.0          # glyph outlines are built at this pixel size, then scaled
_glyph_cache = {}
#: the same for letters drawn along their centre lines
_stroke_cache = {}


def _font(family, bold):
    f = QFont(family) if family else QFont()
    if not family:
        f.setStyleHint(QFont.StyleHint.SansSerif)
    f.setPixelSize(int(_REF))
    f.setBold(bool(bold))
    return f


def stroke_glyph(ch, pen, seed, width=100, style=None):
    """(outline at _REF px centred on the em box, advance in em), or None.

    None means this character has no centre lines - a kanji, say - and the
    caller falls back to the font outline, so a mixed line still comes out
    whole rather than with holes in it.
    """
    key = (ch, pen, int(seed), int(width))
    hit = _stroke_cache.get(key)
    if hit is not None:
        return hit
    got = SF.scaled(ch, _REF)
    if not got:
        return None
    advance, strokes = got
    polys = BR.letter_outlines(strokes, _REF, pen=pen, seed=int(seed),
                               width_scale=max(0.1, width / 100.0),
                               style=style)
    if not polys:
        return None
    path = QPainterPath()
    for poly in polys:
        if len(poly) < 3:
            continue
        path.moveTo(QPointF(poly[0][0], poly[0][1]))
        for (x, y) in poly[1:]:
            path.lineTo(QPointF(x, y))
        path.closeSubpath()
    # centred the same way an outline glyph is, with the metrics of the font
    # the lines were taken from
    asc, desc = SF.metrics()
    k = _REF / float(SF.EM)
    path.translate(-advance / 2.0, (asc - desc) * k / 2.0)
    path.setFillRule(Qt.FillRule.WindingFill)
    res = (path, (advance / _REF) if advance > 0 else 1.0)
    if len(_stroke_cache) > 2000:
        _stroke_cache.clear()
    _stroke_cache[key] = res
    return res


def glyph(ch, family, bold):
    """(outline at _REF px centred on the origin, advance in em). Centred on
    the em box, not on the ink, so ッ sits low and ー sits mid-height as the
    font drew them."""
    key = (ch, family, bool(bold))
    hit = _glyph_cache.get(key)
    if hit is not None:
        return hit
    font = _font(family, bold)
    fm = QFontMetricsF(font)
    adv = fm.horizontalAdvance(ch) if hasattr(fm, "horizontalAdvance") \
        else fm.width(ch)
    path = QPainterPath()
    path.addText(0.0, 0.0, font, ch)
    cx = adv / 2.0
    cy = (-fm.ascent() + fm.descent()) / 2.0
    path.translate(-cx, -cy)
    path.setFillRule(Qt.FillRule.WindingFill)
    res = (path, (adv / _REF) if adv > 0 else 1.0)
    if len(_glyph_cache) > 4000:
        _glyph_cache.clear()
    _glyph_cache[key] = res
    return res


def _bar_path(length, size):
    """A merged ーー run: a long stroke, thick at the start, tapering out."""
    t = size * 0.15
    half = length / 2.0
    path = QPainterPath()
    path.moveTo(-half, -t / 2)
    path.cubicTo(-half + length * 0.3, -t * 0.55, half - length * 0.25,
                 -t * 0.3, half, -t * 0.08)
    path.lineTo(half, t * 0.08)
    path.cubicTo(half - length * 0.25, t * 0.3, -half + length * 0.3,
                 t * 0.55, -half, t / 2)
    path.closeSubpath()
    # round the blunt start
    cap = QPainterPath()
    cap.addEllipse(QPointF(-half, 0.0), t / 2, t / 2)
    return path.united(cap)


def _stroke(path, width):
    if width <= 0:
        return QPainterPath(path)
    st = QPainterPathStroker()
    st.setWidth(width)
    st.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    st.setCapStyle(Qt.PenCapStyle.RoundCap)
    out = st.createStroke(path).united(path)
    out.setFillRule(Qt.FillRule.WindingFill)
    return out



def _ring(path, width):
    """The letter drawn as its own contour line, `width` thick, hollow.

    The band is laid across the contour and then clipped to the letter,
    so only the inward half survives: the shape keeps exactly the outline
    it had, where a band straddling the contour would make it fatter than
    the filled letter it stands in for.
    """
    st = QPainterPathStroker()
    st.setWidth(max(0.4, width * 2.0))
    st.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    st.setCapStyle(Qt.PenCapStyle.RoundCap)
    out = st.createStroke(path).intersected(path)
    out.setFillRule(Qt.FillRule.WindingFill)
    return out


#: letter shapes and the bands grown around them, both built at the
#: origin and moved into place afterwards. Dragging a letter changes
#: where it is, not what it looks like, so both survive the drag.
_shape_cache = {}
_band_cache = {}


def _style_key(style):
    return None if not style else tuple(sorted(style.items()))



def _resample_xy(pts, step):
    """The polyline with its points a steady `step` apart, closed."""
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    px, py = pts[0]
    acc = 0.0
    for cx, cy in list(pts[1:]) + [pts[0]]:
        dx, dy = cx - px, cy - py
        seg = math.hypot(dx, dy)
        while seg > 0 and acc + seg >= step:
            t = (step - acc) / seg
            px, py = px + dx * t, py + dy * t
            out.append((px, py))
            dx, dy = cx - px, cy - py
            seg = math.hypot(dx, dy)
            acc = 0.0
        acc += seg
        px, py = cx, cy
    return out


def warp_path(path, dabs):
    """`path` pushed about by the brush. Both are in the glyph's own em.

    The outline is walked at a steady step first: a contour as the font
    drew it has long straight runs, and a brush that lands in the middle
    of one would move nothing at all.
    """
    if not dabs:
        return path
    # fine enough that a strong dab cannot pull the outline into
    # visible straight runs, coarse enough to stay cheap
    smallest = min(d[3] for d in dabs)
    step = max(2.0, min(smallest / 8.0, 15.0))
    out = QPainterPath()
    for poly in path.toSubpathPolygons(QTransform.fromScale(2.0, 2.0)):
        pts = _resample_xy([(q.x() / 2.0, q.y() / 2.0) for q in poly], step)
        if len(pts) < 3:
            continue
        pts = W.warp_points(pts, dabs)
        out.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            out.lineTo(x, y)
        out.closeSubpath()
    out.setFillRule(Qt.FillRule.WindingFill)
    return out


def _ring_cut(path, radius):
    """A line as a solid shape with round ends: what an eraser takes."""
    st = QPainterPathStroker()
    st.setWidth(max(1.0, radius * 2.0))
    st.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    st.setCapStyle(Qt.PenCapStyle.RoundCap)
    out = st.createStroke(path)
    out.setFillRule(Qt.FillRule.WindingFill)
    return out


def path_from_nodes(contours):
    """Editable nodes -> a path. A segment with no handles is a line."""
    out = QPainterPath()
    for ring in contours or []:
        if len(ring) < 2:
            continue
        out.moveTo(ring[0][0], ring[0][1])
        for k in range(len(ring)):
            a = ring[k]
            b = ring[(k + 1) % len(ring)]
            if a[4] == 0.0 and a[5] == 0.0 and b[2] == 0.0 and b[3] == 0.0:
                out.lineTo(b[0], b[1])
            else:
                out.cubicTo(a[0] + a[4], a[1] + a[5],
                            b[0] + b[2], b[1] + b[3], b[0], b[1])
        out.closeSubpath()
    out.setFillRule(Qt.FillRule.WindingFill)
    return out


def nodes_from_path(path):
    """A path -> editable nodes, segment for segment.

    Nothing is approximated: a font's outline is already cubics and
    lines, and both come back as what they were.
    """
    contours = []
    ring = None
    i = 0
    n = path.elementCount()
    while i < n:
        el = path.elementAt(i)
        if el.isMoveTo():
            ring = [N.node(el.x, el.y)]
            contours.append(ring)
            i += 1
        elif ring is None:
            i += 1
        elif el.isLineTo():
            ring.append(N.node(el.x, el.y))
            i += 1
        elif el.isCurveTo() and i + 2 < n:
            c1, c2, end = (path.elementAt(i), path.elementAt(i + 1),
                           path.elementAt(i + 2))
            prev = ring[-1]
            prev[4], prev[5] = c1.x - prev[0], c1.y - prev[1]
            ring.append(N.node(end.x, end.y, c2.x - end.x, c2.y - end.y))
            i += 3
        else:
            i += 1
    out = []
    for ring in contours:
        # a closed contour comes back with its last point on its first
        if len(ring) > 2 and abs(ring[-1][0] - ring[0][0]) < 0.01 \
                and abs(ring[-1][1] - ring[0][1]) < 0.01:
            last = ring.pop()
            ring[0][2], ring[0][3] = last[2], last[3]
        if len(ring) >= 2:
            out.append(ring)
    return out


def em_shape(pl, family, bold, pen="off", seed=0, pen_width=100,
             pen_style=None, dabs=(), nodes=(), letterset=""):
    """The letter in its own em, before it is placed: what the brush and
    the point editor work on.

    Once a letter has nodes of its own they ARE the letter - the font is
    no longer asked. A warp still applies on top of them, so liquify and
    point editing can be used one after the other.
    """
    if nodes:
        shape = path_from_nodes(nodes)
    else:
        shape = None
        drawn = TR.glyph_of(letterset, pl["ch"]) if letterset else None
        if drawn:
            shape = path_from_nodes(drawn)
        if shape is None and pen and pen != "off":
            got = stroke_glyph(pl["ch"], pen, seed + pl.get("i", 0) * 13,
                               pen_width, pen_style)
            if got is not None:
                shape = got[0]
        if shape is None:                # no centre lines for this character
            shape, _adv = glyph(pl["ch"], family, bold)
    if dabs:
        # the brush works on the glyph as it was drawn, before the letter
        # is turned, leaned and placed - so a warp belongs to the letter
        # and follows it wherever the layout puts it
        shape = warp_path(shape, dabs)
    return shape


def letter_transform(pl, with_pos=True):
    """Where a letter's own coordinates land on the page.

    The shapes are built without the position (see `letter_shapes`), so
    `with_pos=False` gives exactly the transform used there. The panel
    uses the full one, inverted, to find out where on a letter the brush
    is pointing.
    """
    tr = QTransform()
    if with_pos:
        tr.translate(pl["x"], pl["y"])
    tr.rotate(pl["angle"])
    if not pl["bar"]:
        tr.shear(-math.tan(math.radians(pl["shear"])), 0.0)
        k = pl["size"] / _REF
        tr.scale(k * pl["sx"], k)
    return tr


def letter_shapes(pl, family, bold, thicken_pct, pen="off", seed=0,
                  pen_width=100, pen_style=None, dabs=(), nodes=(),
                  letterset=""):
    """(key, thickened, untouched) for one placement, AT THE ORIGIN.

    The caller moves them to `pl["x"], pl["y"]`. Keeping the position out
    of the shape is what makes the cache worth having: a drag changes the
    position sixty times a second and the shape not at all.
    """
    key = (pl["ch"], bool(pl["bar"]), round(pl.get("length", 0.0), 2),
           round(pl["size"], 3), round(pl["angle"], 3),
           round(pl["shear"], 3), round(pl["sx"], 4), family, bool(bold),
           pen, pen_width, _style_key(pen_style),
           seed + pl.get("i", 0) * 13, round(thicken_pct, 3),
           W.fingerprint(dabs), N.fingerprint(nodes),
           TR.fingerprint(letterset, pl["ch"]))
    hit = _shape_cache.get(key)
    if hit is not None:
        return hit
    size = pl["size"]
    if pl["bar"]:
        shape = _bar_path(pl["length"], size)
        path = letter_transform(pl, with_pos=False).map(shape)
    else:
        shape = em_shape(pl, family, bold, pen, seed, pen_width, pen_style,
                         dabs, nodes, letterset)
        path = letter_transform(pl, with_pos=False).map(shape)
    path.setFillRule(Qt.FillRule.WindingFill)
    base = path
    if thicken_pct > 0:
        path = _stroke(path, size * thicken_pct / 100.0 * 2.0)
        path.setFillRule(Qt.FillRule.WindingFill)
    if len(_shape_cache) > 500:
        _shape_cache.clear()
    res = (key, path, base)
    _shape_cache[key] = res
    return res


def grown_band(key, base, width):
    """`base` grown by `width`, at the origin, cached under its shape."""
    ck = (key, round(width, 2))
    hit = _band_cache.get(ck)
    if hit is None:
        hit = _stroke(base, width)
        if len(_band_cache) > 1500:
            _band_cache.clear()
        _band_cache[ck] = hit
    return hit


def letter_path(pl, family, bold, thicken_pct, pen="off", seed=0,
                pen_width=100, pen_style=None, with_base=False):
    """One placement → its filled outline in page coordinates.

    With `with_base`, returns (thickened, untouched): everything that has
    to grow around the letter should grow the untouched one by the sum of
    the distances, not stroke the thickened one again.
    """
    _k, path, base = letter_shapes(pl, family, bold, thicken_pct, pen, seed,
                                   pen_width, pen_style)
    path = path.translated(pl["x"], pl["y"])
    if not with_base:
        return path
    return path, base.translated(pl["x"], pl["y"])


# --- the scene -------------------------------------------------------------

class Layer(object):
    """One shape with one paint. kind: 'fill' | 'outline' | 'shadow' |
    'shake' | 'after' | 'noise' | 'deco' — what it is, so a raster export could
    split layers."""
    __slots__ = ("path", "color", "kind", "opacity", "line_w", "paint")

    def __init__(self, path, color, kind, opacity=1.0, line_w=0.0,
                 paint="solid"):
        self.path = path
        self.color = color
        self.kind = kind
        self.opacity = opacity
        self.line_w = line_w        # > 0: drawn as a line, not filled
        self.paint = paint          # solid | gradient | tone (fills only)


class Scene(object):
    def __init__(self, layers, params, bounds):
        self.layers = layers
        self.params = params
        self.bounds = bounds        # QRectF of everything, before framing

    def is_empty(self):
        return not self.layers or self.bounds.isEmpty()

    def needs_raster(self):
        """Fills Krita cannot be handed as vector art and get back whole."""
        return any(l.paint in ("tone", "tone_grad", "pattern")
                   for l in self.layers)


def advance_fn(params, family="", bold=None):
    """How wide each letter really is, as a fraction of its size.

    The advance has to come from whatever will actually be drawn, or the
    letters shift the moment a pen is switched on - and the path handles,
    which are placed from the same number, would sit beside the letters
    instead of at their ends.
    """
    pen = (params or {}).get("pen") or "off"
    bold = bool((params or {}).get("bold")) if bold is None else bool(bold)

    def adv(ch):
        if pen and pen != "off":
            got = SF.glyph(ch)
            if got:
                return (got[0] / float(SF.EM)) or 1.0
        return glyph(ch, family, bold)[1]
    return adv



CAPTION_POS = ("below", "above", "right", "left")


def caption_path(text, family, bold, px):
    """The caption as one path, centred on the origin, at `px` tall."""
    if not (text or "").strip() or px <= 0:
        return None
    font = _font(family, bold)
    font.setPixelSize(max(2, int(px)))
    fm = QFontMetricsF(font)
    path = QPainterPath()
    path.addText(0.0, 0.0, font, text)
    adv = fm.horizontalAdvance(text) if hasattr(fm, "horizontalAdvance") \
        else fm.width(text)
    path.translate(-adv / 2.0, (fm.ascent() - fm.descent()) / 2.0)
    path.setFillRule(Qt.FillRule.WindingFill)
    return path


def place_caption(path, box, where, gap):
    """Move a caption path next to `box`. Returns the moved path."""
    if path is None or box.isEmpty():
        return path
    r = path.boundingRect()
    if where == "above":
        dx, dy = box.center().x(), box.top() - gap - r.height() / 2.0
    elif where == "right":
        dx, dy = box.right() + gap + r.width() / 2.0, box.center().y()
    elif where == "left":
        dx, dy = box.left() - gap - r.width() / 2.0, box.center().y()
    else:                                   # below
        dx, dy = box.center().x(), box.bottom() + gap + r.height() / 2.0
    out = QPainterPath(path)
    out.translate(dx, dy)
    return out



#: how each hand behaves: damping of the walk, how often it lifts, the
#: step along the contour (x amp), the amplitude and the line width
#: (both x what was asked for). A steady hand keeps most of its last
#: offset, which is what makes a drawn line; no damping is a fringe.
NOISE_LOOK = {
    "hand": (0.72, 0.12, 1.4, 1.0, 1.0),
    "dry": (0.60, 0.45, 1.0, 1.15, 1.25),
    "fuzzy": (0.20, 0.05, 0.7, 0.75, 0.5),
}


def sketch_path(path, amp, seed, style="hand"):
    """`path`'s contour walked again by hand: a wandering line, lifted now
    and then. Returns an open path meant to be drawn as a line."""
    out = QPainterPath()
    if amp <= 0:
        return out
    damp, dry, stepf, ampf, _w = NOISE_LOOK.get(style, NOISE_LOOK["hand"])
    amp = amp * ampf
    rng = random.Random(seed)
    step = max(1.2, amp * stepf)
    # flattened four times larger, so the curves do not come back as
    # visible straight runs at the size the letters are actually drawn
    polys = path.toSubpathPolygons(QTransform.fromScale(4.0, 4.0))
    for poly in polys:
        pts = _resample([QPointF(q.x() / 4.0, q.y() / 4.0) for q in poly],
                        step)
        if len(pts) < 3:
            continue
        off = 0.0
        down = False
        for i, pt in enumerate(pts):
            nxt = pts[(i + 1) % len(pts)]
            tx, ty = nxt.x() - pt.x(), nxt.y() - pt.y()
            ln = math.hypot(tx, ty) or 1.0
            # the hand wanders: a damped walk, not fresh noise per point
            off = off * damp + rng.uniform(-1.0, 1.0) * amp * 0.75
            q = QPointF(pt.x() - ty / ln * off, pt.y() + tx / ln * off)
            if not down or rng.random() < dry:
                out.moveTo(q)
                down = True
            else:
                out.lineTo(q)
    return out


def _resample(pts, step):
    """The same polyline with its points a steady `step` apart."""
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    prev = pts[0]
    acc = 0.0
    for cur in pts[1:] + [pts[0]]:
        dx, dy = cur.x() - prev.x(), cur.y() - prev.y()
        seg = math.hypot(dx, dy)
        while seg > 0 and acc + seg >= step:
            t = (step - acc) / seg
            prev = QPointF(prev.x() + dx * t, prev.y() + dy * t)
            out.append(prev)
            dx, dy = cur.x() - prev.x(), cur.y() - prev.y()
            seg = math.hypot(dx, dy)
            acc = 0.0
        acc += seg
        prev = cur
    return out



def deco_path(item):
    """One decoration as a path, already in page coordinates."""
    kind = item["kind"]
    s = max(0.5, float(item["size"]))
    path = QPainterPath()
    if kind == "ray":
        # a wedge: a point where it meets the word, wide where it ends
        ln = max(1.0, float(item["len"]))
        path.moveTo(0.0, 0.0)
        path.lineTo(ln, -s / 2.0)
        path.lineTo(ln, s / 2.0)
        path.closeSubpath()
    elif kind == "sparkle":
        # a four-pointed star: long points, a waist that almost pinches
        waist = s * 0.16
        pts = []
        for k in range(4):
            ang = math.radians(90.0 * k)
            pts.append((math.cos(ang) * s, math.sin(ang) * s))
            ang += math.radians(45.0)
            pts.append((math.cos(ang) * waist, math.sin(ang) * waist))
        path.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            path.lineTo(x, y)
        path.closeSubpath()
    elif kind == "drops":
        # a teardrop: round at the back, drawn out to a point in front
        path.moveTo(s, 0.0)
        path.quadTo(s * 0.1, -s * 0.5, -s * 0.45, -s * 0.33)
        path.quadTo(-s * 0.9, 0.0, -s * 0.45, s * 0.33)
        path.quadTo(s * 0.1, s * 0.5, s, 0.0)
        path.closeSubpath()
    else:                                   # debris: a chipped shard
        for k, (f, a) in enumerate(((1.0, 0), (0.45, 105), (0.8, 190),
                                    (0.35, 290))):
            ang = math.radians(a)
            x, y = math.cos(ang) * s * f, math.sin(ang) * s * f
            if k == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
    tr = QTransform()
    tr.translate(item["x"], item["y"])
    tr.rotate(item["angle"])
    out = tr.map(path)
    out.setFillRule(Qt.FillRule.WindingFill)
    return out


def build_scene(text, params, family=""):
    """Text + parameters → a Scene. `family` is the resolved font family
    ("" = the default sans)."""
    p = G.effective(params)
    bold = p["bold"]

    pen = p.get("pen", "off")

    places = G.layout(text, p, advance_fn=advance_fn(p, family, bold))
    S = float(p["letter_px"])
    rng = random.Random(p["seed"] * 7 + 3)
    style = BR.style_from(p, pen)
    shapes = [letter_shapes(pl, family, bold, p["thicken"], pen, p["seed"],
                            p.get("pen_width", 100), style,
                            W.warp_of(p, pl["group"], pl["index"]),
                            N.nodes_of(p, pl["group"], pl["index"]),
                            p.get("letterset", ""))
              for pl in places]
    letters = [(pl, path.translated(pl["x"], pl["y"]))
               for pl, (_k, path, _b) in zip(places, shapes)]
    #: how far the letter was thickened: anything growing around it starts
    #: from the untouched shape and grows by the sum, see `_stroke`
    grown = p["thicken"] / 100.0 * 2.0

    def band(i, width):
        """The i-th letter grown by `width`, in page coordinates."""
        key, _path, base = shapes[i]
        pl = places[i]
        return grown_band(key, base, width).translated(pl["x"], pl["y"])
    outs = p["outlines"]
    # cumulative: outline k is everything up to and including its width
    cum = []
    acc = 0.0
    for col, w in outs:
        acc += w
        cum.append((col, acc))

    def stacks(i, size):
        """[(colour, shape)] outer → inner, then the letter itself."""
        res = []
        for col, w in reversed(cum):
            res.append((col, band(i, size * (w / 100.0 * 2.0 + grown))))
        return res

    silhouettes = []
    for i, (pl, path) in enumerate(letters):
        if cum:
            silhouettes.append(
                band(i, pl["size"] * (cum[-1][1] / 100.0 * 2.0 + grown)))
        else:
            silhouettes.append(path)

    layers = []
    # afterimages: faint copies of the whole word trailing against the motion
    if p["afterimage"] and letters:
        n = int(p["afterimage"])
        for k in range(n, 0, -1):
            for (pl, path), sil in zip(letters, silhouettes):
                ang = math.radians(pl["path_angle"])
                d = -S * 0.13 * k
                tr = QTransform.fromTranslate(math.cos(ang) * d,
                                              math.sin(ang) * d)
                layers.append(Layer(tr.map(sil), p["fill"], "after",
                                    opacity=0.32 * (1.0 - (k - 1) / float(n))))
    # shadow, or a 3D extrusion built from many shadow steps
    dx = S * p["shadow_dx"] / 100.0
    dy = S * p["shadow_dy"] / 100.0
    if dx or dy:
        steps = max(1, int(p["extrude"]))
        for i in range(steps, 0, -1):
            f = i / float(steps)
            tr = QTransform.fromTranslate(dx * f, dy * f)
            for sil in silhouettes:
                layers.append(Layer(tr.map(sil), p["shadow_color"], "shadow"))
    # trembling: line-only copies, slightly off
    if p["shake"]:
        for _k in range(int(p["shake"])):
            ox = rng.uniform(-1, 1) * S * 0.05
            oy = rng.uniform(-1, 1) * S * 0.05
            tr = QTransform.fromTranslate(ox, oy)
            for (pl, path), sil in zip(letters, silhouettes):
                layers.append(Layer(tr.map(sil), p["fill"], "shake",
                                    opacity=0.55,
                                    line_w=max(1.0, pl["size"] * 0.018)))

    fill_paint = p["fill_mode"]

    def fill_layer(path, size):
        """The letter's own layer: its body, or only its contour."""
        if fill_paint in ("line", "line_tone"):
            w = size * max(1, int(p.get("fill_line_w", 6))) / 100.0
            return Layer(_ring(path, w), p["fill"], "fill",
                         paint="tone" if fill_paint == "line_tone"
                         else "solid")
        return Layer(path, p["fill"], "fill", paint=fill_paint)
    if fill_paint == "negative":
        # the area is the letters themselves, stroked wide: it follows the
        # lettering instead of being a rectangle behind it
        pad = max(0.0, float(p.get("neg_pad", 22))) / 100.0
        for pl, path in letters:
            layers.append(Layer(_stroke(path, pl["size"] * pad * 2.0),
                                p["fill"], "fill", paint="solid"))
        for pl, path in letters:
            layers.append(Layer(path, "#ffffff", "fill", paint="solid"))
    elif p["outline_mode"] == "merged":
        for depth in range(len(cum)):
            for i, (pl, path) in enumerate(letters):
                col, w = cum[len(cum) - 1 - depth]
                layers.append(Layer(
                    band(i, pl["size"] * (w / 100.0 * 2.0 + grown)),
                    col, "outline"))
        for pl, path in letters:
            layers.append(fill_layer(path, pl["size"]))
    else:
        for i, (pl, path) in enumerate(letters):
            for col, shape in stacks(i, pl["size"]):
                layers.append(Layer(shape, col, "outline"))
            layers.append(fill_layer(path, pl["size"]))

    # noise lines: the edge of what is there, drawn again by hand. After the
    # fill, because they belong on top of it, and before the caption, which
    # is the one thing that is never hand-drawn.
    nlines = int(p.get("noise_lines", 0))
    amp = S * max(0, int(p.get("noise_amp", 40))) / 100.0 * 0.05
    if nlines and letters and amp > 0:
        style = p.get("noise_style", "hand")
        lw = max(0.5, S * 0.011 * NOISE_LOOK.get(
            style, NOISE_LOOK["hand"])[4])
        for k in range(nlines):
            for i, sil in enumerate(silhouettes):
                layers.append(Layer(
                    sketch_path(sil, amp, p["seed"] * 101 + k * 7 + i,
                                style),
                    p["fill"], "noise", opacity=0.9, line_w=lw))

    bounds = QRectF()
    for l in layers:
        r = l.path.boundingRect()
        if l.line_w:
            r = r.adjusted(-l.line_w, -l.line_w, l.line_w, l.line_w)
        bounds = r if bounds.isEmpty() else bounds.united(r)

    # decorations: behind everything, so they never cover the lettering.
    # They are placed against the finished word, which is why the bounds
    # are taken first and then widened by what was scattered around it.
    items = G.deco_items(p, (bounds.x(), bounds.y(),
                             bounds.width(), bounds.height()))
    if items:
        shapes = [(it, deco_path(it)) for it in items]
        deco = []
        if outs:
            # every outline first, then every fill: otherwise one piece's
            # outline is drawn over the piece beside it
            col, w = outs[0]
            deco += [Layer(_stroke(sh, it["size"] * w / 100.0), col,
                           "outline") for it, sh in shapes]
        deco += [Layer(sh, p["fill"], "deco") for _it, sh in shapes]
        layers[0:0] = deco
        for l in deco:
            bounds = bounds.united(l.path.boundingRect())

    # the caption goes against everything above it, so it is measured and
    # placed only once the lettering is complete
    cap = caption_path(p.get("caption", ""), family, False,
                       S * max(1, int(p.get("caption_size", 30))) / 100.0)
    if cap is not None and not bounds.isEmpty():
        cap = place_caption(cap, bounds,
                            p.get("caption_pos", "below"),
                            S * max(1, int(p.get("caption_size", 30)))
                            / 100.0 * 0.55)
        if outs:
            col, w = outs[0]
            layers.append(Layer(_stroke(cap, S * max(
                1, int(p.get("caption_size", 30))) / 100.0 * w / 100.0),
                col, "outline"))
        layers.append(Layer(cap, p["fill"], "fill", paint="solid"))
        r = cap.boundingRect()
        bounds = bounds.united(r)
    return Scene(layers, p, bounds)


# --- painting --------------------------------------------------------------

def _fill_bounds(scene):
    """Where a gradient or halftone runs: across all the fills together, so
    the word shades as one piece rather than letter by letter."""
    r = QRectF()
    for l in scene.layers:
        if l.kind == "fill":
            b = l.path.boundingRect()
            r = b if r.isEmpty() else r.united(b)
    return r


_tile_cache = {}


def pattern_tile(path, scale=100):
    """The library tile at `path`, scaled, or None.

    A missing file is not worth an error: the letter is simply filled with
    its colour instead, which is what it looked like before a pattern was
    picked.
    """
    key = (path, int(scale))
    if key in _tile_cache:
        return _tile_cache[key]
    img = None
    try:
        if path and os.path.exists(path):
            loaded = QImage(path)
            if not loaded.isNull():
                k = max(0.1, float(scale) / 100.0)
                w = max(1, int(round(loaded.width() * k)))
                h = max(1, int(round(loaded.height() * k)))
                img = loaded.scaled(w, h,
                                    Qt.AspectRatioMode.IgnoreAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
    except Exception:                               # noqa: BLE001
        img = None
    if len(_tile_cache) > 32:
        _tile_cache.clear()
    _tile_cache[key] = img
    return img


def _paint_pattern(painter, path, tile):
    """Lay the tile across the letter, clipped to its shape."""
    painter.save()
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    brush = QBrush(tile)
    painter.setBrush(brush)
    painter.drawRect(path.boundingRect())
    painter.restore()


def _paint_tone(painter, path, color, rect, spacing, grad=False):
    """Halftone: dots on a 45° grid.

    Flat (網点) by default - every dot the same, which is what a tone is.
    With `grad` they grow from nothing at the top of the word to solid at
    the bottom (網点のグラデ), which is a different fill and is offered as
    one.
    """
    painter.save()
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    sp = max(2.0, float(spacing))
    h = max(1.0, rect.height())
    painter.translate(rect.center())
    painter.rotate(45)
    diag = math.hypot(rect.width(), rect.height()) / 2.0 + sp
    # the painter is rotated by +45, so the dot's place in the UNROTATED
    # word is R(+45) of its place here. With -45 the formula below comes
    # out as -x: the shading ran across the word instead of down it, and a
    # wide word was solid at one end and blank at the other.
    rot = QTransform()
    rot.rotate(45)
    yy = -diag
    while yy <= diag:
        xx = -diag
        while xx <= diag:
            # position in the unrotated word decides the dot size
            pt = rot.map(QPointF(xx, yy))
            if grad:
                u = (pt.y() + h / 2.0) / h
                u = min(max(u, 0.0), 1.0)
                r = sp * 0.75 * u
            else:
                r = sp * 0.38
            if r > 0.3:
                painter.drawEllipse(QPointF(xx, yy), r, r)
            xx += sp
        yy += sp
    painter.restore()


def paint(scene, painter, offset=QPointF(0, 0), scale=1.0):
    """Paint the scene with `painter`; scene coordinates are scaled by
    `scale` and moved by `offset`."""
    p = scene.params
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(offset)
    painter.scale(scale, scale)
    frect = _fill_bounds(scene)
    for l in scene.layers:
        col = QColor(l.color)
        painter.setOpacity(l.opacity)
        if l.line_w:
            pen = QPen(col)
            pen.setWidthF(l.line_w)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(l.path)
            continue
        painter.setPen(Qt.PenStyle.NoPen)
        if l.paint == "gradient":
            g = QLinearGradient(frect.topLeft(), frect.bottomLeft())
            g.setColorAt(0.0, col)
            g.setColorAt(1.0, QColor(p["fill2"]))
            painter.setBrush(QBrush(g))
            painter.drawPath(l.path)
        elif l.paint in ("tone", "tone_grad"):
            # paper white under the dots, so the tone reads on any art
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawPath(l.path)
            _paint_tone(painter, l.path, col, frect, p["tone_dot"],
                        l.paint == "tone_grad")
        elif l.paint == "pattern":
            tile = pattern_tile(p.get("fill_pattern", ""),
                                p.get("fill_pattern_scale", 100))
            if tile is None:
                painter.setBrush(QBrush(col))       # no tile: just the colour
                painter.drawPath(l.path)
            else:
                painter.setBrush(QBrush(QColor("#ffffff")))
                painter.drawPath(l.path)
                _paint_pattern(painter, l.path, tile)
        else:
            painter.setBrush(QBrush(col))
            painter.drawPath(l.path)
    painter.setOpacity(1.0)
    painter.restore()


def render_image(scene, scale=1.0, margin=4, background=None):
    """The scene as an ARGB image just big enough to hold it. Returns
    (image, top-left of the image in scene coordinates × scale)."""
    b = scene.bounds
    w = max(1, int(math.ceil(b.width() * scale)) + 2 * margin)
    h = max(1, int(math.ceil(b.height() * scale)) + 2 * margin)
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(background) if background else QColor(0, 0, 0, 0))
    painter = QPainter(img)
    off = QPointF(margin - b.left() * scale, margin - b.top() * scale)
    paint(scene, painter, off, scale)
    painter.end()
    return img, QPointF(b.left() * scale - margin, b.top() * scale - margin)


def thumb_transform(scene, w, h, pad=6):
    """(scale, offset x, offset y) mapping scene coordinates into a w x h
    thumbnail - what `render_thumb` draws with, so a caller can map a click
    on the image back to the scene."""
    b = scene.bounds
    k = min((w - 2 * pad) / max(1.0, b.width()),
            (h - 2 * pad) / max(1.0, b.height()))
    k = max(0.01, k)
    return k, (w - b.width() * k) / 2.0 - b.left() * k, \
        (h - b.height() * k) / 2.0 - b.top() * k


def render_thumb(scene, w, h, background="#ffffff"):
    """The scene fitted into a w×h image (gacha options, preview)."""
    img = QImage(max(1, w), max(1, h), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(background) if background else QColor(0, 0, 0, 0))
    if scene.is_empty():
        return img
    k, ox, oy = thumb_transform(scene, w, h)
    off = QPointF(ox, oy)
    painter = QPainter(img)
    paint(scene, painter, off, k)
    painter.end()
    return img


# --- SVG -------------------------------------------------------------------

#: which kinds of layer belong together when the scene is taken apart,
#: back to front. The names are what the files in the ZIP are called.
LAYER_GROUPS = (
    ("deco", ("deco",)),
    ("afterimage", ("after",)),
    ("shadow", ("shadow",)),
    ("shake", ("shake",)),
    ("outline", ("outline",)),
    ("text", ("fill",)),
    ("noise", ("noise",)),
)


def layer_groups(scene):
    """[(name, [layer, ...])] back to front, groups with nothing left out."""
    out = []
    for name, kinds in LAYER_GROUPS:
        got = [l for l in scene.layers if l.kind in kinds]
        if got:
            out.append((name, got))
    return out


def render_layers(scene, scale=1.0, margin=4):
    """[(name, QImage)]: every group drawn on the same canvas.

    The canvas is the whole scene's, not each group's, so the images
    line up when they are stacked again in another program.
    """
    out = []
    for name, layers in layer_groups(scene):
        part = Scene(layers, scene.params, scene.bounds)
        img, _tl = render_image(part, scale=scale, margin=margin)
        out.append((name, img))
    return out


def layer_pngs(scene, scale=1.0, margin=4):
    """[(file name, PNG bytes)] - the same images, ready for a ZIP."""
    out = []
    for i, (name, img) in enumerate(render_layers(scene, scale, margin), 1):
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        out.append(("%d_%s.png" % (i, name), bytes(buf.data())))
        buf.close()
    return out


def _num(v):
    s = "%.2f" % v
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def path_d(path, tr=None):
    """QPainterPath → SVG path data (absolute M/L/C/Z)."""
    if tr is not None:
        path = tr.map(path)
    parts = []
    n = path.elementCount()
    i = 0
    start = None
    while i < n:
        e = path.elementAt(i)
        if e.isMoveTo():
            if start is not None:
                parts.append("Z")
            parts.append("M%s %s" % (_num(e.x), _num(e.y)))
            start = (e.x, e.y)
            i += 1
        elif e.isLineTo():
            parts.append("L%s %s" % (_num(e.x), _num(e.y)))
            i += 1
        elif e.isCurveTo() and i + 2 < n:
            c2 = path.elementAt(i + 1)
            end = path.elementAt(i + 2)
            parts.append("C%s %s %s %s %s %s" % (
                _num(e.x), _num(e.y), _num(c2.x), _num(c2.y),
                _num(end.x), _num(end.y)))
            i += 3
        else:
            i += 1
    if start is not None:
        parts.append("Z")
    return " ".join(parts)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def to_svg(scene, tr=None, width=None, height=None):
    """The scene as an SVG document. `tr` maps scene → output coordinates
    (placement and scale on the page); `width`/`height` set the canvas size
    the way Krita's vector import expects (pixels, no viewBox).

    Without a canvas size the document is framed to the drawing, for a
    standalone .svg file."""
    tr = tr or QTransform()
    p = scene.params
    if width is None or height is None:
        b = tr.mapRect(scene.bounds)
        m = 4.0
        tr = tr * QTransform.fromTranslate(-b.left() + m, -b.top() + m)
        width = int(math.ceil(b.width() + 2 * m))
        height = int(math.ceil(b.height() + 2 * m))
    frect = tr.mapRect(_fill_bounds(scene))
    defs = []
    body = []
    rule = "nonzero"
    if any(l.paint == "gradient" for l in scene.layers):
        defs.append(
            '<linearGradient id="giongoGrad" gradientUnits="userSpaceOnUse"'
            ' x1="%s" y1="%s" x2="%s" y2="%s">'
            '<stop offset="0" stop-color="%s"/>'
            '<stop offset="1" stop-color="%s"/></linearGradient>' % (
                _num(frect.left()), _num(frect.top()), _num(frect.left()),
                _num(frect.bottom()), _esc(p["fill"]), _esc(p["fill2"])))
    if any(l.paint in ("tone", "tone_grad") for l in scene.layers):
        sp = max(2.0, float(p["tone_dot"]))
        defs.append(
            '<pattern id="giongoTone" patternUnits="userSpaceOnUse"'
            ' width="%s" height="%s" patternTransform="rotate(45)">'
            '<rect width="%s" height="%s" fill="#ffffff"/>'
            '<circle cx="%s" cy="%s" r="%s" fill="%s"/></pattern>' % (
                _num(sp), _num(sp), _num(sp), _num(sp), _num(sp / 2),
                _num(sp / 2), _num(sp * 0.38), _esc(p["fill"])))
    for l in scene.layers:
        d = path_d(l.path, tr)
        if not d:
            continue
        op = (' opacity="%s"' % _num(l.opacity)) if l.opacity < 0.999 else ""
        if l.line_w:
            w = l.line_w * math.sqrt(abs(tr.determinant()) or 1.0)
            body.append('<path d="%s" fill="none" stroke="%s"'
                        ' stroke-width="%s" stroke-linejoin="round"%s/>' % (
                            d, _esc(l.color), _num(w), op))
            continue
        if l.paint == "gradient":
            fill = "url(#giongoGrad)"
        elif l.paint in ("tone", "tone_grad"):
            # the gradient one is written as the flat pattern: an SVG of
            # dots that each grow is a different file, and the vector
            # insert takes the raster path for it anyway
            fill = "url(#giongoTone)"
        else:
            fill = _esc(l.color)
        body.append('<path d="%s" fill="%s" fill-rule="%s"%s/>' % (
            d, fill, rule, op))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">\n'
            '%s%s\n</svg>' % (
                int(width), int(height),
                ("<defs>%s</defs>\n" % "".join(defs)) if defs else "",
                "\n".join(body)))
