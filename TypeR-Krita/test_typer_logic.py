# -*- coding: utf-8 -*-
"""Standalone tests for TypeR's Qt-free helpers (no Krita/PyQt5 needed).

Run:  python test_typer_logic.py
Covers detect_manga() and default_preset_for() in typer_kr/langpair.py.
"""
import importlib.util
import math
import os
import re
import sys

# the Windows console defaults to cp1252, which cannot print the kana used
# in some test names
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "langpair", os.path.join(_HERE, "typer_kr", "langpair.py"))
LP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LP)

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  ok   " + name)
    else:
        _fail += 1
        print("  FAIL " + name)


# --- detect_manga ----------------------------------------------------------
saved = ["Sakamoto Days", "Spy x Family", "One Piece"]
check("filename hit",
      LP.detect_manga(saved, "body", "Spy x Family ch12.docx") == "Spy x Family")
check("filename beats body",
      LP.detect_manga(["One Piece", "Spy x Family"],
                      "today we read One Piece", "spy_x_family_005.txt")
      == "Spy x Family")
check("header hit (Title:)",
      LP.detect_manga(saved, "Title: Sakamoto Days\nPage 1", "") == "Sakamoto Days")
check("header hit (Manga:)",
      LP.detect_manga(saved, "Manga: One Piece\n...", "") == "One Piece")
check("first content lines hit",
      LP.detect_manga(saved, "One Piece\nchapter 5", "") == "One Piece")
check("longest/most-specific wins",
      LP.detect_manga(["Spy", "Spy x Family"], "Title: Spy x Family", "")
      == "Spy x Family")
check("no match -> None",
      LP.detect_manga(saved, "nothing here", "notes.txt") is None)
check("name shorter than 3 is ignored",
      LP.detect_manga(["Oz"], "Title: Oz", "Oz ch1.txt") is None)
check("empty saved list -> None",
      LP.detect_manga([], "Title: One Piece", "") is None)
check("accented name matches",
      LP.detect_manga(["Pokémon"], "Title: Pokémon Adventure", "") == "Pokémon")

# --- default_preset_for ----------------------------------------------------
check("'Normal Talking' name wins",
      LP.default_preset_for(["Shout", "Normal Talking", "Whisper"])
      == "Normal Talking")
check("'talking' keyword match",
      LP.default_preset_for(["Angry", "Talking (soft)"]) == "Talking (soft)")
check("most-used fallback",
      LP.default_preset_for(["Style A", "Style B"], {"Style A": 1, "Style B": 5})
      == "Style B")
check("first non-none fallback",
      LP.default_preset_for(["Zeta", "Alpha"]) == "Alpha")
check("only 'none' -> None",
      LP.default_preset_for(["none", "None"]) is None)
check("empty -> None", LP.default_preset_for([]) is None)
check("keyword beats usage",
      LP.default_preset_for(["Normal", "Loud"], {"Loud": 99}) == "Normal")

# --- flatten_presets (simple preset mode: Manga -> preset) ------------------
_chars = {
    "Sakamoto": {"Normal": {"size": 20}, "Shout": {"size": 40}},
    "Shin": {"Normal": {"size": 18}, "Whisper": {"size": 12}},
}
_flat = LP.flatten_presets(_chars)
check("flatten_presets lists every preset of the manga", len(_flat) == 4)
check("flatten_presets sorted case-insensitively by label",
      [e[0] for e in _flat] ==
      sorted([e[0] for e in _flat], key=lambda s: s.lower()))
check("duplicate names get the (Character) suffix",
      ("Normal (Sakamoto)", "Sakamoto", "Normal") in _flat and
      ("Normal (Shin)", "Shin", "Normal") in _flat)
check("unique names keep their plain label",
      ("Shout", "Sakamoto", "Shout") in _flat and
      ("Whisper", "Shin", "Whisper") in _flat)
check("flatten_presets tracks the owning character",
      all(e[2] in _chars[e[1]] for e in _flat))
check("flatten_presets: empty/invalid input -> empty list",
      LP.flatten_presets({}) == [] and LP.flatten_presets(None) == [] and
      LP.flatten_presets({"X": "not a dict"}) == [])

# --- main characters head the dropdowns ------------------------------------
_names = ["Zenitsu", "aoi", "Makima", "Denji"]
check("sort_characters puts the main ones in their own block first",
      LP.sort_characters(_names, ["Denji", "Makima"])
      == (["Denji", "Makima"], ["aoi", "Zenitsu"]))
check("sort_characters sorts both blocks case-insensitively",
      LP.sort_characters(["b", "A"], ["b"]) == (["b"], ["A"]))
check("sort_characters matches a main character case-insensitively",
      LP.sort_characters(["Denji"], ["denji"]) == (["Denji"], []))
check("sort_characters without favourites keeps everyone in one block",
      LP.sort_characters(_names) == ([], sorted(_names, key=str.lower))
      and LP.sort_characters(_names, []) == ([], sorted(_names, key=str.lower)))
check("sort_characters survives junk",
      LP.sort_characters(None) == ([], []) and
      LP.sort_characters(["A"], [None, "", "  "]) == ([], ["A"]))
_favflat = LP.flatten_presets(_chars, ["Shin"])
check("flatten_presets floats a main character's presets to the top",
      [e[1] for e in _favflat] == ["Shin", "Shin", "Sakamoto", "Sakamoto"])
check("flatten_presets keeps each block alphabetical",
      [e[0] for e in _favflat]
      == ["Normal (Shin)", "Whisper", "Normal (Sakamoto)", "Shout"])
check("flatten_presets without favourites is unchanged",
      LP.flatten_presets(_chars, []) == _flat
      and LP.flatten_presets(_chars, None) == _flat)
check("flatten_presets still labels duplicates when favourites are set",
      ("Normal (Shin)", "Shin", "Normal") in _favflat)

# --- script-tab helpers ----------------------------------------------------
import os as _os
check("default_tab_label strips dir + extension",
      LP.default_tab_label(_os.path.join("x", "y", "Spy x Family ch12.docx"))
      == "Spy x Family ch12")
check("default_tab_label empty -> Untitled", LP.default_tab_label("") == "Untitled")
check("unique_untitled counts up",
      LP.unique_untitled(["Untitled"]) == "Untitled 2" and
      LP.unique_untitled(["Untitled", "Untitled 2"]) == "Untitled 3" and
      LP.unique_untitled([]) == "Untitled")
_sess = [{"path": _os.path.abspath("a/b/one.txt")}, {"path": ""}]
check("find_session_by_path matches same file",
      LP.find_session_by_path(_sess, _os.path.abspath("a/b/one.txt")) == 0)
check("find_session_by_path matches via relative/normalized form",
      LP.find_session_by_path(_sess, "a/b/../b/one.txt") == 0)
check("find_session_by_path: unknown -> -1",
      LP.find_session_by_path(_sess, "a/b/two.txt") == -1)
check("find_session_by_path: blank path never matches",
      LP.find_session_by_path(_sess, "") == -1)

# --- per-line x positions (SVG centering without text-anchor) ---------------
_lspec = importlib.util.spec_from_file_location(
    "layout", os.path.join(_HERE, "typer_kr", "layout.py"))
LO = importlib.util.module_from_spec(_lspec)
_lspec.loader.exec_module(LO)

check("line_x_positions center pre-centers each line by width",
      LO.line_x_positions([100.0, 60.0], "center", 10, 200, 300) == [150.0, 170.0])
check("line_x_positions left = same left for all",
      LO.line_x_positions([100.0, 60.0], "left", 10, 200, 300) == [10.0, 10.0])
check("line_x_positions right = right edge minus width",
      LO.line_x_positions([100.0, 60.0], "right", 10, 200, 300) == [200.0, 240.0])

# --- vertical text / tategaki ----------------------------------------------
# The trap this guards: measuring a vertical run with horizontal advances.
_vm = LO.vertical_measurer(1.0)
_width_of, _space_w, _line_h, _asc, _desc = _vm(20)
check("vertical_measurer: a run is characters * em, not advance widths",
      _width_of("abc") == 60.0)
check("vertical_measurer: narrow and wide glyphs stack identically",
      _width_of("IIII") == _width_of("WWWW"))
check("vertical_measurer: space advances a full em",
      _space_w == 20.0)
check("vertical_measurer: line_h is the column advance = em * spacing",
      LO.vertical_measurer(1.5)(20)[2] == 30.0)
check("vertical_measurer: measures run lists too",
      _width_of([("ab", False), ("c", True)]) == 60.0)

check("column_y_positions middle centers each column on its length",
      LO.column_y_positions([100.0, 60.0], "middle", 10, 200, 300)
      == [150.0, 170.0])
check("column_y_positions top = same top for all",
      LO.column_y_positions([100.0, 60.0], "top", 10, 200, 300) == [10.0, 10.0])
check("column_y_positions bottom = bottom edge minus length",
      LO.column_y_positions([100.0, 60.0], "bottom", 10, 200, 300)
      == [200.0, 240.0])

# 3 columns of 20px in a 200-wide box at x=0, no padding: the block is 60 wide,
# centered -> spans x=70..130, and vertical-rl starts at the RIGHT column.
check("horizontal_start centers the block, first column rightmost",
      LO.horizontal_start("center", 0, 200, 0.0, 3, 20) == 120.0)
check("horizontal_start right hugs the right edge",
      LO.horizontal_start("right", 0, 200, 0.0, 3, 20) == 190.0)
check("horizontal_start left hugs the left edge",
      LO.horizontal_start("left", 0, 200, 0.0, 3, 20) == 50.0)
check("horizontal_start honours padding",
      LO.horizontal_start("right", 0, 200, 0.1, 3, 20) == 180.0)
