# -*- coding: utf-8 -*-
"""Integration tests for the Krita-bound module (typer_kr/typer_kr.py).

A fake `krita` module + an offscreen Qt app let the real code run headless:
the insert path is exercised end to end and the SVG it hands to Krita is
captured and inspected; the font picker and the Excel importer are tested too.

Run:  python test_integration.py     (PyQt5 required; no real Krita needed)
"""
import json
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  ok   " + name)
    else:
        _fail += 1
        print("  FAIL " + name)


# --- offscreen Qt + a fake `krita` module -----------------------------------
# binding-agnostic + must NOT import the typer_kr package yet (that pulls in
# `krita`, which is faked further down) — so import straight from PyQt6/PyQt5.
try:
    try:
        from PyQt6.QtWidgets import QApplication, QWidget, QDockWidget
        from PyQt6.QtGui import QColor
    except ImportError:
        from PyQt5.QtWidgets import QApplication, QWidget, QDockWidget
        from PyQt5.QtGui import QColor
    _app = QApplication.instance() or QApplication([])
except Exception as e:                          # pragma: no cover
    print("Qt unavailable, skipping integration tests:", e)
    sys.exit(0)


class _FakeNode:
    def __init__(self, kind="vector"):
        self.svg = None
        self.kind = kind
        self.pixels = None
        self.inherit_alpha = None
        self._kids = []

    def addShapesFromSvg(self, svg):
        self.svg = svg
        return True

    def addChildNode(self, node, above):
        self._kids.append(node)
        return True

    def childNodes(self):
        return list(self._kids)

    def setPixelData(self, buf, x, y, w, h):
        self.pixels = (len(buf), x, y, w, h)
        return True

    def setInheritAlpha(self, value):        # clip-to-layer-below (vector mode)
        self.inherit_alpha = value
        return True


class _FakeSelection:
    def __init__(self, x=100, y=50, w=40, h=20):
        self._x, self._y, self._w, self._h = x, y, w, h

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._w

    def height(self):
        return self._h

    def pixelData(self, x, y, w, h):
        return bytes([255]) * (w * h)               # fully selected


class _FakeDoc:
    def __init__(self, w=800, h=600):
        self._w, self._h = w, h
        self.last = None
        self.sel = None
        self._root = _FakeNode("root")

    def width(self):
        return self._w

    def height(self):
        return self._h

    def selection(self):
        return self.sel

    def rootNode(self):
        return self._root

    def createVectorLayer(self, label):
        n = _FakeNode("vector")
        self.last = n
        return n

    def createNode(self, name, typ):            # raster (paint) insert path
        n = _FakeNode(typ)
        self.last = n
        return n

    def createGroupLayer(self, name):           # 'keep vector' clip path
        n = _FakeNode("grouplayer")
        self.last = n
        return n

    def setSelection(self, sel):
        self.sel = sel

    def setActiveNode(self, node):
        return None

    def waitForDone(self):
        return None

    def refreshProjection(self):
        return None

    def nodeByName(self, name):
        return None

    def topLevelNodes(self):
        return []


class _App:
    def __init__(self):
        self._doc = None
        self._settings = {}                      # (group, key) -> value

    def activeDocument(self):
        return self._doc

    def readSetting(self, group, key, default=""):
        return self._settings.get((group, key), default)

    def writeSetting(self, group, key, val):
        self._settings[(group, key)] = val

    def addDockWidgetFactory(self, factory):     # called by register()
        return None

    def activeWindow(self):                      # used while building the docker
        return None

    def action(self, *a):
        return None

    def notifier(self):
        return _Notifier()


class _Notifier:
    def imageCreated(self):
        return self

    def connect(self, *a):
        return None


_krita = types.ModuleType("krita")
_KR_APP = _App()


class _Krita:
    @classmethod
    def instance(cls):
        return _KR_APP


_DockPosition = type("DockPosition", (object,), {"DockRight": 1, "DockLeft": 0})
_krita.Krita = _Krita
# Real Krita DockWidget extends QDockWidget (setWidget/widget), so the stub must
# too — otherwise building the full TyperDocker fails on self.setWidget(...).
_krita.DockWidget = type("DockWidget", (QDockWidget,), {})
_krita.DockWidgetFactory = type(
    "DockWidgetFactory", (object,),
    {"__init__": lambda self, *a, **k: None})
_krita.DockWidgetFactoryBase = type("DockWidgetFactoryBase", (object,),
                                    {"DockPosition": _DockPosition})
class _StubSelection:
    """Enough of Krita's Selection for the batch path: a rectangle that can be
    overwritten with an elliptical mask, and read back the way _sel_shape and
    insert_text_layer read it."""

    def __init__(self):
        self._x = self._y = self._w = self._h = 0
        self._data = b""

    def select(self, x, y, w, h, _value=255):
        self._x, self._y, self._w, self._h = int(x), int(y), int(w), int(h)
        self._data = bytes([255]) * (self._w * self._h)

    def setPixelData(self, data, x, y, w, h):
        self._x, self._y, self._w, self._h = int(x), int(y), int(w), int(h)
        self._data = bytes(data)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._w

    def height(self):
        return self._h

    def pixelData(self, x, y, w, h):
        if len(self._data) >= w * h:
            return self._data
        return bytes([255]) * (w * h)


_krita.Selection = _StubSelection
sys.modules["krita"] = _krita

sys.path.insert(0, _HERE)
try:
    import typer_kr.typer_kr as TK
    imported = True
except Exception as e:                          # pragma: no cover
    imported = False
    print("  FAIL  could not import typer_kr.typer_kr:", e)
    import traceback
    traceback.print_exc()

check("typer_kr module imports headless (with a fake krita)", imported)
if not imported:
    print("\n%d passed, %d failed" % (_pass, _fail + 1))
    sys.exit(1)

# =====================================================================
# insert_text_layer end to end (capture the SVG handed to Krita)
# =====================================================================
print("--- insert path (captured SVG) ---")


def insert(**kw):
    doc = _FakeDoc(800, 600)
    _KR_APP._doc = doc
    base = dict(line="THAT HE PISSES ME OFF, BUT", font_family="Arial",
                font_px=72, color=QColor(0, 0, 0), auto_fit=True, max_px=72,
                padding_frac=0.1, line_spacing=1.0, align="center",
                valign="middle", layer_index=1, box=(100, 100, 320, 320))
    base.update(kw)
    ok, key, fmt = TK.insert_text_layer(
        base.pop("line"), base.pop("font_family"), base.pop("font_px"),
        base.pop("color"), base.pop("auto_fit"), base.pop("max_px"),
        base.pop("padding_frac"), base.pop("line_spacing"), **base)
    return ok, key, (doc.last.svg if doc.last else None)


ok, key, svg = insert(outline=True, outline_color=QColor(255, 255, 255),
                      outline_px=6)
check("insert succeeds and hands an <svg> to Krita",
      ok and svg and svg.lstrip().startswith("<svg"))
check("single outline -> 2 text layers (outline + fill)",
      svg and svg.count("<text") == 2)

ok, key, svg = insert(outline=True, outline_color=QColor(255, 255, 255),
                      outline_px=6, outline2_color=QColor(0, 0, 0),
                      outline2_px=14)
check("double outline -> 3 text layers (outer + inner + fill)",
      svg and svg.count("<text") == 3)
check("double outline stroke widths are outer=14, inner=6 (no doubling)",
      svg and 'stroke-width="14' in svg and 'stroke-width="6' in svg)

ok, key, svg = insert(outline=False, outline_color=QColor(255, 255, 255),
                      outline_px=0)
check("no outline -> a single fill text layer",
      svg and svg.count("<text") == 1)

# the 2nd outline is coupled to the outline switch: outline off -> no 2nd
# outline either, even when its width is set
ok, key, svg = insert(outline=False, outline_color=QColor(255, 255, 255),
                      outline_px=6, outline2_color=QColor(0, 0, 0),
                      outline2_px=14)
check("outline OFF drops the 2nd outline too (only the fill remains)",
      svg and svg.count("<text") == 1)

# A pattern-filled or soft/blurred outline can't be a Krita vector paint, so
# those styles must route the insert onto a RASTER (paint) layer instead; a
# plain outline stays a vector text layer.
from typer_kr._qt import QImage as _QImage


def insert_node(**kw):
    doc = _FakeDoc(800, 600)
    _KR_APP._doc = doc
    base = dict(line="THAT HE PISSES ME OFF, BUT", font_family="Arial",
                font_px=72, color=QColor(0, 0, 0), auto_fit=True, max_px=72,
                padding_frac=0.1, line_spacing=1.0, align="center",
                valign="middle", layer_index=1, box=(100, 100, 320, 320))
    base.update(kw)
    ok, key, fmt = TK.insert_text_layer(
        base.pop("line"), base.pop("font_family"), base.pop("font_px"),
        base.pop("color"), base.pop("auto_fit"), base.pop("max_px"),
        base.pop("padding_frac"), base.pop("line_spacing"), **base)
    return ok, doc.last


_pat = _QImage(8, 8, _QImage.Format.Format_ARGB32)
_pat.fill(QColor(200, 50, 50).rgb())
ok, node = insert_node(outline=True, outline_color=QColor(255, 255, 255),
                       outline_px=8, pattern_img=_pat)
