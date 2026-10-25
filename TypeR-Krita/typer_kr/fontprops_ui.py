# -*- coding: utf-8 -*-
"""The properties window of a font, the way Windows does it for a file.

Right-click a favourite, choose Properties, and a small window opens with a
tab bar: what the font is, what else belongs to its family, and where it is
in use. Nothing here can be changed - it answers questions, it does not
settle them - so the only button is Close.

Everything it shows is worked out by ``fontinfo.py``, which is Qt-free and
tested on its own. This module lays it out and nothing else.

The window is **not** modal. Properties of two fonts side by side is the
whole point of a window instead of a message box, and the docker stays
usable behind it.
"""

import os

from ._qt import Qt, PYQT, QFont, QFontDatabase, QLocale, font_families
from ._qt import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QTabWidget, QWidget, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QPushButton, QFrame, QHeaderView, QApplication,
)

from . import fontinfo as FI

#: English strings; the docker's translator overrides them where it has the
#: key, exactly as the favourites panel does it.
FALLBACK = {
    "fp_title": "{name} — Properties",
    "fp_tab_general": "General",
    "fp_tab_family": "Family",
    "fp_tab_presets": "Presets",
    "fp_name": "Name:",
    "fp_cut": "Cut:",
    "fp_cut_plain": "Regular",
    "fp_family": "Family:",
    "fp_family_of": "{base} ({n} cuts installed)",
    "fp_family_alone": "{base} (this cut only)",
    "fp_styles": "Styles:",
    "fp_scripts": "Writing systems:",
    "fp_traits": "Properties:",
    "fp_fixed": "fixed pitch",
    "fp_proportional": "proportional",
    "fp_scalable": "scalable",
    "fp_bitmap": "bitmap",
    "fp_favourite": "Favourite:",
    "fp_fav_yes": "yes",
    "fp_fav_no": "no",
    "fp_cats": "Categories:",
    "fp_none": "—",
    "fp_files": "Font files:",
    "fp_location": "Location:",
    "fp_size": "Size:",
    "fp_find_files": "Look for the font files…",
    "fp_searching": "looking…",
    "fp_no_files": "no file found for this family",
    "fp_preview": "Preview:",
    "fp_preview_text": "Handgloves 123",
    "fp_family_one": "Only this one cut of “{base}” is installed.",
    "fp_family_many": "{n} cuts of “{base}” are installed. "
                      "Double-click one to look at it.",
    "fp_this_one": "this one",
    "fp_used_none": "“{name}” is not used by any preset.",
    "fp_used_n": "“{name}” is used by {n} preset(s).",
    "fp_used_family": "{n} of them through another cut of the family.",
    "fp_no_presets": "No presets are available here.",
    "fp_col_manga": "Manga",
    "fp_col_char": "Character",
    "fp_col_preset": "Preset",
    "fp_col_font": "Saved as",
    "fp_default_char": "(default)",
    "fp_types": "Text types set to it: {list}",
    "fp_close": "Close",
}


def _styles_of(family):
    """The styles Qt lists for a family ('Regular', 'Bold', …)."""
    try:
        if PYQT >= 6:
            return list(QFontDatabase.styles(family))
        return list(QFontDatabase().styles(family))
    except Exception:                               # noqa: BLE001
        return []


def _writing_systems_of(family):
    """The scripts a family declares ('Latin', 'Japanese', …)."""
    try:
        if PYQT >= 6:
            db, systems = QFontDatabase, QFontDatabase.writingSystems(family)
        else:
            db = QFontDatabase()
            systems = db.writingSystems(family)
        return [db.writingSystemName(w) for w in systems]
    except Exception:                               # noqa: BLE001
        return []


def _traits_of(family, tr):
    """'proportional, scalable' - the flags the font database knows."""
    out = []
    try:
        db = QFontDatabase if PYQT >= 6 else QFontDatabase()
        out.append(tr("fp_fixed") if db.isFixedPitch(family)
                   else tr("fp_proportional"))
        out.append(tr("fp_scalable") if db.isScalable(family)
                   else tr("fp_bitmap"))
    except Exception:                               # noqa: BLE001
        return ""
    return ", ".join(out)


