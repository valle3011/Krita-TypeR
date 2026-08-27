"""Font favourites with categories (Qt-free core).

A *favourite* is a font family the user has starred. Each favourite can belong
to any number of *categories* (Dialog, SFX, Titel, ...), so the relation is
many-to-many (1..n): one font can sit in several categories, and one category
groups several fonts. The user can then either search a font by name or pick a
category to narrow the list down.

This module is pure Python (no Qt) so it can be unit-tested headlessly, exactly
like ``layout.py``. The Qt widget in ``fontfav_ui.py`` drives an instance of
``FavoritesStore`` and persists it through injected read/write callbacks.

Persistence format (JSON), version 1::

    {
      "version": 1,
      "categories": ["Dialog", "SFX", "Titel"],   # display order, unique
      "fonts": {                                    # family -> its categories
          "Anime Ace 2": ["Dialog"],
          "CC Wild Words": ["Dialog", "SFX"]
      }
    }

Every category named inside ``fonts`` also appears in ``categories`` (the store
keeps that invariant; unknown categories referenced by a font are created on
the fly). Category matching is case-insensitive but the original casing is kept
for display.
"""

import json

VERSION = 1


def _norm(s):
    """Trim surrounding whitespace; return '' for anything non-string."""
    if not isinstance(s, str):
        return ""
    return s.strip()


def _match(name, query):
    """True if every whitespace-separated token of *query* is a substring of
    *name* (both compared case-insensitively). An empty query matches all."""
    q = _norm(query).lower()
    if not q:
        return True
    low = (name or "").lower()
    return all(tok in low for tok in q.split())


