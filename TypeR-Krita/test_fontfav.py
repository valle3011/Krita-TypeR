# -*- coding: utf-8 -*-
"""Standalone tests for the Qt-free font-favourites core (typer_kr/fontfav.py).

Run:  python test_fontfav.py
No Krita/PyQt5 needed.
"""
import importlib.util
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "fontfav", os.path.join(_HERE, "typer_kr", "fontfav.py"))
FF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FF)

# fontinfo asks fontmatch for the vocabulary of cut names, so the package
# directory goes on the path and the plain import inside it resolves.
sys.path.insert(0, os.path.join(_HERE, "typer_kr"))
_ispec = importlib.util.spec_from_file_location(
    "fontinfo", os.path.join(_HERE, "typer_kr", "fontinfo.py"))
FI = importlib.util.module_from_spec(_ispec)
_ispec.loader.exec_module(FI)

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  ok   " + name)
    else:
        _fail += 1
        print("  FAIL " + name)


# --- categories ------------------------------------------------------------
s = FF.FavoritesStore()
check("empty store has no categories", s.categories() == [])
check("add_category returns the name", s.add_category("Dialog") == "Dialog")
check("add_category is case-insensitively idempotent",
      s.add_category("dialog") == "Dialog" and s.categories() == ["Dialog"])
check("blank category is ignored",
      s.add_category("   ") is None and s.categories() == ["Dialog"])
s.add_category("SFX")
check("categories keep insertion order", s.categories() == ["Dialog", "SFX"])
check("rename_category updates the list",
      s.rename_category("SFX", "Sound") == "Sound"
      and s.categories() == ["Dialog", "Sound"])
check("rename unknown category returns None",
      s.rename_category("nope", "x") is None)

# --- fonts + linkage -------------------------------------------------------
s = FF.FavoritesStore()
s.add_font("CC Wild Words", ["Dialog", "SFX"])
check("add_font creates referenced categories",
      set(s.categories()) == {"Dialog", "SFX"})
check("is_favorite true after add", s.is_favorite("CC Wild Words"))
check("font_categories reflects the links (1..n)",
      s.font_categories("CC Wild Words") == ["Dialog", "SFX"])
check("a font can be added to more categories later",
      s.add_font("CC Wild Words", ["Titel"])
      and s.font_categories("CC Wild Words") == ["Dialog", "SFX", "Titel"])
check("re-adding an existing link does not duplicate it",
      s.add_font("CC Wild Words", ["Dialog"])
      and s.font_categories("CC Wild Words") == ["Dialog", "SFX", "Titel"])
check("blank font is ignored", s.add_font("  ") is None)

# one category, several fonts (the other direction of 1..n)
s.add_font("Anime Ace 2", ["Dialog"])
check("many fonts share one category",
      set(s.fonts_in_category("Dialog")) == {"CC Wild Words", "Anime Ace 2"})

# --- toggle ----------------------------------------------------------------
s = FF.FavoritesStore()
check("toggle adds a link and the font", s.toggle("Font A", "SFX") is True)
check("toggle again removes the link", s.toggle("Font A", "SFX") is False)
check("font stays a favourite after its last link is toggled off",
      s.is_favorite("Font A") and s.font_categories("Font A") == [])

# --- queries ---------------------------------------------------------------
s = FF.FavoritesStore()
s.add_font("Zed", ["Dialog"])
s.add_font("alpha", ["Dialog"])
s.add_font("Loose")                         # no category
check("fonts_in_category(None) returns all favourites, sorted CI",
      s.fonts_in_category(None) == ["alpha", "Loose", "Zed"])
check("category filter narrows the list",
      s.fonts_in_category("Dialog") == ["alpha", "Zed"])
check("UNCATEGORIZED returns only link-less favourites",
      s.fonts_in_category(FF.UNCATEGORIZED) == ["Loose"])
check("unknown category yields empty list",
      s.fonts_in_category("Ghost") == [])
check("search filters by substring, case-insensitively",
      s.fonts_in_category(None, "AL") == ["alpha"])
check("multi-token search requires all tokens", s.fonts_in_category(None, "al ph")
      == ["alpha"])
check("category_counts counts references",
      s.category_counts() == {"Dialog": 2})

# --- remove ----------------------------------------------------------------
s = FF.FavoritesStore()
s.add_font("F1", ["A", "B"])
s.add_font("F2", ["A"])
check("remove_category strips it from every font",
      s.remove_category("A")
      and s.font_categories("F1") == ["B"]
      and s.font_categories("F2") == [])