_hs = LO.horizontal_start("center", 0, 200, 0.0, 3, 20)
check("columns march leftwards from the first one",
      [_hs - i * 20 for i in range(3)] == [120.0, 100.0, 80.0])

# fit_text is axis-agnostic: hand it the transposed box + the vertical measurer
# and it wraps into columns. A short, wide box must not stack it all in one.
_vfit = LO.fit_text("AAA BBB CCC", LO.vertical_measurer(1.0),
                    120, 40, 20, 6, 0.0, "rect")
check("fit_text with the vertical measurer wraps into columns",
      _vfit is not None and len(_vfit[1]) >= 2)

# --- balloon shape library --------------------------------------------------
_bspec = importlib.util.spec_from_file_location(
    "balloons", os.path.join(_HERE, "typer_kr", "balloons.py"))
BL = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(BL)


def _path_points(d):
    """Every absolute coordinate pair in a generated path (M/L/C only)."""
    nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", d)]
    return list(zip(nums[0::2], nums[1::2]))


check("SHAPE_ORDER lists every shape exactly once",
      sorted(BL.SHAPE_ORDER) == sorted(BL.SHAPES.keys())
      and len(BL.SHAPE_ORDER) == len(set(BL.SHAPE_ORDER)))
check("every shape maps to a text type",
      set(BL.SHAPE_FOR_TYPE) == set(BL.SHAPES))
check("unknown shape -> None", BL.balloon_path("banana", 0, 0, 100, 70) is None)
check("degenerate box -> None", BL.balloon_path("oval", 0, 0, 0, 70) is None)

for _s in BL.SHAPE_ORDER:
    _d = BL.balloon_path(_s, 10, 20, 200, 140)
    check("%s: produces a closed path" % _s,
          _d is not None and _d.startswith("M") and _d.endswith("Z"))
    # the point of _fit: whatever the modulation does, the shape fills the box
    _pts = _path_points(_d)
    _xs = [p[0] for p in _pts]
    _ys = [p[1] for p in _pts]
    check("%s: fills the box it was given" % _s,
          abs(min(_xs) - 10) < 0.6 and abs(max(_xs) - 210) < 0.6
          and abs(min(_ys) - 20) < 0.6 and abs(max(_ys) - 160) < 0.6)

check("round shapes are smoothed into beziers", "C" in BL.balloon_path("cloud", 0, 0, 100, 70))
check("angular shapes stay polygons", "C" not in BL.balloon_path("burst", 0, 0, 100, 70))
check("a burst has deeper spikes than a radio balloon",
      # the inset is what separates a shout from a phone voice
      BL._mod_burst(0.0, 1) < BL._mod_radio(0.0, 1))

# a rough balloon must look the same every time it is inserted
check("rough is deterministic",
      BL.balloon_path("rough", 0, 0, 100, 70)
      == BL.balloon_path("rough", 0, 0, 100, 70))
check("rough is not a plain oval",
      BL.balloon_path("rough", 0, 0, 100, 70)
      != BL.balloon_path("oval", 0, 0, 100, 70))

check("cloud gets a circle trail, not a spike",
      [t["kind"] for t in BL.tail_path("cloud", 0, 0, 100, 70)] == ["circle", "circle"])
check("oval gets a pointed tail",
      [t["kind"] for t in BL.tail_path("oval", 0, 0, 100, 70)] == ["path"])
check("the tail hangs below the balloon box",
      max(p[1] for p in _path_points(BL.tail_path("oval", 0, 0, 100, 70)[0]["d"])) > 70)

# Regression, seen rendered in Krita: a tail with a straight base drew a chord
# across the balloon's interior, and no stacking order hid it. The base must
# follow the balloon's own bottom outline between the two base points.


