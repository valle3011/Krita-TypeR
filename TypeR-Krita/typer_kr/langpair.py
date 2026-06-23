# -*- coding: utf-8 -*-
"""Language detection (Japanese / English), pairing of source + translation,
and detection of "Page" markers inside a translation script.

Kept free of any Qt dependency so it can be unit-tested in isolation.
"""

import os
import re


def detect_lang(text):
    """Rough per-line language detection: 'ja', 'en' or 'other'.

    Kana (Hiragana/Katakana) is a strong signal for Japanese, because English
    text never contains kana. An embedded English name inside a Japanese line
    therefore does not flip the detection.
    """
    kana = kanji = en = 0
    for ch in text:
        o = ord(ch)
        if (0x3040 <= o <= 0x30FF      # Hiragana + Katakana
                or 0xFF66 <= o <= 0xFF9D):  # half-width Katakana
            kana += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:  # Kanji
            kanji += 1
        elif ch.isascii() and ch.isalpha():
            en += 1
    if kana > 0:
        return "ja"
    if kanji > 0 and (en == 0 or kanji >= en):
        return "ja"
    if en > 0:
        return "en"
    if kanji > 0:
        return "ja"
    return "other"


# ---------------------------------------------------------------------------
# Page markers
#
# Translation scripts usually separate the dialogue per manga page with a line
# like "Page 1", "PAGE 01", "--- Page 3 ---", "[Page 5]" or the German "Seite 1".
# We detect such lines so the typesetter always knows which page the current
# line belongs to and can jump straight to a given page.
#
# A line that merely *looks* like a marker is not necessarily a real page
# number: a character on page 3 might have a line that is just "Page 5". Real
# page numbers never decrease, so we additionally validate the numbers and keep
# only those that form an increasing sequence (preferring consecutive pages).
# A "Page 5" sitting between page 3 and page 4 is out of order, so it is treated
# as ordinary dialogue instead of a page break.
# ---------------------------------------------------------------------------

# decoration that may surround a marker (dashes, brackets, dots, …)
_PAGE_DECOR = r'[\s\-=*_~#.:|/\\–—\[\](){}<>]*'

_PAGE_RE = re.compile(
    r'^' + _PAGE_DECOR +
    r'(?:page|seite)(?![a-z])'           # keyword, but not "pages"/"seiten"
    r'[\s.:=#\-–—]*'            # optional separators
    r'(\d+(?:\s*[\-–]\s*\d+)?)?'     # optional number, e.g. 5 or 4-5
    + _PAGE_DECOR + r'$',
    re.IGNORECASE,
)


def page_marker(line):
    """If `line` is a page marker, return its page label as a string
    (e.g. '3' or '4-5'); otherwise return None.

    A marker without a number (just "Page") returns '' so the caller can
    auto-number it. Whitespace inside a range is removed ('4 - 5' -> '4-5').
    """
    m = _PAGE_RE.match(line or "")
    if not m:
        return None
    num = m.group(1)
    if not num:
        return ""
    return re.sub(r"\s+", "", num)


def _page_number(label):
    """Leading integer of a page label ('4' or '4-5' -> 4); None if it has no
    number (a bare "Page")."""
    if not label:
        return None
    m = re.match(r"\d+", label)
    return int(m.group(0)) if m else None


def _longest_increasing(nums):
    """Indices of a longest strictly-increasing subsequence of `nums`, chosen
    greedily so that an out-of-order spike (e.g. 5 between 3 and 4) is the value
    that gets dropped rather than the consecutive one."""
    import bisect
    tails = []        # tails[k] = index of the smallest tail of a length-(k+1) run
    tail_vals = []    # tail_vals[k] = nums at that index (kept sorted)
    prev = [-1] * len(nums)
    for i, v in enumerate(nums):
        pos = bisect.bisect_left(tail_vals, v)   # strictly increasing
        prev[i] = tails[pos - 1] if pos > 0 else -1
        if pos == len(tail_vals):
            tail_vals.append(v)
            tails.append(i)
        else:
            tail_vals[pos] = v
            tails[pos] = i
    keep = []
    k = tails[-1] if tails else -1
    while k != -1:
        keep.append(k)
        k = prev[k]
    keep.reverse()
    return keep


def _accepted_marker_lines(lines):
    """Return (accepted, labels): `accepted` is the set of line indices that are
    genuine page markers, `labels` maps a line index to its explicit label
    ('' for a bare "Page"). Numbered markers are filtered so their page numbers
    only ever increase; markers without a number are always kept."""
    candidates = []          # (line_index, label)
    for i, ln in enumerate(lines):
        label = page_marker(ln)
        if label is not None:
            candidates.append((i, label))

    numbered = [(i, lab) for (i, lab) in candidates
                if _page_number(lab) is not None]
    nums = [_page_number(lab) for (_i, lab) in numbered]
    keep_numbered = {numbered[j][0] for j in _longest_increasing(nums)}

    accepted = set()
    labels = {}
    for i, lab in candidates:
        if _page_number(lab) is None or i in keep_numbered:
            accepted.add(i)
            labels[i] = lab
    return accepted, labels


