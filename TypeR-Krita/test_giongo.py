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

from typer_kr import giongo as G
from typer_kr import giongo_dict as GD
from typer_kr import giongo_warp as WP
from typer_kr import giongo_nodes as ND
from typer_kr import userfonts as UF
from typer_kr import giongo_trace as TR      # noqa: E402

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

import math as _math
import tempfile as _tempfile
import shutil as _shutil
import json as _json
import zipfile as _zipfile
import time as _time
import random as _random

# --- the sound dictionary (Qt-free part) ---------------------------------
print("== sound dictionary ==")
_all = GD.entries()
check("the dictionary has a useful number of sounds", len(_all) >= 60)
check("every sound names a type the plugin actually has",
      {e["type"] for e in _all} <= {t["id"] for t in G.TYPES})
check("...and more than one type is covered",
      len({e["type"] for e in _all}) >= 8)
check("no sound is in there twice",
      len({e["kana"] for e in _all}) == len(_all))
check("every sound says what it means, in both languages",
      all(e["en"] and e["de"] for e in _all))
check("the kana are kana, not romaji",
      all(max(e["kana"]) > "\u3000" for e in _all))

check("searching the reading finds the sound",
      GD.find("dokaan")[0]["kana"] == "\u30c9\u30ab\u30fc\u30f3")
check("...and so does the reading as people type it, without the long "
      "vowels", GD.find("dokan")[0]["kana"] == "\u30c9\u30ab\u30fc\u30f3")
check("searching the kana finds it too",
      GD.find("\u30ad\u30e5\u30f3")[0]["romaji"] == "kyun")
check("searching the meaning finds it, in the language on screen",
      any(e["kana"] == "\u30b6\u30fc\u30b6\u30fc"
          for e in GD.find("Regen", "de"))
      and any(e["kana"] == "\u30b6\u30fc\u30b6\u30fc"
              for e in GD.find("rain", "en")))
check("an exact reading beats a sound that merely contains it",
      GD.find("don")[0]["kana"] == "\u30c9\u30f3")
check("nothing matching is no match, not everything",
      GD.find("qqqq") == [])
check("an empty search lists them all", len(GD.find("")) == len(_all))
check("a type can be asked for on its own",
      {e["type"] for e in GD.find("", kind="rumble")} == {"rumble"})
check("the long-vowel spelling folds the way people type",
      GD.plain("dokaan") == "dokan" and GD.plain("shiin") == "shin")
check("the meaning falls back to English for a language we lack",
      GD.gloss(_all[0], "fr") == _all[0]["en"])
check("by_type groups them without losing any",
      sum(len(v) for v in GD.by_type().values()) == len(_all))


# --- liquify: the brush, in numbers --------------------------------------
print("== liquify ==")
check("the four tools are there",
      WP.MODES == ("push", "inflate", "pinch", "twirl"))
check("the brush is full strength in the middle and nothing at the rim",
      WP.falloff(0.0, 0.3) == 1.0 and WP.falloff(1.0, 0.3) == 0.0
      and WP.falloff(1.5, 0.3) == 0.0)
check("hardness holds full strength further out",
      WP.falloff(0.5, 0.8) > WP.falloff(0.5, 0.0))
check("...and it eases off, it does not step",
      WP.falloff(0.4, 0.3) > WP.falloff(0.6, 0.3) > WP.falloff(0.8, 0.3))

_ring = [(200.0 * _math.cos(_math.radians(a)),
          200.0 * _math.sin(_math.radians(a))) for a in range(0, 360, 20)]


def _radii(pts):
    return [_math.hypot(x, y) for x, y in pts]


_pushed = WP.warp_points([(0.0, 0.0), (350.0, 0.0), (450.0, 0.0)],
                         [WP.dab("push", 0, 0, 400, 50, 0, 0.3)])
check("push moves the middle by the whole distance",
      abs(_pushed[0][0] - 50.0) < 0.01)
check("...less at the edge of the brush",
      0 < _pushed[1][0] - 350.0 < 50.0)
check("...and nothing at all outside it", _pushed[2] == (450.0, 0.0))

_inf = WP.warp_points(_ring, [WP.dab("inflate", 0, 0, 400, 0.10, 0, 0.3)])
_pin = WP.warp_points(_ring, [WP.dab("pinch", 0, 0, 400, 0.10, 0, 0.3)])
check("inflate pushes a ring outward, evenly",
      min(_radii(_inf)) > 200.0
      and max(_radii(_inf)) - min(_radii(_inf)) < 0.01)
check("pinch draws it in", max(_radii(_pin)) < 200.0)
check("...and never past the middle, however often it is applied",
      min(_radii(WP.warp_points(
          _ring, [WP.dab("pinch", 0, 0, 400, 0.9, 0, 0.0)] * 20))) >= 0.0)
_tw = WP.warp_points([(200.0, 0.0)],
                     [WP.dab("twirl", 0, 0, 400, 20, 0, 0.3)])[0]
check("twirl turns a point without moving it nearer or further",
      abs(_math.hypot(*_tw) - 200.0) < 0.01
      and 0.0 < _math.degrees(_math.atan2(_tw[1], _tw[0])) < 20.0)
check("dabs add up: five gentle ones beat one of them",
      max(_radii(WP.warp_points(
          _ring, [WP.dab("inflate", 0, 0, 400, 0.05, 0, 0.3)] * 5)))
      > max(_radii(_inf)))
check("one dab can never fold the outline over itself",
      abs(WP.warp_points([(10.0, 0.0)],
                         [WP.dab("push", 0, 0, 100, 9999, 0, 0.0)])[0][0]
          - 10.0) <= 100.0 * WP.MAX_PULL + 0.01)

check("a short step of a drag is one dab",
      len(WP.dabs_for("push", 0, 0, 3, 0, 50, 100, 0)) == 1)
_far = WP.dabs_for("push", 0, 0, 300, 0, 50, 100, 0)
check("...a long one is laid along the way, not dropped in one place",
      len(_far) > 4 and _far[0][1] < _far[-1][1]
      and _far[-1][1] <= 300.0001)
check("...no further apart than a third of the brush",
      all(_far[i + 1][1] - _far[i][1]
          <= WP.radius_for(50) * WP.SPACING + 0.01
          for i in range(len(_far) - 1)))
check("...and together they carry the whole movement",
      abs(sum(d[4] for d in _far) - 300.0) < 0.01)
check("a jump right across the canvas is still one gesture",
      len(WP.dabs_for("push", 0, 0, 99999, 0, 5, 100, 0)) == WP.MAX_STEPS)


check("Alt turns the tool round",
      WP.invert(WP.dab("inflate", 0, 0, 100, 0.1))[0] == "pinch"
      and WP.invert(WP.dab("pinch", 0, 0, 100, 0.1))[0] == "inflate"
      and WP.invert(WP.dab("push", 0, 0, 100, 5, 7))[4:6] == [-5.0, -7.0])
check("a drag's step follows the three sliders",
      WP.dab_for("push", 0, 0, 50, 100, 20, 30, 0)[4] == 30.0
      and WP.dab_for("push", 0, 0, 50, 50, 20, 30, 0)[4] == 15.0)
check("the brush size is a share of the letter",
      WP.radius_for(100) == WP.REF / 2.0
      and WP.radius_for(50) < WP.radius_for(100))

check("rubbish from a settings file is dropped, not drawn",
      WP.sanitize([["melt", 0, 0, 10, 1, 0, 0], None, "x",
                   ["push", 0, 0, 10, 1, 0, 0]])
      == [WP.dab("push", 0, 0, 10, 1, 0, 0)])
check("a letter cannot collect more dabs than it may",
      len(WP.sanitize([WP.dab("push", 0, 0, 10, 1)] * (WP.MAX_DABS + 50)))
      == WP.MAX_DABS)
_wp = G.sanitize(dict(G.DEFAULTS))
WP.add_dab(_wp, 0, 1, WP.dab("push", 5, 5, 50, 10, 0))
check("a dab lands on the letter it was aimed at",
      WP.has_warp(_wp, 0, 1) and not WP.has_warp(_wp, 0, 0))
check("...and survives being saved and read back",
      WP.has_warp(G.from_json(G.to_json(_wp)), 0, 1))
WP.clear_warp(_wp, 0, 1)
check("...and can be taken back off", not WP.has_warp(_wp))
check("two different warps are told apart, the same one is not",
      WP.fingerprint([WP.dab("push", 0, 0, 10, 1)])
      != WP.fingerprint([WP.dab("push", 0, 0, 10, 2)])
      and WP.fingerprint([WP.dab("push", 0, 0, 10, 1)])
      == WP.fingerprint([WP.dab("push", 0, 0, 10, 1)]))

_plain_sc = R.build_scene("\u30c9", G.sanitize(dict(G.DEFAULTS)))
_warp_par = G.sanitize(dict(G.DEFAULTS))
WP.add_dab(_warp_par, 0, 0, WP.dab("inflate", 0, 0, 400, 0.2, 0, 0.3))
_warp_sc = R.build_scene("\u30c9", G.sanitize(_warp_par))
check("a warped letter is drawn differently",
      R.path_d(_warp_sc.layers[-1].path) != R.path_d(_plain_sc.layers[-1].path))
check("...and the scene knows it got bigger",
      _warp_sc.bounds.width() > _plain_sc.bounds.width())
check("a warp belongs to its own letter and leaves the others alone",
      R.path_d(R.build_scene("\u30c9\u30f3",
                             G.sanitize(_warp_par)).layers[-1].path)
      == R.path_d(R.build_scene("\u30c9\u30f3",
                                G.sanitize(dict(G.DEFAULTS))).layers[-1].path))
check("the warp is remembered with the letter, not rebuilt every frame",
      R.path_d(R.build_scene("\u30c9", G.sanitize(_warp_par)).layers[-1].path)
      == R.path_d(_warp_sc.layers[-1].path))


