# -*- coding: utf-8 -*-
"""Standalone tests for the tolerant font matcher (typer_kr/fontmatch.py).

Run:  python test_fontmatch.py
No Krita/PyQt5 needed.

The family names below are real: they are what Windows actually reports on a
typesetting machine after the usual mix of Blambot downloads, Fonts.com web
kits and OnlineWebFonts repacks.
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
    "fontmatch", os.path.join(_HERE, "typer_kr", "fontmatch.py"))
FM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FM)

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  ok   " + name)
    else:
        _fail += 1
        print("  FAIL " + name)


INSTALLED = [
    "Anime Ace", "Anime Ace 2.0 BB", "Anime Ace v3",
    "BadaBoom BB",
    "BoogersBB iCielTB",
    "Bold Wicker",
    "CCBattleCry", "CCBattleCry-Regular",
    "CCBeyondBelief", "CCBeyondBelief Heavy",
    "CC Wild Words",
    "CDX Amraam", "CDX Hollow", "Cdx Noodle Doodle", "CDX Seven Cent Pen",
    "CryptCreep Heavy BB",
    "ImaginaryFriendBBW00-Rg",
    "SS Cryptid",
    "Arial", "Comic Sans MS", "Impact",
]
idx = FM.FontIndex(INSTALLED)


def fam(name, **kw):
    m = idx.resolve(name, **kw)
    return m.family if m else None


def tier(name, **kw):
    m = idx.resolve(name, **kw)
    return m.tier if m else None


# --- tokenising ------------------------------------------------------------
check("camelCase splits into words",
      FM.tokens("CCWildWords") == ["cc", "wild", "words"])
check("spaced spelling tokenises the same",
      FM.tokens("CC Wild Words") == FM.tokens("CCWildWords"))
check("version numbers stay in one piece",
      FM.tokens("Anime Ace 2.0") == ["anime", "ace", "2.0"])
check("Fonts.com W-tag is debris",
      "w00" not in FM.tokens("ImaginaryFriendBBW00-Rg"))
check("iCiel branding is debris",
      "iciel" not in FM.tokens("BoogersBB iCielTB"))
check("OnlineWebFonts pointer prefix is ignored",
      FM.tokens("☞CCBattleCry") == ["cc", "battle", "cry"])
check("squash drops spacing and case",
      FM.squash("CC Wild Words") == FM.squash("ccwildwords"))

# --- cut splitting ---------------------------------------------------------
check("trailing Italic is a cut",
      FM.split_cut(["anime", "ace", "italic"]) == (["anime", "ace"], False, True))
check("trailing Regular is a cut",
      FM.split_cut(["cc", "battle", "cry", "regular"])[0] == ["cc", "battle", "cry"])
check("leading Bold is part of the name",
      FM.split_cut(["bold", "wicker"]) == (["bold", "wicker"], False, False))
check("a name that is only a cut word survives",
      FM.split_cut(["regular"]) == (["regular"], False, False))

# --- the ladder ------------------------------------------------------------
check("tier 1 exact", (fam("CDX Amraam"), tier("CDX Amraam")) == ("CDX Amraam", "exact"))
check("tier 2 case-insensitive",
      (fam("cdx amraam"), tier("cdx amraam")) == ("CDX Amraam", "case"))
check("tier 3 squashed: CCWildWords -> CC Wild Words",
      (fam("CCWildWords"), tier("CCWildWords")) == ("CC Wild Words", "squash"))
check("tier 3 squashed: CDX NoodleDoodle -> Cdx Noodle Doodle",
      fam("CDX NoodleDoodle") == "Cdx Noodle Doodle")
check("tier 4 tokens: Anime Ace Italic -> Anime Ace",
      (fam("Anime Ace Italic"), tier("Anime Ace Italic")) == ("Anime Ace", "tokens"))
check("tier 5 tags dropped: Anime Ace 2.0 -> Anime Ace 2.0 BB",
      (fam("Anime Ace 2.0"), tier("Anime Ace 2.0")) == ("Anime Ace 2.0 BB", "tokens-notags"))
check("tier 5: Imaginary Friend BB -> the W00 repack",
      fam("Imaginary Friend BB") == "ImaginaryFriendBBW00-Rg")
check("tier 5: Boogers BB -> the iCiel repack",
      fam("Boogers BB") == "BoogersBB iCielTB")
check("tier 5: Wild Words -> CC Wild Words",
      fam("Wild Words") == "CC Wild Words")

# --- the cut asked for in the name is reported, not swallowed --------------
m = idx.resolve("Anime Ace Italic")
check("italic cut is carried on the Match", m.italic and not m.bold)
m = idx.resolve("CCBeyondBelief Heavy")
check("a real family wins over cut-stripping",
      m.family == "CCBeyondBelief Heavy" and m.tier == "exact")

# --- ambiguity resolves deterministically ---------------------------------
check("duplicate registrations pick the shorter name",
      fam("CC Battle Cry") == "CCBattleCry")
check("picking is stable across calls",
      fam("CC Battle Cry") == fam("CC Battle Cry"))

# --- what must NOT match ---------------------------------------------------
check("BadaBoom Pro BB is not BadaBoom BB", fam("BadaBoom Pro BB") is None)
check("CCWildWordsLower Italic is not CC Wild Words",
      fam("CCWildWordsLower Italic") is None)
check("Astounder Round LC BB is not Astounder Round BB",
      FM.FontIndex(["Astounder Round BB"]).resolve("Astounder Round LC BB") is None)
check("CDX Sidewinder is not CDX Seven Cent Pen", fam("CDX Sidewinder") is None)
check("a face nobody installed stays missing", fam("Telefante") is None)
check("Comic Neue is not Comic Sans MS", fam("Comic Neue") is None)
check("fuzzy can be switched off",
      fam("CDX Amram", fuzzy=False) is None)

# --- degenerate input ------------------------------------------------------
check("None resolves to nothing", idx.resolve(None) is None)
check("blank resolves to nothing", idx.resolve("   ") is None)
check("empty index resolves to nothing",
      FM.FontIndex([]).resolve("Arial") is None)
check("index tolerates blanks in the family list",
      FM.FontIndex(["", None, "Arial"]).resolve("Arial") is not None)

# --- aliases ---------------------------------------------------------------
custom = FM.FontIndex(INSTALLED, aliases={"Zud Juice": "Impact"})
check("a caller alias bridges unrelated names",
      custom.family_of("Zud Juice") == "Impact")
check("an alias to something uninstalled still misses",
      FM.FontIndex(["Arial"], aliases={"X": "Nope"}).resolve("X") is None)

# --- batch API -------------------------------------------------------------
wanted = ["CDX Amraam", "CCWildWords", "BadaBoom Pro BB", "Telefante"]
res, ren, mis = idx.report(wanted)
check("report separates exact hits", res == ["CDX Amraam"])
check("report lists forgiving hits with their Match",
      [w for w, _ in ren] == ["CCWildWords"] and ren[0][1].family == "CC Wild Words")
check("report lists the genuinely missing",
      mis == ["BadaBoom Pro BB", "Telefante"])
check("missing() keeps the original spelling",
      idx.missing(wanted) == ["BadaBoom Pro BB", "Telefante"])
check("is_available agrees with resolve", idx.is_available("CCWildWords") is True)
check("family_of falls back", idx.family_of("Telefante", "Arial") == "Arial")

print()
print("passed %d, failed %d" % (_pass, _fail))
sys.exit(1 if _fail else 0)
