# -*- coding: utf-8 -*-
"""Tolerant font-family matching (Qt-free core).

The same comic face reaches a machine under a dozen spellings. A rule may ask
for ``CC Wild Words`` while the installed family calls itself ``CCWildWords``;
a Fonts.com download registers ``ImaginaryFriendBBW00-Rg`` instead of
``Imaginary Friend BB``; a badly repacked OTF bakes the cut into the family
name (``BadaBoom Pro BB Regular``) so the plain family name matches nothing.
An exact ``name in families`` test fails on every one of those and the user
sees a wrong stand-in face with no idea why.

This module resolves a wanted name against the installed families through a
ladder of increasingly forgiving comparisons, stopping at the first tier that
hits. Tiers are ordered so that a confident match always beats a loose one:

    1  exact
    2  case-insensitive
    3  squashed          -- letters and digits only: CCWildWords == CC Wild Words
    4  tokens            -- word set, trailing cut stripped: Anime Ace Italic -> Anime Ace
    5  tokens, no tags   -- foundry/repack tags dropped too: Anime Ace 2.0 == Anime Ace 2.0 BB
    6  fuzzy             -- character-level near miss, guarded (see _fuzzy)

What it deliberately does NOT do is match faces that merely *look* related.
``BadaBoom Pro BB`` is not ``BadaBoom BB``, and ``CCWildWordsLower Italic`` is
not ``CC Wild Words`` -- Lower is a different cut of a different design. Words
that carry identity (``pro``, ``lower``, ``lc``, ``condensed``) are never
dropped, so those stay unresolved and the user still gets told the truth.

Typical use::

    idx = FontIndex(QFontDatabase().families())
    m = idx.resolve("CC Wild Words")
    if m:
        font.setFamily(m.family)        # the real installed name
        if m.italic:
            font.setItalic(True)        # cut asked for in the name, not the family
"""

import re
from difflib import SequenceMatcher

# --- vocabulary ------------------------------------------------------------
# Cut names. Stripped only from the END of a name and only while something
# else remains, so "Bold Wicker" keeps its Bold but "CCBattleCry-Regular"
# loses its Regular.
_ITALIC = {"italic", "ital", "oblique", "kursiv"}
_BOLD = {"bold", "bld", "semibold", "demibold", "extrabold", "ultrabold",
         "heavy", "black"}
_STYLE = _ITALIC | _BOLD | {
    "regular", "reg", "normal", "roman", "book", "medium", "med", "light",
    "extralight", "ultralight", "thin",
}

# Foundry initials and repack leftovers. Dropping these is a LAST-RESORT tier
# because it is lossy. Anything that distinguishes two real faces of the same
# family -- pro, lower, lc, condensed, wide -- must never appear here.
_TAGS = {"bb", "cc", "cdx", "ss", "lhf", "djb", "itc", "ff", "bt", "mt",
         "rg", "tb", "std", "com", "web", "webfont"}

# Web-shop debris that is not even a word: Fonts.com "W00"/"W1G" licence tags,
# iCiel repack branding, trial markers.
_DEBRIS = re.compile(r"W\d[\dA-Za-z](?![a-z])")
_DEBRIS_WORDS = re.compile(r"iCiel|PERSONAL[ _-]?USE|DEMO|TRIAL", re.IGNORECASE)

# Split on spaces/punctuation AND camelCase humps, keeping version numbers
# ("2.0") in one piece.
_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+(?:[.,]\d+)*")

# Built-in aliases for names no amount of normalising can bridge, because the
# installed family shares no words with the wanted one.
BUILTIN_ALIASES = {
    "cc wild words lower": "CCWildWordsLower",
    "wild words": "CC Wild Words",
    "badaboom": "BadaBoom BB",
}


class Match(object):
    """A resolved family plus the cut that was asked for in the name.

    `tier` names the comparison that hit (see the module docstring) and `exact`
    is True only for tier 1/2 -- callers that warn about substitutions should
    stay quiet for anything up to tier 5 but may still want to log tier 6.
    """

    __slots__ = ("family", "bold", "italic", "tier", "score")

    def __init__(self, family, bold=False, italic=False, tier="exact",
                 score=1.0):
        self.family = family
        self.bold = bold
        self.italic = italic
        self.tier = tier
        self.score = score

    @property
    def exact(self):
        return self.tier in ("exact", "case")

    def __repr__(self):
        cut = "".join(c for c, on in (("B", self.bold), ("I", self.italic)) if on)
        return "<Match %r%s via %s>" % (self.family, "/" + cut if cut else "",
                                        self.tier)

    def __eq__(self, other):
        return (isinstance(other, Match)
                and (self.family, self.bold, self.italic, self.tier)
                == (other.family, other.bold, other.italic, other.tier))


def _clean(name):
    """Strip web-shop debris and decorative junk before tokenising."""
    s = _DEBRIS_WORDS.sub(" ", name or "")
    return _DEBRIS.sub(" ", s)


def tokens(name):
    """Lower-case word list of *name*, camelCase humps split apart.

    ``"CCWildWords"`` and ``"CC Wild Words"`` both give
    ``["cc", "wild", "words"]``.
    """
    return [t.lower() for t in _TOKEN.findall(_clean(name))]