def _separators():
    """The locale's thousands and decimal separator, as plain characters."""
    try:
        loc = QLocale()
        out = []
        for ch in (loc.groupSeparator(), loc.decimalPoint()):
            out.append(ch if isinstance(ch, str) else chr(ch.unicode()))
        return out[0], out[1]
    except Exception:                               # noqa: BLE001
        return ",", "."


def _value(text=""):
    """A read-only field that can still be selected and copied, like Windows."""
    lbl = QLabel(text)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lbl.setWordWrap(True)
    return lbl


class FontPropertiesDialog(QDialog):
    """Tabs over one font family. Call :meth:`open_for` rather than ``exec``."""

    def __init__(self, family, tr, families_fn=None, categories_fn=None,
                 files_fn=None, files_ready_fn=None, presets_fn=None,
                 type_fonts_fn=None, parent=None):
        super().__init__(parent)
        self._tr_fn = tr or (lambda k: FALLBACK.get(k, k))
        self._families_fn = families_fn or font_families
        # None from this one means 'not a favourite at all', which is a
        # different answer from 'a favourite in no category'
        self._categories_fn = categories_fn or (lambda _f: None)
        self._files_fn = files_fn
        self._files_ready_fn = files_ready_fn or (lambda: False)
        self._presets_fn = presets_fn
        self._type_fonts_fn = type_fonts_fn
        self._family = (family or "").strip()
        self._families = []
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._build()
        self.set_family(self._family)

    # -- strings -----------------------------------------------------------
    def t(self, key, **kw):
        s = self._tr_fn(key)
        if s == key:                            # translator has no such key
            s = FALLBACK.get(key, key)
        return s.format(**kw) if kw else s

    # -- construction ------------------------------------------------------
    def _build(self):
        lay = QVBoxLayout(self)

        head = QHBoxLayout()
        self.face = QLabel()
        self.face.setMinimumHeight(44)
        head.addWidget(self.face, 1)
        lay.addLayout(head)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        lay.addWidget(line)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general(), self.t("fp_tab_general"))
        self.tabs.addTab(self._build_family(), self.t("fp_tab_family"))
        self.tabs.addTab(self._build_presets(), self.t("fp_tab_presets"))
        lay.addWidget(self.tabs, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.button(QDialogButtonBox.StandardButton.Close).setText(
            self.t("fp_close"))
        bb.rejected.connect(self.close)
        bb.accepted.connect(self.close)
        lay.addWidget(bb)
        self.resize(420, 470)

    def _build_general(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignTop)
        self.v_name = _value()
        self.v_cut = _value()
        self.v_family = _value()
        self.v_styles = _value()
        self.v_scripts = _value()
        self.v_traits = _value()
        self.v_fav = _value()
        self.v_cats = _value()
        self.v_files = _value()
        self.v_location = _value()
        self.v_size = _value()
        self.preview = QLabel()
        self.preview.setMinimumHeight(40)
        self.preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(self.t("fp_name"), self.v_name)
        form.addRow(self.t("fp_cut"), self.v_cut)
        form.addRow(self.t("fp_family"), self.v_family)
        form.addRow(self.t("fp_styles"), self.v_styles)
        form.addRow(self.t("fp_scripts"), self.v_scripts)
        form.addRow(self.t("fp_traits"), self.v_traits)
        form.addRow(_sep())
        form.addRow(self.t("fp_favourite"), self.v_fav)
        form.addRow(self.t("fp_cats"), self.v_cats)
        form.addRow(_sep())
        form.addRow(self.t("fp_files"), self.v_files)
        form.addRow(self.t("fp_location"), self.v_location)
        form.addRow(self.t("fp_size"), self.v_size)
        self.find_btn = QPushButton(self.t("fp_find_files"))
        self.find_btn.clicked.connect(self._look_for_files)
        form.addRow("", self.find_btn)
        form.addRow(self.t("fp_preview"), self.preview)
        return page

    def _build_family(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.family_hint = QLabel()
        self.family_hint.setWordWrap(True)
        lay.addWidget(self.family_hint)
        self.family_list = QListWidget()
        self.family_list.itemDoubleClicked.connect(
            lambda it: self.set_family(it.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self.family_list, 1)
        return page

    def _build_presets(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.used_hint = QLabel()
        self.used_hint.setWordWrap(True)
        lay.addWidget(self.used_hint)
        self.used_tree = QTreeWidget()
        self.used_tree.setRootIsDecorated(False)
        self.used_tree.setAlternatingRowColors(True)
        self.used_tree.setSortingEnabled(True)
        self.used_tree.setHeaderLabels([self.t("fp_col_manga"),
                                        self.t("fp_col_char"),
                                        self.t("fp_col_preset"),
                                        self.t("fp_col_font")])
        try:
            self.used_tree.header().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents)
        except Exception:                           # noqa: BLE001
            pass
        lay.addWidget(self.used_tree, 1)
        self.types_hint = QLabel()
        self.types_hint.setWordWrap(True)
        lay.addWidget(self.types_hint)
        return page

    # -- filling -----------------------------------------------------------
    def set_family(self, family):
        """Show this family - also when a cut is double-clicked in the family
        tab, which is what makes the window a way of looking around."""
        family = (family or "").strip()
        if not family:
            return
        self._family = family
        try:
            self._families = list(self._families_fn() or [])
        except Exception:                           # noqa: BLE001
            self._families = []
        self.setWindowTitle(self.t("fp_title", name=family))
        self.face.setText(family)
        f = QFont(family)
        f.setPointSize(20)
        self.face.setFont(f)
        self._fill_general()
        self._fill_family()
        self._fill_presets()

    def _fill_general(self):
        fam = self._family
        base, cut = FI.split_cut_name(fam)
        kin = FI.relatives(fam, self._families)
        self.v_name.setText(fam)
        self.v_cut.setText(cut or self.t("fp_cut_plain"))
        self.v_family.setText(
            self.t("fp_family_of", base=base, n=len(kin)) if len(kin) > 1
            else self.t("fp_family_alone", base=base))
        self.v_styles.setText(", ".join(_styles_of(fam)) or self.t("fp_none"))
        scripts = _writing_systems_of(fam)
        self.v_scripts.setText(", ".join(scripts[:8])
                               + ("…" if len(scripts) > 8 else "")
                               or self.t("fp_none"))
        self.v_traits.setText(_traits_of(fam, self.t) or self.t("fp_none"))
        try:
            cats = self._categories_fn(fam)
        except Exception:                           # noqa: BLE001
            cats = None
        # None and [] mean different things here: not starred at all, versus
        # starred but in no category. `list(x or [])` would lose that.
        cats = None if cats is None else list(cats)
        self.v_fav.setText(self.t("fp_fav_no") if cats is None
                           else self.t("fp_fav_yes"))
        self.v_cats.setText(", ".join(cats) if cats else self.t("fp_none"))
        f = QFont(fam)
        f.setPointSize(15)
        self.preview.setFont(f)
        self.preview.setText(self.t("fp_preview_text"))
        self._clear_files()
        if self._files_fn is not None and self._files_ready_fn():
            self._look_for_files()

    def _clear_files(self):
        dash = self.t("fp_none")
        self.v_files.setText(dash)
        self.v_location.setText(dash)
        self.v_size.setText(dash)
        self.find_btn.setVisible(self._files_fn is not None)

    def _look_for_files(self):
        """Ask for the files of this family - the first lookup reads every
        installed font, so it is never done just because a window opened."""
        if self._files_fn is None:
            return
        self.find_btn.setEnabled(False)
        self.v_files.setText(self.t("fp_searching"))
        QApplication.processEvents()
        try:
            paths = list(self._files_fn(self._family) or [])
        except Exception:                           # noqa: BLE001
            paths = []
        finally:
            self.find_btn.setEnabled(True)
        if not paths:
            self.v_files.setText(self.t("fp_no_files"))
            return
        kinds = []
        for p in paths:
            k = FI.file_kind(p)
            if k and k not in kinds:
                kinds.append(k)
        self.v_files.setText("%s\n%s" % (", ".join(kinds),
                                         "\n".join(os.path.basename(p)
                                                   for p in paths)))
        self.v_location.setText(os.path.dirname(paths[0]))
        total = 0
        for p in paths:
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
        self.v_size.setText(FI.human_size(total, *_separators()) if total
                            else self.t("fp_none"))
        self.find_btn.setVisible(False)

    def _fill_family(self):
        self.family_list.clear()
        kin = FI.cuts_of(self._family, self._families)
        base = FI.split_cut_name(self._family)[0]
        self.family_hint.setText(
            self.t("fp_family_one", base=base) if len(kin) < 2
            else self.t("fp_family_many", n=len(kin), base=base))
        for name, cut in kin:
            label = "%s — %s" % (name, cut or self.t("fp_cut_plain"))
            if FI.same_font(name, self._family):
                label += "  (%s)" % self.t("fp_this_one")
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, name)
            f = QFont(name)
            f.setPointSize(11)
            it.setFont(f)
            self.family_list.addItem(it)

    def _fill_presets(self):
        self.used_tree.clear()
        self.types_hint.setText("")
        if self._presets_fn is None:
            self.used_hint.setText(self.t("fp_no_presets"))
            self.used_tree.setVisible(False)
            return
        try:
            groups = self._presets_fn() or {}
        except Exception:                           # noqa: BLE001
            groups = {}
        kin = [n for (n, _c) in FI.cuts_of(self._family, self._families)]
        rows = FI.preset_uses(groups, kin or [self._family])
        self.used_tree.setVisible(True)
        if not rows:
            self.used_hint.setText(self.t("fp_used_none", name=self._family))
        else:
            other = sum(1 for r in rows if not FI.same_font(r[3],
                                                            self._family))
            text = self.t("fp_used_n", name=self._family, n=len(rows))
            if other:
                text += " " + self.t("fp_used_family", n=other)
            self.used_hint.setText(text)
        self.used_tree.setSortingEnabled(False)
        for (manga, char, preset, font) in rows:
            QTreeWidgetItem(self.used_tree,
                            [manga, char or self.t("fp_default_char"),
                             preset, font])
        self.used_tree.setSortingEnabled(True)
        self.used_tree.setColumnHidden(
            3, all(FI.same_font(r[3], self._family) for r in rows))
        if self._type_fonts_fn is not None:
            try:
                types = FI.type_uses(self._type_fonts_fn() or {},
                                     kin or [self._family])
            except Exception:                       # noqa: BLE001
                types = []
            if types:
                self.types_hint.setText(self.t(
                    "fp_types", list=", ".join(label for (label, _f) in types)))


def _sep():
    """A thin line between the blocks of the General tab, as Windows has."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def open_for(family, parent, **kw):
    """Open (or raise) a properties window for *family*.

    The window is kept alive by its parent's list of open windows - a dialog
    that is only shown, not executed, is collected the moment the last
    reference goes out of scope, and would vanish as it appeared.
    """
    held = getattr(parent, "_font_prop_windows", None)
    if held is None:
        held = []
        try:
            parent._font_prop_windows = held
        except Exception:                           # noqa: BLE001
            pass
    for w in list(held):
        try:
            if not w.isVisible():                   # closed, let it go
                held.remove(w)
            elif FI.same_font(w._family, family):
                w.raise_()
                w.activateWindow()
                return w
        except RuntimeError:                        # already destroyed by Qt
            held.remove(w)
    dlg = FontPropertiesDialog(family, parent=parent, **kw)
    held.append(dlg)
    dlg.show()
    return dlg
