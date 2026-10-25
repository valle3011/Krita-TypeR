# -*- coding: utf-8 -*-
"""Tests for the Giongo tab: sound rules, layout, rendering, the panel.

The rules and the layout (typer_kr/giongo.py) need nothing; rendering and the
panel need Qt (PyQt6 or PyQt5) and are skipped cleanly without it. Krita is
faked, so inserting is exercised end to end against a stand-in document.

Run:  python test_giongo.py
"""
import io
import math
import os
import random
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  ok   " + name)
    else:
        _fail += 1
        print("  FAIL " + name)


# the package __init__ registers with Krita; load the modules without it
_pkg = types.ModuleType("typer_kr")
_pkg.__path__ = [os.path.join(_HERE, "typer_kr")]
sys.modules.setdefault("typer_kr", _pkg)

from typer_kr import giongo as G      # noqa: E402

print("== rules ==")
check("voiced + ン + ！ is an impact", G.omakase("ドーーン！")[0] == "impact")
check("a voiced unit said over and over rumbles",
      G.omakase("ゴゴゴゴ")[0] == "rumble")
check("ドドドド rumbles", G.omakase("ドドドド")[0] == "rumble")
check("a clipped sweep is a slash", G.omakase("シュッ")[0] == "slash")
check("soft kana are cute", G.omakase("ふわふわ")[0] == "cute")
check("ポタッ drips", G.omakase("ポタッ")[0] == "drops")
check("ジー glares", G.omakase("ジー")[0] == "glare")
check("ピピピッ is a machine", G.omakase("ピピピッ")[0] == "machine")
check("a drawn-out vowel is a shriek, not a rumble",
      G.omakase("きゃぁぁぁぁ")[0] == "pop")
check("BOOM! hits", G.omakase("BOOM!")[0] == "impact")
check("whoosh is a slash", G.omakase("whoosh")[0] == "slash")
check("auto gives two runners-up", len(G.omakase("ドン")[1]) == 2)
check("empty text still answers", G.omakase("")[0] in G.TYPE_IDS)
check("dakuten detected", G.has_dakuten("ド") and G.has_dakuten("パ")
      and not G.has_dakuten("ト"))
check("classify ranks every type once",
      sorted(t for t, _s in G.classify("ドン")) == sorted(G.TYPE_IDS))

print("== tokens ==")
toks = G.tokenize("ドーーン！")
check("one line", len(toks) == 1)
check("ーー merged into one bar of 2", [t["bar"] for t in toks[0]] ==
      [0, 2, 0, 0])
check("merge off keeps every ー",
      len(G.tokenize("ドーーン", merge_bars=False)[0]) == 4)
check("line breaks make groups", len(G.tokenize("ドン\nガン\n\n")) == 2)
check("trailing spaces dropped", G.tokenize("ドン  ")[0][-1]["ch"] == "ン")

print("== parameters ==")
p = G.sanitize({"spacing": 9999, "lean": "x", "fill": "red",
                "outlines": [["#fff", 3], ["#ffffff", -1], ["#000000", 2],
                             ["#111111", 1], ["#222222", 1]],
                "type": "nope", "bogus": 1, "vertical": 1})
check("numbers clamped", p["spacing"] == G.RANGES["spacing"][1])
check("garbage number keeps the default", p["lean"] == G.DEFAULTS["lean"])
check("bad colour keeps the default", p["fill"] == G.DEFAULTS["fill"])
check("bad outlines dropped, at most three kept",
      p["outlines"] == [["#000000", 2.0], ["#111111", 1.0],
                        ["#222222", 1.0]])
check("unknown type falls back", p["type"] == G.DEFAULTS["type"])
check("unknown key dropped", "bogus" not in p)
check("bool coerced", p["vertical"] is True)
check("sanitize(None) is the defaults", G.sanitize(None) == G.DEFAULTS)
check("json round trip", G.from_json(G.to_json(G.default_params("cute")))
      == G.sanitize(G.default_params("cute")))
check("broken json is the defaults", G.from_json("{nope") == G.DEFAULTS)
check("NaN rejected", G.sanitize({"bend": float("nan")})["bend"] ==
      G.DEFAULTS["bend"])
for tid in G.TYPE_IDS:
    dp = G.default_params(tid)
    check("type %s is already clean" % tid, G.sanitize(dp) == dp)
q = dict(G.default_params("impact"), letter_px=77, seed=5, power=40,
         font="X")
r = G.apply_type(q, "cute")
check("switching type keeps size, seed and macros",
      (r["letter_px"], r["seed"], r["power"]) == (77, 5, 40))
check("switching type brings its look", r["bounce"] ==
      G.default_params("cute")["bounce"])

print("== macros ==")
base = G.default_params("impact")
check("0 on every macro changes nothing",
      G.effective(base) == G.sanitize(base))
hi = G.effective(dict(base, power=100))
check("power thickens", hi["thicken"] > base["thicken"])
check("power widens outlines", hi["outlines"][0][1] > base["outlines"][0][1])
lo = G.effective(dict(base, power=-100))
check("negative power thins", lo["thicken"] < base["thicken"])
check("roughness wobbles more",
      G.effective(dict(base, rough=100))["jitter"] > base["jitter"])
