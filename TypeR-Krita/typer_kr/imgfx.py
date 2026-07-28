# -*- coding: utf-8 -*-
"""Small raster image effects shared by the TypeR and SFX dockers.

Kept out of layout.py (which must stay Qt-free) — this needs Qt. Only used on
the raster insert paths (a blurred, pattern- or colour-filled soft outline can't
be a Krita vector paint, so it is rendered to pixels)."""

from PyQt5.QtGui import QImage, QPixmap, QPainter, QBrush, QColor
from PyQt5.QtCore import QRectF, Qt


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