def squash(name):
    """Letters and digits only, lower-cased -- spacing and punctuation gone."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def split_cut(toks):
    """Peel trailing cut words off a token list.

    Returns ``(remaining_tokens, bold, italic)``. Stops while only one token is
    left, so a face actually *named* after a weight ("Bold Wicker", "Black
    Hole") keeps it.
    """
    out = list(toks)
    bold = italic = False
    while len(out) > 1 and out[-1] in _STYLE:
        t = out.pop()
        if t in _ITALIC:
            italic = True
        elif t in _BOLD:
            bold = True
    return out, bold, italic


def _key(toks, drop_tags):
    """Order-independent key for a token list.

    Sorting before joining makes camelCase splits collapse: ``["bada", "boom"]``
    and ``["badaboom"]`` both key to ``"badaboom"``.
    """
    if drop_tags:
        toks = [t for t in toks if t not in _TAGS]
    return "".join(sorted(toks))


def _significant(toks):
    """Words that carry identity -- neither cut names nor foundry tags."""
    return set(t for t in toks if t not in _STYLE and t not in _TAGS)


class FontIndex(object):
    """Lookup table over the installed families.

    Building it walks the family list once (a few thousand entries is a
    millisecond); every tier except the fuzzy one is then a dict hit, so
    resolving is cheap enough to call per rule and per preview repaint.
    """

    def __init__(self, families, aliases=None):
        self.families = [f for f in (families or []) if f and f.strip()]
        self.aliases = dict(BUILTIN_ALIASES)
        if aliases:
            self.aliases.update({(k or "").strip().lower(): v
                                 for k, v in aliases.items()})

        self._exact = set(self.families)
        self._ci = {}
        self._squash = {}
        self._tok = {}
        self._tok_notags = {}
        self._sig = {}

        for fam in self.families:
            self._ci.setdefault(fam.lower(), []).append(fam)
            self._squash.setdefault(squash(fam), []).append(fam)
            base, _, _ = split_cut(tokens(fam))
            self._tok.setdefault(_key(base, False), []).append(fam)
            self._tok_notags.setdefault(_key(base, True), []).append(fam)
            self._sig[fam] = _significant(base)

    # -- internals ---------------------------------------------------------
    def _pick(self, cands, wanted):
        """Deterministic winner when several families share a key.

        Closest spelling first, then the shorter name (``CCBattleCry`` beats
        ``CCBattleCry-Regular``), then alphabetical so results never wobble.
        """
        if len(cands) == 1:
            return cands[0]
        w = squash(wanted)
        return sorted(
            cands,
            key=lambda f: (-SequenceMatcher(None, w, squash(f)).ratio(),
                           len(f), f))[0]

    def _fuzzy(self, wanted, base, threshold):
        """Character-level near miss, guarded against same-family confusion.

        The guard is what keeps ``BadaBoom Pro BB`` away from ``BadaBoom BB``:
        a face whose identity words differ by a whole word is a different face,
        however similar the letters look. Only names carrying the *same* words
        may be rescued here, which limits tier 6 to real typos and spacing
        accidents.
        """
        w = squash(wanted)
        if len(w) < 4:
            return None
        want_sig = _significant(base)
        best, best_score = None, 0.0
        for fam in self.families:
            if len(self._sig[fam]) != len(want_sig):
                continue
            score = SequenceMatcher(None, w, squash(fam)).ratio()
            if score > best_score:
                best, best_score = fam, score
        if best is not None and best_score >= threshold:
            return best, best_score
        return None

    # -- API ---------------------------------------------------------------
    def resolve(self, name, fuzzy=True, threshold=0.90):
        """Best installed family for *name*, or None.

        Set ``fuzzy=False`` to stop after tier 5 when a wrong guess would be
        worse than an honest miss.
        """
        if not name or not name.strip():
            return None
        name = name.strip()

        if name in self._exact:
            return Match(name, tier="exact")

        hit = self._ci.get(name.lower())
        if hit:
            return Match(self._pick(hit, name), tier="case")

        alias = self.aliases.get(name.lower())
        if alias:
            sub = self.resolve(alias, fuzzy=False)
            if sub:
                sub.tier = "alias"
                return sub

        hit = self._squash.get(squash(name))
        if hit:
            return Match(self._pick(hit, name), tier="squash")

        toks = tokens(name)
        base, bold, italic = split_cut(toks)
        if not base:
            return None

        hit = self._tok.get(_key(base, False))
        if hit:
            return Match(self._pick(hit, name), bold, italic, "tokens")

        hit = self._tok_notags.get(_key(base, True))
        if hit:
            return Match(self._pick(hit, name), bold, italic, "tokens-notags")

        if fuzzy:
            got = self._fuzzy(name, base, threshold)
            if got:
                return Match(got[0], bold, italic, "fuzzy", got[1])

        return None

    def family_of(self, name, fallback=None, **kw):
        """Just the installed family name, or *fallback*."""
        m = self.resolve(name, **kw)
        return m.family if m else fallback

    def is_available(self, name, **kw):
        """True when *name* resolves to something installed."""
        return self.resolve(name, **kw) is not None

    def missing(self, names, **kw):
        """Those of *names* that resolve to nothing, original spelling kept."""
        return [n for n in (names or []) if not self.is_available(n, **kw)]

    def report(self, names, **kw):
        """``(resolved, renamed, missing)`` for a batch of wanted names.

        ``renamed`` lists ``(wanted, Match)`` pairs that only matched through a
        forgiving tier -- exactly the ones worth showing the user, because they
        are the names their rules should eventually be corrected to.
        """
        resolved, renamed, missing = [], [], []
        for n in (names or []):
            m = self.resolve(n, **kw)
            if m is None:
                missing.append(n)
            elif m.exact:
                resolved.append(n)
            else:
                renamed.append((n, m))
        return resolved, renamed, missing