check("pattern-filled outline routes onto a raster paint layer",
      ok and node is not None and node.kind == "paintlayer"
      and node.pixels is not None)
ok, node = insert_node(outline=True, outline_color=QColor(255, 255, 255),
                       outline_px=4, soft=True, soft_color=QColor(0, 0, 0),
                       soft_px=3, soft_blur=8)
check("soft/blurred outline routes onto a raster paint layer",
      ok and node is not None and node.kind == "paintlayer")
ok, node = insert_node(outline=True, outline_color=QColor(255, 255, 255),
                       outline_px=6)
check("a plain outline (no pattern/soft) stays a vector text layer",
      ok and node is not None and node.kind == "vector")
ok, node = insert_node(fill_pattern=_pat)
check("a pattern TEXT FILL routes onto a raster paint layer",
      ok and node is not None and node.kind == "paintlayer")

# 'keep text as vector': a fill pattern with vector_clip makes a GROUP holding
# an editable vector text layer + a pattern paint layer set to inherit-alpha
_vdoc = _FakeDoc(800, 600)
_KR_APP._doc = _vdoc
ok, key, _f = TK.insert_text_layer(
    "HELLO", "Arial", 48, QColor(0, 0, 0), True, 48, 0.1, 1.0,
    align="center", layer_index=1, box=(100, 100, 320, 220),
    fill_pattern=_pat, fill_scale=100, vector_clip=True)
_groups = [n for n in _vdoc._root.childNodes() if n.kind == "grouplayer"]
check("vector_clip fill pattern creates a group layer", ok and len(_groups) == 1)
if _groups:
    _kids = _groups[0].childNodes()
    _kinds = [k.kind for k in _kids]
    check("group holds an editable vector text layer (with SVG)",
          any(k.kind == "vector" and k.svg for k in _kids))
    check("group holds a pattern paint layer set to inherit-alpha",
          any(k.kind == "paintlayer" and k.inherit_alpha is True for k in _kids))
# vertical text keeps the vector path even if a pattern is set (raster is H-only)
ok, node = insert_node(outline=True, outline_color=QColor(255, 255, 255),
                       outline_px=6, pattern_img=_pat, vertical=True)
check("vertical text ignores the raster path (vector only)",
      ok and node is not None and node.kind == "vector")

# no document -> a clean failure, not a crash
_KR_APP._doc = None
ok, key, _f = TK.insert_text_layer("HI", "Arial", 40, QColor(0, 0, 0), True,
                                   40, 0.1, 1.0, box=None)
check("no active document -> (False, 'st_no_doc')",
      ok is False and key == "st_no_doc")

# =====================================================================
# FontPicker: case-insensitive match + adopt an uninstalled name
# =====================================================================
print("--- font picker ---")
fp = TK.FontPicker()
fp._all = ["Anime Ace 2", "CC Wild Words", "Comic Sans MS"]
fp._recents = []
fp._rebuild()

fp.setCurrentFamily("anime ace 2")               # wrong case
check("font picker matches case-insensitively",
      fp.currentFamily() == "Anime Ace 2")

fp.setCurrentFamily("CC Wild Words")             # exact
check("font picker exact match works",
      fp.currentFamily() == "CC Wild Words")

fp.setCurrentFamily("Totally Not Installed")     # missing -> adopt the name
check("font picker adopts an uninstalled font name (no silent keep)",
      fp.currentFamily() == "Totally Not Installed")

# =====================================================================
# Excel importer grid reader (real regression fixtures if present)
# =====================================================================
print("--- excel grid reader ---")
_grid = TK._read_xlsx_grid  # noqa: attribute exists
_sample = os.path.join(
    _HERE, "..", "..", "..", "Desktop", "manga scanlation",
    "Houkago no Idol ni wa Himitsu ga aru", "Fonts.xlsx")
if os.path.exists(_sample):
    rows = _grid(_sample)
    # find the header row with a 'Character' column, count characters+fonts
    hdr = char_col = -1
    for i, row in enumerate(rows):
        for j, c in enumerate(row):
            if c.strip().lower() == "character":
                hdr, char_col = i, j
                break
        if hdr >= 0:
            break
    n_presets = 0
    for row in rows[hdr + 1:] if hdr >= 0 else []:
        if char_col < len(row) and row[char_col].strip():
            n_presets += sum(1 for j in range(char_col + 1, len(row))
                             if j < len(row) and row[j].strip())
    check("real font-guide xlsx: header found + presets parsed",
          hdr >= 0 and n_presets >= 10)
else:
    check("excel grid reader is callable (sample file not present)",
          callable(_grid))

# =====================================================================
# Session persistence: save open tabs + progress, reopen them next start
# =====================================================================
print("--- session persistence ---")
from typer_kr._qt import QTabBar


class _FakeDocker:
    """Borrows the real save/restore methods, bound to a minimal object that
    only carries the state those methods touch."""
    _save_sessions = TK.TyperDocker._save_sessions
    _restore_sessions = TK.TyperDocker._restore_sessions

    def __init__(self):
        self._sessions = []
        self._next_sid = 1
        self._active_sid = None
        self.script_tabs = QTabBar()
        self._restored_sid = None

    def _session_index(self, sid):
        for i, s in enumerate(self._sessions):
            if s["id"] == sid:
                return i
        return -1

    def _snapshot_active(self):
        pass

    def _restore_by_sid(self, sid):
        self._restored_sid = sid

    def _schedule_session_save(self):
        pass

    def _tr(self, k):
        return k


_KR_APP._settings.clear()
d = _FakeDocker()
d._sessions = [
    {"id": 1, "name": "Chapter A", "path": "/a.txt", "text": "JP\nEN",
     "pairs": [("JP", "EN")], "pair_pages": [0], "pages": ["Page 1"],
     "index": 0, "done": {0}, "comments": []},
    {"id": 2, "name": "Chapter B", "path": "", "text": "hi there",
     "pairs": [("", "hi there")], "pair_pages": [0], "pages": [],
     "index": 0, "done": set(), "comments": []},
    {"id": 3, "name": "Untitled", "path": "", "text": "",  # empty -> skipped
     "pairs": [], "pair_pages": [], "pages": [], "index": 0,
     "done": set(), "comments": []},
]
d._active_sid = 2
for s in d._sessions:
    ti = d.script_tabs.addTab(s["name"])
    d.script_tabs.setTabData(ti, s["id"])
d._save_sessions()
check("saving writes the sessions setting",
      ("typer_kr", "sessions") in _KR_APP._settings)

# a fresh docker restores from that setting
d2 = _FakeDocker()
restored = d2._restore_sessions()
check("restore reports success", restored is True)
check("empty untitled tab is skipped, 2 real tabs restored",
      len(d2._sessions) == 2)
check("names + paths + text survive the round-trip",
      d2._sessions[0]["name"] == "Chapter A"
      and d2._sessions[0]["path"] == "/a.txt"
      and d2._sessions[0]["text"] == "JP\nEN")
check("parsed pairs come back as tuples",
      d2._sessions[0]["pairs"] == [("JP", "EN")])
check("progress (done marks + index) survives",
      d2._sessions[0]["done"] == {0} and d2._sessions[0]["index"] == 0)
check("the previously active tab is reactivated",
      d2._restored_sid is not None
      and d2._sessions[d2._session_index(d2._restored_sid)]["name"]
      == "Chapter B")

# no saved sessions -> restore is a clean no-op (caller then opens Untitled)
_KR_APP._settings.pop(("typer_kr", "sessions"), None)
check("no saved sessions -> restore returns False",
      _FakeDocker()._restore_sessions() is False)