check("remove_font drops the favourite",
      s.remove_font("F1") and not s.is_favorite("F1"))
check("remove_font on a missing font returns False",
      s.remove_font("nope") is False)

# --- rename with merge -----------------------------------------------------
s = FF.FavoritesStore()
s.add_font("F", ["Old", "Keep"])
check("renaming onto an existing category merges (no dup on the font)",
      s.rename_category("Old", "keep") == "Keep"
      and s.font_categories("F") == ["Keep"]
      and s.categories() == ["Keep"])

# --- set_font_categories ---------------------------------------------------
s = FF.FavoritesStore()
s.add_font("F", ["A", "B"])
s.set_font_categories("F", ["C"])
check("set_font_categories replaces the whole set",
      s.font_categories("F") == ["C"] and "C" in s.categories())

# --- round-trip ------------------------------------------------------------
s = FF.FavoritesStore()
s.add_font("CC Wild Words", ["Dialog", "SFX"])
s.add_font("Anime Ace 2", ["Dialog"])
s.add_category("Titel")
blob = s.to_json()
s2 = FF.FavoritesStore.from_json(blob)
check("round-trip preserves categories", s2.categories() == s.categories())
check("round-trip preserves font links",
      s2.font_categories("CC Wild Words") == ["Dialog", "SFX"])
check("round-trip preserves an empty category",
      "Titel" in s2.categories())

# --- tolerant loading ------------------------------------------------------
check("from_json('') -> empty store",
      FF.FavoritesStore.from_json("").categories() == []
      and FF.FavoritesStore.from_json("").fonts() == [])
check("from_json(None) -> empty store",
      FF.FavoritesStore.from_json(None).fonts() == [])
check("from_json(garbage) -> empty store, no raise",
      FF.FavoritesStore.from_json("{not json").fonts() == [])
check("from_json(non-dict json) -> empty store",
      FF.FavoritesStore.from_json("[1,2,3]").fonts() == [])
_partial = FF.FavoritesStore.from_json('{"fonts": {"X": "notalist"}}')
check("from_json tolerates a bad font value (keeps font, no links)",
      _partial.is_favorite("X") and _partial.font_categories("X") == [])

# --- missing fonts ---------------------------------------------------------
s = FF.FavoritesStore()
s.add_font("CC Wild Words", ["Dialog"])
s.add_font("Anime Ace 2", ["Dialog"])
s.add_font("Arial", [])
check("missing_fonts lists favourites not in the installed set",
      s.missing_fonts(["Arial"]) == ["Anime Ace 2", "CC Wild Words"])
check("missing_fonts matches case-insensitively",
      s.missing_fonts(["arial", "anime ace 2", "cc wild words"]) == [])
check("missing_fonts with nothing installed returns all favourites",
      s.missing_fonts([]) == ["Anime Ace 2", "Arial", "CC Wild Words"])

# --- merge -----------------------------------------------------------------
a = FF.FavoritesStore()
a.add_font("Font A", ["Dialog"])
b = FF.FavoritesStore()
b.add_font("Font A", ["SFX"])          # same font, extra category
b.add_font("Font B", ["Titel"])        # brand-new font
added = a.merge(b)
check("merge reports the number of NEW favourites added", added == 1)
check("merge unions a shared font's categories",
      a.font_categories("Font A") == ["Dialog", "SFX"])
check("merge brings in new fonts + their categories",
      a.font_categories("Font B") == ["Titel"] and "Titel" in a.categories())
check("merge(None) is a safe no-op", a.merge(None) == 0)

# --- UI state (last filter) survives round-trip ----------------------------
s = FF.FavoritesStore()
s.add_font("F", ["Dialog"])
check("ui_get default when unset", s.ui_get("last_category", "X") == "X")
s.ui_set("last_category", "Dialog")
s.ui_set("last_search", "wild")
s2 = FF.FavoritesStore.from_json(s.to_json())
check("ui state round-trips (category)", s2.ui_get("last_category") == "Dialog")
check("ui state round-trips (search)", s2.ui_get("last_search") == "wild")
check("ui state does not leak into the data model",
      s2.categories() == ["Dialog"] and s2.fonts() == ["F"])
check("None category round-trips as None",
      FF.FavoritesStore.from_json(
          FF.FavoritesStore().to_json()).ui_get("last_category") is None)

