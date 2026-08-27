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

import os
import tempfile
import zipfile

from ._qt import Qt, pyqtSignal, QSize, QTimer
from ._qt import QFont, QFontMetrics, QColor, QPixmap, QPainter
from ._qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QDialog, QDialogButtonBox,
    QCheckBox, QInputDialog, QMessageBox, QScrollArea, QMenu,
    QFileDialog, QStyledItemDelegate, QStyle, QSlider, QApplication,
)

from .fontfav import FavoritesStore, UNCATEGORIZED
from . import fontmatch
from .fontfiles import add_fonts_to_zip as _zip_font_files

_ROLE_FAMILY = Qt.ItemDataRole.UserRole
_ROLE_CATS = Qt.ItemDataRole.UserRole + 1
_FACE_PX = 16                       # font size of the per-row face preview
#: Cap on how many rendered font faces (and their tinted copies) are kept in
#: memory. Well above any screenful, so scroll locality means an evicted face is
#: always far off-screen; if the user scrolls back to it, paint re-renders it
#: once (no flicker). Bounds memory on huge favourite lists.
_FACE_CACHE_MAX = 400


class _FontItemDelegate(QStyledItemDelegate):
    """Draws each favourite IN ITS OWN FONT — but the potentially slow bit (Qt
    loading a decorative font the first time it's drawn) is done off the paint
    path: the panel renders each face to a cached pixmap on a timer, and until
    that's ready this delegate shows the plain name. So the tab opens instantly
    no matter how many favourites there are, and the faces fade in. The panel
    owns the cache; a fixed row height keeps layout cheap."""

    def __init__(self, panel, px=_FACE_PX, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._px = int(px)

    def _size(self):
        return getattr(self._panel, "_face_px", self._px) if self._panel \
            else self._px

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self._size() + 12)

    def paint(self, painter, option, index):
        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        fam = index.data(_ROLE_FAMILY) or name
        cats = index.data(_ROLE_CATS) or ""
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            fg = option.palette.highlightedText().color()
        else:
            fg = option.palette.text().color()
        rect = option.rect.adjusted(6, 0, -6, 0)
        # Render the face NOW if it isn't cached yet, so a row is *never* drawn
        # in the wrong (default) font and then swapped — that swap is the flicker
        # the user sees when scrolling faster than the background prewarm. Once
        # cached it's a cheap blit; the sync render only ever happens once a row.
        tinted = self._panel._tinted_face(fam, fg) if self._panel else None
        if tinted:                     # cached glyph mask tinted to fg: cheap blit
            painter.drawPixmap(
                rect.left(), rect.top() + (rect.height() - tinted.height()) // 2,
                tinted)
            name_w = tinted.width()
        else:                          # font couldn't be rendered: plain name
            f = QFont()
            f.setPixelSize(self._size())
            painter.setFont(f)
            painter.setPen(fg)
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            name_w = QFontMetrics(f).horizontalAdvance(name)
        if cats:
            off = name_w + 14
            if off < rect.width() - 10:
                df = QFont()
                df.setPixelSize(max(9, self._size() - 4))
                painter.setFont(df)
                c = QColor(fg)
                c.setAlpha(150)
                painter.setPen(c)
                painter.drawText(rect.adjusted(off, 0, 0, 0),
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "· " + cats)
        painter.restore()

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
    "fav_ctx_edit": "Edit categories…",
    "fav_ctx_delete": "Delete…",
    "fav_size": "Aa",
    "fav_size_tip": "Preview size — drag to see the fonts bigger.",
    "fav_import": "Import…",
    "fav_export": "Export…",
    "fav_import_done": "Imported {n} new favourite fonts.",
    "fav_export_done": "Exported {n} favourites with {fonts} font files "
                       "({missing} not found on this PC).",
    "fav_import_bundle_done": "Imported {n} favourites.\nFonts: {inst} installed, "
                              "{skip} already present, {fail} failed.\nRestart "
                              "Krita if a newly installed font doesn't show yet.",
    "fav_export_filter": "TypeR font bundle (*.zip)",
    "fav_import_filter": "TypeR font bundle (*.zip);;JSON (*.json);;All files (*)",
    "fav_io_error": "Could not read/write the file:\n{err}",
    "fav_missing_title": "Missing fonts",
    "fav_missing_intro": "These favourite fonts are not installed on this "
                         "computer. Install/download them so your text renders "
                         "with the intended font:",
    "fav_missing_none": "All favourite fonts are installed. ✓",
    "ok": "OK",
    "cancel": "Cancel",
}