# --- Font-favourites panel (Qt widget, headless) ---------------------------
try:
    from typer_kr.fontfav_ui import FontFavoritesPanel
    _ff_blob = {"v": ""}
    _ff_applied = {"fam": None}
    _ff_panel = FontFavoritesPanel(
        families_fn=lambda: ["Arial", "CC Wild Words", "Anime Ace 2"],
        apply_fn=lambda f: _ff_applied.__setitem__("fam", f),
        load_fn=lambda: _ff_blob["v"],
        save_fn=lambda t: _ff_blob.__setitem__("v", t),
        tr=lambda k: k,
        current_font_fn=lambda: "CC Wild Words")
    check("favourites panel builds headless", _ff_panel is not None)
    _ff_panel.add_favorite("CC Wild Words", ["Dialog", "SFX"])
    _ff_panel.add_favorite("Anime Ace 2", ["Dialog"])
    check("adding favourites persists via save_fn", "CC Wild Words" in _ff_blob["v"])
    check("both favourites show in the list", _ff_panel.list.count() == 2)
    from typer_kr.fontfav_ui import _FontItemDelegate as _FFDel
    check("favourites list uses the per-font delegate (shows faces, stays fast)",
          isinstance(_ff_panel.list.itemDelegate(), _FFDel)
          and _ff_panel.list.uniformItemSizes())
    # category filter narrows to the SFX-tagged font
    _sfx_i = next((i for i in range(_ff_panel.cat_combo.count())
                   if _ff_panel.cat_combo.itemData(i) == "SFX"), None)
    check("SFX category is offered in the filter", _sfx_i is not None)
    _ff_panel.cat_combo.setCurrentIndex(_sfx_i)
    check("category filter narrows the list to 1", _ff_panel.list.count() == 1)
    # applying routes the family out through apply_fn
    _ff_panel.list.setCurrentRow(0)
    _ff_panel._apply_current()
    check("applying a favourite calls apply_fn with the family",
          _ff_applied["fam"] == "CC Wild Words")
    # a fresh panel reads the same persisted blob back AND restores the last
    # filter the user left on (SFX category → 1 match)
    _ff_panel2 = FontFavoritesPanel(
        families_fn=lambda: [], apply_fn=lambda f: None,
        load_fn=lambda: _ff_blob["v"], save_fn=lambda t: None, tr=lambda k: k)
    check("a new panel restores the last category filter (SFX → 1 match)",
          _ff_panel2.cat_combo.currentData() == "SFX"
          and _ff_panel2.list.count() == 1)
    # clearing the filter reveals both favourites again
    _ff_panel2.cat_combo.setCurrentIndex(0)
    check("clearing the filter shows both favourites again",
          _ff_panel2.list.count() == 2)
    # import/export + missing-font detection are wired
    check("panel exposes import/export buttons",
          hasattr(_ff_panel, "import_btn") and hasattr(_ff_panel, "export_btn"))
    check("panel has a right-click handler + missing-fonts dialog",
          hasattr(_ff_panel, "_list_context_menu")
          and hasattr(_ff_panel, "show_missing_fonts_dialog"))
    _miss = _ff_panel._store.missing_fonts(["Arial"])
    check("missing_fonts flags favourites that aren't installed",
          "CC Wild Words" in _miss and "Anime Ace 2" in _miss)
    # preview-size slider: bigger faces, remembered across panels
    check("panel offers a preview-size slider defaulting to the face size",
          hasattr(_ff_panel, "size_slider")
          and _ff_panel.size_slider.value() == _ff_panel._face_px)
    _ff_panel.size_slider.setValue(44)
    check("dragging the slider grows the delegate's face size + drops the cache",
          _ff_panel._face_px == 44
          and _ff_panel.list.itemDelegate()._size() == 44
          and not _ff_panel._face_cache)
    _ff_panel3 = FontFavoritesPanel(
        families_fn=lambda: [], apply_fn=lambda f: None,
        load_fn=lambda: _ff_blob["v"], save_fn=lambda t: None, tr=lambda k: k)
    check("a new panel restores the chosen preview size",
          _ff_panel3._face_px == 44)
    # perf: a tinted face is cached per (family, colour) — same colour reuses it
    from typer_kr._qt import QColor as _QC
    _c1, _c2 = _QC(200, 200, 200), _QC(255, 255, 255)
    check("tinting a face caches the result (reused on the next repaint)",
          _ff_panel3._tinted_face("Arial", _c1)
          is _ff_panel3._tinted_face("Arial", _c1))
    check("a different text colour makes its own tinted copy",
          _ff_panel3._tinted_face("Arial", _c2)
          is not _ff_panel3._tinted_face("Arial", _c1))
    # memory: the face/tint caches are bounded — oldest (off-screen) evicted
    import typer_kr.fontfav_ui as _FFUImod
    _old_max = _FFUImod._FACE_CACHE_MAX
    try:
        _FFUImod._FACE_CACHE_MAX = 20
        for _i in range(120):
            _fam = "Fam%03d" % _i
            _ff_panel3._ensure_face(_fam)
            _ff_panel3._tinted_face(_fam, _c1)
        check("face + tint caches stay bounded under the cap (no leak)",
              len(_ff_panel3._face_cache) <= 20
              and len(_ff_panel3._tint_cache) <= 20)
        check("eviction drops the oldest face and keeps the newest",
              "Fam000" not in _ff_panel3._face_cache
              and "Fam119" in _ff_panel3._face_cache)
    finally:
        _FFUImod._FACE_CACHE_MAX = _old_max
except Exception as _ff_e:                          # pragma: no cover
    check("font-favourites panel smoke test ran", False)
    import traceback
    traceback.print_exc()

# --- Main-tab order/label integrity (regression) ---------------------------
# A custom, persisted tab order must reorder the *pages* together with the tab
# labels. The old _apply_tab_order blocked the tab bar's signals, so QTabWidget
# never moved its page stack — every tab then showed another tab's content
# (labels 'scrambled', the real Setup page hiding under a wrong label).
if imported:
    try:
        def _build_docker(tab_order):
            # pretend the one-time order repair already ran, so a custom order
            # is honoured (the repair would otherwise clear it on first build)
            _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
            _KR_APP._settings[("typer_kr", "tabOrder")] = tab_order
            return TK.TyperDocker()

        for _order in ("sfx,type,style,setup,bubblr,shapr",
                       "shapr,sfx,fonts,type,style,setup,bubblr", ""):
            _d = _build_docker(_order)
            _bar = _d.main_tabs.tabBar()
            _synced = all(
                _d.main_tabs.widget(i) is _d._tab_pages.get(_bar.tabData(i))
                for i in range(_d.main_tabs.count()))
            check("tab labels match their page content (order=%r)"
                  % (_order or "default"), _synced)
            # the Setup tab is never toggleable, so it must always be present
            check("Setup tab present (order=%r)" % (_order or "default"),
                  _d._tab_index_of("setup") is not None)
            if _order == "":
                check("Setup 'missing favourite fonts' button is present",
                      hasattr(_d, "fav_missing_btn"))
            _d.deleteLater()

        # Robustness: a saved order that names an ABSENT tab (BubblR hidden) and
        # omits a PRESENT one (Fonts) must not shuffle tabs around — the missing
        # id is ignored and the unlisted tab lands at the end, content in sync.
        _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
        _KR_APP._settings[("typer_kr", "enableBubblr")] = "false"
        _KR_APP._settings[("typer_kr", "tabOrder")] = \
            "type,style,setup,bubblr,shapr,sfx"
        _d = TK.TyperDocker()
        _bar = _d.main_tabs.tabBar()
        _got = [_bar.tabData(i) for i in range(_d.main_tabs.count())]
        check("absent id ignored + unlisted tabs appended at the end",
              _got == ["type", "style", "setup", "shapr", "sfx",
                       "batch", "fonts"])
        check("content stays in sync with a ghost-id order",
              all(_d.main_tabs.widget(i) is _d._tab_pages.get(_bar.tabData(i))
                  for i in range(_d.main_tabs.count())))
        _d.deleteLater()

        # One-time repair clears a corrupted order exactly once.
        _KR_APP._settings.pop(("typer_kr", "tabOrderRepairV2"), None)
        _KR_APP._settings[("typer_kr", "enableBubblr")] = "true"
        _KR_APP._settings[("typer_kr", "tabOrder")] = "sfx,fonts,type"
        _d = TK.TyperDocker()
        check("repair clears the saved order once",
              _KR_APP._settings.get(("typer_kr", "tabOrder")) == ""
              and _KR_APP._settings.get(("typer_kr", "tabOrderRepairV2")) == "done")
        _d.deleteLater()
        for _k in ("tabOrder", "tabOrderRepairV2", "enableBubblr"):
            _KR_APP._settings.pop(("typer_kr", _k), None)
    except Exception as _to_e:                      # pragma: no cover
        check("main-tab order regression ran", False)
        import traceback
        traceback.print_exc()

# --- 'Missing fonts' report: gathers from favourites + SFX + main presets --
if imported:
    try:
        _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
        _md = TK.TyperDocker()
        check("TypeR version bumped for a real feature update (not 1.7)",
              TK.VERSION != "1.7")
        _sfxf = _md._sfx_fonts()
        check("SFX referenced fonts include the built-in presets",
              "CC Shout Out" in _sfxf and "Creepster" in _sfxf)
        # fonts that are never installed anywhere -> always 'missing'
        _md.fonts_panel.add_favorite("Zzz Fake Face 42", ["Dialog"])
        _md._groups = {"M": {"C": {"p": {"font": "Yyy Fake Face 99"}}}}
        check("missing report flags a favourite that isn't installed",
              "Zzz Fake Face 42" in _md._missing_of(_md._favorite_fonts()))
        _allmiss = _md._missing_of(_md._all_referenced_fonts())
        check("'all missing' spans favourites AND main presets",
              "Zzz Fake Face 42" in _allmiss and "Yyy Fake Face 99" in _allmiss)
        check("missing lists are de-duplicated case-insensitively",
              len(_md._dedup_ci(["Arial", "arial", "ARIAL"])) == 1)
        _md.deleteLater()
    except Exception:                               # pragma: no cover
        check("missing-fonts report ran", False)
        import traceback
        traceback.print_exc()

