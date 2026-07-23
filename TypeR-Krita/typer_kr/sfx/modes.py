# -*- coding: utf-8 -*-
"""The five ways to handle a Japanese sound effect.

Japanese has roughly three times as many onomatopoeia as English and most have
no equivalent, so there is no single right answer for an SFX — there are five
established ones, and which to use is a per-panel judgement the typesetter has
been making by hand every time. This module names them and provides the parts
that are the same whatever the UI does with them.

The ladder, cheapest first (Blambot / Nekyou / roxybudgy):

  ignore   leave the Japanese alone. Costs nothing; the sound is lost on
           readers who cannot read it.
  romaji   transliterate the sound: ドカン -> "dokan". Faithful, but only
           helps a reader who knows what "dokan" means.
  note     a numbered marker by the SFX and a list at the panel edge:
           "(1) ドキ = doki (heartbeat)". Non-invasive; the art is untouched.
  overlay  a small English word beside the original, which stays visible. The
           compromise between faithfulness and readability.
  redraw   remove the Japanese, rebuild the art behind it, and set the English
           SFX in the same dynamic style. The cleanest and the most work.

Qt-free on purpose: the romaji table is the substance here and it is testable
without Krita.
"""

# --- the strategies --------------------------------------------------------
# `translation` = does the mode need the typesetter's English word?
# `inserts` = does it put text on the page at all?

STRATEGIES = [
    {"id": "ignore",  "translation": False, "inserts": False},
    {"id": "romaji",  "translation": False, "inserts": True},
    {"id": "note",    "translation": True,  "inserts": True},
    {"id": "overlay", "translation": True,  "inserts": True},
    {"id": "redraw",  "translation": True,  "inserts": True},
]

STRATEGY_IDS = [s["id"] for s in STRATEGIES]

_BY_ID = {s["id"]: s for s in STRATEGIES}


def strategy(sid):
    """The strategy dict for `sid`, or None."""
    return _BY_ID.get(sid)


def needs_translation(sid):
    s = _BY_ID.get(sid)
    return bool(s and s["translation"])


def inserts_text(sid):
    s = _BY_ID.get(sid)
    return bool(s and s["inserts"])


# --- numbered markers for the 'note' strategy ------------------------------
# Circled numbers, the convention the reference uses ("(1) ドキ = doki"). They
# exist as single glyphs up to 20; past that fall back to a plain "(21)" rather
# than silently renumbering from the start.
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def note_marker(index):
    """The marker for the `index`-th note (1-based)."""
    if 1 <= index <= len(_CIRCLED):
        return _CIRCLED[index - 1]
    return "({})".format(index)


def note_line(index, source, meaning=""):
    """One line of the panel-edge SFX list: marker, the original, its romaji,
    and what it means. The romaji is derived, never typed twice."""
    romaji = to_romaji(source)
    line = "{} {}".format(note_marker(index), source)
    if romaji and romaji != source:
        line += " = {}".format(romaji)
    if meaning:
        line += " ({})".format(meaning)
    return line


# --- kana -> romaji (Hepburn) ----------------------------------------------
# Longest match first: three-kana clusters, then youon pairs, then singles.
# Written for SFX, so a long-vowel mark doubles the vowel ("ドーン" -> "doon")
# instead of taking a macron — that is how manga SFX are written in the wild,
# and a macron would not survive most comic fonts anyway.

_ROMAJI = {
    # gojuon
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "ゐ": "i", "ゑ": "e", "を": "o", "ん": "n",
    # dakuten / handakuten
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ゔ": "vu",
}

_YOUON = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo",
    "ぢゃ": "ja", "ぢゅ": "ju", "ぢょ": "jo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
    # foreign-sound clusters, common in SFX
    "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo",
    "うぃ": "wi", "うぇ": "we", "うぉ": "wo",
    "ゔぁ": "va", "ゔぃ": "vi", "ゔぇ": "ve", "ゔぉ": "vo",
    "てぃ": "ti", "でぃ": "di", "とぅ": "tu", "どぅ": "du",
    "しぇ": "she", "ちぇ": "che", "じぇ": "je",
    "つぁ": "tsa", "つぃ": "tsi", "つぇ": "tse", "つぉ": "tso",
}

_SMALL_VOWELS = {"ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}

_SOKUON = "っ"
_PROLONG = "ー"
_VOWELS = "aiueo"


def _to_hiragana(text):
    """Katakana -> hiragana, so one table covers both. SFX are usually
    katakana; the kana blocks sit 0x60 apart."""
    out = []
    for ch in text:
        code = ord(ch)
        # full-width katakana ア(0x30A1)..ヶ(0x30F6) -> hiragana
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def to_romaji(text):
    """Transliterate Japanese kana to Hepburn romaji.

    Anything that is not kana (Latin, digits, punctuation, kanji) is passed
    through untouched — an SFX is rarely pure kana, and mangling the rest would
    be worse than leaving it.
    """
    if not text:
        return ""
    src = _to_hiragana(text)
    out = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]

        # small tsu: double the consonant that follows
        if ch == _SOKUON:
            nxt = None
            for size in (2, 1):
                if src[i + 1:i + 1 + size] in (_YOUON if size == 2 else _ROMAJI):
                    tbl = _YOUON if size == 2 else _ROMAJI
                    nxt = tbl[src[i + 1:i + 1 + size]]
                    break
            if nxt and nxt[0] not in _VOWELS:
                # "cch" is wrong; Hepburn doubles it as "tch" (まっちゃ matcha)
                out.append("t" if nxt.startswith("ch") else nxt[0])
            i += 1
            continue

        # long vowel mark: repeat the last vowel we produced
        if ch == _PROLONG:
            prev = "".join(out)
            if prev and prev[-1] in _VOWELS:
                out.append(prev[-1])
            i += 1
            continue

        # youon and other two-kana clusters
        pair = src[i:i + 2]
        if len(pair) == 2 and pair in _YOUON:
            out.append(_YOUON[pair])
            i += 2
            continue

        # a small vowel we have no cluster for: drop the base's vowel and
        # graft this one on (ウァ -> wa), which beats emitting "u" + "a"
        if len(pair) == 2 and pair[1] in _SMALL_VOWELS and pair[0] in _ROMAJI:
            base = _ROMAJI[pair[0]]
            out.append(base[:-1] + _SMALL_VOWELS[pair[1]] if base[-1] in _VOWELS
                       else base + _SMALL_VOWELS[pair[1]])
            i += 2
            continue

        if ch in _ROMAJI:
            out.append(_ROMAJI[ch])
            i += 1
            continue

        if ch in _SMALL_VOWELS:      # stray small vowel
            out.append(_SMALL_VOWELS[ch])
            i += 1
            continue

        if ch == "・":               # katakana middle dot separates words
            out.append(" ")
            i += 1
            continue

        out.append(ch)               # not kana: leave it alone
        i += 1

    return "".join(out)