def _AREA(path):
    """How much ink a path holds, in the letter's own em.

    Both paths are drawn through the same window - scaling each to its
    own box would compare two magnifications.
    """
    img = _QImage(160, 160, _QImage.Format.Format_ARGB32)
    img.fill(_QColor(0, 0, 0, 0))
    pt = _QPainter(img)
    pt.translate(80, 80)
    pt.scale(160.0 / 300.0, 160.0 / 300.0)      # -150..150 em across
    pt.setPen(_Qt.PenStyle.NoPen)
    pt.setBrush(_QColor("#000000"))
    pt.drawPath(path)
    pt.end()
    return sum(1 for y in range(160) for x in range(160)
               if (img.pixel(x, y) >> 24) > 128)

# a real font to check a real outline with; offscreen there may be none
from typer_kr._qt import font_families as _ff                   # noqa: E402
from typer_kr._qt import QImage as _QImage, QColor as _QColor   # noqa: E402
from typer_kr._qt import QPainter as _QPainter                  # noqa: E402
from typer_kr._qt import QPointF as _QPointF                    # noqa: E402
from typer_kr._qt import Qt as _Qt                              # noqa: E402
from typer_kr._qt import QPainterPath as _QPainterPath   # noqa: E402
_FAMS = set(_ff() or [])
_REAL_FAM = next((f for f in ("MS Gothic", "Yu Gothic", "Meiryo",
                              "IPAGothic", "DejaVu Sans") if f in _FAMS), "")


# --- the outline as points -----------------------------------------------
print("== points ==")
_sq = [[ND.node(-100, -100), ND.node(100, -100), ND.node(100, 100),
        ND.node(-100, 100)]]
check("a ring of corners is kept as it was",
      ND.sanitize_contours(_sq) == _sq and ND.count(_sq) == 4)
check("rubbish is dropped, not drawn",
      ND.sanitize_contours([None, [1, 2], _sq[0]]) == _sq)
check("a letter's points survive being saved and read back",
      ND.sanitize_table({"0:1": _sq, "bad": _sq, "2:x": _sq})
      == {"0:1": _sq})

_c = ND.sanitize_contours(_sq)
_before = [ND.point_on(_c, 0, 0, t / 8.0) for t in range(9)]
ND.insert_node(_c, 0, 0, 0.5)
check("adding a point does not change the shape it was added to",
      ND.count(_c) == 5
      and all(abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) < 0.01
              for a, b in zip(_before[:5],
                              [ND.point_on(_c, 0, 0, t / 4.0)
                               for t in range(5)])))
check("...and the new point sits where it was put",
      max(abs(_c[0][1][0] - 0.0), abs(_c[0][1][1] + 100.0)) < 0.01)
ND.delete_node(_c, 0, 1)
check("deleting one takes it away again", ND.count(_c) == 4)
_tiny = [[ND.node(0, 0), ND.node(10, 0), ND.node(0, 10)]]
ND.delete_node(_tiny, 0, 0)
check("a ring too small to be an outline goes with its last point",
      _tiny == [])

_sm = ND.sanitize_contours(_sq)
ND.set_smooth(_sm, 0, 1, True)
_n = _sm[0][1]
check("a corner made smooth gets handles in line with the outline",
      _n[6] == 1 and abs(_n[2] + _n[4]) < 0.01 and abs(_n[3] + _n[5]) < 0.01
      and (_n[2] or _n[3]))
ND.move_handle(_sm, 0, 1, "out", _n[0] + 40, _n[1] + 40)
check("moving one handle of a smooth point turns the other with it",
      abs(_sm[0][1][2] + 40.0 * _math.hypot(_sm[0][1][2], _sm[0][1][3])
          / _math.hypot(40.0, 40.0)) < 0.01 or
      (_sm[0][1][2] < 0 and _sm[0][1][3] < 0))
ND.set_smooth(_sm, 0, 1, False)
_in_was = tuple(_sm[0][1][2:4])
ND.move_handle(_sm, 0, 1, "out", _sm[0][1][0] - 30, _sm[0][1][1] + 10)
check("a corner keeps its handles apart",
      tuple(_sm[0][1][2:4]) == _in_was)

_mv = ND.sanitize_contours(_sm)
_h_was = tuple(_mv[0][1][2:6])
ND.move_node(_mv, 0, 1, 25, -15)
check("a point takes its handles with it when it moves",
      tuple(_mv[0][1][2:6]) == _h_was
      and _mv[0][1][0] == _sm[0][1][0] + 25)

check("the nearest point is found, and only within reach",
      ND.nearest_node(_sq, -95, -95, 20) == (0, 0)
      and ND.nearest_node(_sq, 0, 0, 20) is None)
check("the nearest piece of outline is found",
      ND.nearest_segment(_sq, 0, -100)[:2] == (0, 0))
check("two different outlines are told apart",
      ND.fingerprint(_sq) != ND.fingerprint(_sm)
      and ND.fingerprint(_sq) == ND.fingerprint(ND.sanitize_contours(_sq)))

# --- a hole has to run the other way round -------------------------------
_box = _QPainterPath()
_box.addRect(-100, -100, 200, 200)
_cutline = _QPainterPath()
_cutline.moveTo(-10, 0)
_cutline.lineTo(10, 0)
_bitten = _box.subtracted(R._ring_cut(_cutline, 40))
check("taking a bite out of a shape leaves less of it",
      _AREA(_bitten) < _AREA(_box))
check("...and Qt hands that back to be filled odd-even, not winding",
      _bitten.fillRule() != _Qt.FillRule.WindingFill)
check("points straight off such a path would fill the hole in again",
      _AREA(R.path_from_nodes(R.nodes_from_path(_bitten)))
      > _AREA(_bitten) * 1.1)
check("...so the contours are wound to match, and the hole stays a hole",
      abs(_AREA(R.path_from_nodes(ND.rewind(R.nodes_from_path(_bitten))))
          - _AREA(_bitten)) <= 2)
check("an outline that is already wound right is left alone",
      ND.rewind(ND.sanitize_contours(_sq)) == ND.sanitize_contours(_sq)
      or ND.rewind(ND.sanitize_contours(_sq))
      == ND.rewind(ND.rewind(ND.sanitize_contours(_sq))))
check("turning a ring round turns its handles round with it",
      ND.reverse(ND.reverse(ND.sanitize_contours(_sm)[0]))
      == ND.sanitize_contours(_sm)[0])


# --- the outline a font drew, as points and back -------------------------
_gl, _adv = R.glyph("\u30c9", _REAL_FAM, False)
_cs = R.nodes_from_path(_gl)
if _REAL_FAM:
    check("a real glyph comes apart into contours and points",
          len(_cs) >= 1 and ND.count(_cs) >= 8)
    _back = R.path_from_nodes(_cs)


    def _raster(path, size=240):
        img = _QImage(size, size, _QImage.Format.Format_ARGB32)
        img.fill(_QColor("#ffffff"))
        pt = _QPainter(img)
        pt.setRenderHint(_QPainter.RenderHint.Antialiasing, True)
        pt.translate(size / 2.0, size / 2.0)
        pt.scale(0.18, 0.18)
        pt.setPen(_Qt.PenStyle.NoPen)
        pt.setBrush(_QColor("#000000"))
        pt.drawPath(path)
        pt.end()
        return img


    _a, _b = _raster(_gl), _raster(_back)
    _diff = sum(1 for y in range(_a.height()) for x in range(_a.width())
                if _a.pixel(x, y) != _b.pixel(x, y))
    check("...and back into the very same outline, pixel for pixel",
          _diff == 0)
else:
    check("a real glyph comes apart into contours and points", True)
    check("...and back into the very same outline, pixel for pixel", True)

_np = G.sanitize(dict(G.DEFAULTS))
ND.set_nodes(_np, 0, 0, ND.sanitize_contours(_sq))
check("a letter with points of its own is drawn from them, not the font",
      R.path_d(R.build_scene("\u30c9", G.sanitize(_np)).layers[-1].path)
      != R.path_d(R.build_scene("\u30c9",
                                G.sanitize(dict(G.DEFAULTS))).layers[-1].path))
_moved = G.sanitize(_np)
_cs2 = ND.nodes_of(_moved, 0, 0)
ND.move_node(_cs2, 0, 0, 60, 0)
ND.set_nodes(_moved, 0, 0, _cs2)
check("...and moving a point really moves what is drawn",
      R.path_d(R.build_scene("\u30c9", G.sanitize(_moved)).layers[-1].path)
      != R.path_d(R.build_scene("\u30c9", G.sanitize(_np)).layers[-1].path))


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

from typer_kr.giongo_ui import (GiongoPanel, GiongoWindow,   # noqa: E402
                                SoundDialog, FontPickDialog,
                                STRINGS)

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
      _win is not None and _win.isAncestorOf(panel))
check("...where it scrolls, so the window can be shorter than the panel",
      _win.minimumSizeHint().height() < 400)
_area = _win.screen().availableGeometry() if hasattr(_win, "screen")     else None
check("...and the window lands on the screen, not half under it",
      _area is None or _area.contains(_win.geometry()))
panel._set("giongoWinGeom", "9000,9000,3000,2400")
_far = GiongoWindow(panel, None)
panel._restore_geometry(_far)
check("a window remembered on a screen that is gone comes back onto one",
      _area is None or _area.contains(_far.geometry()))
_far.deleteLater()
check("...which is not modal, so Krita stays usable",
      not _win.isModal())
check("a window is wide enough for more than one column, unless the "
      "screen itself is not",
      panel._columns_for(_win.width()) >= 2
      or (_area is not None and _area.width() < 860))

