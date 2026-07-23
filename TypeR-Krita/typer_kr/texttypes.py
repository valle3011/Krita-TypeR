"""Manga text-type catalogue.

A typesetter never just places "text": every kind of text on a page has its
own established look. A whisper is small and lowercase, a radio voice is
italic, emphasis is bold-italic (not plain bold), a sound effect needs a halo
because it sits on the artwork. This module names each kind once and carries
both the fonts it should prefer and the TypeR style that renders it, so
picking a type sets the whole look up in one step.

The conventions follow standard comic lettering (Blambot's "Comic Book Grammar
& Tradition") and scanlation practice (Nekyou, Insidescanlation):

* emphasis is bold-italic; plain bold is essentially unused in comic dialogue
* thoughts read "quieter" than speech: lighter/grey, often italic
* whispers are small, grey and lowercase
* radio/phone/TV voices are italic
* sound effects and any text over art need an outline so they stay readable
* dialogue is set in capitals

Fonts are *named, not shipped*. Most comic fonts are licensed, so each entry
lists candidates best-first and `resolve_font()` picks the first family that
is actually installed, falling back to something that always exists. Use
`missing_font()` to tell the user which face a type really wants.
"""

# --- font candidate lists ------------------------------------------------
# Best first: the canonical comic faces, then broadly available stand-ins so a
# type is never left without a face.
_SPEECH = ["CC Wild Words", "Wild Words", "Anime Ace 2.0", "Anime Ace BB",
           "Anime Ace", "Comic Neue", "Comic Sans MS", "Arial"]
_THOUGHT = ["CC Jim Lee", "Anime Ace 2.0", "Comic Neue", "Comic Sans MS", "Arial"]
_SHOUT = ["Zud Juice", "CC Wild Words", "Anime Ace 2.0", "Impact",
          "Arial Black", "Arial"]
_SMALL = ["Augie", "CC Wild Words", "Comic Neue", "Comic Sans MS", "Arial"]
_NARRATION = ["Tekton Pro", "Felt", "Flair", "Franklin Gothic Book",
              "Segoe UI", "Arial"]
_RADIO = ["Felt", "GF Matilda Bold", "Anime Ace 2.0", "Segoe UI", "Arial"]
_ROBOT = ["OCR A Extended", "Consolas", "Courier New", "Arial"]
_MONSTER = ["CC Zombie Guts", "Chiller", "Impact", "Arial Black", "Arial"]
_HAND = ["Ampersand", "Gooddog", "SF Grunge Sans", "Segoe Script",
         "Comic Sans MS", "Arial"]
_SFX = ["Badaboom BB", "CC Splashdown", "Impact", "Arial Black", "Arial"]
_DISPLAY = ["Bernard MT Condensed", "VAG Rounded BT", "Impact",
            "Arial Black", "Arial"]

# Shared colours: pure black speech, softer greys for the "quiet" voices.
_INK = "#000000"
_QUIET = "#444444"
_FAINT = "#555555"