def split_page_segments(lines):
    """Split raw `lines` into page segments at every genuine "Page N" marker.

    Returns a list of (label, content_lines) tuples in document order. The
    leading segment before the first marker has the label '' (unknown page).
    Lines that look like a marker but break the increasing page order are kept
    as ordinary content. Markers without an explicit number are auto-numbered
    sequentially; an explicit number resets the auto counter so later unnumbered
    markers stay in sync.
    """
    accepted, labels = _accepted_marker_lines(lines)
    segments = []
    cur_label = ""
    cur_lines = []
    auto = 0
    started = False
    for i, ln in enumerate(lines):
        if i not in accepted:
            cur_lines.append(ln)
            continue
        # a marker ends the current segment and starts a new one
        if started or cur_lines:
            segments.append((cur_label, cur_lines))
        started = True
        label = labels[i]
        if label == "":
            auto += 1
            label = str(auto)
        else:
            auto = _page_number(label)
        cur_label = label
        cur_lines = []
    segments.append((cur_label, cur_lines))
    return segments


# ---------------------------------------------------------------------------
# Line cleaning
#
# Scripts come in many shapes. Two very common extras would otherwise end up as
# stray/garbled units, so they are filtered before pairing:
#   * column headers like a bare "JP" / "EN" line that label the source and
#     translation columns (they are not dialogue);
#   * leading "type" tags that mark the kind of bubble rather than being part of
#     the text, e.g. "{}: ", "“”: ", "SFX: ", "//: ", "[]: ".
# Only a fixed set of tags is stripped, so genuine text such as
# "Act93: Takaya" (where "Act93" is content, not a tag) is left untouched.
# ---------------------------------------------------------------------------

# bare column-header lines (case-insensitive, optional trailing colon)
_HEADER_TOKENS = {
    "jp", "en", "jpn", "eng", "jap", "japanese", "english",
    "raw", "tl", "translation", "source", "target", "kr", "kor", "cn",
}

# known leading bubble-type tags: {} [] () <> "" "" 「」 『』 // SFX FX ST TN SE
_TYPE_PREFIX_RE = re.compile(
    r'^\s*'
    r'(?:\{\}|\[\]|\(\)|<>|""|“”|「」|『』|//|'
    r'SFX|FX|ST|TN|SE)'
    r'\s*[:：]\s*',
    re.IGNORECASE,
)


def is_header_line(text):
    """True for a standalone column header such as 'JP' or 'EN:' that labels the
    source/translation columns rather than carrying dialogue."""
    t = text.strip().strip(":：").strip().lower()
    return t in _HEADER_TOKENS


def strip_type_prefix(text):
    """Remove a known leading bubble-type tag like '{}: ', 'SFX: ' or
    '“”: '. Only the fixed tag set is stripped, so real text such as
    'Act93: Takaya' (where 'Act93' is content) is left untouched."""
    return _TYPE_PREFIX_RE.sub("", text, count=1)


def clean_lines(lines):
    """Drop column-header lines and strip bubble-type prefixes, returning the
    text lines that actually carry dialogue/translation."""
    out = []
    for t in lines:
        if t.strip() == "" or is_header_line(t):
            continue
        c = strip_type_prefix(t)
        if c.strip() == "":
            continue
        out.append(c)
    return out


# A leading speaker label such as "Sakamoto: Hi there". Conservative: the name
# must be letters (plus spaces/'/-/.), no digits, 1-4 words, with non-empty
# dialogue after the colon. So "Act93: ..." (digits) is NOT a speaker.
_SPEAKER_RE = re.compile(r"^\s*([A-Za-z][A-Za-z .'\-]{0,23}?)\s*:\s*(\S.*)$")


def split_speaker(text):
    """If `text` looks like 'Speaker: dialogue' with a plausible speaker name,
    return (speaker, dialogue); otherwise (None, text).

    Deliberately conservative – this only *detects* a possible speaker. The
    caller decides whether to act on it (e.g. only when the name matches a
    known character), so the occasional false positive is harmless."""
    text = text or ""
    # a known bubble-type tag ('SFX:', 'ST:', …) is not a speaker
    if strip_type_prefix(text) != text:
        return None, text
    m = _SPEAKER_RE.match(text)
    if not m:
        return None, text
    name = m.group(1).strip(" .")
    rest = m.group(2).strip()
    if not name or not rest:
        return None, text
    if any(ch.isdigit() for ch in name) or is_header_line(name):
        return None, text
    if not (1 <= len(name.split()) <= 4):
        return None, text
    return name, rest


