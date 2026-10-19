# -*- coding: utf-8 -*-
"""Giongo: turn a typed sound word into drawn manga SFX lettering.

The idea follows MIYADAIKU's browser tool *擬音ジェネレーター* (Oyasumi Game Dev,
tools.oyasumi-gamedev.com/giongo/): type "ドドドド" or "きゃぁぁぁ", pick a kind
of sound, and roll variations until one fits the panel. None of that tool's
code is used here; this is an independent implementation of the idea for
Krita.

This module is the Qt-free half — the rules and the geometry — so it can be
tested without Krita or Qt:

  * the **sound types** (impact, rumble, slash, cute, …) and the parameters
    each one starts from;
  * **おまかせ / auto**: a fixed rule table that reads the sound (dakuten, ッ,
    ー, ン, repeats, small kana) and picks a type. No AI, just rules;
  * the **macro sliders** Power / Roughness / Momentum, applied on top of the
    individual settings;
  * the **layout**: letters along a bent path, growing or shrinking, leaning,
    bouncing and wobbling — one placement per letter;
  * **gacha** and **mutation**: random parameter sets, reproducible from a
    seed.

Drawing the placements is :mod:`giongo_render`'s job.
"""
import copy
import json
import math
import random
import unicodedata

# --- the sound types -------------------------------------------------------
# `fonts` is a preference list of free (SIL OFL / M+) families; the first one
# installed wins. They are suggestions, not requirements: with none of them
# installed the system's bold sans is used.
#
# Widths (`thicken`, outline widths, shadow offsets) are fractions of the
# letter size, so a preset looks the same at 40 px and at 400 px.

TYPES = [
    {"id": "impact",
     "fonts": ["Dela Gothic One", "Zen Kaku Gothic New", "Bowlby One",
               "Bangers"],
     "params": {"size_start": 80, "size_end": 135, "spacing": -12,
                "rise": 6, "bend": 8, "lean": 30, "rot_var": 8,
                "jitter": 18, "size_var": 10, "thicken": 2.0,
                "outlines": [["#ffffff", 7.0]],
                "fill": "#111111"}},
    {"id": "rumble",
     "fonts": ["Reggae One", "Dela Gothic One", "Black Ops One"],
     "params": {"size_start": 120, "size_end": 75, "spacing": -8,
                "rise": -4, "bend": 0, "lean": 0, "rot_var": 4,
                "jitter": 10, "size_var": 6, "thicken": 1.5, "shake": 2,
                "outlines": [["#111111", 3.0], ["#ffffff", 5.0]],
                "fill": "#ffffff"}},
    {"id": "slash",
     "fonts": ["Yuji Syuku", "Yuji Boku", "Knewave", "Caveat Brush"],
     "params": {"size_start": 105, "size_end": 90, "spacing": -18,
                "rise": 14, "bend": -6, "lean": 60, "slant": 18,
                "stretch": 30, "rot_var": 6, "jitter": 12, "size_var": 8,
                "afterimage": 3, "outlines": [["#ffffff", 5.0]],
                "fill": "#111111"}},
    {"id": "cute",
     "fonts": ["Mochiy Pop One", "Hachi Maru Pop", "Titan One",
               "Cherry Bomb One"],
     "params": {"size_start": 100, "size_end": 100, "spacing": 2,
                "rise": 4, "bend": 18, "lean": 40, "bounce": 45,
                "rot_var": 14, "jitter": 10, "size_var": 12,
                "outlines": [["#111111", 3.0], ["#ffffff", 5.0]],
                "fill": "#ffffff"}},
    {"id": "drops",
     "fonts": ["Yusei Magic", "Klee One", "Zen Kurenaido"],
     "params": {"size_start": 100, "size_end": 85, "spacing": 10,
                "rise": -8, "bend": 10, "lean": 20, "bounce": 20,
                "rot_var": 10, "jitter": 14, "size_var": 10,
                "outlines": [["#ffffff", 5.0]], "fill": "#111111"}},
    {"id": "small",
     "fonts": ["Klee One", "Zen Kurenaido", "Yomogi", "Kalam"],
     "params": {"size_start": 100, "size_end": 100, "spacing": 6,
                "rise": 3, "bend": 0, "lean": 0, "rot_var": 6,
                "jitter": 8, "size_var": 6,
                "outlines": [["#ffffff", 4.0]], "fill": "#111111"}},
    {"id": "glare",
     "fonts": ["Kaisei Tokumin", "Yuji Mai", "Zen Kaku Gothic New"],
     "params": {"vertical": True, "size_start": 100, "size_end": 100,
                "spacing": 35, "rise": 0, "bend": 0, "lean": 0,
                "rot_var": 2, "jitter": 4, "size_var": 0,
                "outlines": [["#ffffff", 4.0]], "fill": "#111111"}},
    {"id": "pop",
     "fonts": ["Potta One", "RocknRoll One", "Lilita One", "Bangers"],
     "params": {"size_start": 90, "size_end": 115, "spacing": -6,
                "rise": 8, "bend": 14, "lean": 50, "bounce": 25,
                "rot_var": 12, "jitter": 12, "size_var": 10,
                "thicken": 1.0, "extrude": 6, "shadow_dx": 5.0,
                "shadow_dy": 7.0, "shadow_color": "#111111",
                "outlines": [["#111111", 3.0], ["#ffffff", 4.0]],
                "fill": "#9a9a9a"}},
    {"id": "machine",
     "fonts": ["DotGothic16", "Bungee", "Black Ops One"],
     "params": {"size_start": 100, "size_end": 100, "spacing": 4,
                "rise": 0, "bend": 0, "lean": 0, "rot_var": 0,
                "jitter": 3, "size_var": 0, "shake": 1,
                "outlines": [["#ffffff", 4.0]], "fill": "#111111"}},
]

