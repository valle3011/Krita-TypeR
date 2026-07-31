# -*- coding: utf-8 -*-
"""Integration tests for the Krita-bound module (typer_kr/typer_kr.py).

A fake `krita` module + an offscreen Qt app let the real code run headless:
the insert path is exercised end to end and the SVG it hands to Krita is
captured and inspected; the font picker and the Excel importer are tested too.

Run:  python test_integration.py     (PyQt5 required; no real Krita needed)
"""
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
try:
    from PyQt5.QtWidgets import QApplication, QWidget, QDockWidget
    from PyQt5.QtGui import QColor
    _app = QApplication.instance() or QApplication([])
except Exception as e:                          # pragma: no cover
    print("PyQt5 unavailable, skipping integration tests:", e)
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
_krita.Selection = type("Selection", (object,), {})
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
from PyQt5.QtGui import QImage as _QImage


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


_pat = _QImage(8, 8, _QImage.Format_ARGB32)
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
from PyQt5.QtWidgets import QTabBar


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
    from PyQt5.QtGui import QColor as _QC
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
        check("absent id ignored + unlisted Fonts tab appended at the end",
              _got == ["type", "style", "setup", "shapr", "sfx", "fonts"])
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
        from PyQt5.QtWidgets import QFileDialog as _QFD, QMessageBox as _QMB
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
        # read-only: locating font files omits a font that isn't installed
        _fres = _FFILES.find_font_files(["Zzz Not A Real Font 9999"])
        check("find_font_files omits a font that isn't installed",
              isinstance(_fres, dict) and "Zzz Not A Real Font 9999" not in _fres)
    except Exception:                               # pragma: no cover
        check("font-bundle suite ran", False)
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

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