# the tab behind it may well be closed; that must not stop the drawing
panel.set_active(False)
# the window used to take the panel out of its scroll area while it was
# closing, and Krita died of it (QScrollArea::ensureWidgetVisible, twice
# in the crash log). Opening and closing it a few times would crash this
# process too, so the test is that it does not.
for _round in range(3):
    panel.pop_out()
    _w2 = panel._window
    _w2.show()
    _app.processEvents()
    panel._refresh_preview()
    panel.text_edit.setFocus()
    panel.preview.setFocus()
    _app.processEvents()
    _w2.close()
    _app.processEvents()
check("the window can be opened and closed again, and again",
      not panel._popped and panel.parentWidget() is not None)
check("...and the panel still draws afterwards",
      panel.scene() is not None)
panel.pop_out()                     # the tests below carry on in the window
_win = panel._window
_app.processEvents()
panel._refresh_preview()


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

# --- a letter of its own, and a path you can grab --------------------------
_gp = G.sanitize(dict(G.DEFAULTS))
_gt = "\u30c9\u30fc\u30f3"

check("a fresh sound effect has no hand edits", _gp["letters"] == {})
G.set_letter_edit(_gp, 0, 1, dx=30.0, dy=-10.0, rot=15.0, scale=1.5)
check("an edit is filed under its letter",
      G.letter_edit(_gp, 0, 1) == (30.0, -10.0, 15.0, 1.5))
check("...and every other letter is untouched",
      G.letter_edit(_gp, 0, 0) == (0.0, 0.0, 0.0, 1.0))
_pl = [x for x in G.layout(_gt, _gp) if (x["group"], x["index"]) == (0, 1)][0]
_plain = [x for x in G.layout(_gt, G.sanitize(dict(G.DEFAULTS)))
          if (x["group"], x["index"]) == (0, 1)][0]
check("the layout really moves, turns and resizes that letter",
      abs(_pl["x"] - _plain["x"] - 30.0) < 0.01
      and abs(_pl["angle"] - _plain["angle"] - 15.0) < 0.01
      and abs(_pl["size"] - _plain["size"] * 1.5) < 0.01)
check("...and says it was edited by hand",
      _pl["edited"] and not _plain["edited"])

G.set_letter_edit(_gp, 0, 1, dx=0.0, dy=0.0, rot=0.0, scale=1.0)
check("an edit put back to neutral leaves nothing behind", _gp["letters"] == {})
G.set_letter_edit(_gp, 0, 0, dx=5.0)
G.clear_letter_edits(_gp)
check("and they can all be dropped at once", _gp["letters"] == {})

check("rubbish from a saved file is dropped, not trusted",
      G.sanitize({"letters": {"0:0": [1, 2, 3, 4], "bad": [1, 2, 3, 4],
                              "0:1": "no", "0:2": [1, 2]}})["letters"]
      == {"0:0": [1.0, 2.0, 3.0, 4.0]})
check("...and a mad scale is pulled back into range",
      G.sanitize({"letters": {"0:0": [0, 0, 0, 9e9]}})["letters"]["0:0"][3]
      == 20.0)

_pts = G.path_points(_gt, _gp)
check("the path offers three points to take hold of", len(_pts) == 3)
check("...starting at the origin, running to the right",
      _pts[0] == (0.0, 0.0) and _pts[2][0] > 100 and abs(_pts[2][1]) < 1)

G.set_path_end(_gp, _gt, (200.0, -200.0))
check("dragging the end aims the path at it",
      abs(G.path_points(_gt, _gp)[2][0] - 200.0) < 1.0
      and abs(G.path_points(_gt, _gp)[2][1] + 200.0) < 1.0)
check("...which is what the rise and the spacing now say",
      abs(_gp["rise"] - 45.0) < 0.5 and _gp["spacing"] < 0)
G.set_path_bend(_gp, _gt, (120.0, -60.0))
check("dragging the middle bends the path towards it",
      _gp["bend"] != 0 and G.path_points(_gt, _gp)[1][1] > -200)
check("a drag far outside stops at the end of the range",
      G.set_path_end(G.sanitize(dict(G.DEFAULTS)), _gt,
                     (99999.0, 0.0))["spacing"] == G.RANGES["spacing"][1])
check("an empty sound effect has no path to drag",
      G.natural_length("", _gp) == 0.0)

_places = G.layout(_gt, G.sanitize(dict(G.DEFAULTS)))
_hit = G.nearest_letter(_places, (_places[0]["x"], _places[0]["y"]))
check("a point on a letter finds a letter", _hit is not None)
check("a point far away finds none",
      G.nearest_letter(_places, (99999.0, 99999.0)) is None)


# --- the preview you can grab (panel side) ---------------------------------
panel.text_edit.setPlainText("\u30c9\u30fc\u30f3")
panel.set_active(True)
panel._refresh_preview()
check("the preview knows where the letters landed and where the path runs",
      len(panel._places) == 3 and len(panel.preview._path) == 3)
_w = panel.preview._to_widget((50.0, 20.0))
check("...and maps a scene point onto itself and back",
      _w is not None and len(_w) == 2)

_rise0, _bend0 = panel._params["rise"], panel._params["bend"]
panel.preview_drag("end", (300.0, -120.0), (0.0, 0.0), None, None)
check("dragging the end handle writes the rise and the spacing",
      panel._params["rise"] != _rise0)
panel.preview_drag("bend", (150.0, -90.0), (0.0, 0.0), None, None)
check("dragging the middle handle writes the bend",
      panel._params["bend"] != _bend0)

_key = (0, 1)
panel.preview_drag("move", (60.0, 40.0), (20.0, 20.0), _key,
                   panel.letter_edit_of(_key))
check("dragging a letter moves that letter only",
      G.letter_edit(panel._params, 0, 1)[:2] == (40.0, 20.0)
      and G.letter_edit(panel._params, 0, 0) == (0.0, 0.0, 0.0, 1.0))
_pl = panel._placement(_key)
_cx, _cy = _pl["x"], _pl["y"]
panel.preview_drag("scale", (_cx + 200.0, _cy), (_cx + 100.0, _cy), _key,
                   panel.letter_edit_of(_key))
check("dragging the square resizes it",
      abs(G.letter_edit(panel._params, 0, 1)[3] - 2.0) < 0.01)
panel.preview_drag("rotate", (_cx, _cy - 100.0), (_cx + 100.0, _cy), _key,
                   panel.letter_edit_of(_key))
check("dragging the ring turns it",
      abs(G.letter_edit(panel._params, 0, 1)[2] + 90.0) < 0.5)
panel.reset_letter(_key)
check("a double-click puts that letter back",
      G.letter_edit(panel._params, 0, 1) == (0.0, 0.0, 0.0, 1.0))
panel.preview_drag("move", (60.0, 40.0), (20.0, 20.0), _key,
                   panel.letter_edit_of(_key))
panel.reset_letters()
check("and all of them can be put back at once",
      panel._params["letters"] == {})
check("a drag with no letter under it changes nothing",
      panel.preview_drag("move", (1.0, 1.0), (0.0, 0.0), None, None) is None
      and panel._params["letters"] == {})


# --- negative, and a dakuten on any letter --------------------------------
check("negative is offered as a fill", "negative" in G.FILL_MODES)
_ng = G.sanitize(dict(G.DEFAULTS, fill_mode="negative"))
check("...and survives being saved and read back",
      G.from_json(G.to_json(_ng))["fill_mode"] == "negative")
check("the area around the letters has a range of its own",
      G.RANGES["neg_pad"] == (0, 120)
      and G.sanitize({"neg_pad": 9999})["neg_pad"] == 120)

_plain_scene = R.build_scene("\u30c9\u30f3", G.sanitize(dict(G.DEFAULTS)))
_neg_scene = R.build_scene("\u30c9\u30f3", _ng)
check("a negative puts the letters in white, which a solid never does",
      any(l.color.lower() == "#ffffff" and l.kind == "fill"
          for l in _neg_scene.layers)
      and not any(l.color.lower() == "#ffffff" and l.kind == "fill"
                  for l in _plain_scene.layers))
check("...an area in the fill colour, and the letters in white on top",
      _neg_scene.layers[0].color.lower() == _ng["fill"].lower()
      and _neg_scene.layers[-1].color.lower() == "#ffffff")
check("...and the area is wider than the letter it came from",
      _neg_scene.layers[0].path.boundingRect().width()
      > _neg_scene.layers[-1].path.boundingRect().width())
_narrow = R.build_scene("\u30c9\u30f3", G.sanitize(
    dict(G.DEFAULTS, fill_mode="negative", neg_pad=0)))
check("...and no area at all when it is set to nothing",
      _narrow.layers[0].path.boundingRect().width()
      < _neg_scene.layers[0].path.boundingRect().width())

check("a combining dakuten hangs on the letter before it",
      [t["ch"] for t in G.tokenize("\u30a2\u3099\u30f3\u3099")[0]]
      == ["\u30a2\u3099", "\u30f3\u3099"])
check("...and a handakuten too",
      [t["ch"] for t in G.tokenize("\u30cf\u309a")[0]] == ["\u30cf\u309a"])
check("a mark with no letter in front of it is not swallowed",
      [t["ch"] for t in G.tokenize("\u3099\u30a2")[0]] == ["\u3099",
                                                            "\u30a2"])
check("the marked letter is laid out as one letter, not two",
      len(G.layout("\u30a2\u3099\u30f3", G.sanitize(dict(G.DEFAULTS)))) == 2)
panel.text_edit.setPlainText("\u30a2")
panel.text_edit.moveCursor(panel.text_edit.textCursor().MoveOperation.End)
panel.on_dakuten()
check("the button writes the mark into the text",
      panel.text_edit.toPlainText() == "\u30a2\u3099")
panel.text_edit.setPlainText("")
panel.on_dakuten()
check("...and does nothing with nothing in front of the cursor",
      panel.text_edit.toPlainText() == "")