TYPE_IDS = [t["id"] for t in TYPES]
_TYPE_BY_ID = {t["id"]: t for t in TYPES}

# Every parameter with its default and, for numbers, the range a slider may
# take. Kept in one table so loading a saved/shared set can clamp it.
DEFAULTS = {
    "type": "impact",
    "font": "",             # "" = the type's first installed font
    "bold": False,
    "letter_px": 160,       # size of one letter (px, at 100 %)
    "vertical": False,
    "merge_bars": True,     # "ドーーン": the ーー becomes one long stroke
    "spacing": 0,           # % of the letter size (negative = overlap)
    "rise": 0,              # degrees the path climbs (horizontal) / leans
    "bend": 0,              # % of the path length the middle bulges out
    "size_start": 100,      # % at the start of the path
    "size_end": 100,        # % at the end of the path
    "lean": 0,              # 0 = upright, 100 = letters follow the path
    "slant": 0,             # degrees of italic shear
    "stretch": 0,           # % wider (+) or narrower (-) along the path
    "bounce": 0,            # % of the size letters hop up and down
    "jitter": 0,            # % wobble of the position
    "rot_var": 0,           # degrees of random rotation
    "size_var": 0,          # % random size
    "thicken": 0.0,         # % of the size added around each stroke
    "fill": "#111111",
    "fill_mode": "solid",   # solid | gradient | tone
    "fill2": "#d02020",     # gradient end
    "tone_dot": 8,          # halftone dot spacing (px)
    "outlines": [["#ffffff", 5.0]],   # [colour, width % of size], inner first
    "outline_mode": "letter",         # letter | merged
    "shadow_dx": 0.0,       # % of the size
    "shadow_dy": 0.0,
    "shadow_color": "#111111",
    "extrude": 0,           # 0 = flat shadow, n = n steps of 3D extrusion
    "shake": 0,             # trembling line-only copies
    "afterimage": 0,        # faint copies trailing behind the motion
    "power": 0,             # macro sliders, -100..100 (0 = type default)
    "rough": 0,
    "momentum": 0,
    "seed": 1,
}