def speaker_name(text):
    """The speaker label of a 'Speaker: dialogue' line, or None. See
    :func:`split_speaker`."""
    return split_speaker(text)[0]


def pair_lines(lines):
    """Group lines into (japanese, english) pairs.

    Detects automatically whether the script lists Japanese first or English
    first by looking at neighbouring lines. Each unit consists of a 'head' line
    in the dominant source language plus every following line of the other
    language as its translation.

    Column headers (bare 'JP'/'EN') and bubble-type prefixes ('{}: ', 'SFX: ',
    …) are removed first via :func:`clean_lines`, so they neither show up as
    stray units nor end up inside a bubble.

    Returns a list of (ja, en); either part may be an empty string.
    For monolingual scripts every line becomes its own unit.
    """
    toks = [(detect_lang(t), t) for t in clean_lines(lines)]
    n = len(toks)
    if n == 0:
        return []

    # Determine ordering: does JA->EN or EN->JA occur more often?
    ja_first = en_first = 0
    for (la, _ta), (lb, _tb) in zip(toks, toks[1:]):
        if la == "ja" and lb == "en":
            ja_first += 1
        elif la == "en" and lb == "ja":
            en_first += 1

    # If there is no Japanese line at all -> English is the head, so that a
    # monolingual EN script turns every line into its own unit.
    any_ja = any(l == "ja" for l, _ in toks)
    any_en = any(l == "en" for l, _ in toks)
    if not any_ja:
        head = "en"
    elif not any_en:
        head = "ja"
    else:
        head = "ja" if ja_first >= en_first else "en"

    pairs = []
    i = 0
    while i < n:
        lang, text = toks[i]
        if lang == head:
            head_text = text
            i += 1
            body = []
            while i < n and toks[i][0] != head:
                body.append(toks[i][1])
                i += 1
            body_text = " ".join(body)
            if head == "ja":
                pairs.append((head_text, body_text))
            else:
                pairs.append((body_text, head_text))
        else:
            # line without a preceding head -> put it on the matching side
            if lang == "ja":
                pairs.append((text, ""))
            else:
                pairs.append(("", text))
            i += 1
    return pairs


def pair_lines_paged(lines):
    """Like :func:`pair_lines`, but also tracks "Page N" markers.

    Pairing is performed per page segment, which is exactly what we want: a
    translation unit never spans a page boundary, and every unit can be tagged
    with the page it belongs to.

    Returns (pairs, pair_pages, pages):
        pairs       - list of (ja, en) units (same shape as pair_lines)
        pair_pages  - parallel list: the page label for each unit ('' if the
                      unit appears before the first marker)
        pages       - ordered list of (label, first_unit_index) used to build
                      the "jump to page" control; only segments that actually
                      contain units are listed.
    """
    segments = split_page_segments(lines)
    pairs = []
    pair_pages = []
    pages = []
    for label, seg_lines in segments:
        seg_pairs = pair_lines(seg_lines)
        if not seg_pairs:
            continue
        pages.append((label, len(pairs)))
        for p in seg_pairs:
            pairs.append(p)
            pair_pages.append(label)
    return pairs, pair_pages, pages


def unit_text(pair):
    """Which text gets inserted: the translation (EN) if present, else the
    source (JA)."""
    ja, en = pair
    return en if en.strip() else ja


# ---------------------------------------------------------------------------
# Loose normalization (shared by manga / preset matching)
# ---------------------------------------------------------------------------