# Every entry only sets the fields that actually matter for that type;
# TypeR's _apply_settings() takes partial dicts.
TEXT_TYPES = [
    # ---------------- inside the balloon: the voice ----------------
    {"id": "dialogue", "group": "balloon", "fonts": _SPEECH,
     "style": {"size": 13, "case": "upper", "bold": False, "italic": False,
               "color": _INK, "outline": False, "align": "center",
               "valign": "middle", "round": True}},

    {"id": "emphasis", "group": "balloon", "fonts": _SPEECH,
     # Comics use bold-italic for emphasis; plain bold is a beginner tell.
     "style": {"size": 13, "case": "upper", "bold": True, "italic": True,
               "color": _INK, "outline": False, "align": "center"}},

    {"id": "thought", "group": "balloon", "fonts": _THOUGHT,
     "style": {"size": 13, "case": "upper", "bold": False, "italic": True,
               "color": _QUIET, "outline": False, "align": "center",
               "round": True}},

    {"id": "whisper", "group": "balloon", "fonts": _SMALL,
     "style": {"size": 10, "case": "lower", "bold": False, "italic": False,
               "color": _FAINT, "outline": False, "align": "center"}},

    {"id": "shout", "group": "balloon", "fonts": _SHOUT,
     "style": {"size": 17, "case": "upper", "bold": True, "italic": False,
               "color": _INK, "outline": False, "align": "center"}},

    {"id": "weak", "group": "balloon", "fonts": _SMALL,
     "style": {"size": 10, "case": "lower", "bold": False, "italic": True,
               "color": _QUIET, "outline": False, "align": "center"}},

    {"id": "radio", "group": "balloon", "fonts": _RADIO,
     "style": {"size": 12, "case": "upper", "bold": False, "italic": True,
               "color": _INK, "outline": False, "align": "center"}},

    {"id": "robot", "group": "balloon", "fonts": _ROBOT,
     "style": {"size": 12, "case": "upper", "bold": True, "italic": False,
               "color": _INK, "outline": False, "align": "center",
               "round": False}},

    {"id": "telepathy", "group": "balloon", "fonts": _THOUGHT,
     "style": {"size": 12, "case": "upper", "bold": False, "italic": True,
               "color": _QUIET, "outline": False, "align": "center"}},

    {"id": "monster", "group": "balloon", "fonts": _MONSTER,
     "style": {"size": 15, "case": "upper", "bold": True, "italic": False,
               "color": _INK, "outline": False, "align": "center"}},

    {"id": "song", "group": "balloon", "fonts": _SPEECH,
     # Sung dialogue is italic and framed by music notes (see wrap_marks).
     "style": {"size": 13, "case": "none", "bold": False, "italic": True,
               "color": _INK, "align": "center"},
     "wrap_marks": ("♪ ", " ♫")},

    {"id": "foreign", "group": "balloon", "fonts": _SPEECH,
     # Foreign speech is bracketed in angle brackets, often italic.
     "style": {"size": 13, "case": "upper", "bold": False, "italic": True,
               "color": _INK, "align": "center"},
     "wrap_marks": ("<", ">")},

    {"id": "distress", "group": "balloon", "fonts": _SMALL,
     "style": {"size": 10, "case": "lower", "bold": False, "italic": True,
               "color": _QUIET, "align": "center"}},

    # ---------------- outside: boxes, art, margins ----------------
    {"id": "narration", "group": "outside", "fonts": _NARRATION,
     "style": {"size": 12, "case": "upper", "bold": False, "italic": False,
               "color": _INK, "outline": False, "align": "center",
               "round": False}},

    {"id": "monologue", "group": "outside", "fonts": _NARRATION,
     # Internal-monologue captions have largely replaced thought balloons.
     "style": {"size": 12, "case": "upper", "bold": False, "italic": True,
               "color": _INK, "align": "center", "round": False}},

    {"id": "offpanel", "group": "outside", "fonts": _SPEECH,
     "style": {"size": 13, "case": "upper", "bold": False, "italic": False,
               "color": _INK, "align": "center"}},

    {"id": "aside", "group": "outside", "fonts": _HAND,
     "style": {"size": 11, "case": "none", "bold": False, "italic": True,
               "color": _INK, "outline": False, "align": "center"}},

    {"id": "sfx", "group": "outside", "fonts": _SFX,
     # Sound effects sit on the artwork, so they need a white halo to stay
     # readable. Big, heavy, capitals.
     "style": {"size": 30, "case": "upper", "bold": True, "italic": False,
               "color": _INK, "outline": True, "outline_w": 3,
               "outline_color": "#ffffff", "align": "center"}},

    {"id": "signage", "group": "outside", "fonts": _NARRATION,
     # Text on signs/cans/screens; usually needs warping onto the surface.
     "style": {"size": 11, "case": "upper", "bold": False, "italic": False,
               "color": _INK, "outline": True, "outline_w": 2,
               "outline_color": "#ffffff", "align": "center"}},

    {"id": "display", "group": "outside", "fonts": _DISPLAY,
     "style": {"size": 26, "case": "upper", "bold": True, "italic": False,
               "color": _INK, "outline": False, "align": "center"}},

    {"id": "tn", "group": "outside", "fonts": _NARRATION,
     # Translator's note: small, left aligned, under the panel.
     "style": {"size": 9, "case": "none", "bold": False, "italic": False,
               "color": _INK, "align": "left", "valign": "top"}},
]

# The built-in catalogue never changes at runtime; keep it so custom types can
# be re-merged idempotently without losing or duplicating the built-ins.
_BUILTIN_TYPES = list(TEXT_TYPES)
_BY_ID = {t["id"]: t for t in TEXT_TYPES}

# Baseline look a user-defined type gets unless it carries its own style: plain
# capitalized speech, so a fresh custom type is immediately usable.
_CUSTOM_STYLE = {"size": 13, "case": "upper", "bold": False, "italic": False,
                 "color": _INK, "outline": False, "align": "center",
                 "valign": "middle", "round": True}


def _norm_id(text):
    """A safe, stable id from a label: lowercase, non-alphanumerics -> '_'.
    Custom ids are prefixed 'u_' so they can never collide with a built-in id
    or its 'tt_<id>' translation key."""
    base = "".join(c if c.isalnum() else "_" for c in (text or "").lower())
    base = base.strip("_") or "type"
    return "u_" + base