class FavoritesStore:
    """Holds the favourite fonts and their categories.

    All mutators are forgiving: blank names are ignored, duplicates collapse
    case-insensitively, and referencing a missing category creates it. Nothing
    here raises on ordinary bad input, so the UI never has to guard calls.
    """

    def __init__(self):
        self._categories = []          # ordered, unique display names
        self._fonts = {}               # family -> ordered list of categories
        self._ui = {}                  # small UI state (last filter, …)

    # ------------------------------------------------------------------ #
    #  Serialisation
    # ------------------------------------------------------------------ #
    @classmethod
    def from_json(cls, text):
        """Build a store from a JSON string. Tolerant: any malformed or missing
        piece yields an empty (or partially filled) store rather than raising."""
        store = cls()
        if not text:
            return store
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return store
        if not isinstance(data, dict):
            return store
        for cat in data.get("categories", []) or []:
            store.add_category(cat)
        fonts = data.get("fonts", {}) or {}
        if isinstance(fonts, dict):
            for fam, cats in fonts.items():
                fam = _norm(fam)
                if not fam:
                    continue
                if not isinstance(cats, list):
                    cats = []
                store.add_font(fam, cats)
        ui = data.get("ui", {})
        if isinstance(ui, dict):
            store._ui = dict(ui)
        return store

    def to_json(self):
        return json.dumps({
            "version": VERSION,
            "categories": list(self._categories),
            "fonts": {fam: list(cats) for fam, cats in self._fonts.items()},
            "ui": dict(self._ui),
        }, ensure_ascii=False)

    # ------------------------------------------------------------------ #
    #  Small UI state (survives round-trip; not part of the data model)
    # ------------------------------------------------------------------ #
    def ui_get(self, key, default=None):
        return self._ui.get(key, default)

    def ui_set(self, key, value):
        self._ui[key] = value

    # ------------------------------------------------------------------ #
    #  Categories
    # ------------------------------------------------------------------ #
    def categories(self):
        return list(self._categories)

    def _find_category(self, name):
        """Return the stored display name that matches *name* case-insensitively,
        or None."""
        low = _norm(name).lower()
        if not low:
            return None
        for c in self._categories:
            if c.lower() == low:
                return c
        return None

    def add_category(self, name):
        """Create a category. Returns the canonical (possibly pre-existing)
        display name, or None for a blank name."""
        name = _norm(name)
        if not name:
            return None
        existing = self._find_category(name)
        if existing:
            return existing
        self._categories.append(name)
        return name

    def rename_category(self, old, new):
        """Rename a category everywhere (list + every font's linkage). Returns
        the new canonical name, or None if *old* is unknown or *new* is blank."""
        cur = self._find_category(old)
        new = _norm(new)
        if not cur or not new:
            return None
        clash = self._find_category(new)
        if clash and clash != cur:
            # merge: fold *cur* into the existing *new*
            self._categories = [c for c in self._categories if c != cur]
            for fam in self._fonts:
                self._fonts[fam] = _dedup_keep_order(
                    [clash if c == cur else c for c in self._fonts[fam]])
            return clash
        self._categories = [new if c == cur else c for c in self._categories]
        for fam in self._fonts:
            self._fonts[fam] = [new if c == cur else c for c in self._fonts[fam]]
        return new

    def remove_category(self, name):
        """Delete a category and strip it from every font. Fonts left without
        any category stay as favourites (uncategorised). Returns True if it
        existed."""
        cur = self._find_category(name)
        if not cur:
            return False
        self._categories = [c for c in self._categories if c != cur]
        for fam in self._fonts:
            self._fonts[fam] = [c for c in self._fonts[fam] if c != cur]
        return True

    # ------------------------------------------------------------------ #
    #  Fonts
    # ------------------------------------------------------------------ #
    def fonts(self):
        """All favourite families, case-insensitively sorted."""
        return sorted(self._fonts.keys(), key=lambda f: f.lower())

    def is_favorite(self, family):
        return _norm(family) in self._fonts if isinstance(family, str) else False

    def add_font(self, family, categories=None):
        """Add *family* as a favourite (idempotent) and link it to *categories*
        (each created if new). Returns the family, or None for a blank name."""
        family = _norm(family)
        if not family:
            return None
        self._fonts.setdefault(family, [])
        for cat in (categories or []):
            canon = self.add_category(cat)
            if canon and canon not in self._fonts[family]:
                self._fonts[family].append(canon)
        return family

    def remove_font(self, family):
        family = _norm(family)
        if family in self._fonts:
            del self._fonts[family]
            return True
        return False

    def font_categories(self, family):
        return list(self._fonts.get(_norm(family), []))

    def set_font_categories(self, family, categories):
        """Replace a favourite's category set. Adds the font if new. Unknown
        categories are created."""
        family = _norm(family)
        if not family:
            return None
        self._fonts[family] = []
        for cat in (categories or []):
            canon = self.add_category(cat)
            if canon and canon not in self._fonts[family]:
                self._fonts[family].append(canon)
        return family

    def toggle(self, family, category):
        """Add or remove one category link for a font (adding the font if new).
        Returns True if the link is now present, False if it was removed."""
        family = _norm(family)
        if not family:
            return False
        canon = self.add_category(category)
        if not canon:
            return False
        self._fonts.setdefault(family, [])
        if canon in self._fonts[family]:
            self._fonts[family] = [c for c in self._fonts[family] if c != canon]
            return False
        self._fonts[family].append(canon)
        return True

    # ------------------------------------------------------------------ #
    #  Queries (for the picker)
    # ------------------------------------------------------------------ #
    def fonts_in_category(self, category=None, search=""):
        """Favourites in *category* (None/'' => all) whose name matches *search*,
        case-insensitively sorted. The special value ``UNCATEGORIZED`` returns
        favourites with no category at all."""
        if category == UNCATEGORIZED:
            pool = [f for f in self._fonts if not self._fonts[f]]
        elif not category:
            pool = list(self._fonts.keys())
        else:
            canon = self._find_category(category)
            if not canon:
                return []
            pool = [f for f in self._fonts if canon in self._fonts[f]]
        pool = [f for f in pool if _match(f, search)]
        return sorted(pool, key=lambda f: f.lower())

    def missing_fonts(self, installed, resolve=None):
        """Favourite families that are NOT available, case-insensitively sorted.

        By default a favourite counts as available when its name appears in
        *installed* (compared case-insensitively). Pass *resolve* -- any
        callable mapping a wanted name to an installed one, or to None -- to
        accept spelling variants as well; the UI hands in `fontmatch` so a
        favourite saved as "CCWildWords" is not reported missing on a machine
        that calls the same face "CC Wild Words". This module stays free of the
        dependency so it can still be tested standalone."""
        if resolve is not None:
            return sorted((f for f in self._fonts if not resolve(f)),
                          key=lambda f: f.lower())
        inst = {(f or "").lower() for f in (installed or [])}
        return sorted((f for f in self._fonts if f.lower() not in inst),
                      key=lambda f: f.lower())

    def merge(self, other):
        """Fold another store's categories and font links into this one
        (favourites add up, links union, nothing is dropped). Returns the number
        of *new* favourite families added."""
        if other is None:
            return 0
        before = set(self._fonts)
        for c in other.categories():
            self.add_category(c)
        for fam in other.fonts():
            self.add_font(fam, other.font_categories(fam))
        return len(set(self._fonts) - before)

    def category_counts(self):
        """Map each category to how many favourites reference it."""
        counts = {c: 0 for c in self._categories}
        for cats in self._fonts.values():
            for c in cats:
                if c in counts:
                    counts[c] += 1
        return counts


#: Sentinel category meaning "favourites without any category".
UNCATEGORIZED = "\x00__uncategorized__"


def _dedup_keep_order(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