# --- main characters head the character + preset dropdowns -----------------
if imported:
    try:
        _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
        _KR_APP._settings.pop(("typer_kr", "mainChars"), None)
        _mc = TK.TyperDocker()
        _mc._groups = {"Serie": {
            "Zenitsu": {"Normal": {"size": 10}},
            "Denji": {"Normal": {"size": 11}, "Shout": {"size": 30}},
            "aoi": {"Normal": {"size": 12}},
            "Makima": {"Calm": {"size": 13}},
        }}
        _mc._group = "Serie"
        _mc._main_chars_map = {}
        _mc._refresh_chars_combo()
        _plain = [_mc.char_combo.itemText(i)
                  for i in range(_mc.char_combo.count())]
        check("character dropdown is plain alphabetical without main characters",
              _plain == ["aoi", "Denji", "Makima", "Zenitsu"])

        _mc._toggle_main_char("Denji")
        _mc._toggle_main_char("Makima")
        _mc._refresh_chars_combo()
        _texts = [_mc.char_combo.itemText(i)
                  for i in range(_mc.char_combo.count())]
        _datas = [_mc.char_combo.itemData(i)
                  for i in range(_mc.char_combo.count())]
        check("main characters are starred and listed first",
              _texts[:2] == ["★ Denji", "★ Makima"] and _texts[-2:] == ["aoi", "Zenitsu"])
        check("a separator divides main characters from the rest",
              _datas.count(None) == 1 and _datas[2] is None)
        check("item data stays the plain character name",
              [d for d in _datas if d]
              == ["Denji", "Makima", "aoi", "Zenitsu"])
        check("selecting by name still finds the character",
              _mc.char_combo.findData("Zenitsu") == len(_datas) - 1)

        # the flat (simple-mode) preset list floats their presets up too
        _mc.by_char_chk.setChecked(False)
        _mc._refresh_presets_combo()
        _ptexts = [_mc.preset_combo.itemText(i)
                   for i in range(_mc.preset_combo.count())]
        check("main characters' presets head the flat preset list",
              _ptexts[1:4] == ["★ Calm", "★ Normal (Denji)", "★ Shout"],
              )
        check("the rest follows after a separator",
              _ptexts[-2:] == ["Normal (Zenitsu)", "Normal (aoi)"]
              or _ptexts[-2:] == ["Normal (aoi)", "Normal (Zenitsu)"])
        _pdata = [_mc.preset_combo.itemData(i)
                  for i in range(_mc.preset_combo.count())]
        check("preset items keep their (character, name) data",
              ("Denji", "Shout") in _pdata and ("aoi", "Normal") in _pdata)
        _mc.by_char_chk.setChecked(True)

        # toggling off, persistence, and cleanup when a character is deleted
        check("toggling a main character off reports the new state",
              _mc._toggle_main_char("Makima") is False
              and not _mc._is_main_char("Makima"))
        check("main characters are written to the Krita settings",
              json.loads(_KR_APP._settings[("typer_kr", "mainChars")])
              == {"Serie": ["Denji"]})
        _mc2 = TK.TyperDocker()
        check("they are read back on the next start",
              _mc2._load_main_chars() == {"Serie": ["Denji"]})
        _mc.char_combo.setCurrentIndex(_mc.char_combo.findData("Denji"))
        _mc.on_char_delete()
        check("deleting a character drops it from the main list",
              not _mc._is_main_char("Denji")
              and json.loads(_KR_APP._settings[("typer_kr", "mainChars")]) == {})

        # the Setup dialog edits a working copy and hands back the whole map
        _dlg = TK.MainCharsDialog(None, _mc._tr, {"Serie": {"Denji": {}, "aoi": {}},
                                                  "Andere": {"Bob": {}}},
                                  {"Andere": ["Bob"]}, "Serie")
        _dlg._boxes["aoi"].setChecked(True)
        check("the dialog stars a character of the selected manga",
              _dlg.result_map() == {"Andere": ["Bob"], "Serie": ["aoi"]})
        _dlg.manga_combo.setCurrentIndex(_dlg.manga_combo.findData("Andere"))
        check("switching manga rebuilds the list without losing the other one",
              sorted(_dlg._boxes) == ["Bob"] and _dlg._boxes["Bob"].isChecked()
              and _dlg.result_map()["Serie"] == ["aoi"])
        _dlg._clear()
        check("'none of them' clears only the manga on screen",
              _dlg.result_map() == {"Serie": ["aoi"]})
        _dlg.deleteLater()
        _mc.deleteLater()
        _mc2.deleteLater()
        _KR_APP._settings.pop(("typer_kr", "mainChars"), None)
    except Exception:                               # pragma: no cover
        check("main-character suite ran", False)
        import traceback
        traceback.print_exc()