check("momentum leans more",
      G.effective(dict(base, momentum=100))["lean"] > base["lean"])
check("macros stay in range", all(
    G.RANGES[k][0] <= G.effective(dict(base, power=100, rough=100,
                                       momentum=100))[k] <= G.RANGES[k][1]
    for k in ("thicken", "jitter", "rot_var", "lean", "slant", "size_end")))

print("== layout ==")
flat = dict(G.DEFAULTS, letter_px=100, outlines=[])
pl = G.layout("ドドド", flat)
check("one placement per letter", len(pl) == 3)
xs = sorted(x["x"] for x in pl)
check("flat horizontal: letters one em apart",
      all(abs((b - a) - 100) < 0.5 for a, b in zip(xs, xs[1:])))
check("flat horizontal: on one line", len({round(x["y"], 3) for x in pl}) == 1)
check("flat: upright", all(abs(x["angle"]) < 1e-9 for x in pl))
v = G.layout("ドドド", dict(flat, vertical=True))
ys = sorted(x["y"] for x in v)
check("vertical runs down", ys[-1] - ys[0] > 150 and
      len({round(x["x"], 3) for x in v}) == 1)
up = G.layout("ドドド", dict(flat, rise=30))
first, last = min(up, key=lambda x: x["index"]), max(up, key=lambda x:
                                                       x["index"])
check("rise climbs to the right", last["y"] < first["y"] and
      last["x"] > first["x"])
bent = G.layout("ドドドドド", dict(flat, bend=40))
mid = [x for x in bent if x["index"] == 2][0]
ends = [x for x in bent if x["index"] in (0, 4)]
check("bend pushes the middle sideways",
      abs(mid["y"] - sum(e["y"] for e in ends) / 2) > 30)
gaps = []
bs = sorted(bent, key=lambda x: x["index"])
for a, b in zip(bs, bs[1:]):
    gaps.append(math.hypot(b["x"] - a["x"], b["y"] - a["y"]))
check("bending keeps the letters about an em apart",
      all(80 < g_ <= 101 for g_ in gaps))
lean = G.layout("ドドドドド", dict(flat, bend=40, lean=100))
check("lean 100 follows the path",
      abs(sorted(lean, key=lambda x: x["index"])[0]["angle"]) > 10)
grow = G.layout("ドドドド", dict(flat, size_start=50, size_end=150))
by_i = sorted(grow, key=lambda x: x["index"])
check("size runs from start to end", abs(by_i[0]["size"] - 50) < 0.01 and
      abs(by_i[-1]["size"] - 150) < 0.01)
check("bigger letters are drawn later (nearer)",
      [x["index"] for x in grow] == [0, 1, 2, 3])
shrink = G.layout("ドドドド", dict(flat, size_start=150, size_end=50))
check("shrinking: the first letter is the nearest",
      [x["index"] for x in shrink] == [3, 2, 1, 0])
bars = G.layout("ドーーン", flat)
bar = [x for x in bars if x["bar"]][0]
check("a merged ーー is one stroke two units long",
      len(bars) == 3 and bar["bar"] == 2 and bar["length"] > 150)
a1 = G.layout("ドドドド", dict(flat, jitter=60, rot_var=20, seed=7))
a2 = G.layout("ドドドド", dict(flat, jitter=60, rot_var=20, seed=7))
a3 = G.layout("ドドドド", dict(flat, jitter=60, rot_var=20, seed=8))
check("same seed, same shape", a1 == a2)
check("new seed, new shape", a1 != a3)
two = G.layout("ドン\nガン", flat)
check("second line sits below", min(x["y"] for x in two if x["group"] == 1)
      > max(x["y"] for x in two if x["group"] == 0))
check("empty text lays out nothing", G.layout("", flat) == [])
check("spaces take room but draw nothing",
      len(G.layout("ド ン", flat)) == 2)

print("== gacha / mutate ==")
rng = random.Random(3)
seen = set()
for _ in range(60):
    gp = G.gacha("ドーーン！", base, rng)
    seen.add(gp["type"])
    assert G.sanitize(gp) == gp
check("gacha results are clean parameter sets", True)
check("gacha favours the suggested types but mixes others", "impact" in seen
      and len(seen) >= 4)
m = G.mutate(base, random.Random(1))
check("mutate keeps type and colours", m["type"] == base["type"] and
      m["fill"] == base["fill"] and m["outlines"] == G.sanitize(base)
      ["outlines"])
check("mutate changes something", m != G.sanitize(base))
rr = G.reroll(base, random.Random(2))
check("reroll only moves the seed",
      dict(rr, seed=0) == dict(G.sanitize(base), seed=0)
      and rr["seed"] != base["seed"])
check("font resolves to the chosen family",
      G.resolve_font(dict(base, font="A"), ["A", "Dela Gothic One"]) == "A")
check("font falls back to the type's suggestion",
      G.resolve_font(dict(base, font="Gone"), ["Reggae One",
                                               "Bowlby One"]) == "Bowlby One")