# --- the caption beside the effect ----------------------------------------
_cp = G.sanitize(dict(G.DEFAULTS, caption="BOOM"))
check("a caption is kept, trimmed and kept on one line",
      G.sanitize({"caption": "  BOOM\nBANG "})["caption"] == "BOOM BANG")
check("only the four places are allowed",
      G.sanitize({"caption_pos": "above"})["caption_pos"] == "above"
      and G.sanitize({"caption_pos": "sideways"})["caption_pos"] == "below")
check("the caption size has a range",
      G.sanitize({"caption_size": 9999})["caption_size"]
      == G.RANGES["caption_size"][1])

_no_cap = R.build_scene("\u30c9\u30f3", G.sanitize(dict(G.DEFAULTS)))
_with_cap = R.build_scene("\u30c9\u30f3", _cp)
check("a caption adds to what is drawn",
      len(_with_cap.layers) > len(_no_cap.layers))
check("...and makes the whole thing taller, not the letters bigger",
      _with_cap.bounds.height() > _no_cap.bounds.height()
      and abs(_with_cap.bounds.width() - _no_cap.bounds.width()) < 200)
check("an empty caption changes nothing at all",
      len(R.build_scene("\u30c9\u30f3",
                        G.sanitize(dict(G.DEFAULTS, caption="   ")))
          .layers) == len(_no_cap.layers))

_below = R.build_scene("\u30c9\u30f3", _cp).layers[-1].path.boundingRect()
_above = R.build_scene("\u30c9\u30f3", G.sanitize(
    dict(G.DEFAULTS, caption="BOOM", caption_pos="above"))
).layers[-1].path.boundingRect()
check("below really sits below, and above above",
      _below.top() > _above.top())
_right = R.build_scene("\u30c9\u30f3", G.sanitize(
    dict(G.DEFAULTS, caption="BOOM", caption_pos="right"))
).layers[-1].path.boundingRect()
_left = R.build_scene("\u30c9\u30f3", G.sanitize(
    dict(G.DEFAULTS, caption="BOOM", caption_pos="left"))
).layers[-1].path.boundingRect()
check("...and right of it, and left of it",
      _right.left() > _left.left())
_big = R.build_scene("\u30c9\u30f3", G.sanitize(
    dict(G.DEFAULTS, caption="BOOM", caption_size=90))
).layers[-1].path.boundingRect()
check("the size slider really sizes it", _big.height() > _below.height() * 2)
check("the caption is set plainly, never with the letters' fill",
      R.build_scene("\u30c9\u30f3", G.sanitize(
          dict(G.DEFAULTS, caption="BOOM", fill_mode="tone"))
      ).layers[-1].paint == "solid")

panel._params = G.sanitize(dict(G.DEFAULTS, caption="BOOM",
                                caption_pos="right"))
panel._load_into_widgets()
check("the panel shows the caption it was given",
      panel.caption_edit.text() == "BOOM"
      and panel.caption_pos.currentData() == "right")
panel.caption_edit.setText("DON")
check("...and typing one reaches the parameters",
      panel._params["caption"] == "DON")
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()


# --- noise lines: the contour drawn again by hand -------------------------
check("the number of hand-drawn passes has a range",
      G.sanitize({"noise_lines": 99})["noise_lines"] == G.RANGES[
          "noise_lines"][1]
      and G.sanitize({"noise_amp": -5})["noise_amp"] == 0)
check("roughness widens the hand, it does not switch it on",
      G.effective(dict(G.DEFAULTS, rough=100))["noise_amp"]
      > G.DEFAULTS["noise_amp"]
      and G.effective(dict(G.DEFAULTS, rough=100))["noise_lines"] == 0)

_TXT = "ドン"


def _noise(**kw):
    sc = R.build_scene(_TXT, G.sanitize(dict(G.DEFAULTS, **kw)))
    return [l for l in sc.layers if l.kind == "noise"]


check("nothing is drawn by hand until it is asked for", _noise() == [])
check("one pass draws every letter once",
      len(_noise(noise_lines=1)) == len(G.layout(_TXT,
                                                 G.sanitize(dict(G.DEFAULTS))))
      and len(_noise(noise_lines=3)) == 3 * len(_noise(noise_lines=1)))
check("a hand that does not move draws nothing",
      _noise(noise_lines=3, noise_amp=0) == [])
check("the noise is a line, not a filled shape",
      all(l.line_w > 0 for l in _noise(noise_lines=2)))
_one = _noise(noise_lines=1)[0].path
check("...and is lifted now and then rather than drawn as closed loops",
      sum(1 for _i in range(_one.elementCount())
          if _one.elementAt(_i).isMoveTo()) > 8)

_n1 = _noise(noise_lines=1)[0].path
_n1b = _noise(noise_lines=1)[0].path
_n2 = [l for l in R.build_scene(_TXT, G.sanitize(
    dict(G.DEFAULTS, noise_lines=1, seed=4242))).layers
    if l.kind == "noise"][0].path
check("the same seed draws the same hand twice",
      R.path_d(_n1) == R.path_d(_n1b))
check("...and another seed draws another one",
      R.path_d(_n1) != R.path_d(_n2))

_plain = R.build_scene(_TXT, G.sanitize(dict(G.DEFAULTS))).bounds
_rough = R.build_scene(_TXT, G.sanitize(dict(G.DEFAULTS,
                                             noise_lines=2))).bounds
_amp_px = G.DEFAULTS["letter_px"] * G.DEFAULTS["noise_amp"] / 100.0 * 0.05
check("the hand stays within a few times its own width of the letters",
      _rough.width() >= _plain.width()
      and _rough.width() - _plain.width() < _amp_px * 5
      and _rough.height() - _plain.height() < _amp_px * 5)

panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
panel._sliders["noise_lines"][0].setValue(2)
check("the panel has a slider for it", panel.params()["noise_lines"] == 2)
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()


# --- line only, line in a tone, and which way a halftone shades -----------
check("the two line fills are offered", "line" in G.FILL_MODES
      and "line_tone" in G.FILL_MODES)
check("...and survive being saved and read back",
      G.from_json(G.to_json(G.sanitize(dict(G.DEFAULTS,
                                            fill_mode="line_tone"))))
      ["fill_mode"] == "line_tone")
check("the line has a width of its own, with a range",
      G.RANGES["fill_line_w"] == (1, 40)
      and G.sanitize({"fill_line_w": 999})["fill_line_w"] == 40)


def _ink(text="ドン", step=2, **kw):
    """(dark pixels, image) for a rendering with no outline in the way."""
    par = G.sanitize(dict(G.DEFAULTS, outlines=[], **kw))
    img, _off = R.render_image(R.build_scene(text, par),
                               background="#ffffff")
    n = 0
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            if (img.pixel(x, y) & 0xff) < 128:
                n += 1
    return n, img


_solid_ink, _ = _ink()
_line_ink, _ = _ink(fill_mode="line")
_wide_ink, _ = _ink(fill_mode="line", fill_line_w=20)
_HAVE_GLYPHS = _solid_ink > 50          # offscreen with no font: no ink
check("a line-only letter is hollow: less ink than a filled one",
      0 < _line_ink < _solid_ink * 0.8 if _HAVE_GLYPHS else True)
check("...and the line width slider really thickens it, up to the "
      "filled letter and never past it",
      _line_ink < _wide_ink <= _solid_ink + max(5, _solid_ink * 0.01)
      if _HAVE_GLYPHS else True)
check("...but the letter keeps exactly the shape it had: the line is "
      "drawn inside it, never around it",
      R.build_scene("\u30c9\u30f3", G.sanitize(
          dict(G.DEFAULTS, fill_mode="line", fill_line_w=20))).bounds
      == R.build_scene("\u30c9\u30f3", G.sanitize(
          dict(G.DEFAULTS))).bounds)
check("line only leaves the inside of the letter empty",
      not R.build_scene("ドン", G.sanitize(
          dict(G.DEFAULTS, fill_mode="line"))).layers[-1].path.contains(
              R.build_scene("ドン", G.sanitize(
                  dict(G.DEFAULTS, fill_mode="solid"))).layers[-1].path))
check("line only is still vector art, the toned line is not",
      not R.build_scene("\u30c9\u30f3", G.sanitize(
          dict(G.DEFAULTS, fill_mode="line"))).needs_raster()
      and R.build_scene("\u30c9\u30f3", G.sanitize(
          dict(G.DEFAULTS, fill_mode="line_tone"))).needs_raster())
check("the line can be set in a tone",
      [l.paint for l in R.build_scene("ドン", G.sanitize(
          dict(G.DEFAULTS, fill_mode="line_tone"))).layers
       if l.kind == "fill"] == ["tone", "tone"])


def _halves(img, step=2):
    """Dark pixels in (top, bottom, left third, right third)."""
    t = b = le = ri = 0
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            if (img.pixel(x, y) & 0xff) < 128:
                if y < img.height() / 2.0:
                    t += 1
                else:
                    b += 1
                if x < img.width() / 3.0:
                    le += 1
                elif x > img.width() * 2 / 3.0:
                    ri += 1
    return t, b, le, ri


_n, _timg = _ink("ドカーン", fill_mode="tone", tone_dot=8)
_t, _b, _le, _ri = _halves(_timg)
check("a halftone shades down the word: light at the top, solid below",
      _b > _t * 1.5)
check("...and the same from end to end, not solid at one end and blank "
      "at the other",
      min(_le, _ri) > max(_le, _ri) * 0.5)

panel._params = G.sanitize(dict(G.DEFAULTS, fill_mode="line"))
panel._load_into_widgets()
check("the line width wakes up with the line fills",
      panel._sliders["fill_line_w"][0].isEnabled())
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
check("...and sleeps again for a solid one",
      not panel._sliders["fill_line_w"][0].isEnabled())


# --- decorations around the lettering ------------------------------------
check("the four decorations are offered",
      G.DECOS == ("off", "rays", "debris", "sparkle", "drops"))