def _norm_loose(text):
    """Lowercase, replace every non-alphanumeric char with a space and collapse
    runs of whitespace. Keeps unicode letters/digits, so accented or Japanese
    names still match. '' for empty input."""
    out = []
    for ch in (text or "").lower():
        out.append(ch if (ch.isalnum() or ch.isspace()) else " ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


# ---------------------------------------------------------------------------
# Manga detection
#
# When a translation script is loaded we try to recognise which of the user's
# saved mangas it belongs to, so the docker can switch to it automatically
# (just like "auto character" switches to a speaker's character). Sources are
# tried in order of trust:
#   1) the file name (scripts are often named "<Manga> ch12.docx"),
#   2) explicit header lines ("Title:", "Manga:", "Series:" and localized
#      variants),
#   3) the first ~10 non-empty content lines.
# Matching is done on the loose-normalized form and a saved name must appear as
# a substring. Among several matches the longest (most specific) saved name
# wins; a hit in the file name beats a hit in the body. Saved names shorter
# than 3 characters are ignored to avoid accidental matches.
# ---------------------------------------------------------------------------

_MANGA_HEADER_RE = re.compile(
    r'^\s*(?:title|manga|series|serie|titel|t[ií]tulo|titre|s[eé]rie|'
    r'titolo|obra|werk)\s*[:：]\s*(.+)$',
    re.IGNORECASE,
)


def _manga_header_values(lines):
    """Explicit 'Title:'/'Manga:'/… values found in `lines`."""
    vals = []
    for ln in lines:
        m = _MANGA_HEADER_RE.match(ln or "")
        if m:
            vals.append(m.group(1))
    return vals


def detect_manga(saved_names, script_text, filename=""):
    """Return the saved manga name that best matches the loaded script, or None.

    Priority: file name > explicit header lines > first ~10 content lines.
    Within a source the longest matching saved name wins. Saved names shorter
    than 3 characters are ignored. See the section comment above for details.
    """
    names = [n for n in (saved_names or []) if n and len(n.strip()) >= 3]
    if not names:
        return None
    # longest first so the most specific name wins on a tie
    names_sorted = sorted(names, key=lambda s: len(s), reverse=True)

    def first_hit(haystack):
        h = _norm_loose(haystack)
        if not h:
            return None
        for name in names_sorted:
            if _norm_loose(name) in h:
                return name
        return None

    # 1) file name (without directory and extension)
    base = re.sub(r'.*[\\/]', '', filename or "")     # strip path
    base = re.sub(r'\.[A-Za-z0-9]+$', '', base)        # strip extension
    hit = first_hit(base)
    if hit:
        return hit

    lines = [ln for ln in (script_text or "").splitlines() if ln.strip()]
    # 2) explicit header lines (scan the first ~20 non-empty lines for headers)
    hit = first_hit("\n".join(_manga_header_values(lines[:20])))
    if hit:
        return hit

    # 3) first ~10 non-empty content lines
    return first_hit("\n".join(lines[:10]))


# ---------------------------------------------------------------------------
# Default preset picking
#
# When the docker switches to a character we auto-select that character's
# "default" dialogue preset. Priority:
#   1) a preset whose name contains a known dialogue keyword ('normal talking',
#      'normal', 'talking', 'speech', 'default', …), most specific first;
#   2) the most-used preset (optional usage mapping name -> count);
#   3) the first preset (alphabetical) that is not literally 'none'.
# ---------------------------------------------------------------------------

_DEFAULT_PRESET_KEYWORDS = (
    "normal talking", "normal speech", "normal", "talking", "speech", "default",
)


# ---------------------------------------------------------------------------
# Script "tabs" / sessions
#
# The docker can keep several loaded scripts open at once, each in its own tab.
# These helpers are the Qt-free part of that: normalizing a path so the same
# file isn't opened twice, deriving a tab label from a file name, and numbering
# unnamed scripts ("Untitled", "Untitled 2", …).
# ---------------------------------------------------------------------------

def norm_script_path(path):
    """Normalized, comparable form of a file path (for de-duplicating open
    scripts). An empty path stays empty, so pasted/unsaved scripts never match
    one another."""
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return os.path.normcase(path)


def find_session_by_path(sessions, path):
    """Index of the session whose 'path' matches `path` (after normalization),
    or -1. A blank path never matches (unsaved scripts are always new tabs)."""
    key = norm_script_path(path)
    if not key:
        return -1
    for i, s in enumerate(sessions or []):
        if norm_script_path((s or {}).get("path", "")) == key:
            return i
    return -1


def default_tab_label(path):
    """Tab label from a file path: the file name without its directory or
    extension. Falls back to 'Untitled' for an empty path."""
    base = os.path.basename(path or "")
    name = os.path.splitext(base)[0]
    return name or "Untitled"


def unique_untitled(existing, base="Untitled"):
    """A name like 'Untitled', 'Untitled 2', … that is not in `existing`."""
    taken = set(existing or [])
    if base not in taken:
        return base
    n = 2
    while ("%s %d" % (base, n)) in taken:
        n += 1
    return "%s %d" % (base, n)


def default_preset_for(preset_names, usage=None):
    """Pick the best 'default' preset name for a character, or None when the
    character has no real preset. See the section comment above for the order."""
    names = [n for n in (preset_names or [])
             if n and str(n).strip().lower() != "none"]
    if not names:
        return None
    norm = {n: _norm_loose(n) for n in names}
    # 1) keyword match (most specific first); ties -> alphabetical
    for kw in _DEFAULT_PRESET_KEYWORDS:
        hits = sorted((n for n in names if kw in norm[n]), key=lambda s: s.lower())
        if hits:
            return hits[0]
    # 2) most used
    if usage:
        used = sorted((n for n in names if usage.get(n)),
                      key=lambda n: (-usage.get(n, 0), n.lower()))
        if used:
            return used[0]
    # 3) first alphabetical
    return sorted(names, key=lambda s: s.lower())[0]
