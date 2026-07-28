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
    def __init__(self):
        self.svg = None

    def addShapesFromSvg(self, svg):
        self.svg = svg
        return True

    def addChildNode(self, node, above):
        return True


class _FakeDoc:
    def __init__(self, w=800, h=600):
        self._w, self._h = w, h
        self.last = None

    def width(self):
        return self._w

    def height(self):
        return self._h

    def selection(self):
        return None

    def rootNode(self):
        return _FakeNode()

    def createVectorLayer(self, label):
        n = _FakeNode()
        self.last = n
        return n

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
            _d.deleteLater()
        _KR_APP._settings.pop(("typer_kr", "tabOrder"), None)
    except Exception as _to_e:                      # pragma: no cover
        check("main-tab order regression ran", False)
        import traceback
        traceback.print_exc()

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