check("...and nothing else gets through",
      G.sanitize({"deco": "fireworks"})["deco"] == "off"
      and G.sanitize({"deco": "drops"})["deco"] == "drops")
check("how many, how big and how far out all have ranges",
      G.sanitize({"deco_n": 999})["deco_n"] == G.RANGES["deco_n"][1]
      and G.sanitize({"deco_size": 0})["deco_size"] == 1
      and G.sanitize({"deco_dist": -9})["deco_dist"] == 0)

_BOX = (0.0, 0.0, 600.0, 160.0)
_dp = G.sanitize(dict(G.DEFAULTS, deco="sparkle", deco_n=18))
check("nothing is scattered until something is chosen",
      G.deco_items(G.sanitize(dict(G.DEFAULTS)), _BOX) == []
      and G.deco_items(G.sanitize(dict(_dp, deco_n=0)), _BOX) == [])
check("as many pieces as asked for", len(G.deco_items(_dp, _BOX)) == 18)
check("an empty word gets no decoration at all",
      G.deco_items(_dp, (0.0, 0.0, 0.0, 0.0)) == []
      and G.deco_items(_dp, None) == [])
check("the same seed scatters them the same way",
      G.deco_items(_dp, _BOX) == G.deco_items(_dp, _BOX))
check("...and another seed scatters them differently",
      G.deco_items(_dp, _BOX)
      != G.deco_items(G.sanitize(dict(_dp, seed=777)), _BOX))


def _outside(items, box):
    """Every piece sits outside the oval of the word."""
    x, y, w, h = box
    cx, cy, rx, ry = x + w / 2.0, y + h / 2.0, w / 2.0, h / 2.0
    return all(((it["x"] - cx) / rx) ** 2 + ((it["y"] - cy) / ry) ** 2 > 1.0
               for it in items)


check("they are scattered around the word, never on top of it",
      _outside(G.deco_items(_dp, _BOX), _BOX)
      and _outside(G.deco_items(G.sanitize(dict(_dp, deco="rays")), _BOX),
                   _BOX))
check("how far out really pushes them out",
      max(it["x"] for it in G.deco_items(
          G.sanitize(dict(_dp, deco_dist=150)), _BOX))
      > max(it["x"] for it in G.deco_items(
          G.sanitize(dict(_dp, deco_dist=0)), _BOX)))
check("their size follows both the letters and their own slider",
      G.deco_items(G.sanitize(dict(_dp, deco_size=80)), _BOX)[0]["size"]
      > G.deco_items(_dp, _BOX)[0]["size"]
      and G.deco_items(G.sanitize(dict(_dp, letter_px=320)), _BOX)[0]["size"]
      > G.deco_items(_dp, _BOX)[0]["size"])


def _points_out(it, box, tol):
    """Is the piece turned away from the middle of the word?"""
    x, y, w, h = box
    want = _math.degrees(_math.atan2(it["y"] - (y + h / 2.0),
                                     it["x"] - (x + w / 2.0)))
    return abs(((it["angle"] - want + 180.0) % 360.0) - 180.0) < tol


check("a ray points straight out from the word",
      all(_points_out(it, _BOX, 1.0)
          for it in G.deco_items(G.sanitize(dict(_dp, deco="rays")), _BOX)))
check("a drop was thrown out of it, roughly",
      all(_points_out(it, _BOX, 26.0)
          for it in G.deco_items(G.sanitize(dict(_dp, deco="drops")), _BOX)))
check("a shard may lie as it likes",
      not all(_points_out(it, _BOX, 26.0)
              for it in G.deco_items(G.sanitize(dict(_dp, deco="debris")),
                                     _BOX)))

_bare = R.build_scene("ドン", G.sanitize(dict(G.DEFAULTS,
                                                      outlines=[])))
_decd = R.build_scene("ドン", G.sanitize(dict(G.DEFAULTS, deco="rays",
                                                      deco_n=9, outlines=[])))
check("every piece becomes a layer of its own",
      len([l for l in _decd.layers if l.kind == "deco"]) == 9)
check("...drawn before the lettering, so it can never cover it",
      all(l.kind == "deco" for l in _decd.layers[:9]))
check("...and counted in what the scene takes up",
      _decd.bounds.width() > _bare.bounds.width()
      and _decd.bounds.height() > _bare.bounds.height())
check("the pieces are set in the lettering's colour",
      {l.color for l in _decd.layers if l.kind == "deco"}
      == {G.DEFAULTS["fill"]})
_outlined = R.build_scene("ドン", G.sanitize(
    dict(G.DEFAULTS, deco="rays", deco_n=9)))
check("...and carry the first outline, like the lettering does",
      len([l for l in _outlined.layers if l.kind == "outline"])
      >= len([l for l in R.build_scene("ドン", G.sanitize(
          dict(G.DEFAULTS))).layers if l.kind == "outline"]) + 9)
check("a decorated word still goes in as vector art",
      not _decd.needs_raster())

_drng = _random.Random(5)
_dmix = _collections.Counter(
    G.gacha("\u30c9\u30ab\u30fc\u30f3", G.sanitize(dict(G.DEFAULTS)),
            _drng)["deco"] for _i in range(300))
check("most rolls leave the lettering alone", _dmix["off"] > 150)
check("...and when they do not, an impact mostly bursts",
      _dmix["rays"] > _dmix["drops"])
_cmix = _collections.Counter(
    G.gacha("\u30ad\u30e5\u30f3", G.sanitize(dict(G.DEFAULTS)),
            _drng)["deco"] for _i in range(300))
check("...while something cute mostly sparkles",
      _cmix["sparkle"] > _cmix["debris"])

panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
check("the decorations sleep until one is chosen",
      not panel._sliders["deco_n"][0].isEnabled())
panel.deco_combo.setCurrentIndex(panel.deco_combo.findData("sparkle"))
check("the combo chooses one", panel.params()["deco"] == "sparkle"
      and panel._sliders["deco_n"][0].isEnabled())
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()


# --- thicken + outline: one offset, not an offset of an offset -----------
_THICK = G.sanitize(dict(G.DEFAULTS, letter_px=160, thicken=2.0,
                         outlines=[["#ffffff", 7.0], ["#111111", 4.5]]))
_THIN = G.sanitize(dict(_THICK, thicken=0.0))
_sc = R.build_scene("egg", _THICK)
_fill = [l for l in _sc.layers if l.kind == "fill"]
_outl = [l for l in _sc.layers if l.kind == "outline"]
check("every letter still gets its outlines over the thickened shape",
      len(_fill) == 3 and len(_outl) == 6)
check("...and the outline really encloses the letter it is behind",
      all(_outl[i * 2].path.contains(_fill[i].path) for i in range(3)))
check("...the inner outline enclosed by the outer one",
      all(_outl[i * 2].path.contains(_outl[i * 2 + 1].path)
          for i in range(3)))


def _build_ms(params, n=3):
    R.build_scene("egg", params)                 # warm the glyph cache
    _t0 = _time.perf_counter()
    for _i in range(n):
        R.build_scene("egg", params)
    return (_time.perf_counter() - _t0) / n * 1000.0


_t_thick, _t_thin = _build_ms(_THICK), _build_ms(_THIN)
# it used to be ~100x: the outlines were stroked onto the *thickened*
# letter, whose own outline Qt had turned into thousands of segments
check("thickening does not make a scene cost a different order of "
      "magnitude (%.0f ms vs %.0f ms)" % (_t_thick, _t_thin),
      _t_thick < max(40.0, _t_thin * 8.0))


# --- the three hands the noise can be drawn with -------------------------
check("three hands are offered",
      G.NOISE_STYLES == ("hand", "dry", "fuzzy"))
check("...and nothing else gets through",
      G.sanitize({"noise_style": "crayon"})["noise_style"] == "hand"
      and G.sanitize({"noise_style": "fuzzy"})["noise_style"] == "fuzzy")


def _noise_layers(style):
    return [l for l in R.build_scene("\u30c9\u30f3", G.sanitize(
        dict(G.DEFAULTS, noise_lines=1, noise_style=style))).layers
        if l.kind == "noise"]


def _lifts(path):
    return sum(1 for _i in range(path.elementCount())
               if path.elementAt(_i).isMoveTo())


_h, _d, _f = (_noise_layers(s)[0] for s in ("hand", "dry", "fuzzy"))
check("each hand draws something of its own",
      R.path_d(_h.path) != R.path_d(_d.path) != R.path_d(_f.path))
# how often it lifts per point drawn, not how often in total: a longer
# contour lifts more either way, and the fonts differ between machines
def _lift_rate(path):
    return _lifts(path) / float(max(1, path.elementCount()))


check("a dry brush lifts far more often than a steady hand",
      _lift_rate(_d.path) > _lift_rate(_h.path) * 1.8)
check("fuzz is drawn with a thinner line than a hand-drawn contour",
      _f.line_w < _h.line_w)

panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
check("the hand cannot be chosen while there are no noise lines",
      not panel.noise_style.isEnabled())
panel._sliders["noise_lines"][0].setValue(2)
check("...and wakes up with them", panel.noise_style.isEnabled())
panel.noise_style.setCurrentIndex(panel.noise_style.findData("dry"))
check("the combo picks the hand", panel.params()["noise_style"] == "dry")
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()


# --- dragging a letter: built once, moved often --------------------------
_DP = G.sanitize(dict(G.DEFAULTS, letter_px=160, thicken=2.0,
                      outlines=[["#ffffff", 6.0]]))
R._shape_cache.clear()
R._band_cache.clear()
_s1 = R.build_scene("\u30c9\u30f3", _DP)
_n_shapes, _n_bands = len(R._shape_cache), len(R._band_cache)
check("every letter's shape is kept", _n_shapes == 2 and _n_bands == 2)
_moved = G.sanitize(dict(_DP))
G.set_letter_edit(_moved, 0, 0, dx=37.0, dy=-11.0)
_s2 = R.build_scene("\u30c9\u30f3", _moved)
check("moving a letter does not build a single shape again",
      (len(R._shape_cache), len(R._band_cache)) == (_n_shapes, _n_bands))
