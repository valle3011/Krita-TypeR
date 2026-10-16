# -*- coding: utf-8 -*-
"""Put a cleaned page under finished typesetting, and render the result.

The swap itself touches no Krita and no Qt beyond reading an image file: a
.kra is a ZIP, and `kra.py` rewrites exactly the bottom layer's tiles, leaving
every other entry - text layers, vector layers, masks, effects - byte for byte
as it was.

The PNG is where this differs from the standalone SwapR. There, `render.py`
composites the page with numpy because `krita --export` hangs while Krita is
open. Here Krita is open and is running this code, so `export_png` hands the
finished file to Krita's own exporter. That is the renderer SwapR's was
approximating, so the two workarounds it needed - forcing Qt's FreeType engine,
re-doing Krita's artificial bold - are not needed and could not work anyway:
the font engine is fixed before the QApplication exists, and Krita's has
existed since it started.

Krita is imported inside the function that needs it, never at module level, so
everything except the PNG step runs in a plain Python without Krita present -
which is what the tests do.
"""
import os

from .._qt import QBuffer, QByteArray, QIODevice, QImage, QImageReader, Qt
from .kra import (KraDocument, KraError, OutputKra, replace_background,
                  transplant_layers)

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
TS_SUFFIXES = (".kra",)
CLEAN_SUFFIXES = IMAGE_SUFFIXES + (".kra",)

PREVIEW_SIZE = 256          # the size Krita writes preview.png at
ASPECT_TOLERANCE = 0.01


def is_kra(path):
    return str(path).lower().endswith(".kra")


def image_size(path):
    """The size without decoding the whole image - for a .kra from maindoc."""
    if is_kra(path):
        try:
            doc = KraDocument(path)
        except KraError:
            return None
        return doc.width, doc.height
    size = QImageReader(str(path)).size()
    return (size.width(), size.height()) if size.isValid() else None


def aspect_matches(size, target):
    """Same proportions? Then scaling the clean up is defensible."""
    (w, h), (tw, th) = size, target
    if 0 in (w, h, tw, th):
        return False
    return abs((w / h) - (tw / th)) <= ASPECT_TOLERANCE * (tw / th)


def _image_bytes(img):
    """The raw buffer of a QImage, on either Qt binding.

    PyQt5 calls it byteCount(), PyQt6 sizeInBytes(), and the pointer has to be
    told how long it is before it can be read.
    """
    bits = img.constBits()
    size = (img.sizeInBytes() if hasattr(img, "sizeInBytes")
            else img.byteCount())
    try:
        bits.setsize(size)
    except AttributeError:                      # pragma: no cover - PyQt6
        pass
    return bytes(bits)