check("no suggestion installed → default sans",
      G.resolve_font(base, ["Arial"]) == "")

# --- Qt half ---------------------------------------------------------------
try:
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QColor
    except ImportError:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QColor
    _app = QApplication.instance() or QApplication([])
except Exception as e:                  # pragma: no cover
    print("Qt unavailable, skipping render/panel tests:", e)
    print("\npassed %d, failed %d" % (_pass, _fail))
    sys.exit(1 if _fail else 0)

from typer_kr import giongo_render as R   # noqa: E402

print("== render ==")
sc = R.build_scene("ドーーン！", base)
check("scene has layers and bounds", not sc.is_empty())
kinds = [l.kind for l in sc.layers]
check("each letter: outline then fill",
      kinds.count("fill") == 4 and kinds.count("outline") == 4 and
      kinds[-1] == "fill")
merged = R.build_scene("ドン", dict(base, outline_mode="merged"))
mk = [l.kind for l in merged.layers]
check("merged: all outlines before any fill",
      mk.index("fill") > max(i for i, k in enumerate(mk) if k == "outline"))
three = R.build_scene("ド", dict(base, outlines=[["#000000", 2],
                                               ["#ffffff", 3],
                                               ["#ff0000", 4]]))
widths = [l.path.boundingRect().width() for l in three.layers
          if l.kind == "outline"]
check("outlines drawn outer → inner", widths == sorted(widths, reverse=True)
      and len(widths) == 3)
check("outline colours outer → inner",
      [l.color for l in three.layers if l.kind == "outline"] ==
      ["#ff0000", "#ffffff", "#000000"])
sh = R.build_scene("ドン", dict(base, shadow_dx=5, shadow_dy=5, extrude=4))
check("extrusion: four shadow steps per letter",
      sum(1 for l in sh.layers if l.kind == "shadow") == 8)
check("shadow drawn first", sh.layers[0].kind == "shadow")
af = R.build_scene("ドン", dict(base, afterimage=2, shake=1))
check("afterimages and shake present",
      any(l.kind == "after" for l in af.layers) and
      any(l.kind == "shake" and l.line_w > 0 for l in af.layers))
big = R.build_scene("ドン", dict(base, letter_px=400))
small = R.build_scene("ドン", dict(base, letter_px=100))
ratio = big.bounds.width() / small.bounds.width()
check("doubling the letter size scales the drawing (×4)",
      3.8 < ratio < 4.2)
img, tl = R.render_image(sc)
check("image holds the drawing", img.width() >= sc.bounds.width() and
      img.height() >= sc.bounds.height())
opaque = sum(1 for y in range(0, img.height(), 4)
             for x in range(0, img.width(), 4)
             if QColor.fromRgba(img.pixel(x, y)).alpha() > 0)
check("something was painted", opaque > 50)
for mode in ("gradient", "tone"):
    sm = R.build_scene("ドン", dict(base, fill_mode=mode))
    im, _ = R.render_image(sm)
    check("%s fill renders" % mode, not im.isNull())
check("halftone needs a raster insert",
      R.build_scene("ドン", dict(base, fill_mode="tone")).needs_raster()
      and not sc.needs_raster())
th = R.render_thumb(sc, 150, 84)
check("thumbnail has the asked size", (th.width(), th.height()) == (150, 84))
check("empty text → empty scene", R.build_scene("", base).is_empty())
check("empty scene thumbnail does not crash",
      R.render_thumb(R.build_scene("  ", base), 40, 30).width() == 40)

print("== svg ==")
svg = R.to_svg(sc)
root = ET.fromstring(svg)
paths = [e for e in root.iter() if e.tag.endswith("path")]
check("svg parses, one path per layer", len(paths) == len(sc.layers))
check("path data uses absolute commands only",
      all(set(c for c in e.get("d") if c.isalpha()) <= set("MLCZ")
          for e in paths))
check("standalone svg framed to the drawing",
      abs(float(root.get("width")) - (sc.bounds.width() + 8)) < 2)
from typer_kr._qt import QTransform      # noqa: E402
page = R.to_svg(sc, QTransform.fromTranslate(500, 400), 1000, 800)
proot = ET.fromstring(page)
check("page svg has the canvas size", (proot.get("width"),
                                       proot.get("height")) == ("1000", "800"))
check("page svg has no viewBox (Krita reads pixels)",
      proot.get("viewBox") is None)
gsvg = R.to_svg(R.build_scene("ドン", dict(base, fill_mode="gradient")))
check("gradient defined once and used",
      gsvg.count("<linearGradient") == 1 and "url(#giongoGrad)" in gsvg)
tsvg = R.to_svg(R.build_scene("ドン", dict(base, fill_mode="tone")))
check("halftone as a pattern in the file", "url(#giongoTone)" in tsvg)
asvg = R.to_svg(af)
check("faint layers carry opacity", 'opacity="' in asvg)
check("shake drawn as lines", 'fill="none" stroke=' in asvg)
check("text is escaped (no raw glyph text in the svg)",
      "<text" not in svg)