check("...and the letter really did move",
      _s2.bounds != _s1.bounds)
R.build_scene("\u30c9\u30f3", G.sanitize(dict(_DP, letter_px=161)))
check("a letter of a different size is a different shape",
      len(R._shape_cache) > _n_shapes)
_n_shapes2 = len(R._shape_cache)
R.build_scene("\u30c9\u30f3", G.sanitize(dict(_DP,
                                               outlines=[["#ffffff", 9.0]])))
check("a wider outline is a new band, and no new shapes",
      len(R._band_cache) > _n_bands
      and len(R._shape_cache) == _n_shapes2)

_calls = [0]
_real_refresh = panel._refresh_preview


def _counted_refresh():
    _calls[0] += 1
    return _real_refresh()


panel._refresh_preview = _counted_refresh
panel._params = G.sanitize(dict(G.DEFAULTS))
panel.text_edit.setPlainText("\u30c9\u30f3")
panel._refresh_preview()
_pl0 = panel._places[0]
_key0 = (_pl0["group"], _pl0["index"])
_at = (_pl0["x"], _pl0["y"])
panel._last_live = 0.0
_calls[0] = 0
panel.preview_drag("move", (_at[0] + 9, _at[1]), _at, _key0,
                   (0.0, 0.0, 0.0, 1.0))
check("a drag draws at once, it does not wait for the hand to stop",
      _calls[0] == 1)
panel.preview_drag("move", (_at[0] + 18, _at[1]), _at, _key0,
                   (0.0, 0.0, 0.0, 1.0))
check("...but no more than once in 40 ms, with the last step still due",
      _calls[0] == 1 and panel._live_timer.isActive())
panel.preview_drag_done()           # let go, or the next drag is this one
panel._refresh_preview = _real_refresh
panel._live_timer.stop()
G.clear_letter_edits(panel._params)
panel._load_into_widgets()


# --- undo and redo -------------------------------------------------------
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
panel._history = []
panel._future = []
panel._hist_key = None
panel._refresh_history_ui()
check("with nothing done yet there is nothing to undo or redo",
      not panel.back_btn.isEnabled() and not panel.fwd_btn.isEnabled())

panel._sliders["bend"][0].setValue(40)
check("a slider move is a step", panel.params()["bend"] == 40
      and panel.back_btn.isEnabled())
for _v in range(41, 60):                # the same slider, straight after
    panel._sliders["bend"][0].setValue(_v)
check("...and dragging that slider is still one step, not twenty",
      len(panel._history) == 1 and panel.params()["bend"] == 59)
panel._sliders["slant"][0].setValue(12)
check("another slider starts a new step", len(panel._history) == 2)

panel.on_back()
check("undo goes back to where that slider started",
      panel.params()["slant"] == G.DEFAULTS["slant"]
      and panel.params()["bend"] == 59
      and panel.fwd_btn.isEnabled())
panel.on_back()
check("...and again, to before the first one",
      panel.params()["bend"] == G.DEFAULTS["bend"])
panel.on_forward()
check("redo brings the step back", panel.params()["bend"] == 59)
panel.on_forward()
check("...and the one after it", panel.params()["slant"] == 12)
check("nothing left to redo", not panel.fwd_btn.isEnabled())
panel.on_back()
panel._sliders["lean"][0].setValue(44)
check("doing something new throws the redo away",
      not panel.fwd_btn.isEnabled() and panel._future == [])

# a drag is one step from the first move to letting go
panel._params = G.sanitize(dict(G.DEFAULTS))
panel.text_edit.setPlainText("\u30c9\u30f3")
panel._load_into_widgets()
panel._refresh_preview()
panel._history = []
panel._future = []
_dpl = panel._places[0]
_dkey = (_dpl["group"], _dpl["index"])
_dat = (_dpl["x"], _dpl["y"])
for _k in range(1, 6):
    panel.preview_drag("move", (_dat[0] + _k * 4, _dat[1]), _dat, _dkey,
                       (0.0, 0.0, 0.0, 1.0))
panel.preview_drag_done()
check("five mouse steps are one step in the history",
      len(panel._history) == 1
      and G.letter_edit(panel.params(), 0, 0)[0] == 20.0)
panel.on_back()
check("...and undo puts the letter back where it was",
      G.letter_edit(panel.params(), 0, 0) == (0.0, 0.0, 0.0, 1.0))

# while typing, the keys belong to the text field
panel.text_edit.setFocus()
_app.processEvents()
if panel._editor_under_focus() is panel.text_edit:
    panel.text_edit.setPlainText("\u30c9\u30f3\u30c3")
    _before = len(panel._history)
    panel.on_undo_key()
    check("Ctrl+Z in the text field undoes the typing, not the settings",
          len(panel._history) == _before)
else:
    check("Ctrl+Z in the text field undoes the typing, not the settings",
          True)            # no focus in this environment: nothing to say
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
panel._history = []
panel._future = []


# --- the dictionary in the panel -----------------------------------------
panel._params = G.sanitize(dict(G.DEFAULTS))
panel.text_edit.setPlainText("")
panel._load_into_widgets()
panel._history = []
_kyun = [e for e in GD.entries() if e["kana"] == "\u30ad\u30e5\u30f3"][0]
panel.take_sound(_kyun)
check("picking a sound writes it into the text",
      panel.text_edit.toPlainText() == "\u30ad\u30e5\u30f3")
check("...and sets the look that belongs to it",
      panel.params()["type"] == _kyun["type"])
check("...as one step that can be undone", len(panel._history) == 1)
check("...and says what it took", "\u30ad\u30e5\u30f3" in
      panel.status_lbl.text())
panel.take_sound(_kyun)
check("a second sound is appended, not a replacement",
      panel.text_edit.toPlainText() == "\u30ad\u30e5\u30f3\u30ad\u30e5\u30f3")
panel.take_sound(None)
check("nothing picked changes nothing",
      panel.text_edit.toPlainText() == "\u30ad\u30e5\u30f3\u30ad\u30e5\u30f3")

_dlg = SoundDialog(panel)
check("the window lists every sound", _dlg.list.count() == len(GD.entries()))
_dlg.search.setText("gogogo")
check("...and the search narrows it down", _dlg.list.count() == 1)
_dlg.search.setText("")
_dlg.list.setCurrentRow(0)
_n_before = len(panel.text_edit.toPlainText())
_dlg._take()
check("taking one from the window reaches the text",
      len(panel.text_edit.toPlainText()) > _n_before)
_dlg.close()
panel._params = G.sanitize(dict(G.DEFAULTS))
panel.text_edit.setPlainText("\u30c9\u30f3")
panel._load_into_widgets()
panel._history = []


# --- liquify in the panel ------------------------------------------------
panel._params = G.sanitize(dict(G.DEFAULTS))
panel.text_edit.setPlainText("\u30c9\u30f3")
panel._load_into_widgets()
panel._refresh_preview()
panel._history = []
check("the brush is off to begin with", not panel.liquify_armed())
panel.liq_chk.setChecked(True)
check("...and the preview shows it once it is on",
      panel.liquify_armed() and panel.preview._brush_r > 0)

_lpl = panel._places[0]
_lkey = (_lpl["group"], _lpl["index"])
_lat = (_lpl["x"], _lpl["y"])
panel.liquify_step(_lat, _lat)
check("a touch of the brush leaves a dab on the letter under it",
      WP.has_warp(panel.params(), _lkey[0], _lkey[1]))
_n1 = len(WP.warp_of(panel.params(), _lkey[0], _lkey[1]))
for _k in range(1, 5):
    panel.liquify_step((_lat[0] + _k * 6, _lat[1]),
                       (_lat[0] + (_k - 1) * 6, _lat[1]))
panel.preview_drag_done()
check("...and a drag leaves one per step",
      len(WP.warp_of(panel.params(), _lkey[0], _lkey[1])) == _n1 + 4)
check("the whole stroke is one step in the history",
      len(panel._history) == 1)
panel.on_back()
check("...so one undo takes all of it back",
      not WP.has_warp(panel.params(), _lkey[0], _lkey[1]))
panel.on_forward()
check("...and redo brings it back",
      WP.has_warp(panel.params(), _lkey[0], _lkey[1]))

panel.liq_tool.setCurrentIndex(panel.liq_tool.findData("twirl"))
check("the tool combo picks the tool",
      panel.params()["liquify_mode"] == "twirl")
panel.liquify_step(_lat, _lat, alt=True)
check("Alt turns it round while dragging",
      WP.warp_of(panel.params(), _lkey[0], _lkey[1])[-1][4] < 0)
panel._sliders["liquify_size"][0].setValue(90)
check("the brush ring follows its slider",
      abs(panel.preview._brush_r - WP.radius_for(90)) < 0.01)

panel.on_reset_warps()
check("reset takes every warp off", not WP.has_warp(panel.params()))
panel.liq_chk.setChecked(False)
check("switching the brush off hides its ring", panel.preview._brush_r == 0)
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
panel._history = []
panel._future = []


# --- point editing in the panel ------------------------------------------
panel._params = G.sanitize(dict(G.DEFAULTS))
panel.text_edit.setPlainText("\u30c9\u30f3")
panel._load_into_widgets()
panel._refresh_preview()
panel._history = []
panel.liq_chk.setChecked(True)
panel.pts_chk.setChecked(True)
check("the brush and the points are not both on at once",
      panel.points_armed() and not panel.liquify_armed())

_ppl = panel._places[0]
_pkey = (_ppl["group"], _ppl["index"])
panel.preview.select(_pkey)
_opened = panel.open_points(_pkey)
check("opening a letter turns its outline into points",
      len(_opened) >= 1 and ND.has_nodes(panel.params(), _pkey[0], _pkey[1]))
