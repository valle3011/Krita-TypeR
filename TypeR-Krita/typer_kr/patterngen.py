"""A tiny 'make a pattern' dialog so the user doesn't have to hand-craft an
image to get a texture fill. Pick a kind (stripes, dots/screentone, checker,
grid…), two colours and the feature size/gap, watch the live preview, hit OK —
the caller gets a seamless QImage tile it can use as a text or outline fill.

Qt UI only; the actual tile is built by ``imgfx.make_pattern`` (testable).
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QPainter, QBrush
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QCheckBox, QSpinBox, QColorDialog, QDialogButtonBox, QFrame,
)

from . import imgfx as IMG

_FALLBACK = {
    "patgen_title": "Make a pattern",
    "patgen_kind": "Pattern:",
    "patgen_fg": "Ink colour",
    "patgen_bg": "Background",
    "patgen_transparent": "Transparent background",
    "patgen_size": "Size",
    "patgen_gap": "Gap",
    "patgen_hstripes": "Horizontal stripes",
    "patgen_vstripes": "Vertical stripes",
    "patgen_checker": "Checkerboard",
    "patgen_dots": "Dots (screentone)",
    "patgen_grid": "Grid",
    "patgen_crosshatch": "Cross-hatch",
    "patgen_save": "★ Save to library…",
}


class PatternGeneratorDialog(QDialog):
    #: emitted with the current tile (QImage) whenever any control changes, so a
    #: host can live-apply it to its own preview while the dialog is still open.
    previewChanged = pyqtSignal(object)
    #: emitted with the current tile when the user clicks 'Save to library'.
    saveRequested = pyqtSignal(object)

    def __init__(self, parent=None, tr=None, fg=None, bg=None):
        super().__init__(parent)
        self._tr = tr or (lambda k: _FALLBACK.get(k, k))
        self._fg = QColor(fg) if fg else QColor(0, 0, 0)
        self._bg = QColor(bg) if bg else QColor(255, 255, 255)
        self._image = None
        self.setWindowTitle(self.t("patgen_title"))
        self._build()
        self._update_preview()

    def t(self, key):
        s = self._tr(key)
        return _FALLBACK.get(key, key) if s == key else s

    # -- build --
    def _build(self):
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.t("patgen_kind")))
        self.kind = QComboBox()
        for k in IMG.PATTERN_KINDS:
            self.kind.addItem(self.t("patgen_" + k), k)
        self.kind.currentIndexChanged.connect(lambda _i: self._update_preview())
        row.addWidget(self.kind, 1)
        lay.addLayout(row)

        crow = QHBoxLayout()
        self.fg_btn = QPushButton(self.t("patgen_fg"))
        self.fg_btn.clicked.connect(self._pick_fg)
        self.bg_btn = QPushButton(self.t("patgen_bg"))
        self.bg_btn.clicked.connect(self._pick_bg)
        crow.addWidget(self.fg_btn)
        crow.addWidget(self.bg_btn)
        lay.addLayout(crow)
        self.transparent = QCheckBox(self.t("patgen_transparent"))
        self.transparent.toggled.connect(lambda _v: (self._sync_bg_enabled(),
                                                     self._update_preview()))
        lay.addWidget(self.transparent)

        srow = QHBoxLayout()
        srow.addWidget(QLabel(self.t("patgen_size")))
        self.size = QSpinBox()
        self.size.setRange(1, 200)
        self.size.setValue(6)
        self.size.valueChanged.connect(lambda _v: self._update_preview())
        srow.addWidget(self.size)
        srow.addWidget(QLabel(self.t("patgen_gap")))
        self.gap = QSpinBox()
        self.gap.setRange(0, 200)
        self.gap.setValue(8)
        self.gap.valueChanged.connect(lambda _v: self._update_preview())
        srow.addWidget(self.gap)
        lay.addLayout(srow)

        self.preview = QLabel()
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setMinimumSize(220, 120)
        self.preview.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.preview)

        self.save_btn = QPushButton(self.t("patgen_save"))
        self.save_btn.clicked.connect(
            lambda: self.saveRequested.emit(self._current_tile()))
        lay.addWidget(self.save_btn)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._paint_color_btns()

    # -- colours --
    def _pick_fg(self):
        c = QColorDialog.getColor(self._fg, self, self.t("patgen_fg"))
        if c.isValid():
            self._fg = c
            self._paint_color_btns()
            self._update_preview()

    def _pick_bg(self):
        c = QColorDialog.getColor(self._bg, self, self.t("patgen_bg"))
        if c.isValid():
            self._bg = c
            self._paint_color_btns()
            self._update_preview()

    def _paint_color_btns(self):
        self.fg_btn.setStyleSheet(
            "QPushButton { background-color: %s; }" % self._fg.name())
        self.bg_btn.setStyleSheet(
            "QPushButton { background-color: %s; }" % self._bg.name())

    def _sync_bg_enabled(self):
        self.bg_btn.setEnabled(not self.transparent.isChecked())

    # -- preview / result --
    def _current_tile(self):
        bg = None if self.transparent.isChecked() else self._bg
        return IMG.make_pattern(self.kind.currentData(), self._fg, bg,
                                self.size.value(), self.gap.value())

    def _update_preview(self):
        tile = self._current_tile()
        self._image = tile
        w, h = self.preview.width() or 220, self.preview.height() or 120
        pm = QPixmap(w, h)
        pm.fill(QColor(235, 235, 235))          # backdrop shows transparency
        p = QPainter(pm)
        p.fillRect(0, 0, w, h, QBrush(QPixmap.fromImage(tile)))
        p.end()
        self.preview.setPixmap(pm)
        self.previewChanged.emit(tile)          # let the host live-apply it

    def image(self):
        """The chosen pattern tile (QImage), valid after the dialog is accepted."""
        return self._image

    def run(self):
        """Show modally; return the QImage tile on OK, else None."""
        if self.exec_() != QDialog.Accepted:
            return None
        self._image = self._current_tile()
        return self._image
