# -*- coding: utf-8 -*-
"""Small raster image effects shared by the TypeR and SFX dockers.

Kept out of layout.py (which must stay Qt-free) — this needs Qt. Only used on
the raster insert paths (a blurred, pattern- or colour-filled soft outline can't
be a Krita vector paint, so it is rendered to pixels)."""

from ._qt import QImage, QPixmap, QPainter, QBrush, QColor, QPen
from ._qt import QRectF, Qt


#: Pattern kinds the generator can make (stable ids used by the UI + persistence).
#: Covers the screentones common in manga: dots (halftone), straight + diagonal
#: line tones, cross-hatch, a sand/noise tone (grain for shadows/atmosphere) and
#: a shoujo sparkle/star tone.
PATTERN_KINDS = ("dots", "hstripes", "vstripes", "diagonal", "crosshatch",
                 "grid", "checker", "noise", "sparkle")


def _star4_path(cx, cy, r):
    """A 4-point sparkle star (sharp diamond points) centred at (cx, cy)."""
    from ._qt import QPainterPath, QPolygonF
    from ._qt import QPointF
    ri = r * 0.2
    pts = [(cx, cy - r), (cx + ri, cy - ri), (cx + r, cy), (cx + ri, cy + ri),
           (cx, cy + r), (cx - ri, cy + ri), (cx - r, cy), (cx - ri, cy - ri)]
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(a, b) for a, b in pts]))
    path.closeSubpath()
    return path


def make_pattern(kind, fg=None, bg=None, size=8, gap=8):
    """Build a small, seamlessly-tiling QImage for a generated pattern — an easy
    way to get manga screentone-ish fills without hand-making an image.

    kind: one of PATTERN_KINDS.
    fg:   the ink colour (default black).
    bg:   the background colour, or None for transparent (lets the layer show).
    size: the feature size in px (band/line thickness, dot radius, checker cell).
    gap:  the empty spacing in px between features.

    All tiles are built so that repeating them leaves no seam."""
    fg = fg if isinstance(fg, QColor) else QColor(fg) if fg else QColor(0, 0, 0)
    has_bg = isinstance(bg, QColor) or (bg is not None and bg != "")
    bg_col = bg if isinstance(bg, QColor) else (QColor(bg) if has_bg else None)
    s = max(1, int(size))
    g = max(0, int(gap))

    if kind in ("hstripes", "vstripes"):
        period = max(2, s + g)
        img = _tile(period, period, bg_col)
        p = QPainter(img)
        p.fillRect(0, 0, (period if kind == "hstripes" else s),
                   (s if kind == "hstripes" else period), fg)
        p.end()
        return img
    if kind == "checker":
        cell = max(1, s)
        img = _tile(cell * 2, cell * 2, bg_col)
        p = QPainter(img)
        p.fillRect(0, 0, cell, cell, fg)
        p.fillRect(cell, cell, cell, cell, fg)
        p.end()
        return img
    if kind == "dots":
        r = max(1, s)
        period = max(2 * r + 1, 2 * r + g)
        img = _tile(period, period, bg_col)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QBrush(fg))
        p.setPen(Qt.PenStyle.NoPen)
        c = period / 2.0
        # centre dot + wrapped quarters at the corners keep the grid seamless
        for cx, cy in ((c, c), (0, 0), (period, 0), (0, period),
                       (period, period)):
            p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        p.end()
        return img
    if kind in ("grid", "crosshatch"):
        period = max(2, s + g)
        img = _tile(period, period, bg_col)
        p = QPainter(img)
        pen = QPen(fg)
        pen.setWidth(max(1, s))
        p.setPen(pen)
        p.drawLine(0, 0, period, 0)          # top edge -> horizontal lines
        if kind in ("grid", "crosshatch"):
            p.drawLine(0, 0, 0, period)      # left edge -> vertical lines
        p.end()
        return img
    if kind == "diagonal":                   # seamless 45° line tone
        period = max(2, s + g)
        img = _tile(period, period, bg_col)
        for y in range(period):              # (x + y) mod period < s => a band
            for x in range(period):
                if (x + y) % period < s:
                    img.setPixelColor(x, y, fg)
        return img
    if kind == "noise":                      # sand/grain tone (shadows, texture)
        import random
        period = max(16, (s + g) * 4)
        img = _tile(period, period, bg_col)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QBrush(fg))
        p.setPen(Qt.PenStyle.NoPen)
        r = max(0.6, s / 3.0)
        dens = s / float(s + g)              # more ink as size grows vs the gap
        count = max(1, int(period * period * dens * 0.12 / (r * r)))
        rng = random.Random(1234 + period * 31 + int(dens * 997))
        for _ in range(count):
            x, y = rng.uniform(0, period), rng.uniform(0, period)
            for ox in (0, -period, period):   # wrap so the tile stays seamless
                if ox and not (x < r or x > period - r):
                    continue
                for oy in (0, -period, period):
                    if oy and not (y < r or y > period - r):
                        continue
                    p.drawEllipse(QRectF(x + ox - r, y + oy - r, 2 * r, 2 * r))
        p.end()
        return img
    if kind == "sparkle":                    # shoujo star tone (sparkles)
        period = max(6, s + g)
        img = _tile(period, period, bg_col)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = max(1.5, s * 0.9)
        c = period / 2.0                     # one star centred, quarters wrapped
        for cx, cy in ((c, c), (0, 0), (period, 0), (0, period),
                       (period, period)):
            p.fillPath(_star4_path(cx, cy, r), fg)
        p.end()
        return img
    return _tile(max(2, s), max(2, s), fg)   # unknown -> a solid fg tile