def _seg_dist(p, a, b):
    """Distance from p to the segment a-b."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy))


for _s in ("oval", "burst", "radio", "wavy", "rough", "robot"):
    _outline = BL.shape_points(_s, 0, 0, 100, 70)
    _tpts = _path_points(BL.tail_path(_s, 0, 0, 100, 70)[0]["d"])
    # the base runs along the bottom outline, so every base point (all but the
    # tip and the bolt's zigzag, which hang below the box) lies ON the outline
    _on_outline = [p for p in _tpts if p[1] <= 70.001]
    _off = [p for p in _on_outline
            if min(_seg_dist(p, _outline[i], _outline[(i + 1) % len(_outline)])
                   for i in range(len(_outline))) > 0.01]
    check("%s: the tail base follows the balloon outline" % _s, not _off)
    check("%s: the tail base spans a real width" % _s,
          max(p[0] for p in _on_outline) - min(p[0] for p in _on_outline) > 15)
    check("%s: the tail reaches below the balloon" % _s,
          max(p[1] for p in _tpts) > 70)

_svg = BL.balloon_svg("oval", 10, 20, 200, 140, 800, 1200)
check("balloon_svg wraps a document at image size",
      _svg.startswith("<svg") and 'width="800"' in _svg and 'height="1200"' in _svg)
check("balloon_svg is opaque white with a black stroke",
      'fill="#ffffff"' in _svg and 'stroke="#000000"' in _svg)
check("only the whisper balloon is dashed",
      "stroke-dasharray" in BL.balloon_svg("dashed", 0, 0, 100, 70, 100, 100)
      and "stroke-dasharray" not in _svg)
check("balloon_svg without a tail is just the balloon",
      BL.balloon_svg("oval", 0, 0, 100, 70, 100, 100, tail=False).count("<path") == 1)
check("balloon_svg: unknown shape -> None",
      BL.balloon_svg("banana", 0, 0, 100, 70, 100, 100) is None)

# --- column-aware pairing (tabular scripts, any source language) ------------
check("split_columns splits on tab",
      LP.split_columns("source\ttranslation") == ("source", "translation"))
check("split_columns: no tab -> None", LP.split_columns("just text") is None)
check("split_columns folds extra cells into translation",
      LP.split_columns("a\tb\tc") == ("a", "b c"))

# a 2-column table: header row + a Japanese, a French and an English-source row
_tab = [
    "Page 1",
    "JP\tEN",
    "こんにちは\tHello",
    "Vons êtes parfaites!\tYou're all perfect! (fr)",
    "We came all the way\tWe came all the way *in english",
]
_pairs, _pp, _pages = LP.pair_lines_paged(_tab)
check("column pairing: header row dropped, 3 units", len(_pairs) == 3)
check("column pairing inserts the translation regardless of source language",
      [LP.unit_text(p) for p in _pairs] ==
      ["Hello", "You're all perfect! (fr)", "We came all the way *in english"])
check("column pairing keeps the source on the JA side",
      _pairs[1][0] == "Vons êtes parfaites!")

# backward compatibility: a plain JA/EN script (no tabs) still pairs by language
_plain = ["こんにちは", "Hello", "ありがとう", "Thanks"]
_pp2, _ppg2, _ = LP.pair_lines_paged(_plain)
check("plain JA/EN script still language-paired",
      [LP.unit_text(p) for p in _pp2] == ["Hello", "Thanks"])


# --- TextShapR helpers (layout.py) ------------------------------------------
# A fake monospace measurer: every character is 0.5*px wide, lines 1.2*px tall.
def _measurer(px):
    cw = 0.5 * px

    def width_of(x):
        runs = getattr(x, "runs", None)
        if runs is None:
            if isinstance(x, (list, tuple)):
                return sum(len(t) for t, _b in x) * cw
            return len(x) * cw
        return sum(len(t) for t, _b in runs) * cw

    return width_of, cw, 1.2 * px, 0.96 * px, 0.24 * px


def _texts(cand):
    return [LO.runs_text(r) for r in cand["lines"]]


check("runs_markup wraps bold runs in **",
      LO.runs_markup([("a ", False), ("b", True), (" c", False)]) == "a **b** c")
check("runs_markup plain text unchanged",
      LO.runs_markup([("hello", False)]) == "hello")

_words = LO.make_words("aa bb cc dd", [False] * 11)
# exactly-k balancing: 2 lines allow the biggest size in a square box
_r1 = LO.fit_lines_k(_words, _measurer, 100, 100, 200, 1, 1)
_r2 = LO.fit_lines_k(_words, _measurer, 100, 100, 200, 1, 2)
_r4 = LO.fit_lines_k(_words, _measurer, 100, 100, 200, 1, 4)
check("fit_lines_k k=1 gives one line", _r1 is not None and len(_r1[1]) == 1)
check("fit_lines_k k=2 gives two lines", _r2 is not None and len(_r2[1]) == 2)
check("fit_lines_k k=2 allows a bigger size than k=1",
      _r2 is not None and _r1 is not None and _r2[0] > _r1[0])
check("fit_lines_k k=4 = one word per line",
      _r4 is not None and len(_r4[1]) == 4 and all(len(ws) == 1 for ws in _r4[1]))
check("fit_lines_k k > word count -> None",
      LO.fit_lines_k(_words, _measurer, 100, 100, 200, 1, 5) is None)

_rw = LO.fit_lines_width(_words, _measurer, 100, 100, 200, 1, 0.5)
check("fit_lines_width narrower target -> more lines",
      _rw is not None and len(_rw[1]) >= 2 and _rw[0] > 0)

# widow avoidance: a greedy wrap that would leave a lone last word pulls one
# word down instead ([aa bb cc] / [dd]  ->  [aa bb] / [cc dd])
_wm_wid, _wm_sp, _wm_lh, _wm_a, _wm_d = _measurer(10)
_wl = LO.wrap_greedy(LO.make_words("aa bb cc dd", [False] * 11),
                     _wm_wid, _wm_sp, 40.0)
check("widow avoided: last line is not a lone word",
      [[w.text for w in ln] for ln in _wl] == [["aa", "bb"], ["cc", "dd"]])

# group_words: regroup a flat word list at chosen break-after indices
_gw = LO.make_words("aa bb cc dd", [False] * 11)
check("group_words splits at break-after indices",
      [[w.text for w in ln] for ln in LO.group_words(_gw, {1})]
      == [["aa", "bb"], ["cc", "dd"]])
check("group_words with no breaks -> single line",
      len(LO.group_words(_gw, set())) == 1)

_cb = LO.shape_candidates("aa bb cc dd", _measurer, 100, 100, 200, 1, 0.0,
                          mode="balanced")
check("balanced candidates exist", len(_cb) >= 3)
check("balanced candidates ranked by quality score (best first)",
      [c["score"] for c in _cb] == sorted((c["score"] for c in _cb),
                                          reverse=True))
# The largest font that fits is not automatically the recommendation: where a
# calmer shape exists, it outranks the bigger, more cramped one.
_cq = LO.shape_candidates("stop right there criminal scum", _measurer,
                          200, 150, 200, 1, 0.0)
check("recommendation is quality-based, not merely the largest font",
      _cq and _cq[0]["px"] != max(c["px"] for c in _cq))
check("candidates are deduplicated",
      len({tuple(_texts(c)) for c in _cb}) == len(_cb))

# --- score_arrangement: the quality judgement behind the ranking ------------
def _arr(px, *texts):
    """A throwaway candidate: one run per line, no bold."""
    return {"px": px, "k": len(texts), "lines": [[(t, False)] for t in texts]}

# A block that fills ~60% of the bubble evenly beats one that hugs the rim, even
# though the cramped block is set larger (px_ref caps the size advantage).
_calm = _arr(26, "aaaaa", "bbbbb", "ccccc")
_cramped = _arr(40, "aaaaa", "bbbbb")
check("score prefers a calm ~60% fill over a cramped edge-to-edge block",
      LO.score_arrangement(_calm, _measurer, 100, 100, 40) >
      LO.score_arrangement(_cramped, _measurer, 100, 100, 40))

# A near-empty final line reads as a leftover and scores below an even stack.
check("score penalises a near-empty last line",
      LO.score_arrangement(_arr(20, "aaaa", "bbbb", "cccc"), _measurer, 100, 100)
      > LO.score_arrangement(_arr(20, "aaaa", "bbbb", "c"), _measurer, 100, 100))

# Near-identical shapes are collapsed so the picker shows distinct choices: the
# same block at another size is not a second option worth its own slot.
_dd = LO._dedup_similar(
    [_arr(30, "aaaaa", "bbbbb"),       # kept (best / first)
     _arr(20, "aaaaa", "bbbbb"),       # same shape, smaller -> dropped
     _arr(20, "aa", "bb bb cc")],      # different profile -> kept
    _measurer)
check("dedup collapses a same-shape twin at another size", len(_dd) == 2)
check("dedup keeps the first (best-ranked) of a group", _dd[0]["px"] == 30)

# Break quality: with the same widths, ending a line at a comma reads better
# than snapping it mid-clause, so the punctuation break scores higher.
check("score rewards a line break after punctuation",
      LO.score_arrangement(_arr(20, "well,", "okay"), _measurer, 100, 100) >
      LO.score_arrangement(_arr(20, "well", "okay,"), _measurer, 100, 100))
# A line of only punctuation ('..') is ugly and scores below a real word.
check("score penalises a line that is only punctuation",
      LO.score_arrangement(_arr(20, "no", "oh way"), _measurer, 100, 100) >
      LO.score_arrangement(_arr(20, "..", "oh way"), _measurer, 100, 100))
# Reading measure: the same block scores lower under a tighter char cap.
_long = _arr(20, "aaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbb")
check("score penalises lines longer than the reading measure",
      LO.score_arrangement(_long, _measurer, 400, 400, max_chars=40) >
      LO.score_arrangement(_long, _measurer, 400, 400, max_chars=10))

# No stub lines: a short interior line reads as a gap and scores below an even
# block with the same last line.
check("score penalises a short interior line",
      LO.score_arrangement(_arr(20, "aaaaa", "bbbbb", "ccccc"), _measurer, 100, 100)
      > LO.score_arrangement(_arr(20, "aaaaa", "b", "ccccc"), _measurer, 100, 100))

# Line-count target: the same 4-line block scores higher when the target matches
# its line count than when the target is far off.
_four = _arr(20, "aa", "bb", "cc", "dd")
check("lineTarget rewards arrangements near the target line count",
      LO.score_arrangement(_four, _measurer, 100, 100, line_target=4) >
      LO.score_arrangement(_four, _measurer, 100, 100, line_target=1))

# --- the ideal line count comes from the bubble, not from a constant --------
# A tall box wants a tall stack, a wide one a flat block. Both from the same
# text, so this is purely the geometry talking.
_ideal_tall = LO.ideal_line_count(1000, 20, 0.4)      # narrow, tall box
_ideal_wide = LO.ideal_line_count(1000, 20, 3.5)      # wide, flat box
check("a tall bubble asks for more lines than a wide one",
      _ideal_tall > _ideal_wide + 1)
# scale-free: doubling the font doubles both the text width and the line height
check("the ideal line count does not move with the font size",
      abs(LO.ideal_line_count(2000, 40, 1.0)
          - LO.ideal_line_count(1000, 20, 1.0)) < 1e-9)
check("the ideal line count stays inside the mode's band",
      LO.ideal_line_count(10 ** 6, 20, 0.2, LO.profile_for("wide"))
      <= LO.profile_for("wide")["lines"][1])
check("what physically fits caps the ideal",
      LO.ideal_line_count(10 ** 6, 20, 0.2, LO.profile_for("tall"), max_fit=3)
      <= 3)
check("profile_for falls back to balanced for an unknown mode",
      LO.profile_for("nonsense") is LO.profile_for("balanced")
      and LO.profile_for("tall") is not LO.profile_for("balanced"))

# A tall narrow bubble must not be left three-quarters empty: the old absolute
# 4-line target charged a well-filling 9-line block so hard that a 25%-full
# 5-line block won. Property: the top pick actually uses the bubble.
_tallcands = LO.shape_candidates(
    "you really think you can beat me with a stunt like that", _measurer,
    150, 380, 40, 6, 0.12, mode="balanced")
_tw, _tk, _tlw, _tbw, _tbh, _tlh = LO._arr_metrics(_tallcands[0], _measurer)
check("a tall bubble gets a block that fills it",
      (_tbw * _tbh) / (150 * 0.88 * 380 * 0.88) > 0.55)
# ...and Tall mode does not answer with a ladder of one-word lines
_ladder = LO.shape_candidates(
    "you really think you can beat me with a stunt like that", _measurer,
    150, 380, 40, 6, 0.12, mode="tall")
check("tall mode stays inside its line band",
      _ladder[0]["k"] <= LO.profile_for("tall")["lines"][1])
# The old tall bias was a linear reward for line count, so splitting the
# two-word lines of a good stack into single words won on line count alone.
# Same text, same size: the sensible grouping must score higher.
_sane = _arr(30, "you", "really", "think", "you can", "beat me", "with a",
             "stunt", "like", "that")
_ladder_arr = _arr(30, "you", "really", "think", "you", "can", "beat", "me",
                   "with a", "stunt", "like", "that")
check("tall mode does not reward a ladder of one-word lines",
      LO.score_arrangement(_sane, _measurer, 132, 334, 30, mode="tall") >
      LO.score_arrangement(_ladder_arr, _measurer, 132, 334, 30, mode="tall"))

# --- smoothness, sentence breaks, phrase integrity -------------------------
# Same line count and same total width: an even stack beats one that tapers
# away line by line. Global variance alone barely told these apart.
_even = _arr(20, "aaaaaaa", "aaaaaaa", "aaaaaaa")
_taper = _arr(20, "aaaaaaaaaaa", "aaaaaaa", "aaa")
check("score prefers an even stack over a tapering one",
      LO.score_arrangement(_even, _measurer, 200, 200) >
      LO.score_arrangement(_taper, _measurer, 200, 200))

# A line that carries a sentence end with more words behind it ('trap. Now')
# reads worse than the same shape breaking at the full stop.
_midsent = _arr(20, "it was a trap. Now", "we have to run")
_atstop = _arr(20, "it was a trap.", "Now we have to run")
check("score penalises a sentence starting at the end of a line",
      LO.score_arrangement(_atstop, _measurer, 200, 200)
      > LO.score_arrangement(_midsent, _measurer, 200, 200))
check("the charge is on the mid-line sentence end itself",
      LO._sentence_break_penalty(["it was a trap. Now", "we have to run"]) == 1
      and LO._sentence_break_penalty(["it was a trap.", "Now we have to run"]) == 0)

# A two-word phrase torn across lines when it would have fitted is charged;
# the identical split is NOT charged when the words could not have shared a
# line (a narrow bubble forces it).
_split = _arr(20, "what", "no", "way", "there")
_wide_box = LO.score_arrangement(_split, _measurer, 400, 400)
_narrow_box = LO.score_arrangement(_split, _measurer, 45, 400)
check("an avoidable phrase split is charged, a forced one is not",
      LO._phrase_break_penalty(["what", "no", "way"], [40, 20, 30], 5, 400) > 0
      and LO._phrase_break_penalty(["what", "no", "way"], [40, 20, 30], 5, 45) == 0)
check("a clause end is always a fine place to break",
      LO._phrase_break_penalty(["what?", "no", "way"], [40, 20, 30], 5, 400)
      < LO._phrase_break_penalty(["what", "no", "way"], [40, 20, 30], 5, 400))

# Rim clearance: an area ratio cannot see a block that runs edge to edge in one
# direction only, so a block touching the rim loses to one that clears it.
_touch = _arr(40, "aaaaa", "aaaaa")        # 100 wide in a 100-wide box
_clear = _arr(34, "aaaaa", "aaaaa")
check("score penalises a block that touches the bubble rim",
      LO.score_arrangement(_clear, _measurer, 100, 120, 40) >
      LO.score_arrangement(_touch, _measurer, 100, 120, 40))

# --- the sampled bubble outline --------------------------------------------
_ellipse = [0.3, 0.7, 0.95, 1.0, 0.95, 0.7, 0.3]
check("shape_row_width interpolates between samples",
      0.7 < LO.shape_row_width(_ellipse, 0.5) <= 1.0
      and LO.shape_row_width(_ellipse, 0.0) < 0.5)
check("shape_row_width answers 1.0 without an outline",
      LO.shape_row_width(None, 0.5) == 1.0 and LO.shape_row_width([], 0.2) == 1.0)
check("shape_row_width never returns a zero target",
      LO.shape_row_width([0.0, 0.0], 0.5) >= LO._ROW_FLOOR)
check("line_row_targets samples one width per line",
      len(LO.line_row_targets(_ellipse, 4)) == 4
      and LO.line_row_targets(None, 3) == [1.0, 1.0, 1.0])
# The block sits in the MIDDLE of the bubble, so a short block is measured
# against the balloon's widest part — not against its tapering top and bottom.
_centred = LO.line_row_targets(_ellipse, 3, block_h=30, usable_h=300)
_spread = LO.line_row_targets(_ellipse, 3)
check("a short block is measured against the middle of the bubble",
      min(_centred) > 0.9 and min(_spread) < 0.8)
check("a block filling the bubble is measured across its whole height",
      LO.line_row_targets(_ellipse, 3, block_h=300, usable_h=300) == _spread)
# In a round bubble a block that SPANS it wants a lens shape (short-long-short)
# where a rectangle would crowd the rim, so the outline flips the ranking.
# The lens follows the outline's own proportions (~0.7 / 1.0 / 0.7).
_lens = _arr(20, "aaaaaa", "aaaaaaaa", "aaaaaa")     # block is 3 * 24 = 72 tall
_rect = _arr(20, "aaaaaaa", "aaaaaaa", "aaaaaaa")
check("with an outline, a lens beats a rectangle in a round bubble",
      LO.score_arrangement(_lens, _measurer, 200, 90, shape_rows=_ellipse) >
      LO.score_arrangement(_rect, _measurer, 200, 90, shape_rows=_ellipse))
check("without an outline the rectangle is still the even shape",
      LO.score_arrangement(_rect, _measurer, 200, 90) >
      LO.score_arrangement(_lens, _measurer, 200, 90))
# ...but a small block centred in a big balloon sits in its widest band, where
# the bubble is effectively rectangular — so there the rectangle is right again.
check("a small block in a big round bubble is judged rectangular",
      LO.score_arrangement(_rect, _measurer, 200, 260, shape_rows=_ellipse) >
      LO.score_arrangement(_lens, _measurer, 200, 260, shape_rows=_ellipse))
# An outline says the bubble holds less than its bounding box, so the same
# block reads as fuller — a comfortable block no longer looks half empty.
_blk = _arr(20, "aaaaaa", "aaaaaa")
check("fill is judged against the outline, not the bounding box",
      LO.score_arrangement(_blk, _measurer, 300, 300, shape_rows=_ellipse) !=
      LO.score_arrangement(_blk, _measurer, 300, 300))
check("shape_candidates accepts an outline and still ranks by score",
      [c["score"] for c in LO.shape_candidates(
          "aa bb cc dd ee", _measurer, 120, 120, 40, 6, 0.1,
          shape_rows=_ellipse)] ==
      sorted((c["score"] for c in LO.shape_candidates(
          "aa bb cc dd ee", _measurer, 120, 120, 40, 6, 0.1,
          shape_rows=_ellipse)), reverse=True))

# Round mode ranks by quality too: it used to sort by size first, which put a
# lower-scoring card in the ★ slot.
_rc = LO.shape_candidates("aa bb cc dd ee ff", _measurer, 140, 140, 40, 6, 0.1,
                          mode="round")
check("round mode ranks by score, not by size",
      [c["score"] for c in _rc] == sorted((c["score"] for c in _rc),
                                          reverse=True))

# Starved set: one unbreakable long word leaves the bubble nearly empty, so the
# shaper retries with syllable breaks by itself even though hyphenation is off.
_starved = LO.shape_candidates("Unbelievable", _measurer, 60, 200, 40, 6, 0.1)
check("a starved set is rescued with hyphenated alternatives",
      len(_starved) > 1
      and any("-" in LO.runs_text(c["lines"][0]) for c in _starved))
check("a healthy set is not hyphenated behind the user's back",
      not any("-" in LO.runs_text(r)
              for c in LO.shape_candidates("aa bb cc dd", _measurer, 200, 200,
                                           40, 6, 0.1)
              for r in c["lines"]))

# De-hyphenation: rejoin a word the source split across a line, but keep a
# capitalised compound hyphenated.
_dh1, _ = LO.dehyphenate("embar- rassing")
check("dehyphenate rejoins a lowercase continuation", _dh1 == "embarrassing")
_dh2, _ = LO.dehyphenate("Spider- Man")
check("dehyphenate keeps a capitalised compound hyphenated", _dh2 == "Spider-Man")
check("dehyphenate leaves an ordinary in-word hyphen alone",
      LO.dehyphenate("X-ray vision")[0] == "X-ray vision")
# A Japanese honorific is lowercase, so the capitalisation rule cannot see it:
# without its own rule "Yagi- kun" would come back as "Yagikun".
check("dehyphenate keeps a name + honorific hyphenated",
      LO.dehyphenate("Yagi- kun")[0] == "Yagi-kun"
      and LO.dehyphenate("Tanaka- senpai")[0] == "Tanaka-senpai"
      and LO.dehyphenate("onii- chan!")[0] == "onii-chan!")
check("dehyphenate still rejoins an ordinary broken word",
      LO.dehyphenate("trans- lation")[0] == "translation")

# --- a word that already has a hyphen breaks AT it --------------------------
# "Yagi-kun" used to be fed to the syllable patterns whole, which both missed
# the obvious break and let one land right after the hyphen, so `split_word`
# appended a second one: "Yagi--" / "kun".
_yk = LO.make_words("Yagi-kun", [False] * 8)[0]
check("an existing hyphen is offered as the break point",
      LO.hyphenate("Yagi-kun", "en") == [5])
_yl, _yr = LO.split_word(_yk, 5)
check("breaking at an existing hyphen adds no second hyphen",
      (_yl.text, _yr.text) == ("Yagi-", "kun"))
check("no double hyphen for any compound",
      all(not LO.split_word(LO.make_words(w, [False] * len(w))[0], i)[0]
          .text.endswith("--")
          for w in ("well-known", "Spider-Man", "part-time-job", "mother-in-law")
          for i in LO.hyphenate(w, "en")))
# the parts are hyphenated on their own, so a long compound still offers the
# syllable breaks inside its parts — but never a break that ignores the hyphen
check("both the hyphen and the parts' own breaks are offered",
      LO.hyphenate("Spider-Man", "en") == [3, 7])
check("a plain word hyphenates exactly as before",
      LO.hyphenate("embarrassing", "en") == [2, 5, 9])
check("punctuation after a compound does not move the break",
      LO.hyphenate("Yagi-kun!", "en") == [5]
      and LO.hyphenate("Yagi-kun's", "en") == [5])
check("the minimum letters still apply across the hyphen",
      LO.hyphenate("a-b", "en") == [])
# end to end: the shaper's own output for a compound is a clean single hyphen
_hy = LO.shape_candidates("Yagi-kun is waiting outside", _measurer, 90, 260,
                          40, 6, 0.1, hyphenate=True)
check("the shaper never emits a doubled hyphen",
      _hy and not any("--" in LO.runs_text(r)
                      for c in _hy for r in c["lines"]))
# the bold mask follows the shortened text ('big-Bang', 'Bang' stays bold)
_ht, _hm = LO.dehyphenate("big- Bang",
                          [False, False, False, False, False, True, True, True, True])
check("dehyphenate realigns the bold mask",
      _ht == "big-Bang" and _hm == [False, False, False, False,
                                    True, True, True, True])
# and it feeds through the picker when enabled
_cdh = LO.shape_candidates("hyphen- ation works", _measurer, 200, 200, 60, 1, 0.0,
                           dehyphenate=True)
check("shape_candidates de-hyphenates when asked",
      _cdh and all("- " not in " ".join(_texts(c)) for c in _cdh)
      and any("hyphenation" in " ".join(_texts(c)).lower() for c in _cdh))

_ct = LO.shape_candidates("aa bb cc dd", _measurer, 100, 100, 200, 1, 0.0,
                          mode="tall")
_cw = LO.shape_candidates("aa bb cc dd", _measurer, 100, 100, 200, 1, 0.0,
                          mode="wide")
# tall/wide *bias* the score toward more / fewer lines (a diminishing pull),
# they no longer HARD-sort by line count — so a degenerate extreme can't win,
# but tall still leans taller than wide. Every mode ranks by score.
check("tall leans to at least as many lines as wide",
      _ct and _cw and _ct[0]["k"] >= _cw[0]["k"])
check("tall candidates ranked by score (best first)",
      [c["score"] for c in _ct] == sorted((c["score"] for c in _ct),
                                          reverse=True))
check("wide candidates ranked by score (best first)",
      [c["score"] for c in _cw] == sorted((c["score"] for c in _cw),
                                          reverse=True))

_cr = LO.shape_candidates("aa bb cc dd ee ff", _measurer, 120, 120, 200, 1, 0.0,
                          mode="round")
check("round mode produces ellipse candidates", len(_cr) >= 1)

_ch = LO.shape_candidates("hyphenation hyphenation", _measurer, 60, 300, 60, 1,
                          0.0, mode="balanced", hyphenate=True, lang="en")
check("hyphenation toggle produces hyphenated lines",
      any("-" in t for c in _ch for t in _texts(c)))

# hyphenation must not be blocked by punctuation stuck to the word
check("hyphenate: plain word breaks at syllables",
      LO.hyphenate("EMBARRASSING", "en") == [2, 5, 9])
check("hyphenate: trailing punctuation does not disable it",
      LO.hyphenate("EMBARRASSING!", "en") == [2, 5, 9])
check("hyphenate: quotes/brackets shift the break indices",
      LO.hyphenate("(embarrassing)", "en") == [3, 6, 10])
check("hyphenate: split keeps the punctuation on its part",
      [w.text for w in LO.split_word(
          LO.make_words("EMBARRASSING!", [False] * 13)[0], 5)]
      == ["EMBAR-", "RASSING!"])
check("hyphenate: still nothing to break in a short word",
      LO.hyphenate("SO!", "en") == [] and LO.hyphenate("THIS", "en") == [])
check("hyphenate: a word of only punctuation is no word",
      LO.hyphenate("!!!", "en") == [] and LO.hyphenate("...", "en") == [])
# the case from the panel: the long word only wraps once punctuation is ignored
_chp = LO.shape_candidates("THIS IS SO EMBARRASSING!", _measurer, 60, 300, 60,
                           1, 0.0, mode="balanced", hyphenate=True, lang="en")
check("hyphenation splits a word with a trailing '!'",
      any("-" in t for c in _chp for t in _texts(c)))

# typographic limits: one split per word, at most 2 hyphen lines in a row
def _wrap_texts(max_w, **kw):
    """Wrap the sample line at a fixed size and return its lines as text."""
    words = LO.make_words("THIS IS SO EMBARRASSING!", [False] * 24)
    width_of, space_w, _lh, _a, _d = _measurer(20)
    lines = LO.wrap_greedy(words, width_of, space_w, max_w,
                           lambda w: LO.hyphenate(w.text, "en"), **kw)
    return [LO.runs_text(LO.line_runs(ln)) for ln in lines]


def _max_hyphen_run(texts):
    """Longest run of consecutive lines ending with a hyphen."""
    best = run = 0
    for t in texts:
        run = run + 1 if t.endswith("-") else 0
        best = max(best, run)
    return best


def _hyphens(texts):
    return sum(1 for t in texts if t.endswith("-"))


_narrow = (45.0, 55.0, 60.0, 70.0, 80.0, 90.0)
check("a long word is hyphenated even after a filled line",
      all(_hyphens(_wrap_texts(w)) >= 1 for w in _narrow))
check("by default one word is broken only once",
      all(_hyphens(_wrap_texts(w)) <= 1 for w in _narrow))
check("hyphen ladder never exceeds two lines in a row",
      all(_max_hyphen_run(_wrap_texts(w, max_word_splits=0)) <= 2
          for w in _narrow))
check("without the limits the same wrap splits more often",
      any(_hyphens(_wrap_texts(w, max_ladder=0, max_word_splits=0))
          > _hyphens(_wrap_texts(w)) for w in _narrow))
check("limits never lose or add text",
      all("".join(_wrap_texts(w)).replace("-", "").replace(" ", "")
          == "THISISSOEMBARRASSING!" for w in _narrow))

# fit_fixed_lines: re-fit a hand-edited arrangement without re-wrapping it
_fx = LO.make_words("aa bb cc dd", [False] * 11)
_fixed = [_fx[:2], _fx[2:]]
_ff = LO.fit_fixed_lines(_fixed, _measurer, 100, 100, 200, 1)
check("fit_fixed_lines keeps the given breaks",
      _ff is not None and [[w.text for w in ln] for ln in _ff[1]]
      == [["aa", "bb"], ["cc", "dd"]])
check("fit_fixed_lines finds the same size as the balanced fit",
      _ff is not None and _r2 is not None and _ff[0] == _r2[0])
check("fit_fixed_lines: a smaller box yields a smaller size",
      LO.fit_fixed_lines(_fixed, _measurer, 50, 100, 200, 1)[0] < _ff[0])
check("fit_fixed_lines: nothing to fit -> None",
      LO.fit_fixed_lines([], _measurer, 100, 100, 200, 1) is None and
      LO.fit_fixed_lines(_fixed, _measurer, 1, 1, 200, 100) is None)

check("empty text -> no candidates",
      LO.shape_candidates("   ", _measurer, 100, 100, 200, 1, 0.0) == [])
check("candidate limit respected",
      len(LO.shape_candidates("a b c d e f g h i j k l m n", _measurer,
                              100, 100, 200, 1, 0.0, limit=5)) <= 5)

# --- layer naming (replace previously inserted line) ------------------------
check("typer_layer_prefix zero-pads to two digits",
      LO.typer_layer_prefix(3) == "TypeR 03 — ")
check("typer_layer_prefix keeps three digits",
      LO.typer_layer_prefix(123) == "TypeR 123 — ")
check("is_typer_layer_name matches its own unit",
      LO.is_typer_layer_name("TypeR 03 — DON'T MOVE", 3))
check("is_typer_layer_name: other unit does not match",
      not LO.is_typer_layer_name("TypeR 03 — DON'T MOVE", 13))
check("is_typer_layer_name: 13 does not match a 3-layer",
      not LO.is_typer_layer_name("TypeR 13 — HELLO", 3))
check("is_typer_layer_name needs the full prefix (dash + spaces)",
      not LO.is_typer_layer_name("TypeR03", 3) and
      not LO.is_typer_layer_name("TypeR 03 -", 3))
check("is_typer_layer_name: unrelated / empty names never match",
      not LO.is_typer_layer_name("Background", 3) and
      not LO.is_typer_layer_name("", 3) and
      not LO.is_typer_layer_name(None, 3))
check("is_typer_layer_name: single-digit unit zero-padded",
      LO.is_typer_layer_name("TypeR 07 — text", 7) and
      not LO.is_typer_layer_name("TypeR 7 — text", 7))

# the apply path: baking the chosen breaks as \n and re-fitting capped at the
# candidate's px reproduces exactly the chosen arrangement (WYSIWYG apply)
_pick = _cb[0]
_baked = "\n".join(LO.runs_markup(r) for r in _pick["lines"])
_refit = LO.fit_text(_baked, _measurer, 100, 100, _pick["px"], 1, 0.0)
check("baked hard breaks reproduce the arrangement",
      _refit is not None and _refit[0] == _pick["px"] and
      [LO.runs_text(r) for r in _refit[1]] == _texts(_pick))

# --- BubblR tab helpers (rows_for_page / style_insert_kwargs) ---------------
print("bubblr: page rows + style snapshots")

pages = ["", "", "Page 1", "Page 1", "Page 2"]
check("rows for a page", LP.rows_for_page(pages, "Page 1") == [2, 3])
check("rows before first marker", LP.rows_for_page(pages, "") == [0, 1])
check("no page filter -> all rows",
      LP.rows_for_page(pages, None) == [0, 1, 2, 3, 4])
check("unknown page -> empty", LP.rows_for_page(pages, "Page 9") == [])

_style = {
    "font": "Wild Words", "size": 48, "pad": 12, "spacing": 110,
    "auto": True, "round": True, "outline": True, "outline_w": 3,
    "bold": True, "italic": False, "underline": True,
    "align": "left", "valign": "top", "case": "upper", "tidy": True,
    "color": "#102030", "outline_color": "#ffffff",
    "shadow": True, "shadow_x": 2, "shadow_y": 3,
    "shadow_color": "#0a0a0a", "hyphenate": True, "hyph_lang": "de",
}
_kw = LP.style_insert_kwargs(_style)
check("snapshot round trip",
      _kw["font_family"] == "Wild Words" and _kw["font_px"] == 48 and
      _kw["max_px"] == 48 and abs(_kw["padding_frac"] - 0.12) < 1e-9 and
      abs(_kw["line_spacing"] - 1.10) < 1e-9 and _kw["auto_fit"] and
      _kw["shape"] == "ellipse" and _kw["outline"] and
      _kw["outline_px"] == 3.0 and _kw["bold"] and not _kw["italic"] and
      _kw["underline"] and _kw["align"] == "left" and
      _kw["valign"] == "top" and _kw["case"] == "upper" and _kw["tidy"] and
      _kw["color"] == "#102030" and _kw["shadow"] and
      _kw["shadow_dx"] == 2.0 and _kw["shadow_dy"] == 3.0 and
      _kw["hyphenate"] and _kw["hyph_lang"] == "de")
_kw = LP.style_insert_kwargs({})
check("empty snapshot falls back to defaults",
      _kw["font_family"] == "" and _kw["auto_fit"] and
      _kw["shape"] == "rect" and _kw["align"] == "center" and
      _kw["case"] == "none" and _kw["hyph_lang"] == "auto")
check("fixed size when auto off",
      LP.style_insert_kwargs({"auto": False, "round": True})["shape"]
      == "rect")

# --- BubblR detection/mapping logic (typer_kr/bubbles.py) --------------------
print("bubblr: detection + mapping (bubbles.py)")
_bspec = importlib.util.spec_from_file_location(
    "bubbles", os.path.join(_HERE, "typer_kr", "bubbles.py"))
BB = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(BB)


def _bx(x, y, w=60, h=40, tag=""):
    return {"x": x, "y": y, "w": w, "h": h, "tag": tag}


check("reading order RTL",
      [b["tag"] for b in BB.reading_order(
          [_bx(10, 100, tag="L"), _bx(300, 110, tag="R")], rtl=True)]
      == ["R", "L"])
check("reading order LTR",
      [b["tag"] for b in BB.reading_order(
          [_bx(10, 100, tag="L"), _bx(300, 110, tag="R")], rtl=False)]
      == ["L", "R"])
check("stacked rows top first",
      [b["tag"] for b in BB.reading_order(
          [_bx(10, 300, tag="B"), _bx(300, 100, tag="T")], rtl=True)]
      == ["T", "B"])
# panel-aware ordering (the Magi hybrid): two side-by-side panels (manga RTL:
# right panel read first). Flat reading_order would interleave the rows; with
# panels the right column (R1 top, R2 bottom) comes before the left (L1, L2).
_panels = [_bx(0, 0, w=200, h=400, tag="Lpanel"),
           _bx(220, 0, w=200, h=400, tag="Rpanel")]
_pbubbles = [_bx(20, 20, tag="L1"), _bx(20, 250, tag="L2"),
             _bx(240, 30, tag="R1"), _bx(240, 260, tag="R2")]
check("panel order: right panel first (RTL), top-to-bottom in panel",
      [b["tag"] for b in BB.order_by_panels(_pbubbles, _panels, rtl=True)]
      == ["R1", "R2", "L1", "L2"])
check("panel order: LTR reads left panel first",
      [b["tag"] for b in BB.order_by_panels(_pbubbles, _panels, rtl=False)]
      == ["L1", "L2", "R1", "R2"])
check("panel order: no panels -> falls back to flat reading_order",
      [b["tag"] for b in BB.order_by_panels(_pbubbles, [], rtl=True)]
      == [b["tag"] for b in BB.reading_order(_pbubbles, rtl=True)])
check("panel order: bubble outside all panels still kept",
      len(BB.order_by_panels(_pbubbles + [_bx(900, 900, tag="X")],
                             _panels, rtl=True)) == 5)

check("insert_gap shifts down", BB.insert_gap([0, 1, 2], 1) == [0, -1, 1])
check("remove_gap round-trip",
      BB.remove_gap(BB.insert_gap([0, 1, 2], 1), 1, 3) == [0, 1, 2])

# step-advance pointer (Place & next)
check("next_unplaced: first open box",
      BB.next_unplaced([0, 1, 2], set(), 0) == 0)
check("next_unplaced: skips done units",
      BB.next_unplaced([0, 1, 2], {0, 1}, 0) == 2)
check("next_unplaced: skips gaps",
      BB.next_unplaced([0, -1, 1], {0}, 0) == 2)
check("next_unplaced: starts at given index",
      BB.next_unplaced([0, 1, 2], set(), 1) == 1)
check("next_unplaced: no wrap at end",
      BB.next_unplaced([0, 1], {0, 1}, 0) is None)
check("next_unplaced: empty assign",
      BB.next_unplaced([], set(), 0) is None)

# SFX word database classifier
_words = list(BB.SFX_SEED_WORDS) + ["zuzun"]
check("plain sfx word matches", BB.is_sfx_line("doki", _words))
check("elongation matches ('GOGOGOGO')",
      BB.is_sfx_line("GOGOGOGO", _words))
check("stretched letters match ('Dokii')",
      BB.is_sfx_line("Dokii", _words))
check("decorated sfx matches ('Doki doki!!')",
      BB.is_sfx_line("Doki doki!!", _words))
check("parenthesized action matches ('(Grin grin)')",
      BB.is_sfx_line("(Grin grin)", _words))
check("user word matches", BB.is_sfx_line("zuzun~", _words))
check("dialog with sfx word mid-sentence does NOT match",
      not BB.is_sfx_line("The boom was loud", _words))
check("plain dialog does NOT match",
      not BB.is_sfx_line("Isn't that great Hiyori?", _words))
check("interjection dialog does NOT match",
      not BB.is_sfx_line("yeah...!", _words))
check("SFX: tag always matches",
      BB.is_sfx_line("SFX: rumble of the crowd", _words))
check("empty line does NOT match", not BB.is_sfx_line("  ", _words))

# Japanese kana SFX are transliterated and match the same vocabulary
check("katakana matches (ドキドキ)", BB.is_sfx_line("ドキドキ", _words))
check("hiragana matches (どきどき)", BB.is_sfx_line("どきどき", _words))
check("kana repetition matches (ゴゴゴゴ)",
      BB.is_sfx_line("ゴゴゴゴ", _words))
check("prolongation dropped (ドーン)", BB.is_sfx_line("ドーン", _words))
check("small tsu dropped (ドキッ)", BB.is_sfx_line("ドキッ!!", _words))
check("digraph works (ぴょんぴょん)",
      BB.is_sfx_line("ぴょんぴょん", _words))
check("mufufu matches (ムフフ…)", BB.is_sfx_line("ムフフ…", _words))
check("niyaniya matches (ニヤニヤ)", BB.is_sfx_line("ニヤニヤ", _words))
check("kanji is real dialogue", not BB.is_sfx_line("何ですか", _words))
check("kana dialogue does NOT match",
      not BB.is_sfx_line("これはドキドキします", _words))
check("kana_to_romaji basics",
      BB.kana_to_romaji("ドキドキ") == "dokidoki" and
      BB.kana_to_romaji("ぴょん") == "pyon" and
      BB.kana_to_romaji("シャキーン") == "shakin" and
      BB.kana_to_romaji("漢字") is None)

_kept, _skipped = BB.split_units_sfx(
    ["Hi there!", "gogogogo", "(Grin grin)", "...Mama?"], _words)
check("unit slice skips sfx lines",
      _kept == [0, 3] and _skipped == 2)
_kept, _skipped = BB.split_units_sfx([], _words)
check("empty unit slice", _kept == [] and _skipped == 0)

# DB load/save round trip
import tempfile as _tf2
_dbdir = _tf2.mkdtemp(prefix="typer_sfxdb_")
_dbpath = os.path.join(_dbdir, "sfx_db.json")
check("missing db -> seed only",
      BB.load_sfx_db(_dbpath) == (list(BB.SFX_SEED_WORDS), []))
check("save db ok", BB.save_sfx_db(_dbpath, ["zuzun", " ", "gohh"]))
_seed2, _user2 = BB.load_sfx_db(_dbpath)
check("db round trip keeps user words",
      _user2 == ["zuzun", "gohh"] and
      set(_seed2) == set(BB.SFX_SEED_WORDS))
import shutil as _sh2
_sh2.rmtree(_dbdir, ignore_errors=True)

# heuristic detection smoke test: one outlined bubble with text on a page
_W, _H = 300, 300
_page = bytearray([90]) * (_W * _H)


def _fill(x, y, w, h, val):
    for yy in range(y, y + h):
        base = yy * _W
        for xx in range(x, x + w):
            _page[base + xx] = val


_fill(38, 38, 104, 84, 10)              # outline
_fill(40, 40, 100, 80, 255)             # white bubble
for _k in range(6):                     # text blobs in the middle
    _fill(87, 52 + _k * 12, 6, 6, 20)
_found = BB.detect_bubbles(_page, _W, _H, max_grid_w=_W)
check("heuristic finds the bubble", len(_found) == 1 and
      abs(_found[0]["x"] - 40) <= 2 and abs(_found[0]["w"] - 100) <= 2 and
      _found[0]["kind"] == "bubble")

# --- BubblR AI bridge (typer_kr/ai_backend.py) --------------------------------
print("bubblr: AI bridge (ai_backend.py)")
_aspec = importlib.util.spec_from_file_location(
    "ai_backend", os.path.join(_HERE, "typer_kr", "ai_backend.py"))
AB = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(AB)

import json as _json
import tempfile as _tempfile

_boxes = AB.parse_detect_json(_json.dumps({"boxes": [
    {"x": 1, "y": 2, "w": 30, "h": 40, "kind": "bubble", "score": 0.9},
    {"x": 5, "y": 6, "w": 20, "h": 10, "kind": "panel", "score": 0.8},
]}))
check("detect JSON parsed, unknown kind skipped",
      len(_boxes) == 1 and _boxes[0]["w"] == 30)
try:
    AB.parse_detect_json("{nope")
    check("malformed detect JSON raises", False)
except AB.AIRunError:
    check("malformed detect JSON raises", True)

_lbl = AB.make_yolo_label(
    [{"x": 100, "y": 100, "w": 200, "h": 100, "kind": "bubble"},
     {"x": 0, "y": 0, "w": 50, "h": 50, "kind": "sfx"}], 400, 200)
_lines = _lbl.strip().split("\n")
check("yolo label classes + normalization",
      len(_lines) == 2 and _lines[0].startswith("0 0.5") and
      _lines[1].startswith("1 "))

# Krita exports PYTHONPATH/PYTHONHOME for its own bundled Python; the
# detector subprocess must NOT inherit them (wrong stdlib -> crash).
_tmp = _tempfile.mkdtemp(prefix="typer_bp_test_")
_img = os.path.join(_tmp, "page.png")
open(_img, "wb").close()
_stub = os.path.join(_tmp, "stub_env.py")
with open(_stub, "w") as _fh:
    _fh.write(
        "import json, os, sys\n"
        "bad = [k for k in os.environ if k.upper().startswith('PYTHON')]\n"
        "if bad:\n"
        "    print('leaked: %s' % bad, file=sys.stderr)\n"
        "    sys.exit(4)\n"
        "out = sys.argv[sys.argv.index('--out') + 1]\n"
        "json.dump({'boxes': []}, open(out, 'w'))\n")
os.environ["PYTHONPATH"] = r"C:\Program Files\Krita (x64)\bin"
try:
    _res = AB.detect(_tmp, _img, python_exe=sys.executable, script=_stub)
    check("PYTHON* env vars stripped for the detector", _res == [])
except AB.AIRunError as _exc:
    check("PYTHON* env vars stripped for the detector (%s)" % _exc, False)
finally:
    del os.environ["PYTHONPATH"]
import shutil as _shutil
_shutil.rmtree(_tmp, ignore_errors=True)


# --- layoutmodel.py (customizable panel/tab layout) --------------------------
print("layoutmodel")
_lmspec = importlib.util.spec_from_file_location(
    "layoutmodel", os.path.join(_HERE, "typer_kr", "layoutmodel.py"))
LM = importlib.util.module_from_spec(_lmspec)
_lmspec.loader.exec_module(LM)


def _panels_of(cfg, tab_id):
    for t in cfg["tabs"]:
        if t["id"] == tab_id:
            return t["panels"]
    return None


_d = LM.default_layout()
check("default: every panel present exactly once",
      sorted(LM.all_placed_panels(_d)) == sorted(LM.PANELS))
check("default: presets lives in Type (no Presets tab)",
      "presets" in _panels_of(_d, "type") and
      all(t["id"] != "presets" for t in _d["tabs"]))
check("default: locked", _d["locked"] is True)

# move a panel across tabs
_m = LM.move_panel(_d, "presets", "style", 0)
check("move_panel: presets now first in Style",
      _panels_of(_m, "style")[0] == "presets" and
      "presets" not in _panels_of(_m, "type"))
check("move_panel: still every panel once",
      sorted(LM.all_placed_panels(_m)) == sorted(LM.PANELS))
check("move_panel: unknown panel is a no-op",
      sorted(LM.all_placed_panels(LM.move_panel(_d, "nope", "type"))) ==
      sorted(LM.PANELS))

# reorder within a tab
_r = LM.reorder_panel(_d, "type", 0, 3)
_tp = _panels_of(_r, "type")
check("reorder_panel: script_box moved to index 3", _tp[3] == "script_box")
check("reorder_panel: no panel lost",
      sorted(LM.all_placed_panels(_r)) == sorted(LM.PANELS))

# rename / add / remove / reorder tabs
_rn = LM.rename_tab(_d, "type", "Main")
check("rename_tab", _panels_of(_rn, "type") is not None and
      [t for t in _rn["tabs"] if t["id"] == "type"][0]["name"] == "Main")
_at, _nid = LM.add_tab(_d, "Extra")
check("add_tab: new empty tab appended",
      _panels_of(_at, _nid) == [] and len(_at["tabs"]) == 7)
_rm = LM.remove_tab(_d, "bubblr")
check("remove_tab: tab gone, panels rehomed not lost",
      all(t["id"] != "bubblr" for t in _rm["tabs"]) and
      sorted(LM.all_placed_panels(_rm)) == sorted(LM.PANELS))
_one = LM.default_layout()
_one = LM.remove_tab(LM.remove_tab(LM.remove_tab(LM.remove_tab(LM.remove_tab(
    _one, "style"), "bubblr"), "setup"), "shapr"), "sfx")
check("remove_tab: refuses to delete the last tab",
      len(LM.remove_tab(_one, "type")["tabs"]) == 1)
_ord = LM.reorder_tabs(_d, ["setup", "bubblr"])
check("reorder_tabs: listed first, rest appended in order",
      [t["id"] for t in _ord["tabs"]]
      == ["setup", "bubblr", "type", "style", "shapr", "sfx"])

# detach / reattach round trip
_det = LM.detach(_d, ["bubblr_overlay"], 0)
check("detach: panel leaves its tab",
      "bubblr_overlay" not in _panels_of(_det, "bubblr") and
      LM.is_detached(_det, "bubblr_overlay"))
check("detach: nothing lost overall",
      sorted(LM.all_placed_panels(_det)) == sorted(LM.PANELS))
_rea = LM.reattach(_det, ["bubblr_overlay"], "bubblr")
check("reattach: back in a tab, none detached",
      "bubblr_overlay" in _panels_of(_rea, "bubblr") and
      not _rea["detached"])

# per-panel lock
_pl = LM.set_panel_locked(_d, "font_picker", True)
check("set_panel_locked: pinned", LM.panel_locked(_pl, "font_picker"))
check("set_panel_locked: others free",
      not LM.panel_locked(_pl, "script_box"))

# repair: the safety net
check("repair: empty dict -> valid default-ish",
      sorted(LM.all_placed_panels(LM.repair({}))) == sorted(LM.PANELS))
check("repair: garbage -> valid",
      sorted(LM.all_placed_panels(LM.repair("nonsense"))) ==
      sorted(LM.PANELS))
_stale = {"tabs": [{"id": "type", "panels": ["script_box", "ghost_panel",
                                             "script_box"]}],
          "detached": [], "locked": True}
_fixed = LM.repair(_stale)
check("repair: drops unknown + duplicate panels",
      _panels_of(_fixed, "type").count("script_box") == 1 and
      "ghost_panel" not in LM.all_placed_panels(_fixed))
check("repair: re-homes every missing known panel",
      sorted(LM.all_placed_panels(_fixed)) == sorted(LM.PANELS))
check("repair: guarantees >= 1 tab",
      len(LM.repair({"tabs": []})["tabs"]) >= 1)
# a config from an OLDER plugin (fewer known panels) still repairs cleanly
_older = LM.repair(_d, known_panels=[p for p in LM.PANELS
                                     if p != "hyphenation"])
check("repair: unknown-to-this-version panel dropped",
      "hyphenation" not in LM.all_placed_panels(_older))

# shape_from_fill (selection round/rect detection)
check("shape_from_fill: full bbox -> rect", BB.shape_from_fill(1.0) == "rect")
check("shape_from_fill: ellipse ratio -> round",
      BB.shape_from_fill(0.785) == "round")
check("shape_from_fill: threshold boundary",
      BB.shape_from_fill(BB.RECT_FILL_RATIO) == "rect" and
      BB.shape_from_fill(BB.RECT_FILL_RATIO - 0.01) == "round")

_em = BB.ellipse_mask(10, 10)
check("ellipse_mask: length = w*h", len(_em) == 100)
check("ellipse_mask: centre inside (255)", _em[5 * 10 + 5] == 255)
check("ellipse_mask: corner outside (0)", _em[0] == 0 and _em[9] == 0)
check("ellipse_mask: ~pi/4 fill ratio",
      0.70 <= (sum(_em) / 255.0) / 100.0 <= 0.85)
check("ellipse_mask: degenerate -> empty", BB.ellipse_mask(0, 5) == b"")

# --- SFX strategies + kana->romaji ------------------------------------------
_mspec = importlib.util.spec_from_file_location(
    "sfxmodes", os.path.join(_HERE, "typer_kr", "sfx", "modes.py"))
MD = importlib.util.module_from_spec(_mspec)
_mspec.loader.exec_module(MD)

check("the five strategies, cheapest first",
      MD.STRATEGY_IDS == ["ignore", "romaji", "note", "overlay", "redraw"])
check("only 'ignore' puts nothing on the page",
      [s for s in MD.STRATEGY_IDS if not MD.inserts_text(s)] == ["ignore"])
check("ignore and romaji need no English word",
      [s for s in MD.STRATEGY_IDS if not MD.needs_translation(s)]
      == ["ignore", "romaji"])
check("unknown strategy is not claimed", MD.strategy("banana") is None
      and not MD.inserts_text("banana") and not MD.needs_translation("banana"))

# katakana is what SFX are actually written in
check("romaji: katakana ドカン -> dokan", MD.to_romaji("ドカン") == "dokan")
check("romaji: hiragana too", MD.to_romaji("どかん") == "dokan")
check("romaji: ゴゴゴ -> gogogo", MD.to_romaji("ゴゴゴ") == "gogogo")
check("romaji: ドキドキ -> dokidoki", MD.to_romaji("ドキドキ") == "dokidoki")
check("romaji: ガチャン -> gachan", MD.to_romaji("ガチャン") == "gachan")
check("romaji: ザーッ (prolong) -> zaa", MD.to_romaji("ザーッ") == "zaa")
check("romaji: ドーン doubles the vowel, no macron",
      MD.to_romaji("ドーン") == "doon")
check("romaji: シーン -> shiin", MD.to_romaji("シーン") == "shiin")
# sokuon: the small tsu doubles the NEXT consonant
check("romaji: バッ -> ba (trailing sokuon has nothing to double)",
      MD.to_romaji("バッ") == "ba")
check("romaji: ドッカン -> dokkan", MD.to_romaji("ドッカン") == "dokkan")
check("romaji: ビシッと -> bishitto", MD.to_romaji("ビシッと") == "bishitto")
check("romaji: sokuon before ch becomes 't', not 'c'",
      MD.to_romaji("まっちゃ") == "matcha")
# youon
check("romaji: キャ -> kya", MD.to_romaji("キャ") == "kya")
check("romaji: ジャ -> ja", MD.to_romaji("ジャ") == "ja")
check("romaji: シュゴー -> shugoo", MD.to_romaji("シュゴー") == "shugoo")
# foreign-sound clusters common in SFX
check("romaji: ファ -> fa", MD.to_romaji("ファ") == "fa")
check("romaji: ヴォ -> vo", MD.to_romaji("ヴォ") == "vo")
check("romaji: ティ -> ti", MD.to_romaji("ティ") == "ti")
# non-kana must survive untouched
check("romaji: latin passes through", MD.to_romaji("BOOM!") == "BOOM!")
check("romaji: mixed keeps the non-kana", MD.to_romaji("ドンbang") == "donbang")
check("romaji: kanji is left alone", MD.to_romaji("音ドン") == "音don")
check("romaji: empty stays empty", MD.to_romaji("") == "" and MD.to_romaji(None) == "")
check("romaji: middle dot becomes a space", MD.to_romaji("ド・ン") == "do n")

# note list
check("note_marker: circled numbers to 20",
      MD.note_marker(1) == "①" and MD.note_marker(20) == "⑳")
check("note_marker: past 20 falls back, never renumbers",
      MD.note_marker(21) == "(21)")
check("note_line: marker, original, romaji, meaning",
      MD.note_line(1, "ドキ", "heartbeat") == "① ドキ = doki (heartbeat)")
check("note_line: meaning is optional",
      MD.note_line(2, "ドキ") == "② ドキ = doki")
check("note_line: no romaji repeat when there is nothing to transliterate",
      MD.note_line(3, "BOOM") == "③ BOOM")

# --- SFX rule matching + rule search ----------------------------------------
_rspec = importlib.util.spec_from_file_location(
    "rule_search", os.path.join(_HERE, "typer_kr", "sfx", "rule_search.py"))
RS = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(RS)

# normalize_sfx / keyword_matches (moved here out of sfx_docker.py)
check("normalize_sfx: stretched writings collapse",
      RS.normalize_sfx("BOOOOM") == RS.normalize_sfx("BOOM") == "bom")
check("normalize_sfx: punctuation drops out",
      RS.normalize_sfx("ka-boom!") == "kabom")
check("normalize_sfx: a single repeated char keeps two",
      RS.normalize_sfx("zzz") == "zz" and RS.normalize_sfx("zzzz") == "zz")
check("normalize_sfx: empty stays empty",
      RS.normalize_sfx("") == "" and RS.normalize_sfx(None) == "")
check("keyword_matches: 3+ chars match as substring",
      RS.keyword_matches("boom", RS.normalize_sfx("KA-BOOOOM!")))
check("keyword_matches: 2 chars only as a whole word",
      RS.keyword_matches("ow", RS.normalize_sfx("OW"))
      and not RS.keyword_matches("ow", RS.normalize_sfx("POW")))
check("keyword_matches: 1 char is ignored",
      not RS.keyword_matches("a", RS.normalize_sfx("aaah")))

_rule = {"group": "Boom / Explosion", "keywords": ["boom", "kaboom"],
         "fonts": ["CC Shout Out", "Impact"]}

check("rule_matches_query: empty query keeps every rule",
      RS.rule_matches_query(_rule, "") and RS.rule_matches_query(_rule, "   ")
      and RS.rule_matches_query(_rule, None))
check("rule_matches_query: keyword substring", RS.rule_matches_query(_rule, "boo"))
check("rule_matches_query: font name, case-insensitive",
      RS.rule_matches_query(_rule, "shout"))
check("rule_matches_query: group name",
      RS.rule_matches_query(_rule, "explosion"))
check("rule_matches_query: fuzzy SFX spelling finds the keyword",
      RS.rule_matches_query(_rule, "BOOOOM!")
      and RS.rule_matches_query(_rule, "ka-boom"))
check("rule_matches_query: no hit -> False",
      not RS.rule_matches_query(_rule, "whoosh"))
check("rule_matches_query: several words are ANDed",
      RS.rule_matches_query(_rule, "boom impact")
      and not RS.rule_matches_query(_rule, "boom whoosh"))
check("rule_matches_query: font: prefix limits the field",
      RS.rule_matches_query(_rule, "font:impact")
      and not RS.rule_matches_query(_rule, "font:boom"))
check("rule_matches_query: group: prefix limits the field",
      RS.rule_matches_query(_rule, "group:boom")
      and not RS.rule_matches_query(_rule, "group:impact"))
check("rule_matches_query: kw: prefix limits the field",
      RS.rule_matches_query(_rule, "kw:kaboom")
      and not RS.rule_matches_query(_rule, "kw:impact"))
check("rule_matches_query: unknown prefix is no field filter, just text",
      not RS.rule_matches_query(_rule, "size:impact"))
check("rule_matches_query: a rule without fonts/group survives",
      RS.rule_matches_query({"keywords": ["thud"]}, "thud")
      and not RS.rule_matches_query({"keywords": ["thud"]}, "boom"))

# --- #21: Drive image comments as a script source --------------------------
check("drive_file_id: /file/d/<id>/view",
      LP.drive_file_id("https://drive.google.com/file/d/1A2b3C4d5E6f7G8h9I0jKlMnOpQr/view?usp=sharing")
      == "1A2b3C4d5E6f7G8h9I0jKlMnOpQr")
check("drive_file_id: open?id=",
      LP.drive_file_id("https://drive.google.com/open?id=1A2b3C4d5E6f7G8h9I0jKlMnOpQr")
      == "1A2b3C4d5E6f7G8h9I0jKlMnOpQr")
check("drive_file_id: uc?id=",
      LP.drive_file_id("https://drive.google.com/uc?id=1A2b3C4d5E6f7G8h9I0jKlMnOpQr&export=download")
      == "1A2b3C4d5E6f7G8h9I0jKlMnOpQr")
check("drive_file_id: bare id passes through",
      LP.drive_file_id("1A2b3C4d5E6f7G8h9I0jKlMnOpQr") == "1A2b3C4d5E6f7G8h9I0jKlMnOpQr")
check("drive_file_id: junk -> empty",
      LP.drive_file_id("https://example.com/not-a-drive-link") == "")
check("drive_file_id: empty -> empty",
      LP.drive_file_id("") == "" and LP.drive_file_id(None) == "")


class _FakeComment(object):
    def __init__(self, text): self.text = text


_imgc = [_FakeComment("Everyone clap"), _FakeComment("As an idol"),
         _FakeComment("")]
_script = LP.image_comments_to_script(_imgc)
check("image_comments_to_script: skips empty comments",
      _script.count("\n") == 1)
# the whole point: each comment must survive as exactly ONE unit
_pairs, _pp, _pg = LP.pair_lines_paged(_script.split("\n"))
check("image comments -> one unit per comment",
      len(_pairs) == 2)
check("image comment text lands as the translation",
      [LP.unit_text(p) for p in _pairs] == ["Everyone clap", "As an idol"])
check("a multi-line comment stays one unit",
      len(LP.pair_lines_paged(
          LP.image_comments_to_script([_FakeComment("line one\nline two")]).split("\n"))[0])
      == 1)
check("image_comments_to_script: no comments -> empty script",
      LP.image_comments_to_script([]) == "")

# --- TextShapR line-break quality: dangling stop-words + widows -------------
check("_word_is_stop flags a dangling preposition/article",
      LO._word_is_stop("to") and LO._word_is_stop("the") and LO._word_is_stop("a"))
check("_word_is_stop ignores content words",
      not LO._word_is_stop("homework") and not LO._word_is_stop("run"))
check("a word that ends a clause is a fine break, not a stop",
      not LO._word_is_stop("to,") and not LO._word_is_stop("the."))
check("_bare_last strips quotes/brackets + lowercases",
      LO._bare_last("(The") == "the" and LO._bare_last("to") == "to")


def _cand(px, *line_texts):
    return {"px": px, "k": len(line_texts),
            "lines": [[(t, False)] for t in line_texts]}


# same shape, same widths — only the interior line's LAST word differs: a bare
# stop word ('to') must score exactly the stop penalty below a content word.
_a = _cand(40, "I run to", "the end")     # interior line ends on 'to' (stop)
_b = _cand(40, "I run ox", "the end")     # ends on 'ox' (content), same width
_sa = LO.score_arrangement(_a, _measurer, 200, 200)
_sb = LO.score_arrangement(_b, _measurer, 200, 200)
check("a line ending on a dangling stop-word scores lower",
      _sb - _sa > 0.29 and _sb - _sa < 0.31)

# the shaper keeps short function words attached where the balance allows it:
# this text can be shaped with no interior line dangling a stop-word.
_shp = LO.shape_candidates(
    "we should try to find a way to fix this before it gets worse",
    _measurer, 260, 320, 200, 6, 0.1, mode="balanced")
_top = [LO.runs_text(r) for r in _shp[0]["lines"]]
check("top shape keeps function words attached (no dangling stop-word)",
      not any(L.split() and LO._bare_last(L.split()[-1]) in LO._LINE_END_STOPS
              for L in _top[:-1]))

# widow: the shaper's top pick doesn't leave a lone single word as the last line
check("top shape avoids a single-word widow last line",
      len(_top) < 2 or len(_top[-1].split()) >= 2)

# outline-aware fit: reserving an inset shrinks the fitted size so outlined
# text stays inside the box instead of overflowing.
_p0 = LO.shape_candidates("BIG LOUD TEXT", _measurer, 200, 100, 200, 6, 0.0)
_p1 = LO.shape_candidates("BIG LOUD TEXT", _measurer, 200, 100, 200, 6, 0.0,
                          inset=20)
check("an outline inset shrinks the fitted size (no overflow)",
      _p0 and _p1 and _p1[0]["px"] < _p0[0]["px"])

# richer pool: several distinct line counts are offered for a longer line
_pool = LO.shape_candidates(
    "make sure you plan out all of your summer homework tonight",
    _measurer, 260, 320, 200, 6, 0.1)
check("shaper offers several distinct shapes to choose from",
      len({c["k"] for c in _pool}) >= 3)

# a conjunction reads best at the START of a line (break before 'but')
check("_word_is_conj flags a leading conjunction",
      LO._word_is_conj("but") and LO._word_is_conj("and")
      and not LO._word_is_conj("homework"))

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
