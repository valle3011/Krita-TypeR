# -*- coding: utf-8 -*-
"""Standalone tests for TypeR's Qt-free helpers (no Krita/PyQt5 needed).

Run:  python test_typer_logic.py
Covers detect_manga() and default_preset_for() in typer_kr/langpair.py.
"""
import importlib.util
import os
import sys

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

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