def register_custom(entries):
    """Merge user-defined text types into the catalogue.

    Each entry is a dict {id?, label, font | fonts:[...], style?, group?}. The
    caller owns storage (kritarc); this only rebuilds the in-memory catalogue.
    Idempotent: previously registered custom types are dropped first, so it is
    safe to call again whenever the user's list changes. Returns the list of
    registered custom-type dicts (with their final ids)."""
    global TEXT_TYPES, _BY_ID
    TEXT_TYPES = list(_BUILTIN_TYPES)              # start from the built-ins
    used = {t["id"] for t in TEXT_TYPES}
    registered = []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        label = str(e.get("label") or "").strip()
        tid = str(e.get("id") or "").strip() or _norm_id(label)
        if not tid or not label:
            continue
        while tid in used:                         # keep ids unique
            tid += "_2"
        used.add(tid)
        fonts = e.get("fonts")
        if not isinstance(fonts, list):
            fonts = [e.get("font")] if e.get("font") else []
        fonts = [str(f) for f in fonts if f] or ["Arial"]
        style = dict(_CUSTOM_STYLE)
        if isinstance(e.get("style"), dict):
            style.update(e["style"])
        entry = {"id": tid, "group": str(e.get("group") or "custom"),
                 "label": label, "fonts": fonts, "style": style, "custom": True}
        TEXT_TYPES.append(entry)
        # Return the full definition (incl. style/group) so the caller can
        # persist it verbatim — a captured style must round-trip, not be lost.
        registered.append({"id": tid, "label": label, "font": fonts[0],
                           "fonts": list(fonts), "style": dict(style),
                           "group": entry["group"]})
    _BY_ID = {t["id"]: t for t in TEXT_TYPES}
    return registered


def is_custom(type_id):
    """True for a user-defined type (not one of the built-ins)."""
    t = _BY_ID.get(type_id)
    return bool(t and t.get("custom"))


def label(type_id):
    """Display label for a custom type; None for built-ins (which are named via
    the caller's i18n table under 'tt_<id>')."""
    t = _BY_ID.get(type_id)
    return t.get("label") if t and t.get("custom") else None


def ids():
    """All text-type ids, in catalogue (reading) order."""
    return [t["id"] for t in TEXT_TYPES]


def get(type_id):
    """The raw catalogue entry, or None."""
    return _BY_ID.get(type_id)


def _norm(name):
    return (name or "").strip().lower()


def resolve_font(candidates, installed):
    """First candidate that is actually installed.

    `installed` is any iterable of family names (QFontDatabase().families()).
    Falls back to the last candidate so a type always names *something*.
    """
    have = {_norm(f) for f in (installed or ())}
    for fam in candidates:
        if _norm(fam) in have:
            return fam
    return candidates[-1] if candidates else ""


def missing_font(type_id, installed, overrides=None):
    """The face this type really wants, if it is not installed.

    Returns None when the preferred font is present — or when the user has
    picked their own — so callers only warn when the look is actually a
    stand-in nobody asked for.
    """
    if (overrides or {}).get(type_id):
        return None
    t = _BY_ID.get(type_id)
    if not t or not t["fonts"]:
        return None
    have = {_norm(f) for f in (installed or ())}
    if _norm(t["fonts"][0]) in have:
        return None
    return t["fonts"][0] if resolve_font(t["fonts"], installed) != t["fonts"][0] else None


def default_font(type_id, installed=()):
    """The font this type falls back to when the user has not chosen one."""
    t = _BY_ID.get(type_id)
    return resolve_font(t["fonts"], installed) if t else ""


def effective_font(type_id, installed=(), overrides=None):
    """The font a type actually uses: the user's choice, else the default.

    `overrides` is a plain {type_id: family} dict owned by the caller, so this
    module stays free of any settings storage.
    """
    own = (overrides or {}).get(type_id)
    if own:
        return own
    return default_font(type_id, installed)


def style_for(type_id, installed=(), overrides=None):
    """Full style dict for a type, with the font resolved.

    The result is shaped exactly like a TypeR preset, so it can be handed
    straight to _apply_preset().
    """
    t = _BY_ID.get(type_id)
    if not t:
        return {}
    style = dict(t["style"])
    style["font"] = effective_font(type_id, installed, overrides)
    return style


def wrap_marks(type_id):
    """Prefix/suffix a type frames its text with (music notes, angle brackets).

    Returns ("", "") for types that don't frame their text.
    """
    t = _BY_ID.get(type_id)
    return tuple(t.get("wrap_marks", ("", ""))) if t else ("", "")