RANGES = {
    "letter_px": (8, 2000), "spacing": (-60, 150), "rise": (-60, 60),
    "bend": (-80, 80), "size_start": (20, 300), "size_end": (20, 300),
    "lean": (0, 100), "slant": (-45, 45), "stretch": (-60, 150),
    "bounce": (0, 100), "jitter": (0, 100), "rot_var": (0, 60),
    "size_var": (0, 60), "thicken": (0.0, 12.0), "tone_dot": (3, 60),
    "shadow_dx": (-40.0, 40.0), "shadow_dy": (-40.0, 40.0),
    "extrude": (0, 30), "shake": (0, 5), "afterimage": (0, 6),
    "power": (-100, 100), "rough": (-100, 100), "momentum": (-100, 100),
    "seed": (0, 2 ** 31 - 1),
}

MAX_OUTLINES = 3
FILL_MODES = ("solid", "gradient", "tone")
OUTLINE_MODES = ("letter", "merged")


def type_info(tid):
    return _TYPE_BY_ID.get(tid)


def default_params(tid="impact"):
    """A full parameter set for type `tid` (the type's look on top of the
    global defaults)."""
    p = copy.deepcopy(DEFAULTS)
    t = _TYPE_BY_ID.get(tid) or TYPES[0]
    p["type"] = t["id"]
    p.update(copy.deepcopy(t["params"]))
    return p


def apply_type(params, tid):
    """Switch to type `tid`, keeping what is not a matter of style: the font
    choice, the letter size, the seed and the macro sliders."""
    keep = {k: params.get(k, DEFAULTS[k])
            for k in ("letter_px", "seed", "power", "rough", "momentum")}
    p = default_params(tid)
    p.update(keep)
    return p


def _is_color(v):
    if not isinstance(v, str) or not v.startswith("#"):
        return False
    h = v[1:]
    return len(h) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in h)


