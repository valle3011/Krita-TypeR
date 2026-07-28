# -*- coding: utf-8 -*-
"""Qt-free matching helpers for SFX rules.

Two jobs live here:

* normalizing SFX spellings so stretched/decorated writings all match the same
  keyword (``normalize_sfx`` / ``keyword_matches``, used for the font
  suggestions), and
* filtering the rule list in the docker for the search box
  (``rule_matches_query``).

No Qt / Krita imports, so ``test_typer_logic.py`` can load this module directly.
"""
import re

# Normalize stretched SFX spellings so "BOOOOM", "BOOM" and "GASHAAAN" are all
# treated the same.
_RUN_RE = re.compile(r"(.)\1+")          # any run of a repeated character

# "font:foo" style prefixes: which rule fields a single search token may hit.
_FIELD_PREFIXES = {
    "font": ("fonts",),
    "f": ("fonts",),
    "group": ("group",),
    "g": ("group",),
    "kw": ("keywords",),
}
_ALL_FIELDS = ("keywords", "fonts", "group")


def normalize_sfx(text):
    """Vereinheitlicht ein SFX-Wort fürs Stichwort-Matching:
    klein schreiben, jeden Lauf gleicher Zeichen auf EIN Zeichen stauchen
    ("booooom"->"bom", "gashaaan"->"gashan"), und alles außer Buchstaben/
    Ziffern entfernen ("ka-boom!"->"kabom"). Stichwort und Text werden gleich
    behandelt, daher matchen unterschiedlich gedehnte Schreibweisen sicher.

    Ausnahme: Ein Wort aus nur EINEM wiederholten Zeichen (z. B. "zzz") würde
    sonst auf ein einziges Zeichen schrumpfen und ignoriert werden; daher
    behalten wir dort zwei Zeichen ("zzz"/"zzzz" -> "zz")."""
    raw = re.sub(r"[^a-z0-9]+", "", (text or "").lower())
    s = _RUN_RE.sub(r"\1", raw)
    if len(s) == 1 and len(raw) >= 2:
        s = s * 2
    return s


def keyword_matches(keyword, text_norm):
    """True, wenn das gestauchte Stichwort zum gestauchten Text passt.

    - 1 Zeichen Rest  -> ignorieren (zu breit).
    - 2 Zeichen Rest  -> EXAKT (so matchen "ow"/"gr"/"ah" nur als ganzes Wort,
      nicht versteckt in "pow"/"grab"/"haha").
    - 3+ Zeichen      -> Teilstring (so matchen auch verdoppelte/gedehnte
      Formen wie "boom-boom" -> "bombom" über "boom" -> "bom")."""
    kw = normalize_sfx(keyword)
    if len(kw) < 2:
        return False
    if len(kw) == 2:
        return text_norm == kw
    return kw in text_norm


def _split_token(token):
    """('font:wild', ...) -> ('wild', ('fonts',)). Unknown or empty prefixes
    are left alone, so a plain "boom" searches every field and a stray colon
    (e.g. a font actually named "a:b") still works as a substring."""
    head, sep, rest = token.partition(":")
    if sep and rest:
        fields = _FIELD_PREFIXES.get(head)
        if fields:
            return rest, fields
    return token, _ALL_FIELDS


def _token_matches(rule, token, fields):
    """One search token against one rule, restricted to `fields`."""
    needle = token.casefold()
    if "keywords" in fields:
        norm = normalize_sfx(token)
        for kw in rule.get("keywords", []):
            if needle in (kw or "").casefold():
                return True
            # same fuzzy matching as the suggestions: "BOOOOM!" finds "boom"
            if norm and keyword_matches(kw, norm):
                return True
    if "fonts" in fields:
        for fo in rule.get("fonts", []):
            if needle in (fo or "").casefold():
                return True
    if "group" in fields:
        if needle in (rule.get("group") or "").casefold():
            return True
    return False


def rule_matches_query(rule, query):
    """True if `rule` should stay visible for the search box text `query`.

    An empty query matches everything. Several words narrow the result (AND);
    each word may hit a keyword, a font name or the group name. A word can be
    limited to one field with `font:`/`f:`, `group:`/`g:` or `kw:`."""
    tokens = (query or "").split()
    if not tokens:
        return True
    for token in tokens:
        text, fields = _split_token(token)
        if not text:
            continue
        if not _token_matches(rule, text, fields):
            return False
    return True