class FontFavoritesPanel(QWidget):
    """The favourites tab: category filter + search + list + actions."""

    #: emitted when the user picks a font to use (family name)
    fontChosen = pyqtSignal(str)

    def __init__(self, families_fn, apply_fn, load_fn, save_fn, tr=None,
                 current_font_fn=None, find_fonts_fn=None, install_fonts_fn=None,
                 parent=None):
        super().__init__(parent)
        self._families_fn = families_fn
        self._apply_fn = apply_fn
        self._load_fn = load_fn
        self._save_fn = save_fn
        self._current_font_fn = current_font_fn
        # optional: bundle the actual font files on export + install them on
        # import. When absent, export/import falls back to the list only.
        self._find_fonts_fn = find_fonts_fn
        self._install_fonts_fn = install_fonts_fn
        self._tr = tr or (lambda k: _FALLBACK.get(k, k))
        self._store = FavoritesStore.from_json(self._safe_load())

        # progressively-rendered font-face cache (see _FontItemDelegate): the tab
        # opens instantly with plain names, then each row's own face fades in as
        # it is rendered off the paint path — so opening never stutters.
        self._face_cache = {}          # family -> QPixmap of the name in its font
        self._face_pending = []        # families still to render
        # tinted-to-text-colour blits, keyed (family, colour) — so scrolling
        # doesn't re-tint the glyph mask on every single repaint (a ~100x win).
        self._tint_cache = {}
        try:
            self._face_px = max(10, min(64, int(self._store.ui_get("face_px", 16))))
        except Exception:
            self._face_px = 16
        self._face_timer = QTimer(self)
        # a small interval (not 0) so the background prewarm never competes with
        # the first paint or an active scroll — the sync render in paint covers
        # any row the prewarm hasn't reached yet, so this only trades a gentler
        # CPU load for the prewarm finishing a touch later.
        self._face_timer.setInterval(5)
        self._face_timer.timeout.connect(self._render_faces_step)
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

        # preview size: drag to make the font faces bigger for a closer look
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel(self.t("fav_size")))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(10, 64)
        self.size_slider.setValue(self._face_px)
        self.size_slider.setToolTip(self.t("fav_size_tip"))
        self.size_slider.valueChanged.connect(self._on_face_size_changed)
        size_row.addWidget(self.size_slider, 1)
        lay.addLayout(size_row)

        self.list = QListWidget()
        self.list.setMinimumHeight(160)
        # Speed: uniform row height + a delegate that renders each font in its own
        # face for the VISIBLE rows only. This shows what every favourite looks
        # like (the whole point) without the per-item font resolution that made a
        # long list lag on every rebuild/click.
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(_FontItemDelegate(self, _FACE_PX, self.list))
        self.list.itemDoubleClicked.connect(self._on_double)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_context_menu)
        lay.addWidget(self.list, 1)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color: gray; font-size: 10px;")
        lay.addWidget(self.count_lbl)

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

        io_row = QHBoxLayout()
        self.import_btn = QPushButton(self.t("fav_import"))
        self.import_btn.clicked.connect(self._import_favorites)
        self.export_btn = QPushButton(self.t("fav_export"))
        self.export_btn.clicked.connect(self._export_favorites)
        io_row.addWidget(self.import_btn)
        io_row.addWidget(self.export_btn)
        lay.addLayout(io_row)

    # -- selection helpers --------------------------------------------------
    def _selected_family(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

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
            item = QListWidgetItem(fam)             # name only; delegate paints it
            item.setData(_ROLE_FAMILY, fam)
            item.setData(_ROLE_CATS, ", ".join(cats) if cats else "")
            self.list.addItem(item)
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(0)
            self.count_lbl.setText(self.t("fav_count", n=self.list.count()))
        else:
            self.count_lbl.setText(self.t("fav_none"))
        has = self.list.count() > 0
        for b in (self.apply_btn, self.edit_btn, self.remove_btn):
            b.setEnabled(has)
        self._prewarm_faces(fams)

    # -- progressive font-face rendering (no first-open stutter) -----------
    def _prewarm_faces(self, families):
        """Queue rows' faces (not just the visible ones) to render in the
        background, so scrolling doesn't keep hitting un-rendered rows. Capped at
        the cache size: on a huge list we prewarm the first _FACE_CACHE_MAX and
        let the sync render in paint cover the rest on demand (no point rendering
        faces we'd only evict). A face, once shown, stays its own font for good."""
        budget = _FACE_CACHE_MAX - (len(self._face_cache) + len(self._face_pending))
        for fam in families:
            if budget <= 0:
                break
            if fam and fam not in self._face_cache and fam not in self._face_pending:
                self._face_pending.append(fam)
                budget -= 1
        if self._face_pending and not self._face_timer.isActive():
            self._face_timer.start()
    def _face_pixmap(self, family):
        """The cached alpha-mask pixmap of `family`'s name in its own font, or
        None if not rendered yet."""
        return self._face_cache.get(family)

    def _ensure_face(self, family):
        """Return the face pixmap, rendering + caching it now if needed. Called
        from the delegate's paint so a row is never shown in the wrong font and
        then swapped (the scroll flicker). The background prewarm means this
        usually just hits the cache; the sync render happens at most once a row."""
        if not family:
            return None
        pm = self._face_cache.get(family)
        if pm is None:
            pm = self._make_face(family)
            self._face_cache[family] = pm      # cache even False, so no retry
            self._evict_faces()
        return pm

    def _evict_faces(self):
        """Keep the caches bounded. dict preserves insertion order, so the
        oldest-rendered faces go first — with scroll locality those are the
        furthest off-screen, never a currently-visible row (see _FACE_CACHE_MAX).
        The matching tinted copies are dropped in one pop (tints are per-family)."""
        over = len(self._face_cache) - _FACE_CACHE_MAX
        if over <= 0:
            return
        for fam in list(self._face_cache.keys())[:over]:
            self._face_cache.pop(fam, None)
            self._tint_cache.pop(fam, None)

    def _tinted_face(self, family, color):
        """The face pixmap tinted to `color`, cached per family then per colour.
        The tint is a full compositing pass, so doing it once and blitting the
        result keeps scrolling smooth (rows repaint constantly). Returns None if
        the face couldn't be rendered (caller falls back to the plain name)."""
        face = self._ensure_face(family)
        if not face:
            return None
        by_colour = self._tint_cache.get(family)
        if by_colour is None:
            by_colour = self._tint_cache[family] = {}
        rgba = color.rgba()
        tinted = by_colour.get(rgba)
        if tinted is None:
            tinted = QPixmap(face.size())
            tinted.fill(Qt.GlobalColor.transparent)
            tp = QPainter(tinted)
            tp.drawPixmap(0, 0, face)
            tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            tp.fillRect(tinted.rect(), color)
            tp.end()
            by_colour[rgba] = tinted
        return tinted

    def _on_face_size_changed(self, v):
        """Preview-size slider: bigger font faces for a closer look. Re-applies
        the row height, drops the (old-size) cache so faces re-render, and
        remembers the choice."""
        self._face_px = int(v)
        self._face_cache.clear()
        self._tint_cache.clear()
        self._face_pending = []
        try:
            self._store.ui_set("face_px", int(v))
            self._persist()
        except Exception:
            pass
        # uniform-item-sizes cached the old row height; toggle to recompute it
        self.list.setUniformItemSizes(False)
        self.list.setUniformItemSizes(True)
        self.list.doItemsLayout()
        # re-render every face at the new size so scrolling stays flicker-free
        self._prewarm_faces([self.list.item(i).data(_ROLE_FAMILY)
                             for i in range(self.list.count())])
        self.list.viewport().update()

    def _request_face(self, family):
        """A visible row's face isn't cached yet — queue it to render off the
        paint path so opening the tab stays instant. A currently-visible row
        jumps to the front so what the user is looking at renders first."""
        if not family or family in self._face_cache:
            return
        if family in self._face_pending:
            self._face_pending.remove(family)          # re-prioritise it
        self._face_pending.insert(0, family)
        if not self._face_timer.isActive():
            self._face_timer.start()

    def _render_faces_step(self):
        """Render a batch of queued faces, then repaint so those rows swap from
        the plain name to the real face. A big-enough batch means scrolling
        rarely catches a row mid-render (which would look like a flicker)."""
        drew = False
        for _ in range(8):
            if not self._face_pending:
                break
            fam = self._face_pending.pop(0)
            if fam not in self._face_cache:
                self._face_cache[fam] = self._make_face(fam)
                drew = True
        if drew:
            self._evict_faces()
        if not self._face_pending:
            self._face_timer.stop()
        if drew:
            self.list.viewport().update()

    def _make_face(self, family):
        """Pixmap of `family`'s name drawn IN that font as an opaque-on-transparent
        mask (the delegate tints it to the row's text colour). Rendering this is
        what loads the font — done here, off the paint path. False on failure."""
        try:
            f = QFont(family)
            f.setPixelSize(self._face_px)
            fm = QFontMetrics(f)
            w = max(1, min(fm.horizontalAdvance(family) + 4, 1600))
            pm = QPixmap(w, self._face_px + 8)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setFont(f)
            p.setPen(QColor(0, 0, 0))
            p.drawText(2, self._face_px, family)
            p.end()
            return pm
        except Exception:              # noqa: BLE001
            return False

    # -- actions ------------------------------------------------------------
    def _apply_current(self):
        fam = self._selected_family()
        if fam:
            self._use(fam)

    def _on_double(self, item):
        if item is not None:
            self._use(item.data(Qt.ItemDataRole.UserRole))

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
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
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
        _ManageCategoriesDialog(self, self.t, self._store).exec()
        self._persist()
        self._reload_categories()
        self._refresh_list()

    def _list_context_menu(self, pos):
        """Right-click a favourite: edit its categories or delete it (delete
        asks for confirmation)."""
        it = self.list.itemAt(pos)
        if it is None:
            return
        self.list.setCurrentItem(it)
        menu = QMenu(self.list)
        act_edit = menu.addAction(self.t("fav_ctx_edit"))
        menu.addSeparator()
        act_del = menu.addAction(self.t("fav_ctx_delete"))
        chosen = menu.exec(self.list.mapToGlobal(pos))
        if chosen is act_edit:
            self._edit_categories()
        elif chosen is act_del:
            self._remove_current()      # already asks for confirmation

    # -- import / export ----------------------------------------------------
    def _export_favorites(self):
        """Export a .zip bundle: the favourites list PLUS the actual font files
        (found on this PC by family name), so it can be moved to another machine.
        Every cut of a family travels — Regular, Bold, Italic — because a bundle
        that only carries one of them still leaves work on the other machine.
        Fonts that aren't installed here can't be bundled."""
        path, _f = QFileDialog.getSaveFileName(
            self, self.t("fav_export"), "font-favourites.zip",
            self.t("fav_export_filter"))
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        fams = self._store.fonts()
        files = self._lookup_font_files(fams)
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("favourites.json", self._store.to_json())
                n_files = _zip_font_files(z, files)
        except Exception as e:                          # noqa: BLE001
            QMessageBox.warning(self, self.t("fav_export"),
                                self.t("fav_io_error", err=e))
            return
        missing = [f for f in fams if f not in files]
        QMessageBox.information(
            self, self.t("fav_export"),
            self.t("fav_export_done", n=len(fams), fonts=n_files,
                   missing=len(missing)))

    def _lookup_font_files(self, families):
        """{family: [font file paths]} for *families* — the lookup can take a
        moment the first time (it reads every installed font file), so the
        cursor says so."""
        if self._find_fonts_fn is None:
            return {}
        app = QApplication.instance()
        if app is not None:
            app.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            files = self._find_fonts_fn(families) or {}
        except Exception:                               # noqa: BLE001
            files = {}
        finally:
            if app is not None:
                app.restoreOverrideCursor()
        # the callback may hand back one path per family or a list of them
        return {fam: ([p] if isinstance(p, str) else list(p))
                for fam, p in files.items() if p}

    def _import_favorites(self):
        """Import a .zip bundle (favourites + font files, fonts get installed)
        or an old plain .json (list only)."""
        path, _f = QFileDialog.getOpenFileName(
            self, self.t("fav_import"), "", self.t("fav_import_filter"))
        if not path:
            return
        if zipfile.is_zipfile(path):
            self._import_bundle(path)
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except Exception as e:                          # noqa: BLE001
            QMessageBox.warning(self, self.t("fav_import"),
                                self.t("fav_io_error", err=e))
            return
        incoming = FavoritesStore.from_json(text)
        n = self._store.merge(incoming)
        self._persist()
        self._reload_categories()
        self._restore_filter()
        self._refresh_list()
        QMessageBox.information(self, self.t("fav_import"),
                                self.t("fav_import_done", n=n))
        missing = incoming.missing_fonts(self._families(), self._font_resolver())
        if missing:
            self._warn_missing(missing)

    def _import_bundle(self, path):
        incoming = FavoritesStore()
        font_paths = []
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                if "favourites.json" in names:
                    incoming = FavoritesStore.from_json(
                        z.read("favourites.json").decode("utf-8"))
                fonts = [nm for nm in names
                         if nm.startswith("fonts/") and not nm.endswith("/")]
                if fonts:
                    tmp = tempfile.mkdtemp(prefix="typer_fonts_")
                    for nm in fonts:
                        dest = os.path.join(tmp, os.path.basename(nm))
                        with open(dest, "wb") as fh:
                            fh.write(z.read(nm))
                        font_paths.append(dest)
        except Exception as e:                          # noqa: BLE001
            QMessageBox.warning(self, self.t("fav_import"),
                                self.t("fav_io_error", err=e))
            return
        n = self._store.merge(incoming)
        res = {"installed": [], "skipped": [], "failed": []}
        if font_paths and self._install_fonts_fn is not None:
            try:
                res = self._install_fonts_fn(font_paths) or res
            except Exception:                           # noqa: BLE001
                pass
        self._persist()
        self._reload_categories()
        self._restore_filter()
        self._refresh_list()
        QMessageBox.information(
            self, self.t("fav_import"),
            self.t("fav_import_bundle_done", n=n,
                   inst=len(res.get("installed", [])),
                   skip=len(res.get("skipped", [])),
                   fail=len(res.get("failed", []))))
        # only nag about missing fonts the bundle couldn't provide
        if not font_paths:
            missing = incoming.missing_fonts(self._families(),
                                             self._font_resolver())
            if missing:
                self._warn_missing(missing)

    # -- missing fonts ------------------------------------------------------
    def _warn_missing(self, missing):
        QMessageBox.information(
            self, self.t("fav_missing_title"),
            self.t("fav_missing_intro") + "\n\n• " + "\n• ".join(missing))

    def show_missing_fonts_dialog(self):
        """Public: list favourite fonts that aren't installed (or confirm all
        are). Used by the Setup-tab button too."""
        missing = self._store.missing_fonts(self._families(),
                                            self._font_resolver())
        if missing:
            self._warn_missing(missing)
        else:
            QMessageBox.information(self, self.t("fav_missing_title"),
                                    self.t("fav_missing_none"))
        return missing

    # -- small dialogs / utilities -----------------------------------------
    def _families(self):
        try:
            return list(self._families_fn() or [])
        except Exception:
            return []

    def _font_resolver(self):
        """Callable for FavoritesStore.missing_fonts().

        Favourites travel between machines inside bundles, so their spelling is
        whatever the exporting machine used. Matching tolerantly keeps the
        import dialog from listing a dozen fonts as missing that are in fact
        installed under a slightly different family name."""
        idx = fontmatch.FontIndex(self._families())
        return idx.is_available

    def _ask_font(self):
        """Pick an installed family from a searchable list."""
        fams = self._families()
        if not fams:
            return None
        fam, ok = _FontChooserDialog(self, self.t, fams).run()
        return fam if ok else None

    def _select_family(self, family):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == family:
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
        self.list.setUniformItemSizes(True)      # fast with thousands of fonts
        for fam in families:
            it = QListWidgetItem(fam)
            it.setData(_ROLE_FAMILY, fam)
            self.list.addItem(it)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.list, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
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
            name = it.data(Qt.ItemDataRole.UserRole).lower()
            hide = not all(tok in name for tok in low)
            it.setHidden(hide)
            if not hide and first is None:
                first = i
        if first is not None:
            cur = self.list.currentItem()
            if cur is None or cur.isHidden():
                self.list.setCurrentRow(first)

    def run(self):
        if self.exec() != QDialog.DialogCode.Accepted:
            return None, False
        it = self.list.currentItem()
        if it is None or it.isHidden():
            return None, False
        return it.data(Qt.ItemDataRole.UserRole), True


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

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
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
        if self.exec() != QDialog.DialogCode.Accepted:
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

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
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
            self.list.item(i).setData(Qt.ItemDataRole.UserRole, c)

    def _current(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

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