# --- pattern generator (imgfx.make_pattern + the dialog) -------------------
if imported:
    try:
        from typer_kr import imgfx as _IMG

        def _opaque(im):
            return sum(1 for y in range(im.height()) for x in range(im.width())
                       if (im.pixel(x, y) >> 24) & 0xFF)

        for _k in _IMG.PATTERN_KINDS:
            _t = _IMG.make_pattern(_k, QColor(0, 0, 0), QColor(255, 255, 255),
                                   size=6, gap=6)
            check("make_pattern(%r) yields a non-empty tile" % _k,
                  _t is not None and not _t.isNull() and _opaque(_t) > 0)
        # a transparent background really leaves holes
        _dots = _IMG.make_pattern("dots", QColor(0, 0, 0), None, size=4, gap=12)
        _trans = sum(1 for y in range(_dots.height())
                     for x in range(_dots.width())
                     if ((_dots.pixel(x, y) >> 24) & 0xFF) == 0)
        check("transparent-bg pattern keeps transparent pixels", _trans > 0)
        # the common manga screentones are all offered (dots, line tones incl.
        # diagonal, cross-hatch, sand/noise grain, shoujo sparkle)
        check("manga screentones present (dots/diagonal/noise/sparkle/…)",
              set(("dots", "hstripes", "vstripes", "diagonal", "crosshatch",
                   "noise", "sparkle")).issubset(set(_IMG.PATTERN_KINDS)))
        # and each has a working screentone-gradient variant (dense -> sparse)
        for _gk in ("diagonal", "noise", "sparkle"):
            _gg = _IMG.make_pattern_gradient(_gk, QColor(0, 0, 0), None,
                                             5, 7, 0.0, 200, 80)

            def _side(_im, _x0, _x1):
                return sum(1 for _y in range(0, _im.height(), 3)
                           for _x in range(_x0, _x1, 3)
                           if (_im.pixel(_x, _y) >> 24) & 0xFF)
            check("%r gradient is denser at the dark tail than the head" % _gk,
                  not _gg.isNull() and _side(_gg, 0, 50) > _side(_gg, 150, 200))

        from typer_kr.patterngen import PatternGeneratorDialog
        _pg = PatternGeneratorDialog(None, lambda k: k)
        _pg.kind.setCurrentIndex(0)
        check("pattern-generator dialog builds and makes a tile",
              _pg._current_tile() is not None
              and not _pg._current_tile().isNull())
        # live preview: every change emits the current tile so the host can
        # apply it to the real text preview while the dialog is open
        _emits = {"n": 0, "last": None}
        _pg.previewChanged.connect(
            lambda t: _emits.update(n=_emits["n"] + 1, last=t))
        _pg.kind.setCurrentIndex(3)
        _pg.size.setValue(9)
        check("generator emits a live tile on every change",
              _emits["n"] >= 2 and _emits["last"] is not None
              and not _emits["last"].isNull())
        # 'Save to library' button emits the current tile
        _saved = {}
        _pg.saveRequested.connect(lambda t: _saved.update(t=t))
        _pg.save_btn.click()
        check("generator's Save button emits the current tile",
              _saved.get("t") is not None and not _saved["t"].isNull())
        # gradient (dark -> light) with a direction
        _grad = TK.IMG.make_gradient(QColor(0, 0, 0), QColor(255, 255, 255), 0, 48)
        check("make_gradient goes dark -> light across the tile",
              QColor(_grad.pixel(2, 24)).lightness()
              < QColor(_grad.pixel(45, 24)).lightness())
        _pg.gradient_chk.setChecked(True)
        check("generator gradient mode produces a tile",
              _pg.is_gradient() and _pg._current_tile() is not None
              and not _pg._current_tile().isNull())
        # screentone-density gradient: ink is dense at the tail, sparse at the
        # head (this is what lets the user recreate a manga tone fade)
        _kinds = [_pg.kind.itemData(_i) for _i in range(_pg.kind.count())]
        check("generator offers a 'smooth' gradient option next to the patterns",
              "smooth" in _kinds and "dots" in _kinds)
        _pg.kind.setCurrentIndex(_kinds.index("dots"))
        check("pattern kind stays live in gradient mode (it shapes the tone)",
              _pg.kind.isEnabled() and _pg.size.isEnabled())
        _spec = _pg.gradient_spec()
        check("gradient_spec exposes the params for re-rendering at size",
              _spec and _spec["kind"] == "dots" and "angle_deg" in _spec)
        _hg = TK.IMG.make_pattern_gradient("dots", QColor(0, 0, 0), None,
                                           6, 8, 0.0, 240, 80)

        def _ink(_x0, _x1):
            _n = 0
            for _y in range(0, _hg.height(), 3):
                for _x in range(_x0, _x1, 3):
                    if (_hg.pixel(_x, _y) >> 24) & 0xFF:
                        _n += 1
            return _n
        check("screentone gradient is denser at the dark tail than the light head",
              _ink(0, 60) > _ink(180, 240) * 1.5)
        _pg.gradient_chk.setChecked(False)

        # the live preview must render pattern/soft/fill without crashing
        _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
        _pd = TK.TyperDocker()
        # pattern fills + 'kind of text' are experimental and OFF by default
        check("pattern fills are experimental + off by default (controls hidden)",
              not _pd.enable_patterns_chk.isChecked()
              and _pd._style_pattern_box.isHidden()
              and _pd._fill_panel.isHidden()
              and not _pd._patterns_on())
        check("'kind of text' is experimental + off by default (panel hidden)",
              not _pd.enable_texttypes_chk.isChecked()
              and _pd._texttype_panel.isHidden())
        _pd.enable_patterns_chk.setChecked(True)   # opt in for the tests below
        check("enabling the experiment reveals the pattern controls",
              not _pd._style_pattern_box.isHidden()
              and not _pd._fill_panel.isHidden() and _pd._patterns_on())
        _pv = _pd.preview
        _pv.resize(220, 110)
        _pv.set_text("HELLO WORLD")

        def _pv_nonempty():
            _im = _pv.grab().toImage()
            return any((_im.pixel(x, y) >> 24) & 0xFF
                       for y in range(0, _im.height(), 5)
                       for x in range(0, _im.width(), 5))

        check("live preview paints normally", _pv_nonempty())
        _pd.outline_chk.setChecked(True)
        _pd._outline_pattern_img = _pat
        _pd.style_soft_chk.setChecked(True)
        _pd.style_soft_width_spin.setValue(3)
        _pd.style_soft_blur_spin.setValue(6)
        _pd._update_text_preview()
        check("live preview renders pattern outline + soft (no crash)",
              _pv_nonempty())

        # manual refresh button + NON-modal generator (so other style edits stay
        # live in the preview while the generator is open)
        check("live preview has a manual refresh button",
              hasattr(_pd, "preview_refresh_btn"))
        _pd.preview_refresh_btn.click()          # must not crash
        _pd._run_pattern_generator(QColor(0, 0, 0), "fill")
        _gdlg = _pd._patgen_dlg
        check("generator opens non-modally and live-applies to the fill",
              _gdlg is not None and not _gdlg.isModal()
              and _pd._fill_pattern_img is not None)
        _gdlg.size.setValue(13)                  # a change → live tile applied
        check("changing the generator keeps applying live",
              _pd._fill_pattern_img is not None)
        _gdlg.accept()
        check("accepting commits the pattern and closes the generator",
              _pd._patgen_dlg is None and bool(_pd._fill_pattern_path))
        # saved-pattern library: 'Saved…' buttons + persistence round-trip
        check("outline + fill rows have a 'Saved…' picker button",
              hasattr(_pd, "outline_pattern_saved_btn")
              and hasattr(_pd, "fill_pattern_saved_btn"))
        check("pattern library starts empty", _pd._load_pattern_library() == [])
        _tile = TK.IMG.make_pattern("dots", QColor(0, 0, 0), None, 5, 8)
        _ppath = _pd._save_generated_pattern(_tile)
        _pd._save_pattern_library([{"name": "My Dots", "path": _ppath}])
        check("a saved pattern persists and reloads",
              len(TK.TyperDocker()._load_pattern_library()) == 1)
        _KR_APP._settings.pop(("typer_kr", "patternLibrary"), None)
        try:
            os.remove(_ppath)
        except Exception:
            pass
        # fill a canvas SELECTION with a pattern (generator + fill-panel buttons)
        check("generator has a 'fill selection' button + signal",
              hasattr(_pg, "apply_sel_btn")
              and hasattr(_pg, "applyToSelectionRequested"))
        check("fill panel has a 'fill selection' button",
              hasattr(_pd, "fill_sel_btn"))
        _sdoc = _FakeDoc()
        _sdoc.sel = _FakeSelection(100, 50, 40, 20)
        _KR_APP._doc = _sdoc
        _pd._fill_selection_with_pattern(
            TK.IMG.make_pattern("checker", QColor(0, 0, 0), None, 6, 6))
        check("filling a selection makes a clipped paint layer at its position",
              _sdoc.last is not None and _sdoc.last.kind == "paintlayer"
              and _sdoc.last.pixels is not None
              and _sdoc.last.pixels[1] == 100 and _sdoc.last.pixels[2] == 50)
        # a gradient stretches across the selection (doesn't crash / tiles)
        _sdoc.last = None
        _pd._fill_selection_with_pattern(
            TK.IMG.make_gradient(QColor(0, 0, 0), QColor(255, 255, 255), 0, 48),
            stretch=True)
        check("a gradient fills the selection (stretched)",
              _sdoc.last is not None and _sdoc.last.kind == "paintlayer")
        # a screentone-gradient spec is re-rendered at the exact selection size
        # (round dots), with no source tile passed at all
        _sdoc.last = None
        _pd._fill_selection_with_pattern(
            None, True,
            {"kind": "dots", "fg": QColor(0, 0, 0), "bg": None,
             "size": 6, "gap": 8, "angle_deg": 0})
        check("a screentone-gradient spec fills the selection (re-rendered at size)",
              _sdoc.last is not None and _sdoc.last.kind == "paintlayer")
        # outline pattern can target the 1st / 2nd / both outlines
        check("outline pattern offers a 1st/2nd/both target",
              hasattr(_pd, "outline_pattern_target_combo")
              and _pd.outline_pattern_target_combo.count() == 3)
        _pd.deleteLater()
    except Exception:                               # pragma: no cover
        check("pattern-generator suite ran", False)
        import traceback
        traceback.print_exc()

# --- Font bundle: export favourites WITH font files, import + install ------
if imported:
    try:
        import zipfile as _zip
        import tempfile as _tf
        from typer_kr._qt import QFileDialog as _QFD, QMessageBox as _QMB
        from typer_kr.fontfav_ui import FontFavoritesPanel as _FP
        from typer_kr import fontfiles as _FFILES
        _QMB.information = staticmethod(lambda *a, **k: None)
        _QMB.warning = staticmethod(lambda *a, **k: None)
        _fdir = _tf.mkdtemp()
        _ff = os.path.join(_fdir, "MyFont.ttf")
        with open(_ff, "wb") as _fh:
            _fh.write(b"dummy-font")
        _b1 = {"v": ""}
        _pan = _FP(families_fn=lambda: ["Arial"], apply_fn=lambda f: None,
                   load_fn=lambda: _b1["v"],
                   save_fn=lambda t: _b1.__setitem__("v", t), tr=lambda k: k,
                   find_fonts_fn=lambda fams: ({"MyFont": _ff}
                                               if "MyFont" in fams else {}))
        _pan.add_favorite("MyFont", ["Dialog"])
        _zp = os.path.join(_fdir, "bundle.zip")
        _QFD.getSaveFileName = staticmethod(lambda *a, **k: (_zp, ""))
        _pan._export_favorites()
        _names = _zip.ZipFile(_zp).namelist()
        check("export bundles favourites.json + the actual font file",
              "favourites.json" in _names
              and any(n.startswith("fonts/") for n in _names))
        _inst = {"paths": None}
        _b2 = {"v": ""}
        _pan2 = _FP(
            families_fn=lambda: ["Arial"], apply_fn=lambda f: None,
            load_fn=lambda: _b2["v"], save_fn=lambda t: _b2.__setitem__("v", t),
            tr=lambda k: k,
            install_fonts_fn=lambda ps: (
                _inst.update(paths=[os.path.basename(x) for x in ps]),
                {"installed": [os.path.basename(x) for x in ps],
                 "skipped": [], "failed": []})[1])
        _QFD.getOpenFileName = staticmethod(lambda *a, **k: (_zp, ""))
        _pan2._import_favorites()
        check("import merges favourites AND installs the bundled font",
              _pan2._store.is_favorite("MyFont") and _inst["paths"] == ["MyFont.ttf"])
        # export bundles EVERY cut of a family, not just the file that matched
        _many = {"MyFont": [_ff, os.path.join(_fdir, "MyFont-Bold.ttf")]}
        with open(_many["MyFont"][1], "wb") as _fh:
            _fh.write(b"dummy-bold")
        _pan3 = _FP(families_fn=lambda: [], apply_fn=lambda f: None,
                    load_fn=lambda: _b1["v"], save_fn=lambda t: None,
                    tr=lambda k: k, find_fonts_fn=lambda fams: _many)
        _zp3 = os.path.join(_fdir, "bundle3.zip")
        _QFD.getSaveFileName = staticmethod(lambda *a, **k: (_zp3, ""))
        _pan3._export_favorites()
        _n3 = [n for n in _zip.ZipFile(_zp3).namelist() if n.startswith("fonts/")]
        check("export carries every cut of a family (regular + bold)",
              sorted(_n3) == ["fonts/MyFont-Bold.ttf", "fonts/MyFont.ttf"])
        # read-only: locating font files omits a font that isn't installed
        _fres = _FFILES.find_font_files(["Zzz Not A Real Font 9999"])
        check("find_font_files omits a font that isn't installed",
              isinstance(_fres, dict) and "Zzz Not A Real Font 9999" not in _fres)
    except Exception:                               # pragma: no cover
        check("font-bundle suite ran", False)
        import traceback
        traceback.print_exc()

