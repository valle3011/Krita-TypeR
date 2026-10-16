# -*- coding: utf-8 -*-
"""Qt panel for the Swap tab: raws out, cleans in, typesetting untouched.

Drives :mod:`typer_kr.swapr`. Decoupled from the docker the way the fonts
panel is - a translator and two settings callbacks - so the main file barely
grows and the panel can be built in a plain Qt app for testing.

**Where the work happens.** Writing a .kra is plain zipping and LZF, no Krita
at all, so it runs in a worker thread and a 20-page chapter does not freeze
Krita. The optional PNG is the opposite: it is Krita rendering the finished
file, and Krita's API may only be touched from the thread that owns the UI.
So the worker emits a page as soon as its .kra is on disk and the PNG is made
here, in the slot, which Qt runs on the UI thread.

The status column is written here rather than taken from the engine, so it
follows the interface language. Only an unexpected malformed-file message
comes through from the vendored reader, which is kept byte-identical to the
standalone SwapR and therefore stays German.
"""
import os
import traceback

from ._qt import Qt, pyqtSignal, QThread
from ._qt import QColor
from ._qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QPlainTextEdit, QAbstractItemView,
)

from .swapr import swap as SW
from .swapr.kra import KraError
from .swapr.pairing import make_pairs, natural_key

_EN = {
    "sw_intro": ("Lift finished typesetting off the raws: every .kra keeps "
                 "its text and vector layers, only the bottom layer is "
                 "replaced by the cleaned page."),
    "sw_ts_folder": "Typeset pages (.kra):",
    "sw_clean_folder": "Clean pages:",
    "sw_out_folder": "Target folder:",
    "sw_choose": "Choose…",
    "sw_col_ts": "Typeset page",
    "sw_col_clean": "Clean page",
    "sw_col_status": "What will happen",
    "sw_scale": "Scale the clean to canvas size",
    "sw_scale_tip": ("Off, a clean of a different size is refused so nothing "
                     "is distorted unnoticed. A clean that is itself a .kra "
                     "can never be scaled."),
    "sw_png": "Also write a PNG (rendered by Krita)",
    "sw_png_tip": ("Krita opens each finished page in the background and "
                   "exports it. Slower, and it is also put into the .kra as "
                   "its preview, so the file manager stops showing the raw."),
    "sw_overwrite": "Overwrite files that are already there",
    "sw_run": "Transfer",
    "sw_cancel": "Cancel",
    "sw_none": "no clean page",
    "sw_ready": "{ok} page(s) ready, {skip} without a clean.",
    "sw_nothing": "Nothing to transfer.",
    "sw_same_folder": ("The target folder may not be the typeset or the "
                       "clean folder."),
    "sw_no_out": "Pick a target folder first.",
    "sw_busy": "Page {i} of {n}…",
    "sw_done": "Done: {ok} transferred, {fail} not.",
    "sw_exists": "skipped, already there",
    "sw_replaced": "replaced ‘{layer}’ with {clean}",
    "sw_replaced_layers": ("replaced ‘{layer}’ with {count} layer(s) "
                           "from {clean}"),
    "sw_scaled_note": " (scaled)",
    "sw_st_no_clean": "no clean page",
    "sw_st_unreadable": "clean image not readable",
    "sw_st_ok": "OK – replaces ‘{layer}’",
    "sw_st_ok_layers": "OK – replaces ‘{layer}’ with {count} layer(s)",
    "sw_st_size": "size {cw}x{ch} != {w}x{h} – switch scaling on",
    "sw_st_size_kra": ("size {cw}x{ch} != {w}x{h} – a clean .kra cannot "
                       "be scaled"),
    "sw_st_aspect": "proportions do not match ({cw}x{ch} vs {w}x{h})",
    "sw_st_scaled": "scales {cw}x{ch} -> {w}x{h}, replaces ‘{layer}’",
}

_ROLE_PATH = Qt.ItemDataRole.UserRole