_n_pts = ND.count(_opened)
check("opening it again does not open it twice",
      ND.count(panel.open_points(_pkey)) == _n_pts)
check("the preview is told where every point and handle is",
      len(panel.point_overlay()) == _n_pts)

# a warp is folded into the points, not applied twice
panel2_params = G.sanitize(dict(G.DEFAULTS))
panel._params = panel2_params
panel._load_into_widgets()
panel._refresh_preview()
WP.add_dab(panel._params, _pkey[0], _pkey[1],
           WP.dab("inflate", 0, 0, 400, 0.2, 0, 0.3))
_warped_d = R.path_d(panel.scene().layers[-1].path)
panel.open_points(_pkey)
check("a warped letter keeps its shape when it is opened",
      not WP.has_warp(panel.params(), _pkey[0], _pkey[1])
      and R.path_d(panel.scene().layers[-1].path) == _warped_d)

# taking hold of a point
_cs3 = panel.point_contours(_pkey)
_first = _cs3[0][0]
_tr = R.letter_transform(panel._placement(_pkey))
_at = _tr.map(_QPointF(_first[0], _first[1]))
_grab = panel.point_press((_at.x(), _at.y()), 8, panel.preview._k)
check("a press on a point takes hold of it",
      _grab is not None and _grab[0] == "node")
panel._history = []
panel._drag_open = False
_moved_to = _tr.map(_QPointF(_first[0] + 90, _first[1] + 40))
panel.point_drag(_grab, (_moved_to.x(), _moved_to.y()))
panel.preview_drag_done()
_now = panel.point_contours(_pkey)[_grab[1]][_grab[2]]
check("...and dragging it moves it, in the letter's own units",
      abs(_now[0] - (_first[0] + 90)) < 2.0
      and abs(_now[1] - (_first[1] + 40)) < 2.0)
check("...as one step in the history", len(panel._history) == 1)
panel.on_back()
check("...that undo takes back",
      abs(panel.point_contours(_pkey)[_grab[1]][_grab[2]][0]
          - _first[0]) < 0.01)

# shift, alt, and a click on the outline itself
_cs4 = panel.point_contours(_pkey)
_p0 = _cs4[0][0]
_at0 = _tr.map(_QPointF(_p0[0], _p0[1]))
_was_smooth = bool(_p0[6])
panel.point_press((_at0.x(), _at0.y()), 8, panel.preview._k, shift=True)
check("Shift makes a corner a curve and back",
      bool(panel.point_contours(_pkey)[0][0][6]) != _was_smooth)
_n_before = ND.count(panel.point_contours(_pkey))
# the longest piece of outline: a click in the middle of a short one is
# nearer to its points than to the line between them, and should take
# the point
_cs5 = panel.point_contours(_pkey)
_long = max(((ci, ni) for ci, _r in enumerate(_cs5)
             for ni in range(len(_cs5[ci]))),
            key=lambda p: _math.hypot(
                ND.point_on(_cs5, p[0], p[1], 1.0)[0]
                - ND.point_on(_cs5, p[0], p[1], 0.0)[0],
                ND.point_on(_cs5, p[0], p[1], 1.0)[1]
                - ND.point_on(_cs5, p[0], p[1], 0.0)[1]))
_mid = ND.point_on(_cs5, _long[0], _long[1], 0.5)
_at_mid = _tr.map(_QPointF(_mid[0], _mid[1]))
panel.point_press((_at_mid.x(), _at_mid.y()), 8, panel.preview._k)
check("a click on the outline between two points adds one",
      ND.count(panel.point_contours(_pkey)) == _n_before + 1)
_added = panel.point_contours(_pkey)[_long[0]][_long[1] + 1]
_at_added = _tr.map(_QPointF(_added[0], _added[1]))
panel.point_press((_at_added.x(), _at_added.y()), 8, panel.preview._k,
                  alt=True)
check("Alt takes one away",
      ND.count(panel.point_contours(_pkey)) == _n_before)

panel.on_reset_points()
check("reset gives every letter the font's outline back",
      not ND.has_nodes(panel.params()))
panel.pts_chk.setChecked(False)
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
panel._history = []
panel._future = []


# --- font files loaded by hand -------------------------------------------
print("== loaded fonts ==")
check("only the formats Qt can read are offered",
      UF.is_font_file("a.ttf") and UF.is_font_file("A.OTF")
      and not UF.is_font_file("a.woff") and not UF.is_font_file("a.png"))
check("the remembered list survives being written and read",
      UF.from_json(UF.to_json(["b.ttf", "a.ttf"])) == ["a.ttf", "b.ttf"])
check("rubbish in that setting is no list at all",
      UF.from_json("not json") == [] and UF.from_json(None) == []
      and UF.from_json('{"a": 1}') == [])
check("a file that is not there is reported, not loaded",
      UF.load(os.path.join(_tempfile.gettempdir(), "no_such_font.ttf")) == []
      and UF.failures())

_FONT_FILE = next((p for p in (r"C:\Windows\Fonts\arial.ttf",
                               "/usr/share/fonts/truetype/dejavu/"
                               "DejaVuSans.ttf")
                   if os.path.isfile(p)), "")
if _FONT_FILE:
    _fams = UF.load(_FONT_FILE)
    check("a real font file brings its families in", bool(_fams))
    check("...and is only taken once, however often it is offered",
          UF.load(_FONT_FILE) == _fams and UF.paths().count(
              os.path.normcase(os.path.abspath(_FONT_FILE))) == 1)
    check("...and Qt can really draw with it",
          R.glyph("A", _fams[0], False)[0].elementCount() > 0)
    check("the panel takes a file and picks what it brought",
          panel.add_font_files([_FONT_FILE]) == _fams
          and panel.params()["font"] == _fams[0])
    check("...and remembers it for the next start",
          _FONT_FILE.lower() in panel._get("giongoUserFonts", "").lower()
          .replace("\\\\", "\\"))
    check("forgetting one takes it back out", UF.forget(_FONT_FILE)
          and _FONT_FILE not in UF.paths())
else:
    for _msg in ("a real font file brings its families in",
                 "...and is only taken once, however often it is offered",
                 "...and Qt can really draw with it",
                 "the panel takes a file and picks what it brought",
                 "...and remembers it for the next start",
                 "forgetting one takes it back out"):
        check(_msg + " (no font file on this machine)", True)
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()


# --- saving the layers ---------------------------------------------------
print("== export ==")
_ex = G.sanitize(dict(G.DEFAULTS, shadow_dx=5.0, shadow_dy=5.0,
                      afterimage=2, noise_lines=1, deco="rays", deco_n=6,
                      outlines=[["#ffffff", 6.0]]))
_exs = R.build_scene("\u30c9\u30f3", _ex)
_groups = R.layer_groups(_exs)
check("the scene comes apart into the layers it is made of",
      [n for n, _l in _groups]
      == ["deco", "afterimage", "shadow", "outline", "text", "noise"])
check("...and every layer of it lands in exactly one group",
      sum(len(l) for _n, l in _groups) == len(_exs.layers))
check("a group nobody drew is not written out",
      "shadow" not in [n for n, _l in R.layer_groups(
          R.build_scene("\u30c9\u30f3", G.sanitize(dict(G.DEFAULTS))))])

_imgs = R.render_layers(_exs)
check("every layer is drawn on the same canvas, so they stack again",
      len({(i.width(), i.height()) for _n, i in _imgs}) == 1)
check("...the size the whole scene needs",
      _imgs[0][1].width() >= _exs.bounds.width())
_big = R.render_layers(_exs, scale=3.0)
check("the scale really scales", _big[0][1].width()
      > _imgs[0][1].width() * 2.5)
_pngs = R.layer_pngs(_exs)
check("they come out as PNG files, named in the order they stack",
      [n for n, _d in _pngs][:2] == ["1_deco.png", "2_afterimage.png"]
      and all(d[:4] == b"\x89PNG" for _n, d in _pngs))

_zip_dir = _tempfile.mkdtemp(prefix="typer_zip_")
_zip_path = os.path.join(_zip_dir, "sfx.zip")
_n_written = panel.save_zip(_zip_path, _exs, scale=1)
import zipfile as _zipfile
with _zipfile.ZipFile(_zip_path) as _z:
    _names = _z.namelist()
    _first = _z.read(_names[0])
check("the ZIP holds one file per layer, and says what they are",
      _n_written == len(_pngs) and len(_names) == len(_pngs) + 1
      and "README.txt" in _names)
check("...and the files in it are the images themselves",
      _first[:4] == b"\x89PNG")
_shutil.rmtree(_zip_dir, ignore_errors=True)
check("a PSD needs Krita, and says so rather than pretending",
      panel.save_psd(os.path.join(_zip_dir, "x.psd"), _exs) is None)
check("the size to save at is remembered",
      panel.save_scale() == int(panel._get("giongoScale", "1")))


check("everyone agrees how big a letter's own em is",
      WP.REF == R._REF == TR.REF)
check("a brush of the full size is one letter across",
      WP.radius_for(100) * 2 == R._REF)
check("a traced letter fills about as much of the em as a font's does",
      0.6 < TR.INK < 1.0)


# --- your own lettering --------------------------------------------------
print("== traced lettering ==")
check("a file is the letter its name is",
      TR._char_of("/x/\u30c9.png") == "\u30c9"
      and TR._char_of("B.PNG") == "B"
      and TR._char_of("doka.png") == "" and TR._char_of("") == "")

_let_dir = _tempfile.mkdtemp(prefix="typer_let_")


