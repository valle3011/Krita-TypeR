"""Qt panel for the font-favourites tab.

Drives a :class:`typer_kr.fontfav.FavoritesStore`. The widget is deliberately
decoupled from the rest of TypeR through four callbacks so the huge main docker
barely has to change and so the panel could be reused elsewhere:

    families_fn()      -> list[str]   installed font families (for the picker)
    apply_fn(family)   -> None        apply a chosen font (main picker + canvas)
    load_fn()          -> str         read the stored JSON blob
    save_fn(json_str)  -> None        persist the JSON blob

A translator ``tr(key)`` supplies localized strings; a tiny English fallback is
built in so the panel also works standalone (tests / other hosts).
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QDialog, QDialogButtonBox,
    QCheckBox, QInputDialog, QMessageBox, QScrollArea, QFrame,
)

from .fontfav import FavoritesStore, UNCATEGORIZED

# English fallback so the panel is self-sufficient if no translator is passed.
_FALLBACK = {
    "fav_title": "Font favourites",
    "fav_intro": "Star fonts and sort them into categories (Dialog, SFX, …). "
                 "A font can be in several categories. Filter by category or "
                 "search by name, then double-click to use it.",
    "fav_all": "All favourites",
    "fav_uncat": "(no category)",
    "fav_search_ph": "Search font…",
    "fav_add_current": "★ Add current font",
    "fav_add": "Add font…",
    "fav_edit_cats": "Categories…",
    "fav_remove": "Remove",
    "fav_manage": "Manage categories…",
    "fav_apply": "Use font",
    "fav_none": "No favourites yet. Add one with “★ Add current font”.",
    "fav_pick_font": "Add a favourite font",
    "fav_choose_cats": "Categories for this font:",
    "fav_new_cat_ph": "New category…",
    "fav_new_cat_add": "Add",
    "fav_manage_title": "Manage categories",
    "fav_rename": "Rename",
    "fav_delete": "Delete",
    "fav_delete_font_q": "Remove “{name}” from favourites?",
    "fav_count": "{n} fonts",
    "ok": "OK",
    "cancel": "Cancel",
}


class FontFavoritesPanel(QWidget):
    """The favourites tab: category filter + search + list + actions."""

    #: emitted when the user picks a font to use (family name)
    fontChosen = pyqtSignal(str)

    def __init__(self, families_fn, apply_fn, load_fn, save_fn, tr=None,
                 current_font_fn=None, parent=None):
        super().__init__(parent)
        self._families_fn = families_fn
        self._apply_fn = apply_fn
        self._load_fn = load_fn
        self._save_fn = save_fn
        self._current_font_fn = current_font_fn
        self._tr = tr or (lambda k: _FALLBACK.get(k, k))
        self._store = FavoritesStore.from_json(self._safe_load())

        self._build()
        self._reload_categories()
        self._restore_filter()
        self._refresh_list()

    # -- i18n / IO helpers --------------------------------------------------
    def t(self, key, **kw):
        s = self._tr(key)
        if s == key:                       # translator missed it → fallback
            s = _FALLBACK.get(key, key)
        return s.format(**kw) if kw else s

    def _safe_load(self):
        try:
            return self._load_fn() or ""
        except Exception:
            return ""

    def _persist(self):
        try:
            self._save_fn(self._store.to_json())
        except Exception:
            pass

    # -- build --------------------------------------------------------------
    def _build(self):
        lay = QVBoxLayout()
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self.setLayout(lay)

        self.intro = QLabel(self.t("fav_intro"))
        self.intro.setWordWrap(True)
        self.intro.setStyleSheet("color: gray;")
        lay.addWidget(self.intro)

        filt = QHBoxLayout()
        self.cat_combo = QComboBox()
        self.cat_combo.currentIndexChanged.connect(lambda _i: self._on_filter_changed())
        filt.addWidget(self.cat_combo, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.t("fav_search_ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._on_filter_changed())
        filt.addWidget(self.search, 1)
        lay.addLayout(filt)

        self.list = QListWidget()
        self.list.setMinimumHeight(160)
        self.list.itemDoubleClicked.connect(self._on_double)
        self.list.currentItemChanged.connect(lambda *_: self._update_preview())
        lay.addWidget(self.list, 1)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color: gray; font-size: 10px;")
        lay.addWidget(self.count_lbl)

        self.preview = QLabel("")
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(44)
        lay.addWidget(self.preview)

        # action buttons, wrapped so they never clip on a narrow docker
        btns = QHBoxLayout()
        self.apply_btn = QPushButton(self.t("fav_apply"))
        self.apply_btn.clicked.connect(self._apply_current)
        self.add_cur_btn = QPushButton(self.t("fav_add_current"))
        self.add_cur_btn.clicked.connect(self._add_current_font)
        btns.addWidget(self.apply_btn)
        btns.addWidget(self.add_cur_btn)
        lay.addLayout(btns)

        btns2 = QHBoxLayout()
        self.add_btn = QPushButton(self.t("fav_add"))
        self.add_btn.clicked.connect(self._add_font_dialog)
        self.edit_btn = QPushButton(self.t("fav_edit_cats"))
        self.edit_btn.clicked.connect(self._edit_categories)
        self.remove_btn = QPushButton(self.t("fav_remove"))
        self.remove_btn.clicked.connect(self._remove_current)
        btns2.addWidget(self.add_btn)
        btns2.addWidget(self.edit_btn)
        btns2.addWidget(self.remove_btn)
        lay.addLayout(btns2)

        self.manage_btn = QPushButton(self.t("fav_manage"))
        self.manage_btn.clicked.connect(self._manage_categories)
        lay.addWidget(self.manage_btn)

    # -- selection helpers --------------------------------------------------
    def _selected_family(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _selected_category(self):
        """The category filter value: None (all), UNCATEGORIZED, or a name."""
        return self.cat_combo.currentData()

    # -- refresh ------------------------------------------------------------
    def _reload_categories(self):
        keep = self._selected_category()
        self.cat_combo.blockSignals(True)
        self.cat_combo.clear()
        self.cat_combo.addItem(self.t("fav_all"), None)
        counts = self._store.category_counts()
        for c in self._store.categories():
            self.cat_combo.addItem("%s (%d)" % (c, counts.get(c, 0)), c)
        self.cat_combo.addItem(self.t("fav_uncat"), UNCATEGORIZED)
        # restore previous selection if still present
        idx = 0
        for i in range(self.cat_combo.count()):
            if self.cat_combo.itemData(i) == keep:
                idx = i
                break
        self.cat_combo.setCurrentIndex(idx)
        self.cat_combo.blockSignals(False)

    def _on_filter_changed(self):
        """Category or search changed: re-list and remember the choice so the
        tab reopens exactly where the user left it."""
        self._refresh_list()
        self._store.ui_set("last_category", self._selected_category())
        self._store.ui_set("last_search", self.search.text())
        self._persist()

    def _restore_filter(self):
        """Re-select the category + search the user last used (from the store)."""
        cat = self._store.ui_get("last_category", None)
        search = self._store.ui_get("last_search", "") or ""
        self.cat_combo.blockSignals(True)
        idx = 0
        for i in range(self.cat_combo.count()):
            if self.cat_combo.itemData(i) == cat:
                idx = i
                break
        self.cat_combo.setCurrentIndex(idx)
        self.cat_combo.blockSignals(False)
        self.search.blockSignals(True)
        self.search.setText(search)
        self.search.blockSignals(False)

    def category_names(self):
        """Public: the category list (for a picker context menu)."""
        return self._store.categories()

    def _refresh_list(self):
        fams = self._store.fonts_in_category(
            self._selected_category(), self.search.text())
        self.list.blockSignals(True)
        self.list.clear()
        for fam in fams:
            cats = self._store.font_categories(fam)
            label = fam if not cats else "%s   ·  %s" % (fam, ", ".join(cats))
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, fam)
            f = QFont(fam)
            f.setPixelSize(15)
            item.setFont(f)
            self.list.addItem(item)
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.preview.setText(self.t("fav_none"))
            self.preview.setFont(QFont())
        self.count_lbl.setText(self.t("fav_count", n=self.list.count()))
        has = self.list.count() > 0
        for b in (self.apply_btn, self.edit_btn, self.remove_btn):
            b.setEnabled(has)

    def _update_preview(self):
        fam = self._selected_family()
        if not fam:
            return
        self.preview.setText(fam + "  –  AaBb 123")
        f = QFont(fam)
        f.setPixelSize(22)
        self.preview.setFont(f)

    # -- actions ------------------------------------------------------------
    def _apply_current(self):
        fam = self._selected_family()
        if fam:
            self._use(fam)

    def _on_double(self, item):
        if item is not None:
            self._use(item.data(Qt.UserRole))

    def _use(self, family):
        try:
            self._apply_fn(family)
        except Exception:
            pass
        self.fontChosen.emit(family)

    def _current_font(self):
        if self._current_font_fn is None:
            return ""
        try:
            return self._current_font_fn() or ""
        except Exception:
            return ""

    def _add_current_font(self):
        fam = self._current_font()
        if not fam:
            fam = self._ask_font()
        if not fam:
            return
        # add, then immediately let the user tag it
        self._store.add_font(fam)
        self._persist()
        self._reload_categories()
        self._refresh_list()
        self._select_family(fam)
        self._edit_categories()      # jump straight into tagging

    def _add_font_dialog(self):
        fam = self._ask_font()
        if not fam:
            return
        self._store.add_font(fam)
        self._persist()
        self._reload_categories()
        self._refresh_list()
        self._select_family(fam)
        self._edit_categories()

    def _remove_current(self):
        fam = self._selected_family()
        if not fam:
            return
        if QMessageBox.question(
                self, self.t("fav_remove"),
                self.t("fav_delete_font_q", name=fam),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._store.remove_font(fam)
        self._persist()
        self._reload_categories()
        self._refresh_list()

    def _edit_categories(self):
        fam = self._selected_family()
        if not fam:
            return
        chosen = _CategoryDialog(
            self, self.t, self._store.categories(),
            self._store.font_categories(fam),
            title=fam).run()
        if chosen is None:
            return
        self._store.set_font_categories(fam, chosen)
        self._persist()
        self._reload_categories()
        self._refresh_list()
        self._select_family(fam)

    def _manage_categories(self):
        _ManageCategoriesDialog(self, self.t, self._store).exec_()
        self._persist()
        self._reload_categories()
        self._refresh_list()

    # -- small dialogs / utilities -----------------------------------------
    def _ask_font(self):
        """Pick an installed family from a searchable list."""
        fams = []
        try:
            fams = list(self._families_fn() or [])
        except Exception:
            fams = []
        if not fams:
            return None
        fam, ok = _FontChooserDialog(self, self.t, fams).run()
        return fam if ok else None

    def _select_family(self, family):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == family:
                self.list.setCurrentRow(i)
                return

    def refresh(self):
        """Public: re-read the store from disk (e.g. after an import)."""
        self._store = FavoritesStore.from_json(self._safe_load())
        self._reload_categories()
        self._restore_filter()
        self._refresh_list()

    def add_favorite(self, family, categories=None):
        """Public: star a font from elsewhere (e.g. the picker's ★ button)."""
        if not family:
            return
        self._store.add_font(family, categories or [])
        self._persist()
        self._reload_categories()
        self._refresh_list()


# ---------------------------------------------------------------------------
#  Dialogs
# ---------------------------------------------------------------------------
class _FontChooserDialog(QDialog):
    """A searchable list of installed families."""

    def __init__(self, parent, tr, families):
        super().__init__(parent)
        self._tr = tr
        self.setWindowTitle(tr("fav_pick_font"))
        self.resize(360, 440)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("fav_search_ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        for fam in families:
            it = QListWidgetItem(fam)
            it.setData(Qt.UserRole, fam)
            f = QFont(fam)
            f.setPixelSize(15)
            it.setFont(f)
            self.list.addItem(it)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.list, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.search.setFocus()

    def _filter(self, text):
        low = (text or "").lower().split()
        first = None
        for i in range(self.list.count()):
            it = self.list.item(i)
            name = it.data(Qt.UserRole).lower()
            hide = not all(tok in name for tok in low)
            it.setHidden(hide)
            if not hide and first is None:
                first = i
        if first is not None:
            cur = self.list.currentItem()
            if cur is None or cur.isHidden():
                self.list.setCurrentRow(first)

    def run(self):
        if self.exec_() != QDialog.Accepted:
            return None, False
        it = self.list.currentItem()
        if it is None or it.isHidden():
            return None, False
        return it.data(Qt.UserRole), True


class _CategoryDialog(QDialog):
    """Checkboxes for every category + inline 'new category' entry. Used to tag
    one font."""

    def __init__(self, parent, tr, categories, selected, title=""):
        super().__init__(parent)
        self._tr = tr
        self.setWindowTitle(title or tr("fav_edit_cats"))
        self.resize(300, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("fav_choose_cats")))
        self._box = QWidget()
        self._box_lay = QVBoxLayout(self._box)
        self._box_lay.setContentsMargins(0, 0, 0, 0)
        self._checks = {}
        sel_low = {c.lower() for c in (selected or [])}
        for c in categories:
            cb = QCheckBox(c)
            cb.setChecked(c.lower() in sel_low)
            self._checks[c] = cb
            self._box_lay.addWidget(cb)
        self._box_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._box)
        lay.addWidget(scroll, 1)

        new_row = QHBoxLayout()
        self._new = QLineEdit()
        self._new.setPlaceholderText(tr("fav_new_cat_ph"))
        self._new.returnPressed.connect(self._add_new)
        add = QPushButton(tr("fav_new_cat_add"))
        add.clicked.connect(self._add_new)
        new_row.addWidget(self._new, 1)
        new_row.addWidget(add)
        lay.addLayout(new_row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add_new(self):
        name = self._new.text().strip()
        if not name or name in self._checks:
            self._new.clear()
            return
        cb = QCheckBox(name)
        cb.setChecked(True)
        self._checks[name] = cb
        # insert before the trailing stretch
        self._box_lay.insertWidget(self._box_lay.count() - 1, cb)
        self._new.clear()

    def run(self):
        if self.exec_() != QDialog.Accepted:
            return None
        return [c for c, cb in self._checks.items() if cb.isChecked()]


class _ManageCategoriesDialog(QDialog):
    """Add / rename / delete categories globally."""

    def __init__(self, parent, tr, store):
        super().__init__(parent)
        self._tr = tr
        self._store = store
        self.setWindowTitle(tr("fav_manage_title"))
        self.resize(320, 400)
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        self._new = QLineEdit()
        self._new.setPlaceholderText(tr("fav_new_cat_ph"))
        self._new.returnPressed.connect(self._add)
        add = QPushButton(tr("fav_new_cat_add"))
        add.clicked.connect(self._add)
        row.addWidget(self._new, 1)
        row.addWidget(add)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        ren = QPushButton(tr("fav_rename"))
        ren.clicked.connect(self._rename)
        rem = QPushButton(tr("fav_delete"))
        rem.clicked.connect(self._delete)
        row2.addWidget(ren)
        row2.addWidget(rem)
        lay.addLayout(row2)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        # Close maps to reject by default; wire it to accept so it just closes
        bb.clicked.connect(lambda _b: self.accept())
        lay.addWidget(bb)
        self._reload()

    def _reload(self):
        self.list.clear()
        counts = self._store.category_counts()
        for c in self._store.categories():
            self.list.addItem("%s (%d)" % (c, counts.get(c, 0)))
        # store raw names on items
        for i, c in enumerate(self._store.categories()):
            self.list.item(i).setData(Qt.UserRole, c)

    def _current(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _add(self):
        name = self._new.text().strip()
        if name:
            self._store.add_category(name)
            self._new.clear()
            self._reload()

    def _rename(self):
        cur = self._current()
        if not cur:
            return
        new, ok = QInputDialog.getText(self, self._tr("fav_rename"),
                                       self._tr("fav_rename"), text=cur)
        if ok and new.strip():
            self._store.rename_category(cur, new.strip())
            self._reload()

    def _delete(self):
        cur = self._current()
        if not cur:
            return
        self._store.remove_category(cur)
        self._reload()