def sanitize(params):
    """A clean parameter set from anything (a saved setting, a shared JSON):
    unknown keys dropped, missing ones defaulted, numbers clamped, wrong types
    replaced. Never raises."""
    p = copy.deepcopy(DEFAULTS)
    if not isinstance(params, dict):
        return p
    tid = params.get("type")
    if tid in _TYPE_BY_ID:
        p["type"] = tid
    for k, dv in DEFAULTS.items():
        if k in ("type", "outlines") or k not in params:
            continue
        v = params[k]
        if isinstance(dv, bool):
            p[k] = bool(v)
        elif isinstance(dv, (int, float)):
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if math.isnan(v) or math.isinf(v):
                continue
            lo, hi = RANGES.get(k, (None, None))
            if lo is not None:
                v = min(max(v, lo), hi)
            p[k] = int(round(v)) if isinstance(dv, int) else v
        elif k in ("fill", "fill2", "shadow_color"):
            if _is_color(v):
                p[k] = v
        elif k == "fill_mode":
            if v in FILL_MODES:
                p[k] = v
        elif k == "outline_mode":
            if v in OUTLINE_MODES:
                p[k] = v
        elif isinstance(dv, str):
            if isinstance(v, str):
                p[k] = v
    outs = []
    for o in params.get("outlines", p["outlines"]) or []:
        try:
            col, w = o[0], float(o[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if _is_color(col) and w > 0 and not math.isinf(w):
            outs.append([col, min(w, 40.0)])
    p["outlines"] = outs[:MAX_OUTLINES]
    return p


def to_json(params):
    return json.dumps(sanitize(params), ensure_ascii=False, sort_keys=True)


def from_json(text):
    try:
        return sanitize(json.loads(text))
    except (TypeError, ValueError):
        return sanitize(None)


# --- macro sliders ---------------------------------------------------------

def _clamp(k, v):
    lo, hi = RANGES[k]
    return min(max(v, lo), hi)


def effective(params):
    """The parameters the layout and the renderer actually use: the
    individual settings with Power / Roughness / Momentum applied on top.

    0 on a macro slider changes nothing, so the individual sliders stay the
    truth and the macros are a quick way to push a whole group of them."""
    p = sanitize(params)
    pw = p["power"] / 100.0
    rg = p["rough"] / 100.0
    mo = p["momentum"] / 100.0
    if pw:
        f = 1.0 + 0.8 * pw
        p["thicken"] = _clamp("thicken", p["thicken"] * f + 1.5 * max(pw, 0))
        p["outlines"] = [[c, max(0.2, w * f)] for c, w in p["outlines"]]
        # the size progression: more power, more "coming at you"
        p["size_end"] = _clamp("size_end", p["size_end"] + 35 * pw)
        p["size_start"] = _clamp("size_start", p["size_start"] - 15 * pw)
    if rg:
        p["jitter"] = _clamp("jitter", p["jitter"] + 35 * rg)
        p["rot_var"] = _clamp("rot_var", p["rot_var"] * (1 + rg) + 8 * rg)
        p["size_var"] = _clamp("size_var", p["size_var"] + 14 * rg)
    if mo:
        p["lean"] = _clamp("lean", p["lean"] + 50 * mo)
        p["slant"] = _clamp("slant", p["slant"] + 16 * mo)
        p["stretch"] = _clamp("stretch", p["stretch"] + 30 * mo)
        p["rise"] = _clamp("rise", p["rise"] + 8 * mo)
    return p


# --- reading the sound -----------------------------------------------------

_BARS = "ーｰ〜～－—―"
_SMALL = "ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ"
_VOWELS = set("あいうえおアイウエオ")
_SOFT = set("ふぷぽぴぱぺほわゆよもぬんフプポピパペホワユヨモヌ")
_DROP_WORDS = ("ぽた", "ポタ", "ぴちゃ", "ピチャ", "ちゃぷ", "チャプ", "しと",
               "シト", "ぽちゃ", "ポチャ", "ぴと", "ピト", "ざあ", "ザア",
               "ざー", "ザー", "drip", "plip", "splash", "plop")
_SLASH_WORDS = ("しゅ", "シュ", "ひゅ", "ヒュ", "ずば", "ズバ", "ざん", "ザン",
                "びゅ", "ビュ", "さっ", "サッ", "ばっ", "バッ", "しゃ", "シャ",
                "swish", "whoosh", "slash", "zoom", "fwoosh", "swoosh")
_MACHINE_WORDS = ("ぴぴ", "ピピ", "がちゃ", "ガチャ", "うぃ", "ウィ", "かち",
                  "カチ", "ぶぶ", "ブブ", "ぴこ", "ピコ", "びー", "ビー",
                  "beep", "click", "whirr", "bzz", "clank")
_GLARE_WORDS = ("じー", "ジー", "じろ", "ジロ", "ぎろ", "ギロ", "ぎん", "ギン",
                "ぬっ", "ヌッ", "ずい", "ズイ", "stare", "glare")
_CUTE_WORDS = ("きゅん", "キュン", "ふわ", "フワ", "ぽわ", "ポワ", "ほわ",
               "ホワ", "ぷに", "プニ", "もふ", "モフ", "きら", "キラ",
               "にこ", "ニコ", "どき", "ドキ", "dokidoki", "squee", "boing", "poof")
_RUMBLE_WORDS = ("ごご", "ゴゴ", "ざわ", "ザワ", "がた", "ガタ", "ずず", "ズズ",
                 "ごろ", "ゴロ", "どど", "ドド", "rumble", "grr")
_IMPACT_WORDS = ("どん", "ドン", "どか", "ドカ", "ばきっ", "バキ", "どご",
                 "ドゴ", "ずどん", "ズドン", "がしゃ", "ガシャ", "ばん",
                 "バン", "boom", "bam", "crash", "kaboom", "pow", "wham",
                 "smash", "thud")


def has_dakuten(ch):
    """True for a kana (or Latin letter) carrying ゛ or ゜."""
    d = unicodedata.normalize("NFD", ch)
    return any(c in "゙゚" for c in d) or ch in "゛゜"


def _norm(text):
    return unicodedata.normalize("NFKC", text or "").lower()


def sound_features(text):
    """What the rule table looks at, as plain numbers (testable on its own)."""
    s = (text or "").replace("\n", "")
    chars = [c for c in s if not c.isspace()]
    kana = [c for c in chars if "぀" <= c <= "ヿ"]
    n = max(1, len(chars))
    # the longest run of one full-size letter ("ドドド"); a drawn-out vowel
    # ("ぁぁぁ", "ーー") is counted apart as a scream
    longest_run = 0
    stretch_run = 0
    run = 0
    prev = None
    for c in chars:
        run = run + 1 if c == prev else 1
        prev = c
        if c in _SMALL or c in _BARS or c in _VOWELS:
            stretch_run = max(stretch_run, run)
        else:
            longest_run = max(longest_run, run)
    # repeats of a whole unit: "ドドドド", "ゴゴゴ", "ガタガタ"
    unit_repeat = 0
    for size in (1, 2, 3):
        if len(chars) >= size * 2:
            unit = chars[:size]
            reps = 0
            i = 0
            while chars[i:i + size] == unit:
                reps += 1
                i += size
            unit_repeat = max(unit_repeat, reps if reps >= 2 else 0)
    return {
        "len": len(chars),
        "dakuten": sum(1 for c in chars if has_dakuten(c)) / n,
        "small": sum(1 for c in chars if c in _SMALL) / n,
        "bars": sum(1 for c in chars if c in _BARS) / n,
        "soft": sum(1 for c in chars if c in _SOFT) / n,
        "bang": sum(1 for c in chars if c in "!！"),
        "question": sum(1 for c in chars if c in "?？"),
        "ends_n": bool(chars) and chars[-1] in "んンｎn!！" and
        any(c in "んン" for c in chars[-3:]),
        "ends_tsu": bool(chars) and chars[-1] in "っッ" or
        (len(chars) > 1 and chars[-2] in "っッ" and chars[-1] in "!！"),
        "katakana": sum(1 for c in kana if "゠" <= c <= "ヿ") /
        max(1, len(kana)),
        "latin": sum(1 for c in chars if c.isascii() and c.isalpha()) / n,
        "upper": sum(1 for c in chars if c.isascii() and c.isupper()) / n,
        "run": longest_run,
        "scream": stretch_run,
        "repeat": unit_repeat,
    }


def classify(text):
    """Every type with a score for `text`, best first: the おまかせ rule table.

    Words the tables above know win outright; past that the shape of the sound
    decides — voiced (゛) and ending in ン or ！ hits hard, a voiced unit said
    three times rumbles, a clipped ッ is quick, soft kana are cute."""
    f = sound_features(text)
    low = _norm(text)
    score = {tid: 0.0 for tid in TYPE_IDS}

    def words(lst):
        return any(_norm(w) in low for w in lst)

    if words(_DROP_WORDS):
        score["drops"] += 5
    if words(_SLASH_WORDS):
        score["slash"] += 5
    if words(_MACHINE_WORDS):
        score["machine"] += 5
    if words(_GLARE_WORDS):
        score["glare"] += 5
    if words(_CUTE_WORDS):
        score["cute"] += 5
    if words(_RUMBLE_WORDS):
        score["rumble"] += 4
    if words(_IMPACT_WORDS):
        score["impact"] += 4

    score["impact"] += 3 * f["dakuten"] + 1.2 * min(f["bang"], 3)
    if f["ends_n"]:
        score["impact"] += 1.5
    if f["scream"] >= 3:
        # "きゃぁぁぁ", "うわあああ": a shriek, loud but not heavy
        score["pop"] += 3
    if f["run"] >= 3 or (f["repeat"] >= 3 and not f["scream"]):
        score["rumble"] += 2 + 3 * f["dakuten"]
        score["impact"] -= 1
    if f["ends_tsu"]:
        score["slash"] += 2
    if f["bars"] >= 0.25:
        score["slash"] += 0.8
        score["rumble"] += 0.5
    score["cute"] += 3 * f["soft"] - 2 * f["dakuten"]
    if f["small"] >= 0.2 and f["dakuten"] < 0.2:
        score["cute"] += 1
        score["pop"] += 0.5
    if f["question"]:
        score["small"] += 1
    if f["latin"] > 0.5:
        if f["upper"] > 0.5 and f["bang"]:
            score["impact"] += 2
        else:
            score["pop"] += 1.5
    if f["len"] <= 2 and not f["bang"] and f["dakuten"] == 0:
        score["small"] += 1.5
    if f["katakana"] < 0.5 and f["dakuten"] == 0 and not f["bang"]:
        score["small"] += 1
    # a tiny floor so the order of the rest is the table's order, stable
    ranked = sorted(TYPE_IDS, key=lambda t: (-score[t], TYPE_IDS.index(t)))
    return [(t, score[t]) for t in ranked]


def omakase(text):
    """(best type, the next two) for `text`."""
    ranked = classify(text)
    return ranked[0][0], [t for t, _s in ranked[1:3]]


# --- tokens ----------------------------------------------------------------

def tokenize(text, merge_bars=True):
    """Lines of tokens. A token is {"ch": str, "bar": int}: `bar` > 0 marks a
    run of ー merged into one long stroke of that many units."""
    lines = []
    for raw in (text or "").splitlines():
        toks = []
        for ch in raw:
            if ch.isspace():
                if toks:
                    toks.append({"ch": " ", "bar": 0})
                continue
            if merge_bars and ch in _BARS:
                if toks and toks[-1]["bar"]:
                    toks[-1]["bar"] += 1
                    continue
                toks.append({"ch": ch, "bar": 1})
                continue
            toks.append({"ch": ch, "bar": 0})
        while toks and toks[-1]["ch"] == " ":
            toks.pop()
        if toks:
            lines.append(toks)
    return lines


# --- the path --------------------------------------------------------------

def _bezier(p0, p1, p2, t):
    a = (1 - t) * (1 - t)
    b = 2 * (1 - t) * t
    c = t * t
    return (a * p0[0] + b * p1[0] + c * p2[0],
            a * p0[1] + b * p1[1] + c * p2[1])


def _bezier_tan(p0, p1, p2, t):
    dx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
    dy = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
    return math.atan2(dy, dx)


class _Path(object):
    """A quadratic curve sampled by arc length: start at the origin, chord
    along `angle`, middle pushed out sideways by `bend` × chord."""

    STEPS = 96

    def __init__(self, chord, angle_deg, bend):
        a = math.radians(angle_deg)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        self.p0 = (0.0, 0.0)
        self.p2 = (chord * ux, chord * uy)
        # the control point sits at twice the bulge (a quadratic's midpoint
        # is halfway between the chord's middle and its control point)
        self.p1 = (chord * ux / 2 + nx * bend * chord * 2,
                   chord * uy / 2 + ny * bend * chord * 2)
        self.ts = [i / float(self.STEPS) for i in range(self.STEPS + 1)]
        self.lens = [0.0]
        prev = self.p0
        for t in self.ts[1:]:
            pt = _bezier(self.p0, self.p1, self.p2, t)
            self.lens.append(self.lens[-1] + math.hypot(pt[0] - prev[0],
                                                        pt[1] - prev[1]))
            prev = pt
        self.length = self.lens[-1]

    def at(self, s):
        """(x, y, tangent angle in degrees) at arc length `s`."""
        if self.length <= 0:
            return 0.0, 0.0, 0.0
        s = min(max(s, 0.0), self.length)
        lo, hi = 0, len(self.lens) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.lens[mid] < s:
                lo = mid
            else:
                hi = mid
        span = self.lens[hi] - self.lens[lo]
        f = (s - self.lens[lo]) / span if span > 0 else 0.0
        t = self.ts[lo] + f * (self.ts[hi] - self.ts[lo])
        x, y = _bezier(self.p0, self.p1, self.p2, t)
        return x, y, math.degrees(_bezier_tan(self.p0, self.p1, self.p2, t))


def _path_for(length, angle_deg, bend):
    """A path whose ARC length is `length`: bending lengthens a curve, so the
    chord is shortened until the letters fit it exactly."""
    probe = _Path(1.0, angle_deg, bend)
    k = probe.length if probe.length > 0 else 1.0
    return _Path(length / k, angle_deg, bend)


# --- layout ----------------------------------------------------------------

def layout(text, params, advance_fn=None):
    """One placement per letter, in drawing order (back to front).

    A placement is a dict:
        ch, bar (units of a merged ー run, 0 for a letter), group, index,
        x, y      centre on the page (px, relative; the renderer frames it),
        size      letter size (px),
        angle     rotation (degrees, clockwise),
        sx        width factor (stretch),
        shear     italic shear (degrees),
        length    a bar's length along the path (px),
        path_angle the tangent there (degrees) — afterimages trail against it.

    `advance_fn(ch)` → advance as a fraction of the size; the renderer passes
    the real font metrics, tests and the Qt-free path use 1.0 (a full em,
    right for kana and kanji)."""
    p = effective(params)
    rng = random.Random(p["seed"])
    adv = advance_fn or (lambda _ch: 1.0)
    S = float(p["letter_px"])
    base = 90.0 if p["vertical"] else 0.0
    # a positive rise climbs: up-right when horizontal, a lean to the left of
    # the column (top-right → bottom-left) when vertical
    angle = base - p["rise"] if not p["vertical"] else base + p["rise"]
    sx = max(0.2, 1.0 + p["stretch"] / 100.0)
    spacing = p["spacing"] / 100.0
    out = []
    for g, toks in enumerate(tokenize(text, p["merge_bars"])):
        n = len(toks)
        sizes = []
        advances = []
        for i, tok in enumerate(toks):
            u = i / float(n - 1) if n > 1 else 0.0
            pct = p["size_start"] + (p["size_end"] - p["size_start"]) * u
            var = 1.0 + (p["size_var"] / 100.0) * rng.uniform(-1, 1)
            size = max(2.0, S * pct / 100.0 * var)
            sizes.append(size)
            if tok["ch"] == " ":
                a = size * 0.45
            elif tok["bar"]:
                a = size * 0.9 * tok["bar"]
            else:
                a = size * (adv(tok["ch"]) if not p["vertical"] else 1.0)
                if not p["vertical"]:
                    a *= sx
            advances.append(max(1.0, a * (1.0 + spacing)))
        total = sum(advances)
        path = _path_for(total, angle, p["bend"] / 100.0)
        # lines go below each other (horizontal) or right-to-left (vertical)
        if p["vertical"]:
            gx, gy = -g * S * 1.35, g * S * 0.5
        else:
            gx, gy = g * S * 0.6, g * S * 1.3
        s = 0.0
        for i, tok in enumerate(toks):
            mid = s + advances[i] / 2.0
            s += advances[i]
            if tok["ch"] == " ":
                continue
            size = sizes[i]
            x, y, tan = path.at(mid)
            rel = tan - base
            nrm = math.radians(tan + 90.0)
            hop = (p["bounce"] / 100.0) * size * 0.28 * (1 if i % 2 else -1)
            x += math.cos(nrm) * hop
            y += math.sin(nrm) * hop
            j = (p["jitter"] / 100.0) * size * 0.16
            x += rng.uniform(-j, j)
            y += rng.uniform(-j, j)
            if tok["bar"]:
                rot = tan + rng.uniform(-1, 1) * p["rot_var"] * 0.3
                length = advances[i] * 0.92
            else:
                rot = rel * p["lean"] / 100.0 + \
                    rng.uniform(-1, 1) * p["rot_var"]
                length = 0.0
            out.append({
                "ch": tok["ch"], "bar": tok["bar"], "group": g, "index": i,
                "x": x + gx, "y": y + gy, "size": size, "angle": rot,
                "sx": sx, "shear": p["slant"], "length": length,
                "path_angle": tan,
            })
    # the bigger letter is the nearer one: drawn last, its outline cuts into
    # the letter behind it ("手前の字のフチが奥の字を切る")
    out.sort(key=lambda pl: (round(pl["size"], 1), pl["group"], pl["index"]))
    return out


# --- gacha and mutation ----------------------------------------------------

def reroll(params, rng=None):
    """Same type, same settings, a new random shape (only the seed moves)."""
    rng = rng or random.Random()
    p = sanitize(params)
    p["seed"] = rng.randint(1, 2 ** 31 - 1)
    return p


def gacha(text, params, rng=None, wild=False):
    """A fresh option: mostly the types the sound suggests, now and then
    another one; macro sliders shaken a little (a lot when `wild`)."""
    rng = rng or random.Random()
    ranked = [t for t, _s in classify(text)]
    pool = ranked[:3] * 3 + ranked
    tid = rng.choice(pool)
    p = apply_type(params, tid)
    keep_font = sanitize(params).get("font", "")
    t = type_info(tid)
    if keep_font and keep_font not in (t["fonts"] if t else []):
        p["font"] = ""          # a type brings its own lettering
    amp = 90 if wild else 45
    for k in ("power", "rough", "momentum"):
        p[k] = int(_clamp(k, rng.uniform(-amp, amp)))
    p["seed"] = rng.randint(1, 2 ** 31 - 1)
    if rng.random() < 0.3:
        p["bend"] = int(_clamp("bend", p["bend"] + rng.uniform(-25, 25)))
    if rng.random() < 0.3:
        p["rise"] = int(_clamp("rise", p["rise"] + rng.uniform(-15, 15)))
    return sanitize(p)


_MUTABLE = ("spacing", "rise", "bend", "size_start", "size_end", "lean",
            "slant", "stretch", "bounce", "jitter", "rot_var", "size_var",
            "thicken")


def mutate(params, rng=None, amount=0.25):
    """A variation of the current set: a few numbers nudged by up to
    `amount` of their range, a new seed. Type, colours and font stay."""
    rng = rng or random.Random()
    p = sanitize(params)
    keys = rng.sample(_MUTABLE, k=min(len(_MUTABLE), rng.randint(3, 6)))
    for k in keys:
        lo, hi = RANGES[k]
        delta = (hi - lo) * amount * rng.uniform(-1, 1) * 0.5
        v = _clamp(k, p[k] + delta)
        p[k] = int(round(v)) if isinstance(DEFAULTS[k], int) else round(v, 2)
    p["seed"] = rng.randint(1, 2 ** 31 - 1)
    return sanitize(p)


def resolve_font(params, families):
    """The family to draw with: the chosen one if installed, else the type's
    first installed suggestion, else "" (the caller's bold sans)."""
    fams = set(families or ())
    p = sanitize(params)
    if p["font"] and p["font"] in fams:
        return p["font"]
    t = type_info(p["type"]) or TYPES[0]
    for f in t["fonts"]:
        if f in fams:
            return f
    return ""
