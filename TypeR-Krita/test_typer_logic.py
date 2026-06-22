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

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