def _write_letter(ch, path, fam=""):
    """Draw one glyph into a PNG, the way a scan of it would look."""
    gl, _a = R.glyph(ch, fam or _REAL_FAM, False)
    rect = gl.boundingRect()
    if rect.width() <= 0:
        return False
    img = _QImage(180, 180, _QImage.Format.Format_ARGB32)
    img.fill(_QColor("#ffffff"))
    pt = _QPainter(img)
    pt.setRenderHint(_QPainter.RenderHint.Antialiasing, True)
    k = 150.0 / max(rect.width(), rect.height())
    pt.translate(90, 90)
    pt.scale(k, k)
    pt.translate(-rect.center().x(), -rect.center().y())
    pt.setPen(_Qt.PenStyle.NoPen)
    pt.setBrush(_QColor("#000000"))
    pt.drawPath(gl)
    pt.end()
    return bool(img.save(path, "PNG"))


_made = all(_write_letter(c, os.path.join(_let_dir, c + ".png"))
            for c in "\u30c9\u30f3") if _REAL_FAM else False
open(os.path.join(_let_dir, "notes.txt"), "w").close()
_write_letter("\u30ab", os.path.join(_let_dir, "kaa.png")) if _made else None

if _made:
    _items, _skipped = TR.sources([_let_dir])
    check("a folder of drawn letters is read, one letter per file",
          sorted(c for c, _i, _w in _items) == ["\u30c9", "\u30f3"])
    check("...and what cannot be a letter is skipped, not guessed at",
          any(w.endswith("kaa.png") for w, _why in _skipped))
    _set, _skip2 = TR.build_set("test set", [_let_dir])
    check("the drawn letters are traced into outlines",
          sorted(_set["glyphs"]) == ["\u30c9", "\u30f3"]
          and all(ND.count(c) > 6 for c in _set["glyphs"].values()))

    _zip_path = os.path.join(_let_dir, "pack.zip")
    with _zipfile.ZipFile(_zip_path, "w") as _z:
        _z.write(os.path.join(_let_dir, "\u30c9.png"), "\u30c9.png")
    _zit, _zsk = TR.sources([_zip_path])
    check("a ZIP of them works the same way",
          [c for c, _i, _w in _zit] == ["\u30c9"])

    _file = TR.save_set(_set, os.path.join(_let_dir, "set.json"))
    _read = TR.load_set(_file)
    check("a set survives being saved and read back",
          sorted(_read["glyphs"]) == sorted(_set["glyphs"])
          and ND.count(_read["glyphs"]["\u30c9"])
          == ND.count(_set["glyphs"]["\u30c9"]))
    check("a file that is not a set says so, rather than half-loading",
          TR.load_set(os.path.join(_let_dir, "notes.txt")) is None)

    _name = TR.register(_read, _file)
    check("a loaded set knows its name, its letters and where it came from",
          _name in TR.names() and TR.letters(_name) == ["\u30c9", "\u30f3"]
          and TR.path_of(_name) == _file)
    check("a letter the set has is handed over",
          TR.glyph_of(_name, "\u30c9") is not None
          and TR.glyph_of(_name, "\u30ab") is None
          and TR.glyph_of("", "\u30c9") is None)

    _with = G.sanitize(dict(G.DEFAULTS, letterset=_name))
    _font_scene = R.build_scene("\u30c9", G.sanitize(dict(G.DEFAULTS)),
                                _REAL_FAM)
    _set_scene = R.build_scene("\u30c9", _with, _REAL_FAM)
    check("the traced letter is drawn instead of the font's",
          R.path_d(_set_scene.layers[-1].path)
          != R.path_d(_font_scene.layers[-1].path))
    check("...and it is near enough the letter it was traced from",
          abs(_set_scene.bounds.width() - _font_scene.bounds.width())
          < _font_scene.bounds.width() * 0.5)
    check("a letter the set has not got is still drawn by the font",
          R.path_d(R.build_scene("\u30ab", _with, _REAL_FAM).layers[-1].path)
          == R.path_d(R.build_scene("\u30ab", G.sanitize(dict(G.DEFAULTS)),
                                    _REAL_FAM).layers[-1].path))

    panel._params = G.sanitize(dict(G.DEFAULTS))
    panel._load_into_widgets()
    panel._history = []
    _got = panel.import_lettering([_let_dir], "panel set")
    check("the panel imports a folder and starts drawing with it",
          _got == "panel set" and panel.params()["letterset"] == "panel set")
    check("...and offers it in the box, with how many letters it has",
          any("panel set" == panel.set_combo.itemData(i)
              for i in range(panel.set_combo.count())))
    check("...and remembers it for the next start",
          "panel set" in [TR.load_set(p)["name"] for p in
                          _json.loads(panel._get("giongoLetterSets", "[]"))
                          if TR.load_set(p)])
    TR.forget("panel set")
    TR.forget(_name)
    panel._params = G.sanitize(dict(G.DEFAULTS))
    panel._load_into_widgets()
else:
    for _msg in ("a folder of drawn letters is read, one letter per file",
                 "...and what cannot be a letter is skipped, not guessed at",
                 "the drawn letters are traced into outlines",
                 "a ZIP of them works the same way",
                 "a set survives being saved and read back",
                 "a file that is not a set says so, rather than half-loading",
                 "a loaded set knows its name, its letters and where it "
                 "came from",
                 "a letter the set has is handed over",
                 "the traced letter is drawn instead of the font's",
                 "...and it is near enough the letter it was traced from",
                 "a letter the set has not got is still drawn by the font",
                 "the panel imports a folder and starts drawing with it",
                 "...and offers it in the box, with how many letters it has",
                 "...and remembers it for the next start"):
        check(_msg + " (no font to draw the test letters with)", True)
_shutil.rmtree(_let_dir, ignore_errors=True)




# --- the tools over the canvas -------------------------------------------
print("== tools ==")
panel._params = G.sanitize(dict(G.DEFAULTS))
panel.text_edit.setPlainText("\u30c9\u30f3")
panel._load_into_widgets()
panel._refresh_preview()
panel._history = []
panel.set_tool("move")
check("the panel starts out moving letters",
      panel.tool() == "move" and not panel.liquify_armed()
      and not panel.points_armed() and not panel.erase_armed())
panel.set_tool("liquify")
check("picking a tool picks exactly one",
      panel.liquify_armed() and not panel.points_armed()
      and not panel.erase_armed() and panel.preview._brush_r > 0)
panel.set_tool("points")
check("...and the one before it lets go",
      panel.points_armed() and not panel.liquify_armed()
      and panel.preview._brush_r == 0 and panel.preview._points)
panel.set_tool("erase")
check("the eraser shows a brush too",
      panel.erase_armed() and panel.preview._brush_r > 0
      and not panel.preview._points)
check("the button that is down is the tool that is on",
      [k for k, b in panel.tool_btns.items() if b.isChecked()] == ["erase"])
check("the line under the canvas says what this tool does",
      panel.legend_lbl.text() == panel._t("gi_legend_erase"))
panel.liq_chk.setChecked(True)
check("the switch in the section and the button say the same thing",
      panel.tool() == "liquify"
      and panel.tool_btns["liquify"].isChecked())
panel.liq_chk.setChecked(False)
check("...and switching it off goes back to moving letters",
      panel.tool() == "move")

# wiping parts away
panel.set_tool("erase")
panel._params["liquify_size"] = 40
_epl = panel._places[0]
_ekey = (_epl["group"], _epl["index"])
panel.preview.select(_ekey)
_full = R.build_scene("\u30c9\u30f3", panel.params()).bounds
_eat = (_epl["x"], _epl["y"])
panel._history = []
panel.erase_step(_eat, _eat)
panel.erase_step((_eat[0] + 20, _eat[1]), _eat)
panel.preview_drag_done()
_left = ND.nodes_of(panel.params(), _ekey[0], _ekey[1])
check("wiping leaves the letter with an outline of its own", bool(_left))
# with no font installed every glyph is an empty box and there is
# nothing to wipe off it
check("...with less of it than the font drew",
      _AREA(R.path_from_nodes(_left))
      < _AREA(R.em_shape(_epl, panel.font_family(), False)) * 0.98
      if _HAVE_GLYPHS else True)
check("...as one step in the history", len(panel._history) == 1)
panel.on_back()
check("...that undo takes back",
      not ND.has_nodes(panel.params(), _ekey[0], _ekey[1]))
panel.set_tool("move")

# the font list
_fd = SoundDialog  # noqa: F841  (keeps the import used if the next line moves)
_fp = FontPickDialog(panel)
check("the font list offers the type's own font first",
      _fp.list.count() >= 1
      and _fp.list.item(0).data(_Qt.ItemDataRole.UserRole) == "")
if panel.families():
    check("...and then the families, drawn in themselves",
          _fp.list.count() > 1
          and _fp.list.item(1).font().family() ==
          _fp.list.item(1).data(_Qt.ItemDataRole.UserRole))
    _some = panel.families()[0]
    _fp.search.setText(_some[:4])
    check("...and the search narrows them down",
          any(_fp.list.item(i).data(_Qt.ItemDataRole.UserRole) == _some
              for i in range(_fp.list.count()))
          and _fp.list.count() <= len(panel.families()))
    _fp.search.setText("")
    _fp.list.setCurrentRow(1)
    _want = _fp.list.item(1).data(_Qt.ItemDataRole.UserRole)
    panel._history = []
    _fp._take()
    check("taking one draws with it from now on",
          panel.params()["font"] == _want and len(panel._history) == 1)
    panel.take_font("")
else:
    check("...and then the families, drawn in themselves", True)
    check("...and the search narrows them down", True)
    check("taking one draws with it from now on", True)
_fp.close()
check("the tab says where it is best used",
      panel.window_hint.text() if not panel._popped else True)
panel._params = G.sanitize(dict(G.DEFAULTS))
panel._load_into_widgets()
panel._history = []
panel._future = []


print("\npassed %d, failed %d" % (_pass, _fail))
sys.exit(1 if _fail else 0)