q = R.path_d(R._bar_path(100, 50))
check("path_d closes subpaths", q.startswith("M") and q.endswith("Z"))

print("== panel ==")


class _Sel(object):
    def __init__(self, x, y, w, h):
        self._r = (x, y, w, h)

    def x(self):
        return self._r[0]

    def y(self):
        return self._r[1]

    def width(self):
        return self._r[2]

    def height(self):
        return self._r[3]


class _Node(object):
    def __init__(self, name, kind):
        self.name, self.kind = name, kind
        self.svg = None
        self.pixels = None
        self._kids = []

    def addShapesFromSvg(self, svg):      # noqa: N802 (Krita API)
        self.svg = svg
        return True

    def setPixelData(self, data, x, y, w, h):   # noqa: N802
        self.pixels = (len(data), x, y, w, h)

    def childNodes(self):                 # noqa: N802
        return list(self._kids)

    def addChildNode(self, node, above):  # noqa: N802
        self._kids.append(node)
        return True


class _Doc(object):
    def __init__(self, w=1200, h=900, sel=None):
        self._w, self._h, self._sel = w, h, sel
        self.root = _Node("root", "group")
        self.active = None
        self.refreshed = 0

    def width(self):
        return self._w

    def height(self):
        return self._h

    def selection(self):
        return self._sel

    def rootNode(self):                   # noqa: N802
        return self.root

    def createVectorLayer(self, name):    # noqa: N802
        return _Node(name, "vectorlayer")

    def createNode(self, name, kind):     # noqa: N802
        return _Node(name, kind)

    def setActiveNode(self, n):           # noqa: N802
        self.active = n

    def refreshProjection(self):          # noqa: N802
        self.refreshed += 1


class _Krita(object):
    doc = None

    @classmethod
    def instance(cls):
        return cls

    @classmethod
    def activeDocument(cls):              # noqa: N802
        return cls.doc


_krita = types.ModuleType("krita")
_krita.Krita = _Krita
sys.modules["krita"] = _krita

from typer_kr.giongo_ui import GiongoPanel, STRINGS   # noqa: E402

check("German has every English string",
      set(STRINGS["de"]) == set(STRINGS["en"]))
store = {}
lang = ["en"]
panel = GiongoPanel(lang_fn=lambda: lang[0],
                    get_setting=lambda k, d="": store.get(k, d),
                    set_setting=lambda k, v: store.__setitem__(k, v),
                    families_fn=lambda: ["IPAGothic", "DejaVu Sans"])
panel.resize(360, 900)
panel._rng = random.Random(11)
panel.text_edit.setPlainText("ゴゴゴゴ")
panel.on_auto()
check("auto switches the type", panel.params()["type"] == "rumble")
check("auto says what it chose", "“" in panel.status_lbl.text())
panel.on_back()
check("back undoes auto", panel.params()["type"] == "impact")
panel.on_gacha()
check("gacha shows a sheet of options",
      panel.options_box.isVisibleTo(panel) and len(panel._options) == 6 and
      not panel._option_btns[0].icon().isNull())
chosen = panel._options[3]
panel.on_pick(3)
check("picking an option adopts it", panel.params() == G.sanitize(chosen))
panel.on_mutate()
check("mutate fills the sheet", len(panel._options) == 6)
seed = panel.params()["seed"]
panel.on_reroll()
check("other shape moves the seed", panel.params()["seed"] != seed)
check("seed box follows", panel.seed_spin.value() == panel.params()["seed"])
panel._sliders["lean"][0].setValue(77)
check("a slider writes its parameter", panel.params()["lean"] == 77)
panel._sliders["thicken"][0].setValue(10)
check("a float slider scales its steps", panel.params()["thicken"] == 2.5)
panel._outline_rows[0][0].setChecked(False)
check("switching outline 1 off clears all outlines",
      panel.params()["outlines"] == [])
panel._outline_rows[0][0].setChecked(True)
ticked = 0
for _chk, _b, _s in panel._outline_rows:
    if not _chk.isChecked():
        break
    ticked += 1
check("and back on restores the ticked rows",
      ticked >= 1 and len(panel.params()["outlines"]) == ticked)
panel.type_combo.setCurrentIndex(panel.type_combo.findData("cute"))
check("type combo applies the type", panel.params()["type"] == "cute"
      and panel.params()["bounce"] == G.default_params("cute")["bounce"])
check("the widgets follow", panel._sliders["bounce"][0].value() ==
      G.default_params("cute")["bounce"])
panel._save_state()
check("settings are remembered", "giongoParams" in store and
      G.from_json(store["giongoParams"])["type"] == "cute" and
      store.get("giongoText") == "ゴゴゴゴ")
panel2 = GiongoPanel(lang_fn=lambda: "en",
                     get_setting=lambda k, d="": store.get(k, d),
                     set_setting=lambda k, v: None,
                     families_fn=lambda: [])
check("a new panel starts where the last one stopped",
      panel2.params() == G.from_json(store["giongoParams"]) and
      panel2.text() == "ゴゴゴゴ")