def _collect(folder, suffixes):
    """The files of one folder with those suffixes, in page order."""
    if not folder or not os.path.isdir(folder):
        return []
    out = [os.path.join(folder, n) for n in os.listdir(folder)
           if n.lower().endswith(suffixes)]
    out = [p for p in out if os.path.isfile(p)]
    return sorted(out, key=natural_key)


class SwapWorker(QThread):
    """Writes the .kra files. Touches no Krita, so it may leave the UI thread."""

    progress = pyqtSignal(int, str, bool, str)   # row, message, ok, out path
    finished_all = pyqtSignal(int, int)          # ok, failed

    def __init__(self, jobs, out_dir, overwrite, allow_scale, tr):
        super().__init__()
        self.jobs = jobs                 # [(row, ts, clean), ...]
        self.out_dir = out_dir
        self.overwrite = overwrite
        self.allow_scale = allow_scale
        self._tr = tr
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        ok = fail = 0
        for row, ts, clean in self.jobs:
            if self._abort:
                break
            name = os.path.basename(ts)
            out = os.path.join(self.out_dir, name)
            try:
                if os.path.exists(out) and not self.overwrite:
                    self.progress.emit(row, self._tr("sw_exists"), False, "")
                    fail += 1
                    continue
                res = SW.swap(ts, clean, out, allow_scale=self.allow_scale,
                              png=False)
                if res.clean_layers:
                    msg = self._tr("sw_replaced_layers").format(
                        layer=res.layer, count=len(res.clean_layers),
                        clean=os.path.basename(clean))
                else:
                    msg = self._tr("sw_replaced").format(
                        layer=res.layer, clean=os.path.basename(clean))
                    if res.scaled:
                        msg += self._tr("sw_scaled_note")
                self.progress.emit(row, msg, True, out)
                ok += 1
            except KraError as exc:
                self.progress.emit(row, str(exc), False, "")
                fail += 1
            except Exception:                    # noqa: BLE001
                self.progress.emit(row, traceback.format_exc(limit=2),
                                   False, "")
                fail += 1
        self.finished_all.emit(ok, fail)