def make_gradient(c1, c2, angle_deg=0.0, size=256):
    """A linear gradient image from c1 (e.g. dark) to c2 (light) across the tile
    at `angle_deg` (0 = left→right, 90 = top→bottom, 45 = top-left→bottom-right).
    Meant to be STRETCHED over a selection (dark on one side, light on the
    other), not tiled."""
    import math
    from ._qt import QLinearGradient
    from ._qt import QPointF
    c1 = c1 if isinstance(c1, QColor) else QColor(c1) if c1 else QColor(0, 0, 0)
    c2 = c2 if isinstance(c2, QColor) else QColor(c2) if c2 else QColor(255, 255, 255)
    s = max(2, int(size))
    img = QImage(s, s, QImage.Format.Format_ARGB32)
    a = math.radians(angle_deg)
    dx, dy, half = math.cos(a), math.sin(a), s / 2.0
    g = QLinearGradient(QPointF(half - dx * half, half - dy * half),
                        QPointF(half + dx * half, half + dy * half))
    g.setColorAt(0.0, c1)
    g.setColorAt(1.0, c2)
    p = QPainter(img)
    p.fillRect(0, 0, s, s, QBrush(g))
    p.end()
    return img


def make_pattern_gradient(kind, fg=None, bg=None, size=6, gap=8,
                          angle_deg=0.0, width=256, height=256):
    """A screentone-DENSITY gradient of `kind`: the pattern's ink coverage ramps
    from full (dense/dark) at the tail of `angle_deg` to none (light) at the head
    — the classic manga tone fade (e.g. a dot tone that thins out towards one
    edge). Unlike ``make_gradient`` (a smooth *colour* fade) the ink stays one
    solid colour; it's the dot size / line thickness that changes, so it reads as
    real screentone, not grey.

    kind: one of PATTERN_KINDS, or "smooth" for a plain colour gradient.
    angle_deg: 0 = dense on the left fading right, 90 = dense on top, etc.
    Rendered at width x height so dots stay round — draw it 1:1 over the fill,
    don't stretch it (stretching would squash the dots into ovals)."""
    import math
    fg = fg if isinstance(fg, QColor) else QColor(fg) if fg else QColor(0, 0, 0)
    has_bg = isinstance(bg, QColor) or (bg is not None and bg != "")
    bg_col = bg if isinstance(bg, QColor) else (QColor(bg) if has_bg else None)
    W, H = max(2, int(width)), max(2, int(height))
    img = QImage(W, H, QImage.Format.Format_ARGB32)
    img.fill(bg_col if isinstance(bg_col, QColor) else QColor(0, 0, 0, 0))

    if kind == "smooth":                     # plain dark->light(/transparent) fade
        light = bg_col if isinstance(bg_col, QColor) else QColor(fg.red(),
                                                                 fg.green(),
                                                                 fg.blue(), 0)
        return _linear_fill(img, fg, light, angle_deg)

    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    # normalise the projection onto the direction so the ramp spans the whole
    # image (0 at the densest tail corner, 1 at the lightest head corner)
    projs = [x * dx + y * dy for x in (0, W) for y in (0, H)]
    pmin, span = min(projs), (max(projs) - min(projs)) or 1.0

    def coverage(px, py):
        ramp = (px * dx + py * dy - pmin) / span      # 0 at tail .. 1 at head
        c = 1.0 - ramp                                # dense at the tail
        return 0.0 if c < 0.0 else 1.0 if c > 1.0 else c

    s = max(1, int(size))
    g = max(0, int(gap))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if kind in ("dots", "checker", "sparkle"):
        step = max(2, s + g)
        max_feat = step * (0.72 if kind == "dots"
                           else 1.15 if kind == "sparkle" else 1.0)
        p.setBrush(QBrush(fg))
        p.setPen(Qt.PenStyle.NoPen)
        cy = step / 2.0
        while cy < H + step:
            cx = step / 2.0
            while cx < W + step:
                f = coverage(cx, cy) * max_feat
                if f >= 0.6:
                    if kind == "dots":
                        p.drawEllipse(QRectF(cx - f / 2, cy - f / 2, f, f))
                    elif kind == "sparkle":
                        p.fillPath(_star4_path(cx, cy, f / 2.0), fg)
                    else:
                        p.fillRect(QRectF(cx - f / 2, cy - f / 2, f, f), fg)
                cx += step
            cy += step
    elif kind == "noise":                     # grain fade (denser -> sparser)
        import random
        step = max(2, s + g)
        r = max(0.6, s / 3.0)
        rng = random.Random(4321 + W * 7 + H * 13)
        gy = 0.0
        while gy < H:
            gx = 0.0
            while gx < W:
                if rng.random() < coverage(gx, gy):    # ink prob ramps down
                    p.setBrush(QBrush(fg))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawEllipse(QRectF(gx - r, gy - r, 2 * r, 2 * r))
                gx += step
            gy += step
    elif kind == "diagonal":                  # 45° line tone, thickness ramp
        from ._qt import QPointF
        step = max(2, s + g)
        # walk bands by their (x+y) offset; sample coverage on the band centre
        k = -H
        while k < W:
            cxx = min(max((k + H / 2.0), 0), W)
            f = coverage(cxx, H / 2.0) * s
            if f >= 0.6:
                pen = QPen(fg)
                pen.setWidthF(f)
                p.setPen(pen)
                p.drawLine(QPointF(k, 0), QPointF(k + H, H))
            k += step
    elif kind in ("hstripes", "vstripes"):
        step = max(2, s + g)
        horiz = (kind == "hstripes")
        pos = step / 2.0
        length = W if horiz else H
        while pos < (H if horiz else W) + step:
            # sample the ramp on the band's centre line (perpendicular to it)
            f = coverage(length / 2.0 if horiz else pos,
                         pos if horiz else length / 2.0) * step
            if f >= 0.6:
                if horiz:
                    p.fillRect(QRectF(0, pos - f / 2, W, f), fg)
                else:
                    p.fillRect(QRectF(pos - f / 2, 0, f, H), fg)
            pos += step
    else:                                     # grid / crosshatch: ramp line width
        step = max(2, s + g)
        y = step / 2.0
        while y < H + step:
            f = coverage(W / 2.0, y) * s
            if f >= 0.6:
                p.fillRect(QRectF(0, y - f / 2, W, f), fg)
            y += step
        x = step / 2.0
        while x < W + step:
            f = coverage(x, H / 2.0) * s
            if f >= 0.6:
                p.fillRect(QRectF(x - f / 2, 0, f, H), fg)
            x += step
    p.end()
    return img