check("missing type fonts are pointed out",
      panel2.font_hint.isVisibleTo(panel2) and
      "Mochiy Pop One" in panel2.font_hint.text())
lang[0] = "de"
panel.retranslate()
check("German labels", panel.insert_vec_btn.text() == "Einfügen (Vektor)")
check("an & in a section title is shown, not eaten as a shortcut",
      panel.sec_fill.btn.text() == "Füllung && Konturen")
lang[0] = "en"
panel.retranslate()

# inserting
_Krita.doc = None
check("no document → no insert", panel.insert() is None and
      "document" in panel.status_lbl.text())
doc = _Doc()
_Krita.doc = doc
node = panel.insert(raster=False)
check("vector insert makes a vector layer with the shapes",
      node is not None and node.kind == "vectorlayer" and
      node in doc.root._kids and "<path" in node.svg and doc.refreshed == 1)
sroot = ET.fromstring(node.svg)
check("the svg has the canvas size",
      (sroot.get("width"), sroot.get("height")) == ("1200", "900"))
# where did it land? the fill shapes should be centred on the canvas
sc_now = panel.scene()
tr, k = panel.placement(sc_now, 1200, 900)
c = tr.mapRect(sc_now.bounds).center()
check("no selection: centred on the canvas",
      abs(c.x() - 600) < 1 and abs(c.y() - 450) < 1 and k == 1.0)
doc._sel = _Sel(100, 100, 300, 200)
tr, k = panel.placement(sc_now, 1200, 900, (100, 100, 300, 200))
r = tr.mapRect(sc_now.bounds)
check("selection + fit: inside the selection",
      r.left() >= 99 and r.right() <= 401 and r.top() >= 99 and
      r.bottom() <= 301)
panel.fit_chk.setChecked(False)
tr, k = panel.placement(sc_now, 1200, 900, (100, 100, 300, 200))
check("selection without fit: centred on it at full size",
      k == 1.0 and abs(tr.mapRect(sc_now.bounds).center().x() - 250) < 1)
panel.fit_chk.setChecked(True)
pnode = panel.insert(raster=True)
check("pixel insert makes a paint layer with pixels",
      pnode is not None and pnode.kind == "paintlayer" and
      pnode.pixels is not None and pnode.pixels[0] ==
      pnode.pixels[3] * pnode.pixels[4] * 4)
check("pixels land inside the selection",
      pnode.pixels[1] >= 98 and pnode.pixels[2] >= 98 and
      pnode.pixels[1] + pnode.pixels[3] <= 403 and
      pnode.pixels[2] + pnode.pixels[4] <= 303)
panel._params["fill_mode"] = "tone"
tnode = panel.insert(raster=False)
check("a halftone vector insert falls back to pixels",
      tnode.kind == "paintlayer" and "pixels" in panel.status_lbl.text())
panel._params["fill_mode"] = "solid"
doc._sel = _Sel(5000, 5000, 10, 10)
check("lettering placed off the canvas is refused, not crashed",
      panel.insert(raster=True) is None)
doc._sel = None
panel.text_edit.setPlainText("   ")
check("empty text is refused", panel.insert() is None and
      "Type" in panel.status_lbl.text())
panel.text_edit.setPlainText("ドン")

# saving
tmp = tempfile.mkdtemp()
png = os.path.join(tmp, "a.png")
svgp = os.path.join(tmp, "a.svg")
check("PNG saved", panel.save_to(png) and os.path.getsize(png) > 100)
check("SVG saved", panel.save_to(svgp) and
      ET.parse(svgp).getroot().tag.endswith("svg"))
check("save folder remembered", store.get("giongoSaveDir") == tmp)
check("unwritable path reports failure",
      panel.save_to(os.path.join(tmp, "no", "such", "dir", "x.svg"))
      is False)

# --- its own window, and columns when there is room -----------------------
# A docker is one narrow column and this panel has outgrown it. The same
# widget moves into a window rather than a second one being built, so these
# check that it really moves and that it keeps working on both sides.
check("the width decides the columns, not where the panel lives",
      panel._columns_for(420) == 1 and panel._columns_for(900) == 2
      and panel._columns_for(1300) == 3)
check("the settings are grouped into blocks the grid can arrange",
      len(panel._blocks) >= 5)
check("the first block is the one with the text and the preview",
      panel.preview in panel._blocks[0].findChildren(type(panel.preview)))

from typer_kr._qt import QWidget as _QW, QVBoxLayout as _QVL
_host = _QW()
_hl = _QVL(_host)
_hl.addWidget(panel)
panel.set_active(True)

panel.pop_out()
_win = panel._window
check("the panel moves into a window of its own",
      _win is not None and panel.parentWidget() is _win)
check("...which is not modal, so Krita stays usable",
      not _win.isModal())
check("a window is wide enough for more than one column",
      panel._columns_for(_win.width()) >= 2)

# the tab behind it may well be closed; that must not stop the drawing
panel.set_active(False)
check("a panel in a window keeps working with its tab closed",
      panel._active is True)

