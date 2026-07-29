# -*- coding: utf-8 -*-
"""Small raster image effects shared by the TypeR and SFX dockers.

Kept out of layout.py (which must stay Qt-free) — this needs Qt. Only used on
the raster insert paths (a blurred, pattern- or colour-filled soft outline can't
be a Krita vector paint, so it is rendered to pixels)."""

from PyQt5.QtGui import QImage, QPixmap, QPainter, QBrush, QColor, QPen
from PyQt5.QtCore import QRectF, Qt


#: Pattern kinds the generator can make (stable ids used by the UI + persistence).
PATTERN_KINDS = ("hstripes", "vstripes", "checker", "dots", "grid", "crosshatch")


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
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QBrush(fg))
        p.setPen(Qt.NoPen)
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
    return _tile(max(2, s), max(2, s), fg)   # unknown -> a solid fg tile


def _tile(w, h, bg_col):
    img = QImage(max(1, int(w)), max(1, int(h)), QImage.Format_ARGB32)
    img.fill(bg_col if isinstance(bg_col, QColor) else QColor(0, 0, 0, 0))
    return img


def blur_argb(img, radius):
    """Gaussian-blur an ARGB QImage by `radius` px using Qt's own blur effect
    (fast C++). Returns a new premultiplied QImage; the caller must give an image
    with enough transparent margin for the blur to spread into."""
    if img is None or img.isNull() or radius <= 0:
        return img
    # imported lazily so the module imports without a QApplication present
    from PyQt5.QtWidgets import (QGraphicsScene, QGraphicsPixmapItem,
                                 QGraphicsBlurEffect)
    eff = QGraphicsBlurEffect()
    eff.setBlurRadius(float(radius))
    try:
        eff.setBlurHints(QGraphicsBlurEffect.QualityHint)
    except Exception:
        pass
    item = QGraphicsPixmapItem(QPixmap.fromImage(img))
    item.setGraphicsEffect(eff)
    scene = QGraphicsScene()
    scene.addItem(item)
    out = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
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
    layer = QImage(size, QImage.Format_ARGB32)
    layer.fill(0)
    p = QPainter(layer)
    p.setRenderHint(QPainter.Antialiasing, True)
    if isinstance(fill, QImage) and not fill.isNull():
        tw, th = (tile if tile else (fill.width(), fill.height()))
        pm = QPixmap.fromImage(fill).scaled(
            max(1, int(tw)), max(1, int(th)),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        brush = QBrush(pm)
    else:
        brush = QBrush(fill if isinstance(fill, QColor) else QColor(fill))
    if expand and expand > 0:
        # widen the silhouette with a stroke of the same brush before the fill
        from PyQt5.QtGui import QPen
        pen = QPen(brush, float(expand) * 2.0)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        p.strokePath(path, pen)
    p.fillPath(path, brush)
    p.end()
    return blur_argb(layer, blur)