def _linear_fill(img, c1, c2, angle_deg):
    """Fill `img` in place with a linear c1->c2 gradient at `angle_deg`."""
    import math
    from ._qt import QLinearGradient
    from ._qt import QPointF
    W, H = img.width(), img.height()
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    cx, cy = W / 2.0, H / 2.0
    ext = (abs(dx) * W + abs(dy) * H) / 2.0
    g = QLinearGradient(QPointF(cx - dx * ext, cy - dy * ext),
                        QPointF(cx + dx * ext, cy + dy * ext))
    g.setColorAt(0.0, c1)
    g.setColorAt(1.0, c2)
    p = QPainter(img)
    p.fillRect(0, 0, W, H, QBrush(g))
    p.end()
    return img


def _tile(w, h, bg_col):
    img = QImage(max(1, int(w)), max(1, int(h)), QImage.Format.Format_ARGB32)
    img.fill(bg_col if isinstance(bg_col, QColor) else QColor(0, 0, 0, 0))
    return img


def blur_argb(img, radius):
    """Gaussian-blur an ARGB QImage by `radius` px using Qt's own blur effect
    (fast C++). Returns a new premultiplied QImage; the caller must give an image
    with enough transparent margin for the blur to spread into."""
    if img is None or img.isNull() or radius <= 0:
        return img
    # imported lazily so the module imports without a QApplication present
    from ._qt import (QGraphicsScene, QGraphicsPixmapItem,
                                 QGraphicsBlurEffect)
    eff = QGraphicsBlurEffect()
    eff.setBlurRadius(float(radius))
    try:
        eff.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    except Exception:
        pass
    item = QGraphicsPixmapItem(QPixmap.fromImage(img))
    item.setGraphicsEffect(eff)
    scene = QGraphicsScene()
    scene.addItem(item)
    out = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    p = QPainter(out)
    scene.render(p, QRectF(out.rect()), QRectF(img.rect()))
    p.end()
    return out