panel.text_edit.setPlainText("ドン")
panel._refresh_preview()
check("...and still draws", panel.preview.pixmap() is not None
      and not panel.preview.pixmap().isNull())

_win.close()
check("closing the window puts the panel back", panel._popped is False
      and panel._window is None and panel.parentWidget() is _host)
check("the size it had is remembered for next time",
      len(str(store.get("giongoWinGeom", "")).split(",")) == 4)
check("back in the tab it answers to the tab again",
      panel._active is False)

panel.resize(420, 900)
panel._recheck_columns()
check("a narrow panel falls back to one column", panel._cols == 1)
panel.resize(1300, 900)
panel._recheck_columns()
check("a wide one spreads out", panel._cols == 3)
panel.set_active(True)

# --- the centre lines, and the brush that runs along them -----------------
from typer_kr import strokefont as SF        # noqa: E402
from typer_kr import giongo_brush as BR      # noqa: E402

_count, _strokes, _points = SF.info()
check("the data file carries the whole set", _count >= 250)
check("every glyph has at least one stroke", _strokes >= _count)
check("kana are covered", SF.has("ド") and SF.has("ん") and SF.has("ー"))
check("so is the Latin alphabet, out of the Hershey lines",
      all(SF.has(c) for c in "ABCXYZabcxyz0189"))
check("a kanji is honestly reported as missing", not SF.has("漢"))
check("coverage counts letters, not spaces",
      SF.coverage("ドン ！") == 1.0 and SF.coverage("") == 1.0)
check("...and says which ones it cannot draw",
      SF.missing("ド漢ン字") == ["漢", "字"])

_adv, _st = SF.glyph("ド")
check("ド comes back as a handful of strokes", 3 <= len(_st) <= 8)
check("the points sit in em units around the baseline",
      all(-1200 <= y <= 400 and -200 <= x <= 1200
          for s in _st for (x, y) in s))
check("a full stop is a dot, not a line", SF.is_dot(SF.glyph(".")[1][0]))
check("the tittle of an i is kept",
      len(SF.glyph("i")[1]) == 2 and any(SF.is_dot(s)
                                         for s in SF.glyph("i")[1]))

_sc = SF.scaled("A", 200)
check("scaling keeps the advance in proportion",
      abs(_sc[0] - SF.glyph("A")[0] * 0.2) < 0.01)
check("a missing glyph scales to nothing", SF.scaled("漢", 200) is None)
check("a data file that is not there is not an error",
      SF.load(os.path.join(tmp, "no-such-file.txt")) == {})

# the brush itself
_line = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]
for _pen in BR.PENS:
    _poly = BR.stroke_outline(_line, 100.0, pen=_pen, seed=3)
    check("%s draws a closed shape" % _pen, len(_poly) >= 6)

_brush = BR.stroke_outline(_line, 100.0, pen="brush", seed=3)
_ys = [y for (_x, y) in _brush]
_start_w = max(y for (x, y) in _brush if x < 30) - min(
    y for (x, y) in _brush if x < 30)
_end_w = max(y for (x, y) in _brush if x > 170) - min(
    y for (x, y) in _brush if x > 170)
check("a brush lands heavy and runs out thin", _start_w > _end_w * 2)

_marker = BR.stroke_outline(_line, 100.0, pen="marker", seed=3)
_m_start = max(y for (x, y) in _marker if x < 30) - min(
    y for (x, y) in _marker if x < 30)
_m_end = max(y for (x, y) in _marker if x > 170) - min(
    y for (x, y) in _marker if x > 170)
check("a marker keeps one weight", abs(_m_start - _m_end) < _m_start * 0.35)

check("a dot becomes a blob, not a line",
      len(BR.stroke_outline([(10.0, 10.0), (10.0, 10.0)], 100.0,
                            pen="marker")) >= 8)

_turned = []
for _ln in ([(0.0, 0.0), (200.0, 0.0)], [(0.0, 0.0), (0.0, 200.0)]):
    _turned.append(BR.letter_outlines([_ln], 200.0, pen="brush")
                   != BR.letter_outlines([_ln[::-1]], 200.0, pen="brush"))
check("the brush draws a stroke the way the data runs, across and down",
      all(_turned))
_fwd = BR.letter_outlines([[(0.0, 0.0), (200.0, 0.0)]], 200.0, pen="brush")


def _thick(poly, far):
    ys = [y for (x, y) in poly if (x > 150) == far]
    return max(ys) - min(ys)


check("...landing heavy where the stroke starts",
      _thick(_fwd[0], False) > _thick(_fwd[0], True))

check("a dry pen does not trip over a dot",
      len(BR.stroke_shapes([(10.0, 10.0), (10.0, 10.0)], 100.0,
                           pen="rough")) >= 1)
check("...nor over a stroke of two points",
      len(BR.stroke_shapes([(10.0, 10.0), (90.0, 10.0)], 100.0,
                           pen="rough")) >= 1)

check("the same seed draws the same stroke twice",
      BR.stroke_outline(_line, 100.0, pen="rough", seed=7)
      == BR.stroke_outline(_line, 100.0, pen="rough", seed=7))
