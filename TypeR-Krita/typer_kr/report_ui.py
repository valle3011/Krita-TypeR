# -*- coding: utf-8 -*-
"""The window the report button opens.

The report is shown in full and can be edited before it goes anywhere:
what is sent is what the person read. Three ways out - the clipboard, a
file, or a prefilled issue in the browser - because not everybody has a
GitHub account and not everybody wants one.
"""
from ._qt import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                  QPlainTextEdit, QApplication, QFileDialog, QLineEdit,
                  QDesktopServices, QUrl)
from . import report as RP

STRINGS = {
    "en": {
        "title": "Report a problem",
        "intro": ("This is what will be sent. Read it, change what you "
                  "like, then copy it or open an issue. Nothing leaves "
                  "this window on its own."),
        "what": "What happened?",
        "what_ph": "e.g. the letters vanish when I switch the fill to…",
        "refresh": "Build it again",
        "copy": "Copy",
        "save": "Save as file…",
        "issue": "Open an issue…",
        "close": "Close",
        "copied": "Copied. Paste it wherever you report it.",
        "saved": "Written to {p}",
        "opened": ("The browser is open with the report in it. If it looks "
                   "cut short, paste from the clipboard instead."),
    },
    "de": {
        "title": "Problem melden",
        "intro": ("Das wird gesendet. Lies es, ändere, was du möchtest, "
                  "und kopiere es dann oder öffne ein Issue. Von allein "
                  "verlässt nichts dieses Fenster."),
        "what": "Was ist passiert?",
        "what_ph": "z. B. die Buchstaben verschwinden, wenn ich die "
                   "Füllung auf … stelle",
        "refresh": "Neu zusammenstellen",
        "copy": "Kopieren",
        "save": "Als Datei speichern…",
        "issue": "Issue öffnen…",
        "close": "Schließen",
        "copied": "Kopiert. Füg es ein, wo du es meldest.",
        "saved": "Geschrieben nach {p}",
        "opened": ("Der Browser ist mit dem Bericht offen. Wirkt er "
                   "abgeschnitten, nimm lieber die Zwischenablage."),
    },
}


class ReportDialog(QDialog):
    """Shows the report, and lets it out by one of three doors."""

    def __init__(self, parent=None, info=None, settings=None, lang="en"):
        super().__init__(parent)
        self._info = dict(info or {})
        self._settings = settings
        self._lang = lang if lang in STRINGS else "en"
        self.setModal(False)
        self.setWindowTitle(self._t("title"))
        lay = QVBoxLayout(self)
        hint = QLabel(self._t("intro"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(QLabel(self._t("what")))
        self.what = QLineEdit()
        self.what.setPlaceholderText(self._t("what_ph"))
        self.what.textChanged.connect(self.refresh)
        row.addWidget(self.what, 1)
        lay.addLayout(row)
        self.text = QPlainTextEdit()
        lay.addWidget(self.text, 1)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: gray;")
        lay.addWidget(self.note)
        row = QHBoxLayout()
        for key, slot in (("refresh", self.refresh), ("copy", self.copy),
                          ("save", self.save), ("issue", self.issue),
                          ("close", self.close)):
            btn = QPushButton(self._t(key))
            btn.clicked.connect(slot)
            row.addWidget(btn)
        lay.addLayout(row)
        self.resize(640, 520)
        self.refresh()

    def _t(self, key):
        return STRINGS.get(self._lang, STRINGS["en"]).get(key, key)

    def refresh(self, *_a):
        self.text.setPlainText(RP.build(self._info, self._settings,
                                        self.what.text()))

    def body(self):
        return self.text.toPlainText()

    def copy(self, *_a):
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(self.body())
            self.note.setText(self._t("copied"))

    def save(self, *_a):
        path, _f = QFileDialog.getSaveFileName(
            self, self._t("save"), "typer-report.md", "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.body())
        except OSError as exc:
            self.note.setText(str(exc))
            return
        self.note.setText(self._t("saved").format(p=path))

    def issue(self, *_a):
        self.copy()
        QDesktopServices.openUrl(QUrl(RP.issue_url(self.body())))
        self.note.setText(self._t("opened"))


def open_for(parent, info=None, settings=None, lang="en"):
    """Open the window (and keep a reference, or Qt would bin it)."""
    dlg = ReportDialog(parent, info, settings, lang)
    if parent is not None:
        parent._typer_report_dialog = dlg
    dlg.show()
    dlg.raise_()
    return dlg