# --- Font-file index: one family, all its files, tolerant spelling ----------
if imported:
    try:
        from typer_kr import fontfiles as _FI
        _decl = {
            r"C:\F\MyComicBB-Regular.otf": ({"My Comic BB"},
                                            {"My Comic BB Regular"}),
            r"C:\F\MyComicBB-Bold.otf": ({"My Comic BB"}, {"My Comic BB Bold"}),
            r"C:\F\MyComicBB-Ital.otf": ({"My Comic BB Italic"},
                                         {"My Comic BB Italic"}),
            r"C:\F\Unrelated.ttf": ({"Something Else"}, {"Something Else"}),
            r"C:\F\Vari.ttf": ({"Bahnschrift"}, {"Bahnschrift Regular"}),
        }
        _ix = _FI.FontFileIndex(list(_decl), names_fn=lambda p: _decl[p])
        _base = sorted(os.path.basename(p) for p in _ix.files_for("My Comic BB"))
        check("index returns every file of a family, cuts included",
              _base == ["MyComicBB-Bold.otf", "MyComicBB-Ital.otf",
                        "MyComicBB-Regular.otf"])
        check("index matches a squashed spelling",
              len(_ix.files_for("MyComicBB")) == 3)
        check("index matches a full name with the cut baked in",
              len(_ix.files_for("My Comic BB Regular")) == 3)
        check("index falls back to the base family of a named instance",
              [os.path.basename(p)
               for p in _ix.files_for("Bahnschrift SemiBold Condensed")]
              == ["Vari.ttf"])
        check("index reports nothing for a font it doesn't have",
              _ix.files_for("Zzz Nothing Here 9999") == [])
        check("a file that isn't a font parses to no names",
              _FI.font_file_names(os.path.join(_HERE, "run_tests.py"))
              == (set(), set()))
    except Exception:                               # pragma: no cover
        check("font-index suite ran", False)
        import traceback
        traceback.print_exc()

# --- Presets export as a self-installing bundle (presets + their fonts) -----
if imported:
    try:
        import zipfile as _z2
        import tempfile as _t2
        from typer_kr._qt import QFileDialog as _QFD2, QMessageBox as _QMB2
        from typer_kr import fontfiles as _FF2
        _QMB2.information = staticmethod(lambda *a, **k: None)
        _pdir = _t2.mkdtemp()
        _pfont = os.path.join(_pdir, "PresetFont.otf")
        with open(_pfont, "wb") as _fh:
            _fh.write(b"dummy-font")
        _orig_collect = _FF2.collect_font_files
        _FF2.collect_font_files = lambda fams, **kw: (
            {f: [_pfont] for f in fams if f == "PresetFont"},
            [f for f in fams if f != "PresetFont"])
        _pd2 = TK.TyperDocker()
        _pd2._groups = {"Manga": {"Bob": {"Dialog": {"font": "PresetFont",
                                                     "size": 12},
                                          "SFX": {"font": "Not Installed X"}}}}
        _pz = os.path.join(_pdir, "presets.zip")
        _pd2._export_presets_bundle(_pz)
        _pn = _z2.ZipFile(_pz).namelist()
        check("preset export writes presets.json + the fonts they name",
              "presets.json" in _pn and "fonts/PresetFont.otf" in _pn)
        check("preset export lists the fonts it could not bundle",
              _pd2.preset_font_names() == ["PresetFont", "Not Installed X"])
        # importing the bundle merges the presets AND installs the fonts
        _got = {"paths": None}
        _pd3 = TK.TyperDocker()
        _pd3._groups = {}
        _pd3._install_fonts_and_refresh = lambda ps: (
            _got.update(paths=[os.path.basename(p) for p in ps]),
            {"installed": [os.path.basename(p) for p in ps],
             "skipped": [], "failed": []})[1]
        _QFD2.getOpenFileName = staticmethod(lambda *a, **k: (_pz, ""))
        _pd3.on_preset_import()
        check("preset import restores the presets from a bundle",
              _pd3._groups.get("Manga", {}).get("Bob", {})
              .get("Dialog", {}).get("font") == "PresetFont")
        check("preset import installs the bundled fonts",
              _got["paths"] == ["PresetFont.otf"])
        # the SFX docker's own presets/rules export travels with its fonts too
        _sfxd = getattr(_pd2, "_sfx_docker", None)
        if _sfxd is not None:
            _sfxd._user_presets = [{"name": "Boom", "font": "PresetFont"}]
            _sfxd._font_rules = [{"keywords": ["bang"], "fonts": ["PresetFont"]}]
            check("SFX bundle collects the fonts of own presets + rules",
                  _sfxd._exported_fonts() == ["PresetFont"])
            _sz = os.path.join(_pdir, "sfx.zip")
            _sfxd._write_sfx_bundle(_sz, '{"manga_sfx": 1, "presets": [], '
                                         '"font_rules": []}')
            check("SFX bundle holds the json + the font files",
                  "manga_sfx_presets.json" in _z2.ZipFile(_sz).namelist()
                  and "fonts/PresetFont.otf" in _z2.ZipFile(_sz).namelist())
            _sdata, _sfonts = _sfxd._read_sfx_bundle(_sz)
            check("SFX bundle reads back its data and fonts",
                  _sdata.get("manga_sfx") == 1
                  and [os.path.basename(p) for p in _sfonts]
                  == ["PresetFont.otf"])
        _FF2.collect_font_files = _orig_collect
    except Exception:                               # pragma: no cover
        check("preset-bundle suite ran", False)
        import traceback
        traceback.print_exc()

# --- TextShapR: a PICKED shape never silently changes on a style change ----
if imported:
    try:
        _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
        _sd = TK.TyperDocker()
        _sw = _sd.shapr_widget
        _sd._current_text = (
            lambda: "make sure you plan out all of your summer homework tonight")
        _sd.insert_arrangement = lambda c, a, replace=None: True
        _KR_APP._doc = _FakeDoc(500, 700)
        _sd.font_picker.setCurrentFamily("Arial")
        _sw.refresh()
        if len(_sw._cards) >= 3:
            _sw._select(2, user=True)              # user pins card #3
            _pin = [TK.L.runs_text(r) for r in _sw._cands[_sw._sel]["lines"]]
            _sd.font_picker.setCurrentFamily("Times New Roman")
            _sw.restyle()
            check("a picked TextShapR shape survives a FONT change",
                  [TK.L.runs_text(r)
                   for r in _sw._cands[_sw._sel]["lines"]] == _pin)
            _sd.size_spin.setValue(max(10, _sd.size_spin.value() - 20))
            _sw.restyle()
            check("a picked TextShapR shape survives a SIZE change",
                  [TK.L.runs_text(r)
                   for r in _sw._cands[_sw._sel]["lines"]] == _pin)
            _sw._reshuffle()
            check("an explicit reshuffle (mode toggle) drops the pin",
                  _sw._custom is None)
        else:
            check("shaper produced cards for the lock test", False)
        _KR_APP._doc = None
        _sd.deleteLater()
    except Exception:                               # pragma: no cover
        check("shape-lock suite ran", False)
        import traceback
        traceback.print_exc()

# --- Preset export: readable + reusable Excel table ------------------------
if imported:
    try:
        import zipfile as _zf2
        import tempfile as _tf2
        from typer_kr import xlsx as _XL
        # ONE manga -> a MATRIX: characters as rows, purposes as columns
        _chars = {
            "Luffy": {"Shout": {"font": "CC Wild Words"},
                      "Talk": {"font": "Anime Ace"}},
            "Nami": {"Talk": {"font": "Manga Temple"}},
            "": {"Narrator": {"font": "Times"}},   # simple-mode bucket char
        }
        _hdr, _rows = TK.presets_to_table(_chars, lambda k: k,
                                          default_char="(default)")
        check("matrix: character is the first column",
              _hdr[0] == "col_character")
        check("matrix: purposes become columns (most-used first -> Talk)",
              _hdr[1] == "Talk"
              and set(_hdr[1:]) == {"Talk", "Shout", "Narrator"})
        check("matrix: one row per character", len(_rows) == 3)
        _luffy = next(r for r in _rows if r[0] == "Luffy")
        _ti, _si, _ni = (_hdr.index("Talk"), _hdr.index("Shout"),
                         _hdr.index("Narrator"))
        check("matrix: fonts land in the right character x purpose cell",
              _luffy[_ti] == "Anime Ace" and _luffy[_si] == "CC Wild Words"
              and _luffy[_ni] == "")
        check("matrix: blank character shows the default label",
              any(r[0] == "(default)" for r in _rows))
        # a legacy bare-string preset (font name only) must not crash it
        _h2, _r2 = TK.presets_to_table({"C": {"P": "SomeFont"}}, lambda k: k)
        check("matrix: tolerates a legacy bare-font preset",
              _h2 == ["col_character", "P"] and _r2 == [["C", "SomeFont"]])
        # write a real .xlsx and read it back (valid zip + data present)
        _p = os.path.join(_tf2.mkdtemp(), "presets.xlsx")
        _XL.write_xlsx(_p, "Manga", _hdr, _rows, widths=[16] * len(_hdr),
                       freeze_rows=1, freeze_cols=1)
        _z = _zf2.ZipFile(_p)
        check("xlsx export is a zip with the expected parts",
              "xl/worksheets/sheet1.xml" in _z.namelist()
              and "xl/styles.xml" in _z.namelist()
              and "[Content_Types].xml" in _z.namelist())
        _sheet = _z.read("xl/worksheets/sheet1.xml")
        check("xlsx export carries the fonts matrix data",
              b"Luffy" in _sheet and b"CC Wild Words" in _sheet
              and b"Talk" in _sheet)
        check("xlsx export freezes the header row AND character column",
              b'xSplit="1"' in _sheet and b'ySplit="1"' in _sheet
              and b'state="frozen"' in _sheet)
        # every part is well-formed XML
        import xml.etree.ElementTree as _ET
        _wf = True
        for _n in _z.namelist():
            try:
                _ET.fromstring(_z.read(_n))
            except Exception:
                _wf = False
        check("xlsx export: all parts are well-formed XML", _wf)
    except Exception:                               # pragma: no cover
        check("preset Excel export suite ran", False)
        import traceback
        traceback.print_exc()