check("a different seed does not",
      BR.stroke_outline(_line, 100.0, pen="rough", seed=7)
      != BR.stroke_outline(_line, 100.0, pen="rough", seed=8))

check("a dry brush comes apart and throws specks",
      len(BR.stroke_shapes(_line, 100.0, pen="rough", seed=5)) > 1)
check("a marker does not", len(BR.stroke_shapes(_line, 100.0, pen="marker",
                                                seed=5)) == 1)

_letter = BR.letter_outlines(SF.scaled("ド", 200)[1], 200.0, pen="brush",
                             seed=2)
check("a whole letter comes out as one shape per stroke",
      len(_letter) >= len(SF.glyph("ド")[1]))
check("and it sits where the letter would",
      all(-300 <= x <= 300 and -300 <= y <= 120
          for poly in _letter for (x, y) in poly))

# --- a pen replaces the font outline, letter by letter --------------------
_p_off = G.sanitize(dict(G.DEFAULTS, pen="off"))
_p_brush = G.sanitize(dict(G.DEFAULTS, pen="brush"))
check("a pen is one of the known ones",
      G.sanitize(dict(G.DEFAULTS, pen="brush"))["pen"] == "brush"
      and G.sanitize(dict(G.DEFAULTS, pen="nonsense"))["pen"] == "off")
check("its weight is kept in range",
      G.sanitize(dict(G.DEFAULTS, pen_width=9999))["pen_width"] <= 220)

_s_off = R.build_scene("ドン", _p_off)
_s_brush = R.build_scene("ドン", _p_brush)
check("the brush really changes what is drawn",
      not _s_off.is_empty() and not _s_brush.is_empty()
      and _s_off.bounds != _s_brush.bounds)

# a letter with no centre lines keeps the font's outline, so a mixed line
# comes out whole instead of with holes in it
_k_off = R.build_scene("漢", _p_off)
_k_brush = R.build_scene("漢", _p_brush)
check("a kanji falls back to the font outline",
      _k_off.bounds == _k_brush.bounds)
check("...and a mixed line still draws every letter",
      not R.build_scene("ド漢ン", _p_brush).is_empty())

_glyph = R.stroke_glyph("ド", "brush", 1)
check("a stroke glyph comes back with its advance",
      _glyph is not None and _glyph[1] > 0)
check("and nothing comes back for a kanji",
      R.stroke_glyph("漢", "brush", 1) is None)
check("the same seed gives the same letter twice",
      R.stroke_glyph("ド", "brush", 5)[0].elementCount()
      == R.stroke_glyph("ド", "brush", 5)[0].elementCount())
check("the pen's weight changes how heavy it is",
      R.stroke_glyph("ド", "brush", 5, width=60)[0].elementCount() > 0
      and R.stroke_glyph("ド", "brush", 5, width=200)[0].boundingRect()
      .width() > R.stroke_glyph("ド", "brush", 5, width=60)[0]
      .boundingRect().width())

check("the letters sit on the same line either way",
      abs(_s_off.bounds.center().y() - _s_brush.bounds.center().y())
      < _s_off.bounds.height() * 0.3)

# --- the stroke-lettering block in the panel ------------------------------
check("every pen is offered, the font included",
      panel.pen_combo.count() == len(G.PENS)
      and panel.pen_combo.itemData(0) == "off")
check("all five settings have a slider",
      all(k in panel._sliders for k in ("pen_width", "pen_taper",
                                        "pen_wobble", "pen_angle",
                                        "pen_dry")))

panel.pen_combo.setCurrentIndex(
    [panel.pen_combo.itemData(i)
     for i in range(panel.pen_combo.count())].index("brush"))
check("choosing a pen reaches the parameters",
      panel.params()["pen"] == "brush")

panel.text_edit.setPlainText("ドン")
panel._refresh_pen_hint()
check("nothing is said when every letter can be drawn",
      not panel.pen_hint.isVisibleTo(panel))

panel.text_edit.setPlainText("ド漢ン")
panel._refresh_pen_hint()
check("a letter the pen cannot draw is named, not passed over in silence",
      "漢" in panel.pen_hint.text())

panel.pen_combo.setCurrentIndex(0)
panel._refresh_pen_hint()
check("with the pen off there is nothing to warn about",
      panel.params()["pen"] == "off"
      and not panel.pen_hint.isVisibleTo(panel))
panel.text_edit.setPlainText("ゴゴゴゴ")

# --- the gacha rolls a fill, and a tile can come from the library ---------
import collections as _collections

_rng = random.Random(4)
_base = G.sanitize(dict(G.DEFAULTS))
_mix = _collections.Counter(G.gacha("ジーーー", _base, _rng)["fill_mode"]
                            for _ in range(300))
check("the gacha no longer returns nothing but solid black",
      _mix["solid"] < 300 and (_mix["tone"] + _mix["gradient"]) > 20)
check("...but solid still wins, as it should on a sound effect",
      _mix["solid"] > _mix["tone"])
check("a pattern is only offered when a tile has been picked",
      _mix["pattern"] == 0)