class SwapPanel(QWidget):
    """Folders in, paired table, one run."""

    def __init__(self, tr=None, get_setting=None, set_setting=None,
                 parent=None):
        super().__init__(parent)
        self._tr_fn = tr
        self._get = get_setting or (lambda _k, d="": d)
        self._set = set_setting or (lambda _k, _v: None)
        self._pairs = []
        self._worker = None
        self._total = 0
        self._png_wanted = False

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.setLayout(lay)

        self.intro = QLabel(self._tr("sw_intro"))
        self.intro.setWordWrap(True)
        self.intro.setStyleSheet("color: gray;")
        lay.addWidget(self.intro)

        self.ts_lbl, self.ts_edit, self.ts_btn = self._folder_row(
            lay, "sw_ts_folder", "swapTsDir", self._on_folders_changed)
        self.clean_lbl, self.clean_edit, self.clean_btn = self._folder_row(
            lay, "sw_clean_folder", "swapCleanDir", self._on_folders_changed)

        self.table = QTableWidget(0, 3)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)

        self.scale_chk = QCheckBox(self._tr("sw_scale"))
        self.scale_chk.setToolTip(self._tr("sw_scale_tip"))
        self.scale_chk.setChecked(self._get("swapScale", "false") == "true")
        self.scale_chk.toggled.connect(self._on_scale_toggle)
        lay.addWidget(self.scale_chk)

        self.png_chk = QCheckBox(self._tr("sw_png"))
        self.png_chk.setToolTip(self._tr("sw_png_tip"))
        self.png_chk.setChecked(self._get("swapPng", "false") == "true")
        self.png_chk.toggled.connect(
            lambda on: self._set("swapPng", "true" if on else "false"))
        lay.addWidget(self.png_chk)

        self.overwrite_chk = QCheckBox(self._tr("sw_overwrite"))
        lay.addWidget(self.overwrite_chk)

        self.out_lbl, self.out_edit, self.out_btn = self._folder_row(
            lay, "sw_out_folder", "swapOutDir", None)

        run_row = QHBoxLayout()
        self.run_btn = QPushButton(self._tr("sw_run"))
        self.run_btn.clicked.connect(self._on_run)
        run_row.addWidget(self.run_btn)
        self.status_lbl = QLabel("")
        run_row.addWidget(self.status_lbl, 1)
        lay.addLayout(run_row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        lay.addWidget(self.log)

        self._rescan()
        self.retranslate()          # also sets the column headers

    # -- small helpers -----------------------------------------------------

    def _tr(self, key):
        if self._tr_fn is not None:
            text = self._tr_fn(key)
            if text and text != key:
                return text
        return _EN.get(key, key)

    def _folder_row(self, lay, label_key, setting, on_change):
        row = QHBoxLayout()
        lbl = QLabel(self._tr(label_key))
        row.addWidget(lbl)
        edit = QLineEdit(self._get(setting, ""))
        edit.setReadOnly(True)
        row.addWidget(edit, 1)
        btn = QPushButton(self._tr("sw_choose"))

        def pick():
            start = edit.text() or ""
            folder = QFileDialog.getExistingDirectory(self, self._tr(label_key),
                                                      start)
            if folder:
                edit.setText(folder)
                self._set(setting, folder)
                if on_change is not None:
                    on_change()

        btn.clicked.connect(pick)
        row.addWidget(btn)
        lay.addLayout(row)
        return lbl, edit, btn

    def _log(self, text):
        self.log.appendPlainText(text)

    # -- the table ---------------------------------------------------------

    def _on_folders_changed(self):
        self._rescan()

    def _on_scale_toggle(self, on):
        self._set("swapScale", "true" if on else "false")
        self._refresh_status()

    def _rescan(self):
        """Read both folders and pair them up."""
        ts = _collect(self.ts_edit.text(), SW.TS_SUFFIXES)
        cleans = _collect(self.clean_edit.text(), SW.CLEAN_SUFFIXES)
        self._pairs, _rest = make_pairs(ts, cleans)   # (pairs, unused cleans)
        self.table.setRowCount(len(self._pairs))
        for row, pair in enumerate(self._pairs):
            name = QTableWidgetItem(os.path.basename(pair.ts))
            name.setData(_ROLE_PATH, pair.ts)
            self.table.setItem(row, 0, name)
            combo = QComboBox()
            combo.addItem(self._tr("sw_none"), "")
            for c in cleans:
                combo.addItem(os.path.basename(c), c)
            if pair.clean:
                idx = combo.findData(pair.clean)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.currentIndexChanged.connect(
                lambda _i, r=row: self._on_combo(r))
            self.table.setCellWidget(row, 1, combo)
            self.table.setItem(row, 2, QTableWidgetItem(""))
        self._refresh_status()

    def _on_combo(self, row):
        combo = self.table.cellWidget(row, 1)
        if combo is not None and row < len(self._pairs):
            self._pairs[row].clean = combo.currentData() or None
            self._pairs[row].note = ""
            self._set_status(row)
            self._update_ready()

    def _refresh_status(self):
        for row in range(len(self._pairs)):
            self._set_status(row)
        self._update_ready()

    def _update_ready(self):
        ok = sum(1 for p in self._pairs if p.clean)
        self.status_lbl.setText(self._tr("sw_ready").format(
            ok=ok, skip=len(self._pairs) - ok))

    def _set_status(self, row):
        text, colour = self._status(self._pairs[row])
        item = self.table.item(row, 2)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(row, 2, item)
        item.setText(text)
        item.setForeground(QColor(colour))

    def _status(self, pair):
        """What this row will do, in the interface language."""
        if not pair.clean:
            return (pair.note or self._tr("sw_st_no_clean"), "#a07000")
        try:
            w, h, layer = SW.inspect(pair.ts)
        except KraError as exc:
            return (str(exc), "#c00000")
        size = SW.image_size(pair.clean)
        if size is None:
            return (self._tr("sw_st_unreadable"), "#c00000")
        f = dict(cw=size[0], ch=size[1], w=w, h=h, layer=layer)
        if SW.is_kra(pair.clean):
            try:
                names = SW.inspect_clean_kra(pair.clean)
            except KraError as exc:
                return (str(exc), "#c00000")
            if size != (w, h):
                return (self._tr("sw_st_size_kra").format(**f), "#c00000")
            return (self._tr("sw_st_ok_layers").format(count=len(names), **f),
                    "#107010")
        if size != (w, h):
            if not self.scale_chk.isChecked():
                return (self._tr("sw_st_size").format(**f), "#c00000")
            if not SW.aspect_matches(size, (w, h)):
                return (self._tr("sw_st_aspect").format(**f), "#c00000")
            return (self._tr("sw_st_scaled").format(**f), "#a07000")
        return (self._tr("sw_st_ok").format(**f), "#107010")

    # -- the run -----------------------------------------------------------

    def _on_run(self):
        if self._worker is not None:
            self._worker.abort()
            self.run_btn.setEnabled(False)
            return
        out_dir = self.out_edit.text()
        if not out_dir:
            self._log(self._tr("sw_no_out"))
            return
        same = {os.path.normcase(os.path.abspath(p))
                for p in (self.ts_edit.text(), self.clean_edit.text()) if p}
        if os.path.normcase(os.path.abspath(out_dir)) in same:
            self._log(self._tr("sw_same_folder"))
            return
        jobs = [(row, p.ts, p.clean)
                for row, p in enumerate(self._pairs) if p.clean]
        if not jobs:
            self._log(self._tr("sw_nothing"))
            return
        self._total = len(jobs)
        self._png_wanted = self.png_chk.isChecked()
        self._worker = SwapWorker(jobs, out_dir,
                                  self.overwrite_chk.isChecked(),
                                  self.scale_chk.isChecked(), self._tr)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_all.connect(self._on_finished)
        self.run_btn.setText(self._tr("sw_cancel"))
        self._worker.start()

    def _on_progress(self, row, message, ok, out_path):
        """Runs on the UI thread - so this is where Krita may be asked."""
        if ok and out_path and self._png_wanted:
            try:
                png, warnings = SW.add_png(out_path)
            except Exception as exc:              # noqa: BLE001
                png, warnings = None, [str(exc)]
            if png:
                message += " + " + os.path.basename(png)
            for w in warnings:
                message += "\n     " + w
        if 0 <= row < self.table.rowCount():
            item = self.table.item(row, 2)
            if item is not None:
                item.setText(message.splitlines()[0])
                item.setForeground(QColor("#107010" if ok else "#c00000"))
        name = (os.path.basename(self._pairs[row].ts)
                if row < len(self._pairs) else "?")
        self._log("%s: %s" % (name, message))
        self.status_lbl.setText(self._tr("sw_busy").format(
            i=row + 1, n=self._total))

    def _on_finished(self, ok, fail):
        self._worker = None
        self.run_btn.setText(self._tr("sw_run"))
        self.run_btn.setEnabled(True)
        self.status_lbl.setText(self._tr("sw_done").format(ok=ok, fail=fail))

    def shutdown(self):
        """Stop a run before the docker goes away (Krita closing, tab reset)."""
        worker = self._worker
        if worker is not None:
            worker.abort()
            worker.wait(5000)
            self._worker = None

    def retranslate(self):
        self.intro.setText(self._tr("sw_intro"))
        self.ts_lbl.setText(self._tr("sw_ts_folder"))
        self.clean_lbl.setText(self._tr("sw_clean_folder"))
        self.out_lbl.setText(self._tr("sw_out_folder"))
        for btn in (self.ts_btn, self.clean_btn, self.out_btn):
            btn.setText(self._tr("sw_choose"))
        self.scale_chk.setText(self._tr("sw_scale"))
        self.scale_chk.setToolTip(self._tr("sw_scale_tip"))
        self.png_chk.setText(self._tr("sw_png"))
        self.png_chk.setToolTip(self._tr("sw_png_tip"))
        self.overwrite_chk.setText(self._tr("sw_overwrite"))
        if self._worker is None:
            self.run_btn.setText(self._tr("sw_run"))
        self.table.setHorizontalHeaderLabels(
            [self._tr("sw_col_ts"), self._tr("sw_col_clean"),
             self._tr("sw_col_status")])
        self._refresh_status()