def load_bgra(path, target=None):
    """An image as (bgra_bytes, w, h) - B,G,R,A, the order Krita stores.

    ARGB32 is little-endian in memory, so its bytes already are B,G,R,A.
    """
    img = QImage(str(path))
    if img.isNull():
        raise KraError("Bild nicht lesbar: %s" % os.path.basename(str(path)))
    if target and (img.width(), img.height()) != tuple(target):
        img = img.scaled(target[0], target[1],
                         Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    stride = img.bytesPerLine()
    raw = _image_bytes(img)
    if stride == w * 4:
        return raw, w, h
    # Qt may pad each row - then take the rows apart again
    rows = [raw[y * stride: y * stride + w * 4] for y in range(h)]
    return b"".join(rows), w, h


def png_bytes(img):
    """A QImage as PNG bytes, without going through a file.

    The QByteArray has to stay in a variable: handing QBuffer a temporary
    (`QBuffer(QByteArray())`) lets Python free it immediately and the buffer
    writes into freed memory - a segfault, measured, not a theory.
    """
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = img.save(buf, "PNG")
    buf.close()
    if not ok:
        raise KraError("PNG konnte nicht kodiert werden")
    return bytes(ba)


def inspect(ts_path):
    """(width, height, name of the bottom layer) - for the table."""
    doc = KraDocument(ts_path)
    layer = doc.background_layer()
    return doc.width, doc.height, (layer.get("name") or "?")


def inspect_clean_kra(clean_path):
    """The layer names of a clean .kra, topmost first."""
    doc = KraDocument(clean_path)
    names = [l.get("name") or "?" for l in doc.top_level_layers()]
    if not names:
        raise KraError("Clean-.kra hat keine Ebenen")
    return names


def png_path_for(out_path):
    root = out_path[:-4] if is_kra(out_path) else out_path
    return root + ".png"


class SwapResult:
    __slots__ = ("layer", "scaled", "clean_layers", "png", "warnings")

    def __init__(self, layer, scaled=False, clean_layers=None):
        self.layer = layer
        self.scaled = scaled
        self.clean_layers = clean_layers or []
        self.png = None
        self.warnings = []


def export_png(kra_path, png_path):
    """Render a finished .kra to PNG with Krita itself.

    Returns "" on success, otherwise why not. The document is opened in batch
    mode so no dialog can appear, and closed again whatever happens - a plugin
    that leaves documents open behind the user's back is worse than one that
    skips a preview.
    """
    try:
        from krita import Krita, InfoObject
    except ImportError as exc:                  # pragma: no cover - no Krita
        return "Krita nicht verfuegbar (%s)" % exc
    app = Krita.instance()
    doc = app.openDocument(str(kra_path))
    if doc is None:
        return "Krita konnte %s nicht oeffnen" % os.path.basename(str(kra_path))
    try:
        doc.setBatchmode(True)
        doc.waitForDone()
        if not doc.exportImage(str(png_path), InfoObject()):
            return "Krita konnte das PNG nicht schreiben"
    finally:
        doc.close()
    return ""


def embed_preview(kra_path, png_data):
    """Put the finished page into the .kra as mergedimage/preview.

    Without this the file still holds the raw's preview, so Krita's open dialog
    and the file manager show the page the swap just replaced.
    """
    img = QImage()
    if not img.loadFromData(png_data, "PNG"):
        return "Vorschau nicht lesbar"
    out = OutputKra(KraDocument(kra_path))
    out.set("mergedimage.png", png_data)
    thumb = img.scaled(PREVIEW_SIZE, PREVIEW_SIZE,
                       Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    out.set("preview.png", png_bytes(thumb))
    out.write(kra_path)
    return ""


def swap(ts_path, clean_path, out_path, allow_scale=False, png=False,
         exporter=None):
    """Write out_path: the typeset file with its bottom layer replaced by the
    clean - pixels when that is an image, its layers when it is a .kra.

    ts_path and clean_path are never written to. With png=True the finished
    page is rendered next to it (by Krita, unless `exporter` says otherwise)
    and embedded as the file's own preview.
    """
    ts_path, clean_path, out_path = [os.path.abspath(str(p))
                                     for p in (ts_path, clean_path, out_path)]
    png_out = png_path_for(out_path) if png else None
    if {out_path, png_out} & {ts_path, clean_path}:
        raise KraError("Ziel wuerde eine Quelldatei ueberschreiben")

    doc_w, doc_h, _name = inspect(ts_path)
    if is_kra(clean_path):
        out, layer, clean_layers = transplant_layers(ts_path, clean_path)
        result = SwapResult(layer, clean_layers=clean_layers)
    else:
        size = image_size(clean_path)
        scaled = size is not None and size != (doc_w, doc_h)
        if scaled and not allow_scale:
            raise KraError(
                "Clean ist %dx%d, die .kra %dx%d - Skalieren ist nicht "
                "eingeschaltet" % (size[0], size[1], doc_w, doc_h))
        bgra, w, h = load_bgra(clean_path, (doc_w, doc_h) if allow_scale else None)
        out, layer = replace_background(ts_path, bgra, w, h)
        result = SwapResult(layer, scaled=scaled)

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    out.write(out_path)

    if png:
        result.png, warnings = add_png(out_path, exporter)
        result.warnings.extend(warnings)
    return result


def add_png(out_path, exporter=None):
    """Render a written .kra to PNG and embed it as the file's own preview.

    Returns (png path or None, warnings). Split out of `swap` because Krita's
    API may only be touched from the UI thread: the docker runs the swap
    itself in a worker (plain zip and LZF work, no Krita) and calls this from
    the thread Krita handed it.
    """
    png_out = png_path_for(out_path)
    warnings = []
    why = (exporter or export_png)(out_path, png_out)
    if why:
        return None, ["kein PNG: %s" % why]
    try:
        with open(png_out, "rb") as fh:
            data = fh.read()
        why = embed_preview(out_path, data)
    except (OSError, KraError) as exc:
        why = str(exc)
    if why:
        warnings.append("Vorschau in der .kra nicht aktualisiert: %s" % why)
    return png_out, warnings