# --- what the properties window knows (fontinfo) ---------------------------
check("the same font spelled two ways is one font",
      FI.same_font("CC Wild Words", "CCWildWords")
      and FI.same_font("Anime Ace", "anime ace"))
check("...but two different fonts are not",
      not FI.same_font("Arial", "Arial Black")
      and not FI.same_font("Anime Ace", "Anime Ace 2.0")
      and not FI.same_font("", "Arial"))

check("a cut is split off the name",
      FI.split_cut_name("Anime Ace Bold Italic") == ("Anime Ace",
                                                     "Bold Italic"))
check("a font with no cut keeps its whole name",
      FI.split_cut_name("CC Wild Words") == ("CC Wild Words", ""))
check("a font NAMED after a weight does not dissolve into a cut",
      FI.split_cut_name("Black") == ("Black", ""))
check("Regular is a cut like any other",
      FI.split_cut_name("Badaboom BB Regular") == ("Badaboom BB", "Regular"))

_installed = ["Anime Ace", "Anime Ace Bold", "AnimeAce Italic",
              "Anime Ace 2.0", "CC Wild Words", "Arial"]
_kin = FI.relatives("Anime Ace", _installed)
check("a family gathers its own cuts, however they are spelled",
      _kin == ["Anime Ace", "Anime Ace Bold", "AnimeAce Italic"])
check("...and leaves a different family alone",
      "Anime Ace 2.0" not in _kin and "Arial" not in _kin)
check("a font nothing is installed for still reports itself",
      FI.relatives("Ghost Sans", []) == ["Ghost Sans"])
check("the cuts come back named",
      FI.cuts_of("Anime Ace", _installed)[1] == ("Anime Ace Bold", "Bold"))
check("an empty name asks nothing", FI.relatives("", _installed) == []
      and FI.split_cut_name("") == ("", ""))

_groups = {
    "Chainsaw Man": {
        "Denji": {"normal": {"font": "CC Wild Words", "size": 12},
                  "shout": {"font": "Badaboom BB"}},
        "": {"narration": {"font": "CCWildWords"}},
    },
    "Berserk": {
        "Guts": {"normal": {"font": "Anime Ace Bold"},
                 "broken": {"font": ""},
                 "odd": "not a dict"},
    },
    "empty": {},
    "wrong": "not a dict either",
}
_rows = FI.preset_uses(_groups, "CC Wild Words")
check("a preset that uses the font is found, whatever the spelling",
      len(_rows) == 2 and {r[2] for r in _rows} == {"normal", "narration"})
check("...with its manga and its character",
      _rows[0][0] == "Chainsaw Man" and ("Denji", "") ==
      (_rows[1][1], _rows[0][1]))
check("rubbish in the tree is stepped over, not tripped on",
      FI.preset_uses(_groups, "Anime Ace Bold") == [
          ("Berserk", "Guts", "normal", "Anime Ace Bold")])
check("asking for a whole family finds the cut too",
      len(FI.preset_uses(_groups, ["Anime Ace", "Anime Ace Bold"])) == 1)
check("a font in no preset says so, rather than guessing",
      FI.preset_uses(_groups, "Comic Sans MS") == []
      and FI.preset_uses({}, "CC Wild Words") == []
      and FI.preset_uses(_groups, "") == [])
check("the rows read manga, character, preset",
      all(len(r) == 4 for r in _rows))

_types = {"SFX": "Badaboom BB", "Dialogue": "CC Wild Words", "Thought": ""}
check("a text type set to the font is found",
      FI.type_uses(_types, "CCWildWords") == [("Dialogue", "CC Wild Words")])
check("...and none is honestly none",
      FI.type_uses(_types, "Arial") == [] and FI.type_uses({}, "Arial") == [])

check("a font file is named by its kind",
      FI.file_kind("C:/x/Wild.TTF") == "TrueType"
      and FI.file_kind("x.otf") == "OpenType" and FI.file_kind("x") == "")
check("a size reads the way a properties window writes it",
      FI.human_size(22204).startswith("21.7 KB")
      and "22,204 bytes" in FI.human_size(22204)
      and FI.human_size(900) == "900 bytes" and FI.human_size(None) == "")
check("...in the separators of whoever is reading it",
      FI.human_size(22204, ".", ",") == "21,7 KB (22.204 bytes)"
      and FI.human_size(9000, ".", ",") == "8,8 KB (9.000 bytes)")

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
