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
    QRectF, Qt,
)
from . import giongo as G
from . import strokefont as SF
from . import giongo_brush as BR

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


def letter_path(pl, family, bold, thicken_pct, pen="off", seed=0,
                pen_width=100, pen_style=None):
    """One placement → its filled outline in page coordinates."""
    size = pl["size"]
    if pl["bar"]:
        base = _bar_path(pl["length"], size)
        tr = QTransform()
        tr.translate(pl["x"], pl["y"])
        tr.rotate(pl["angle"])
        path = tr.map(base)
    else:
        base = None
        if pen and pen != "off":
            got = stroke_glyph(pl["ch"], pen, seed + pl.get("i", 0) * 13,
                               pen_width, pen_style)
            if got is not None:
                base = got[0]
        if base is None:                 # no centre lines for this character
            base, _adv = glyph(pl["ch"], family, bold)
        k = size / _REF
        tr = QTransform()
        tr.translate(pl["x"], pl["y"])
        tr.rotate(pl["angle"])
        tr.shear(-math.tan(math.radians(pl["shear"])), 0.0)
        tr.scale(k * pl["sx"], k)
        path = tr.map(base)
    if thicken_pct > 0:
        path = _stroke(path, size * thicken_pct / 100.0 * 2.0)
    path.setFillRule(Qt.FillRule.WindingFill)
    return path


# --- the scene -------------------------------------------------------------

class Layer(object):
    """One shape with one paint. kind: 'fill' | 'outline' | 'shadow' |
    'shake' | 'after' — what it is, so a raster export could split layers."""
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
        return any(l.paint in ("tone", "pattern") for l in self.layers)


def build_scene(text, params, family=""):
    """Text + parameters → a Scene. `family` is the resolved font family
    ("" = the default sans)."""
    p = G.effective(params)
    bold = p["bold"]

    pen = p.get("pen", "off")

    def adv(ch):
        # the advance must come from whatever will actually be drawn, or the
        # letters would shift when a pen is switched on
        if pen and pen != "off":
            got = SF.glyph(ch)
            if got:
                return (got[0] / float(SF.EM)) or 1.0
        return glyph(ch, family, bold)[1]

    places = G.layout(text, p, advance_fn=adv)
    S = float(p["letter_px"])
    rng = random.Random(p["seed"] * 7 + 3)
    letters = [(pl, letter_path(pl, family, bold, p["thicken"],
                                pen=pen, seed=p["seed"],
                                pen_width=p.get("pen_width", 100),
                                pen_style=BR.style_from(p, pen)))
               for pl in places]
    outs = p["outlines"]
    # cumulative: outline k is everything up to and including its width
    cum = []
    acc = 0.0
    for col, w in outs:
        acc += w
        cum.append((col, acc))

    def stacks(path, size):
        """[(colour, shape)] outer → inner, then the letter itself."""
        res = []
        for col, w in reversed(cum):
            res.append((col, _stroke(path, size * w / 100.0 * 2.0)))
        return res

    silhouettes = []
    for pl, path in letters:
        if cum:
            silhouettes.append(_stroke(path, pl["size"] * cum[-1][1] / 100.0
                                       * 2.0))
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
    if p["outline_mode"] == "merged":
        for depth in range(len(cum)):
            for pl, path in letters:
                col, w = cum[len(cum) - 1 - depth]
                layers.append(Layer(_stroke(path, pl["size"] * w / 100.0
                                            * 2.0), col, "outline"))
        for pl, path in letters:
            layers.append(Layer(path, p["fill"], "fill", paint=fill_paint))
    else:
        for pl, path in letters:
            for col, shape in stacks(path, pl["size"]):
                layers.append(Layer(shape, col, "outline"))
            layers.append(Layer(path, p["fill"], "fill", paint=fill_paint))

    bounds = QRectF()
    for l in layers:
        r = l.path.boundingRect()
        if l.line_w:
            r = r.adjusted(-l.line_w, -l.line_w, l.line_w, l.line_w)
        bounds = r if bounds.isEmpty() else bounds.united(r)
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


def _paint_tone(painter, path, color, rect, spacing):
    """Halftone: dots on a 45° grid, growing from nothing at the top of the
    word to solid at the bottom (網点のグラデ)."""
    painter.save()
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    sp = max(2.0, float(spacing))
    h = max(1.0, rect.height())
    painter.translate(rect.center())
    painter.rotate(45)
    diag = math.hypot(rect.width(), rect.height()) / 2.0 + sp
    rot = QTransform()
    rot.rotate(-45)
    yy = -diag
    while yy <= diag:
        xx = -diag
        while xx <= diag:
            # position in the unrotated word decides the dot size
            pt = rot.map(QPointF(xx, yy))
            u = (pt.y() + h / 2.0) / h
            u = min(max(u, 0.0), 1.0)
            r = sp * 0.75 * u
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
        elif l.paint == "tone":
            # paper white under the dots, so the tone reads on any art
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawPath(l.path)
            _paint_tone(painter, l.path, col, frect, p["tone_dot"])
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


def render_thumb(scene, w, h, background="#ffffff"):
    """The scene fitted into a w×h image (gacha options, preview)."""
    img = QImage(max(1, w), max(1, h), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(background) if background else QColor(0, 0, 0, 0))
    if scene.is_empty():
        return img
    b = scene.bounds
    pad = 6
    k = min((w - 2 * pad) / max(1.0, b.width()),
            (h - 2 * pad) / max(1.0, b.height()))
    k = max(0.01, k)
    off = QPointF((w - b.width() * k) / 2.0 - b.left() * k,
                  (h - b.height() * k) / 2.0 - b.top() * k)
    painter = QPainter(img)
    paint(scene, painter, off, k)
    painter.end()
    return img


# --- SVG -------------------------------------------------------------------

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
    if any(l.paint == "tone" for l in scene.layers):
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
        elif l.paint == "tone":
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