def soft_outline_image(path, size, blur, expand, fill, tile=None):
    """Render a soft (blurred) outline/glow for a glyph `path` into an ARGB image
    of `size` (a QSize).

    fill: a QColor (solid) OR a QImage (a texture/pattern tiled into the shape).
    expand: px the silhouette is widened before blurring (a thicker halo).
    tile: (w, h) tile size for a texture fill, else the image's own size.

    The result is the blurred silhouette on transparent; drawn UNDER the crisp
    text it reads as a soft coloured/patterned outline around the letters."""
    layer = QImage(size, QImage.Format.Format_ARGB32)
    layer.fill(0)
    p = QPainter(layer)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if isinstance(fill, QImage) and not fill.isNull():
        tw, th = (tile if tile else (fill.width(), fill.height()))
        pm = QPixmap.fromImage(fill).scaled(
            max(1, int(tw)), max(1, int(th)),
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        brush = QBrush(pm)
    else:
        brush = QBrush(fill if isinstance(fill, QColor) else QColor(fill))
    if expand and expand > 0:
        # widen the silhouette with a stroke of the same brush before the fill
        from ._qt import QPen
        pen = QPen(brush, float(expand) * 2.0)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.strokePath(path, pen)
    p.fillPath(path, brush)
    p.end()
    return blur_argb(layer, blur)