# --- Picking lines the short way + a style of its own per line -------------
if imported:
    try:
        _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
        _KR_APP._settings.pop(("typer_kr", "tabOrder"), None)
        _KR_APP._settings[("typer_kr", "batchStyle")] = "false"
        _ld = TK.TyperDocker()
        _KR_APP._doc = _FakeDoc(800, 1200)
        _ld.editor.setPlainText("Alpha line\nBeta line\nGamma line")
        _ld.analyze()
        _ld._bp_boxes = [{"x": 10, "y": 10, "w": 200, "h": 120,
                          "kind": "bubble", "shape": "rect", "fill": 1.0}
                         for _ in range(3)]
        _ld._bp_assign = []
        _ld.bp_batch_page_chk.blockSignals(True)
        _ld.bp_batch_page_chk.setChecked(False)
        _ld.bp_batch_page_chk.blockSignals(False)
        _ld.on_bp_batch_assign()

        # --- selecting several rows at once
        _ld.bp_batch_table.selectAll()
        check("select all really selects every row",
              _ld._bp_batch_rows() == [0, 1, 2])
        _ld.bp_batch_table.clearSelection()
        _ld.bp_batch_table.selectRow(1)
        check("one selected row is the row that is acted on",
              _ld._bp_batch_rows() == [1])
        check("a single row also arms that bubble",
              _ld._bp_current == 1)

        # --- take the current line (and the ones after it)
        _ld._bp_assign = [-1, -1, -1]
        _ld._index = 1                        # 'Beta line' is current
        _ld.bp_batch_table.clearSelection()
        _ld.bp_batch_table.selectRow(0)
        _ld.on_bp_batch_take_line()
        check("take gives the selected bubble the current line",
              _ld._bp_assign == [1, -1, -1])
        _ld.bp_batch_table.selectAll()
        _ld._index = 0
        _ld.on_bp_batch_take_line()
        check("take fills a multi-row selection with consecutive lines",
              _ld._bp_assign == [0, 1, 2])

        # --- assign by clicking through the script
        _ld._bp_assign = [-1, -1, -1]
        _ld.bp_batch_table.clearSelection()
        _ld.bp_batch_table.selectRow(0)
        _ld.bp_batch_pick_btn.setChecked(True)
        _ld.table.selectRow(2)                # click 'Gamma line'
        check("clicking a line assigns it to the armed bubble",
              _ld._bp_assign[0] == 2)
        check("... and steps on to the next bubble",
              _ld.bp_batch_table.currentRow() == 1)
        _ld.table.selectRow(0)
        _ld.table.selectRow(1)
        check("clicking on down the script fills the following bubbles",
              _ld._bp_assign == [2, 0, 1])
        check("the mode switches itself off once every bubble has a line",
              not _ld.bp_batch_pick_btn.isChecked())

        # an SFX box is stepped over while clicking
        _ld._bp_boxes[1]["kind"] = "sfx"
        _ld._bp_assign = [-1, -1, -1]
        _ld._bp_batch_refresh()
        _ld.bp_batch_table.clearSelection()
        _ld.bp_batch_table.selectRow(0)
        _ld.bp_batch_pick_btn.setChecked(True)
        _ld.table.selectRow(0)
        check("click-assign skips an SFX box instead of feeding it a line",
              _ld.bp_batch_table.currentRow() == 2)
        _ld.bp_batch_pick_btn.setChecked(False)
        _ld._bp_boxes[1]["kind"] = "bubble"

        # --- the line filter
        _ld._bp_assign = [0, 1, 2]
        _ld._bp_batch_refresh()
        _full = _ld.bp_batch_table.cellWidget(0, 1).count()
        _ld.bp_batch_search.setText("gamma")
        _combo = _ld.bp_batch_table.cellWidget(1, 1)
        check("the filter narrows the line pickers",
              _combo.count() < _full)
        check("a row's OWN line survives the filter (nothing is lost)",
              _combo.findData(1) >= 0)
        _ld.bp_batch_search.setText("")

        # --- per-line style: hidden until switched on
        check("the style columns are hidden by default",
              _ld.bp_batch_table.isColumnHidden(3)
              and _ld.bp_batch_table.isColumnHidden(4))
        _ld.bp_batch_style_chk.setChecked(True)
        check("switching the setting on shows font and preset columns",
              not _ld.bp_batch_table.isColumnHidden(3)
              and not _ld.bp_batch_table.isColumnHidden(4))
        check("the setting is remembered",
              _KR_APP._settings.get(("typer_kr", "batchStyle")) == "true")

        # --- stamping the current style onto selected rows
        _ld.font_picker.setCurrentFamily("Arial")
        _ld.bp_batch_table.clearSelection()
        _ld.bp_batch_table.selectRow(0)
        _ld.bp_batch_table.selectRow(2)
        _ld.on_bp_batch_stamp_style()
        check("the stamped rows carry the font",
              _ld._bp_style[2].get("font") == "Arial")
        check("an untouched row keeps the global style",
              _ld._bp_style[1] == {})
        _ld.on_bp_batch_clear_style()
        check("clearing the style gives the row back to the global one",
              _ld._bp_style[2] == {})

        # --- a row style really reaches the docker, and is given back
        _ld._bp_style = [{}, {"font": "Times New Roman"}, {}]
        _ld.font_picker.setCurrentFamily("Arial")
        check("applying a row style switches the docker's font",
              _ld._bp_apply_row_style(1)
              and _ld.font_picker.currentFamily() == "Times New Roman")
        check("a row without a style leaves the font alone",
              not _ld._bp_apply_row_style(0)
              and _ld.font_picker.currentFamily() == "Times New Roman")

        _ld.font_picker.setCurrentFamily("Arial")
        _ld._bp_assign = [0, 1, 2]
        _ld._bp_run = {"pairs": TK.BB.batch_pairs(_ld._bp_assign, 3),
                       "at": 0, "done": 0, "skipped": 0, "units": [],
                       "review": False, "waiting": False, "back_to": 0,
                       "restyled": False,
                       "style": _ld._collect_settings(),
                       "font": _ld.font_picker.currentFamily()}
        for _ in range(8):
            if _ld._bp_run is None:
                break
            _ld._bp_batch_tick()
        check("after a run with per-line styles the font is back to normal",
              _ld.font_picker.currentFamily() == "Arial")
        _ld.deleteLater()
        _KR_APP._doc = None
        _KR_APP._settings.pop(("typer_kr", "batchStyle"), None)
    except Exception:                               # pragma: no cover
        check("line picking / per-line style suite ran", False)
        import traceback
        traceback.print_exc()

