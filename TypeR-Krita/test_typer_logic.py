# -*- coding: utf-8 -*-
"""Standalone tests for TypeR's Qt-free helpers (no Krita/PyQt5 needed).

Run:  python test_typer_logic.py
Covers detect_manga() and default_preset_for() in typer_kr/langpair.py.
"""
import importlib.util
import os
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
check("balanced candidates sorted by size (biggest first)",
      [c["px"] for c in _cb] == sorted((c["px"] for c in _cb), reverse=True))
check("balanced first candidate is the 2-line arrangement",
      _cb and _cb[0]["k"] == 2)
check("candidates are deduplicated",
      len({tuple(_texts(c)) for c in _cb}) == len(_cb))

_ct = LO.shape_candidates("aa bb cc dd", _measurer, 100, 100, 200, 1, 0.0,
                          mode="tall")
_cw = LO.shape_candidates("aa bb cc dd", _measurer, 100, 100, 200, 1, 0.0,
                          mode="wide")
check("tall mode puts the most lines first",
      _ct and _ct[0]["k"] == max(c["k"] for c in _ct))
check("wide mode puts the fewest lines first", _cw and _cw[0]["k"] == 1)

_cr = LO.shape_candidates("aa bb cc dd ee ff", _measurer, 120, 120, 200, 1, 0.0,
                          mode="round")
check("round mode produces ellipse candidates", len(_cr) >= 1)

_ch = LO.shape_candidates("hyphenation hyphenation", _measurer, 60, 300, 60, 1,
                          0.0, mode="balanced", hyphenate=True, lang="en")
check("hyphenation toggle produces hyphenated lines",
      any("-" in t for c in _ch for t in _texts(c)))

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

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