_with = G.sanitize(dict(G.DEFAULTS, fill_pattern="C:/x/tile.png"))
_mix2 = _collections.Counter(G.gacha("ジーーー", _with, _rng)["fill_mode"]
                             for _ in range(300))
check("...and is offered once there is one", _mix2["pattern"] > 0)
check("the tile survives a change of type",
      G.apply_type(_with, "impact")["fill_pattern"] == "C:/x/tile.png")
check("a rolled screentone gets a usable dot spacing",
      all(G.RANGES["tone_dot"][0] <= G.gacha("ジーーー", _base, _rng)["tone_dot"]
          <= G.RANGES["tone_dot"][1] for _ in range(50)))

# the tile itself
from typer_kr._qt import QImage, QColor      # noqa: E402
_tile_path = os.path.join(tmp, "tile.png")
_tile = QImage(8, 8, QImage.Format.Format_ARGB32)
_tile.fill(QColor(0, 0, 0, 0))
for _i in range(8):
    _tile.setPixelColor(_i, _i, QColor(20, 20, 20))
_tile.save(_tile_path, "PNG")

check("a missing tile is not an error, it just has nothing to give",
      R.pattern_tile(os.path.join(tmp, "nope.png")) is None
      and R.pattern_tile("") is None)
_loaded = R.pattern_tile(_tile_path, 200)
check("a tile is loaded and scaled",
      _loaded is not None and _loaded.width() == 16)

_pat = G.sanitize(dict(G.DEFAULTS, fill_mode="pattern",
                       fill_pattern=_tile_path))
_scene = R.build_scene("ドン", _pat)
check("a pattern fill asks to be inserted as pixels",
      _scene.needs_raster())
check("a solid one does not",
      not R.build_scene("ドン", G.sanitize(dict(G.DEFAULTS))).needs_raster())
_img, _o = R.render_image(_scene, 1.0)
check("and it really draws", not _img.isNull() and _img.width() > 10)

# the panel's side
check("the fill list offers the pattern",
      "pattern" in [panel.fill_mode.itemData(i)
                    for i in range(panel.fill_mode.count())])
_picked = []


def _fake_picker():
    _picked.append(1)
    return None, _tile_path


panel._pick_pattern_fn = _fake_picker
panel.on_pick_pattern()
check("picking a tile sets it and switches the fill over",
      panel.params()["fill_pattern"] == _tile_path
      and panel.params()["fill_mode"] == "pattern")
check("the chosen tile is named, not just implied",
      "tile.png" in panel.pattern_lbl.text())
check("the tile size slider wakes up with it",
      panel._sliders["fill_pattern_scale"][0].isEnabled())

panel._pick_pattern_fn = lambda: (None, "")
panel.on_pick_pattern()
check("picking nothing changes nothing",
      panel.params()["fill_pattern"] == _tile_path)
panel._set_param("fill_mode", "solid")
panel.fill_mode.setCurrentIndex(max(0, panel.fill_mode.findData("solid")))


# --- the strokes are the ones a hand writes --------------------------------
check("a is written in three strokes, not cut up at every crossing",
      len(SF.glyph("\u3042")[1]) == 3)
check("...and the other tangled ones likewise",
      len(SF.glyph("\u306d")[1]) == 2 and len(SF.glyph("\u308c")[1]) == 2
      and len(SF.glyph("\u3080")[1]) == 3)
check("a mark on a kana is two strokes of its own",
      len(SF.glyph("\u30c9")[1]) - len(SF.glyph("\u30c8")[1]) == 2)

_first = SF.glyph("\u3042")[1][0]
check("a stroke runs the way it is written: a starts to the right",
      _first[-1][0] > _first[0][0] + 300)
_i_first = SF.glyph("\u3044")[1][0]
check("...and the first stroke of i runs downwards",
      _i_first[-1][1] > _i_first[0][1] + 300)
_bar = SF.glyph("\u30fc")[1]
check("a long vowel is one stroke, left to right",
      len(_bar) == 1 and _bar[0][-1][0] > _bar[0][0][0] + 600)

check("the German letters are there too",
      all(SF.has(c) for c in "\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc"
                             "\u00df"))
check("an eszett is written in one stroke",
      len(SF.glyph("\u00df")[1]) == 1)
check("a vowel with marks keeps the advance of the vowel",
      SF.glyph("\u00e4")[0] == SF.glyph("a")[0])
check("the Japanese marks are there",
      all(SF.has(c) for c in "\u3001\u3002\u300c\u300d\u300e\u300f"
                             "\u301c\u2026\uff01\uff1f"))
check("every printable ASCII character can be drawn",
      all(SF.has(chr(c)) for c in range(0x21, 0x7f)))
with io.open(SF.DATA, encoding="ascii") as _fh:        # raises if it is not
    _raw = _fh.read()
check("the data file is plain ASCII, as the reader needs",
      "KanjiVG" in _raw and "\n#" in _raw)

print("\npassed %d, failed %d" % (_pass, _fail))
sys.exit(1 if _fail else 0)