# --- The Batch tab: its own view and tools, independent of BubblR ----------
# The point of the separate tab is that marking bubbles and filling them must
# not require the detection tab. Both tabs are views of ONE box list, so what
# is checked here is that the two views stay in step.
if imported:
    try:
        _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
        _KR_APP._settings.pop(("typer_kr", "tabOrder"), None)
        _td = TK.TyperDocker()
        check("the Batch tab is present by default",
              _td._tab_index_of("batch") is not None)
        check("marking, page view and the run live on the Batch tab",
              _td._panel_tab.get("batch_mark") == "batch"
              and _td._panel_tab.get("batch_overlay") == "batch"
              and _td._panel_tab.get("bubblr_batch") == "batch")
        check("BubblR keeps its own detection panel and page view",
              _td._panel_tab.get("bubblr_detect") == "bubblr"
              and _td._panel_tab.get("bubblr_overlay") == "bubblr")
        check("there are two page views, not one widget in two places",
              len(_td._bp_overlays) == 2
              and _td.bp_overlay is not _td.batch_overlay)

        # both views show the same boxes
        _td._bp_boxes = [{"x": 10, "y": 10, "w": 100, "h": 80,
                          "kind": "bubble", "shape": "rect", "fill": 1.0}]
        _td._bp_refresh_overlay()
        check("a box marked once shows up in both views",
              len(_td.bp_overlay._boxes) == 1
              and len(_td.batch_overlay._boxes) == 1)

        # the click modes are one mode with two sets of buttons
        _td.batch_edit_btn.setChecked(True)
        check("switching a mode on in the Batch tab arms it in BubblR too",
              _td.bp_edit_btn.isChecked())
        check("the mode really reaches the page views",
              _td.bp_overlay._edit and _td.batch_overlay._edit)
        _td.bp_sfxmark_btn.setChecked(True)
        check("modes stay exclusive ACROSS the two tabs",
              not _td.batch_edit_btn.isChecked()
              and not _td.bp_edit_btn.isChecked()
              and _td.batch_sfxmark_btn.isChecked())
        check("leaving edit mode also switches it off in the views",
              not _td.bp_overlay._edit and not _td.batch_overlay._edit)
        _td.bp_sfxmark_btn.setChecked(False)

        # clearing throws the boxes away in both views
        _td.on_batch_clear_boxes()
        check("clearing removes the boxes from both views",
              _td._bp_boxes == []
              and not _td.bp_overlay._boxes and not _td.batch_overlay._boxes)
        _td.deleteLater()

        # ... and none of it needs the BubblR tab to be switched on
        _KR_APP._settings[("typer_kr", "enableBubblr")] = "false"
        _bt = TK.TyperDocker()
        check("with BubblR switched off the Batch tab is still there",
              _bt._tab_index_of("bubblr") is None
              and _bt._tab_index_of("batch") is not None)
        _bt._on_bp_box_added(20.0, 30.0, 120.0, 90.0)
        check("marking by hand works with BubblR off",
              len(_bt._bp_boxes) == 1 and _bt._bp_boxes[0]["x"] == 20)
        _bt.editor.setPlainText("Only line")
        _bt.analyze()
        _bt.on_bp_batch_assign()
        check("pairing works with BubblR off",
              _bt._bp_assign == [0])
        _bt.deleteLater()
        _KR_APP._settings.pop(("typer_kr", "enableBubblr"), None)
    except Exception:                               # pragma: no cover
        check("Batch tab suite ran", False)
        import traceback
        traceback.print_exc()

# --- Batch placement: pair lines with bubbles, then fill them in one run ---
# The whole point of the batch is that it drives the NORMAL insert path once
# per bubble, so these tests check the wiring rather than the layout: does each
# bubble become the selection, does each line land on its own numbered layer,
# and does "undo batch" take back exactly those layers.
if imported:
    try:
        _KR_APP._settings[("typer_kr", "tabOrderRepairV2")] = "done"
        _bd = TK.TyperDocker()
        _bdoc = _FakeDoc(800, 1200)
        _KR_APP._doc = _bdoc
        _bd.editor.setPlainText("Page 1\nHello there\nSecond line\n"
                                "Page 2\nOn the next page")
        _bd.analyze()
        check("script parsed into units across two pages",
              len(_bd._pairs) == 3 and len(_bd._pages) == 2)

        _bd._bp_boxes = [{"x": 60, "y": 80, "w": 220, "h": 150,
                          "kind": "bubble", "shape": "rect", "fill": 1.0},
                         {"x": 380, "y": 300, "w": 240, "h": 160,
                          "kind": "bubble", "shape": "round", "fill": 0.78}]
        _bd._bp_assign = []
        _bd.bp_batch_page_chk.setChecked(True)
        _bd.on_bp_batch_assign()
        check("page 1's two lines pair with the two bubbles",
              _bd._bp_assign == [0, 1])
        check("the table shows one row per bubble",
              _bd.bp_batch_table.rowCount() == 2)
        check("the text column previews the paired line",
              _bd.bp_batch_table.item(0, 2).text() == "Hello there")

        # an SFX box must not consume a line
        _bd._bp_boxes.insert(1, {"x": 300, "y": 100, "w": 90, "h": 60,
                                 "kind": "sfx", "shape": "rect", "fill": 1.0})
        _bd._bp_assign = []
        _bd.on_bp_batch_assign()
        check("an SFX box is passed over, the next bubble keeps its line",
              _bd._bp_assign == [0, -1, 1])
        del _bd._bp_boxes[1]
        _bd._bp_assign = []
        _bd.on_bp_batch_assign()

        # a gap fixes an off-by-one after a false detection
        _bd._bp_assign = TK.BB.insert_gap(_bd._bp_assign, 0)
        check("inserting a gap moves the lines down one bubble",
              _bd._bp_assign == [-1, 0])
        _bd._bp_assign = TK.BB.remove_gap(_bd._bp_assign, 0, len(_bd._pairs))
        check("removing it again restores the pairing",
              _bd._bp_assign == [0, 1])

        # selecting a box really goes through Krita's selection
        check("a bubble box becomes the document selection",
              _bd._select_box(_bd._bp_boxes[0])
              and _bdoc.sel.x() == 60 and _bdoc.sel.width() == 220)
        check("a round bubble gets an elliptical selection, not a rectangle",
              _bd._select_box(_bd._bp_boxes[1])
              and _bdoc.sel.pixelData(0, 0, 240, 160).count(0) > 0)

        # the run itself: no dialog in review mode, so drive that one
        _bd.font_picker.setCurrentFamily("Arial")
        _bd.bp_batch_review_chk.setChecked(False)
        _placed = []
        _real_insert = _bd.insert_arrangement

        def _spy(cand, advance, replace=None):
            _placed.append((_bd._index, cand["px"]))
            return _real_insert(cand, advance, replace)

        _bd.insert_arrangement = _spy
        _bd._bp_run = {"pairs": TK.BB.batch_pairs(_bd._bp_assign,
                                                  len(_bd._pairs)),
                       "at": 0, "done": 0, "skipped": 0, "units": [],
                       "review": False, "waiting": False, "back_to": 0}
        # run the chain synchronously: tick until the run is over
        for _ in range(10):
            if _bd._bp_run is None:
                break
            _bd._bp_batch_tick()
        check("every paired bubble was filled once",
              len(_placed) == 2)
        check("each line was placed under its own unit index",
              [u for u, _px in _placed] == [0, 1])
        check("both lines are marked done",
              _bd._done == {0, 1})
        check("both bubbles are marked placed",
              _bd._bp_placed == {0, 1})
        _bd.insert_arrangement = _real_insert

        # 'this page only' really limits the range
        _bd._index = 2                       # a unit on page 2
        _bd._bp_assign = []
        _bd.on_bp_batch_assign()
        check("on page 2 the batch only offers that page's single line",
              _bd._bp_assign == [2, -1])
        _bd.bp_batch_page_chk.blockSignals(True)
        _bd.bp_batch_page_chk.setChecked(False)
        _bd.bp_batch_page_chk.blockSignals(False)
        _bd._bp_assign = []
        _bd.on_bp_batch_assign()
        check("switched off, it draws from the whole script",
              _bd._bp_assign == [0, 1])

        # undo removes exactly the layers of the last run
        _bd._bp_last_units = [0, 1]
        _bd._done = {0, 1}
        _removed = []
        _real_remove = TK._remove_existing_layers
        TK._remove_existing_layers = (
            lambda doc, idx, box=None: (_removed.append(idx) or 1))
        try:
            _bd.on_bp_batch_undo()
        finally:
            TK._remove_existing_layers = _real_remove
        check("undo batch removes the layer of every unit it wrote",
              _removed == [1, 2])          # layer numbers are 1-based
        check("undo batch clears the done marks it set",
              _bd._done == set())
        check("undo batch cannot run twice",
              _bd._bp_last_units == []
              and not _bd.bp_batch_undo_btn.isEnabled())

        # review mode: the run parks on each bubble and is continued by the
        # normal insert path, not by a button of its own
        _bd._done = set()
        _bd._bp_placed = set()
        _bd._bp_assign = [0, 1]
        _bd._bp_run = {"pairs": TK.BB.batch_pairs(_bd._bp_assign,
                                                  len(_bd._pairs)),
                       "at": 0, "done": 0, "skipped": 0, "units": [],
                       "review": True, "waiting": False, "back_to": 0}
        _bd._bp_batch_tick()
        check("review mode parks on the first bubble instead of placing it",
              _bd._bp_run is not None and _bd._bp_run["waiting"]
              and _bd._bp_run["done"] == 0)
        check("review mode arms the bubble it is waiting on",
              _bd._bp_current == 0 and _bd._index == 0)
        check("review mode has the shape cards ready to pick from",
              len(_bd.shapr_widget._cands) > 0)
        # applying a shape through the normal path books it and moves on
        _bd.insert_arrangement(_bd.shapr_widget._cands[0], False, replace=True)
        check("applying a shape continues the run to the next bubble",
              _bd._bp_run is not None and _bd._bp_run["done"] == 1
              and _bd._bp_run["units"] == [0])
        # Stop leaves what is placed on the page
        _bd.on_bp_batch_stop()
        check("stopping ends the run and keeps what was placed",
              _bd._bp_run is None and _bd._bp_last_units == [0])

        # nothing paired -> the run refuses to start
        _bd._bp_assign = [-1, -1]
        _bd._bp_run = None
        _bd.on_bp_batch_start()
        check("with nothing paired the batch does not start",
              _bd._bp_run is None)
        _bd.deleteLater()
        _KR_APP._doc = None
    except Exception:                               # pragma: no cover
        check("batch placement suite ran", False)
        import traceback
        traceback.print_exc()

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
