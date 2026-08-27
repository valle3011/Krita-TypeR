# -*- coding: utf-8 -*-
"""Pure layout logic: line wrapping, even balancing, ellipse fitting (round
speech bubbles) and auto-sizing.

Deliberately free of any Qt dependency so it can be unit-tested in isolation.
Text widths come from a 'measurer(px)' function that returns:
    (width_of, space_w, line_h, ascent, descent)
"""

import math
import os
import re


# ---------------------------------------------------------------------------
# Bold runs: internally text is represented as a sequence of (subtext, bold)
# runs so that individual words (or parts of them) can be bold. A "word"
# carries its full string (for width measurement) and its runs (for drawing).
# ---------------------------------------------------------------------------

class Word(object):
    __slots__ = ("text", "bold", "runs")

    def __init__(self, text, bold, runs):
        self.text = text      # full word string
        self.bold = bold      # True if any character is bold
        self.runs = runs      # list [(subtext, bold), ...]

    def __str__(self):
        return self.text


def make_runs(text, mask):
    """(text, mask) -> list [(subtext, bold), ...] with equal-bold sections
    merged. mask: list of bool with the same length as text."""
    runs = []
    for ch, b in zip(text, mask):
        b = bool(b)
        if runs and runs[-1][1] == b:
            runs[-1] = (runs[-1][0] + ch, b)
        else:
            runs.append((ch, b))
    return runs


def make_words(text, mask):
    """Split text into words at spaces; keep each word's bold runs. Multiple
    spaces are collapsed, like str.split()."""
    words = []
    cur, curm = [], []
    for ch, b in zip(text, mask):
        if ch == " ":
            if cur:
                words.append(Word("".join(cur), any(curm),
                                  make_runs(cur, curm)))
                cur, curm = [], []
        else:
            cur.append(ch)
            curm.append(bool(b))
    if cur:
        words.append(Word("".join(cur), any(curm), make_runs(cur, curm)))
    return words


def split_paragraphs(text, mask):
    """Split (text, mask) at \\n into (paragraph_text, paragraph_mask) pairs."""
    out = []
    s = 0
    for i, ch in enumerate(text):
        if ch == "\n":
            out.append((text[s:i], mask[s:i]))
            s = i + 1
    out.append((text[s:], mask[s:]))
    return out


def line_runs(words):
    """Join the words of a (wrapped) line into a single run list; words are
    separated by a space (the space inherits the bold property of the previous
    run end), and equal-bold runs are merged."""
    runs = []

    def push(txt, b):
        if runs and runs[-1][1] == b:
            runs[-1] = (runs[-1][0] + txt, b)
        else:
            runs.append((txt, b))

    for wi, wd in enumerate(words):
        if wi > 0:
            push(" ", runs[-1][1] if runs else False)
        for (txt, b) in wd.runs:
            push(txt, b)
    return runs


def runs_text(runs):
    """Plain text of a run list."""
    return "".join(t for t, _ in runs)


def group_words(words, break_after):
    """Split a flat word list into lines. `break_after` is a set of 0-based
    word indices; a line ends after each such word. Used by TextShapR's manual
    break editor to regroup a chosen candidate."""
    lines = []
    cur = []
    for i, w in enumerate(words):
        cur.append(w)
        if i in break_after:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines



# ---------------------------------------------------------------------------
# Hyphenation (Liang's algorithm with bundled, freely-licensed TeX patterns)
#
# The pattern files live in the "hyph" subfolder and come from the free
# hyph-utf8 / tex-hyphen project (see hyph/LICENSE.txt). `hyphenate()` returns
# the linguistically valid break positions of a word; `split_word()` splits a
# Word object there while keeping its bold runs intact.
# ---------------------------------------------------------------------------

_HYPH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hyph")
# lang -> (pattern file, exception file or None). All files are bundled and
# freely licensed (see hyph/LICENSE.txt).
_HYPH_FILES = {
    "en": ("hyph-en-us.pat.txt", "hyph-en-us.hyp.txt"),
    "de": ("hyph-de-1996.pat.txt", None),
    "es": ("hyph-es.pat.txt", None),
    "fr": ("hyph-fr.pat.txt", None),
    "pt": ("hyph-pt.pat.txt", "hyph-pt.hyp.txt"),
    "it": ("hyph-it.pat.txt", None),
}
# language codes whose patterns ship with the plugin (UI offers only these)
HYPH_LANGS = ("en", "de", "es", "fr", "pt", "it")
# per-language minimum letters before/after a break (from each file's header)
_HYPH_MINS = {
    "en": (2, 3), "de": (2, 2), "es": (2, 2),
    "fr": (2, 2), "pt": (2, 3), "it": (2, 2),
}
_hyphenators = {}                       # lang -> _Hyphenator (or False = failed)
_DIGITS_RE = re.compile(r"[0-9]")
_WORD_RE = re.compile(r"^[^\W\d_]+(?:[''’-][^\W\d_]+)*$", re.UNICODE)


def _norm_lang(lang):
    """Map a code/locale (e.g. 'de_DE', 'pt-BR') to a bundled language key."""
    code = str(lang or "").lower().replace("-", "_").split("_")[0]
    return code if code in _HYPH_FILES else "en"


class _Hyphenator(object):
    """Liang's hyphenation algorithm over a tree of competing patterns."""

    def __init__(self, pattern_lines, exception_lines=()):
        self.tree = {}
        for pat in pattern_lines:
            pat = pat.strip()
            if pat and not pat.startswith("%"):
                self._insert(pat)
        self.exceptions = {}
        for ex in exception_lines:
            ex = ex.strip().lower()
            if not ex or ex.startswith("%"):
                continue
            key = ex.replace("-", "")
            pts = [0]
            for piece in ex.split("-"):
                pts.extend([0] * (len(piece) - 1))
                pts.append(1)
            if pts:
                pts[-1] = 0             # never break after the last piece
            self.exceptions[key] = pts

    def _insert(self, pattern):
        # "a1bc3d" -> chars "abcd", points [0,1,0,3,0]
        chars = _DIGITS_RE.sub("", pattern)
        points = [0] * (len(chars) + 1)
        ci = 0
        for ch in pattern:
            if ch.isdigit():
                points[ci] = int(ch)
            else:
                ci += 1
        node = self.tree
        for c in chars:
            node = node.setdefault(c, {})
        node[None] = points

    def split(self, word):
        """Split `word` into its syllable pieces (lowercased internally)."""
        w = word.lower()
        if w in self.exceptions:
            points = self.exceptions[w]
            offset = 1
        else:
            work = "." + w + "."
            points = [0] * (len(work) + 1)
            for i in range(len(work)):
                node = self.tree
                for c in work[i:]:
                    node = node.get(c)
                    if node is None:
                        break
                    pts = node.get(None)
                    if pts:
                        for off, p in enumerate(pts):
                            if p > points[i + off]:
                                points[i + off] = p
            points[0] = points[1] = 0
            points[-1] = points[-2] = 0
            offset = 2
        pieces = [""]
        for k, c in enumerate(w):
            pieces[-1] += c
            if points[k + offset] % 2:
                pieces.append("")
        return [p for p in pieces if p]


def _get_hyphenator(lang):
    lang = _norm_lang(lang)
    if lang in _hyphenators:
        return _hyphenators[lang] or None
    pat_name, hyp_name = _HYPH_FILES[lang]
    try:
        with open(os.path.join(_HYPH_DIR, pat_name), encoding="utf-8") as fh:
            pat_lines = fh.read().splitlines()
        hyp_lines = []
        if hyp_name:
            p = os.path.join(_HYPH_DIR, hyp_name)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    hyp_lines = fh.read().splitlines()
        h = _Hyphenator(pat_lines, hyp_lines)
    except Exception:
        h = False
    _hyphenators[lang] = h
    return h or None


def _core_span(word):
    """Span (start, end) of the actual word inside `word`, ignoring attached
    punctuation: quotes, brackets, "!", "?", ",", "…" and the like. Without
    this, everyday words would never hyphenate — "EMBARRASSING!" is not a
    plain word, but "EMBARRASSING" is."""
    i, j = 0, len(word)
    while i < j and not word[i].isalpha():
        i += 1
    while j > i and not word[j - 1].isalpha():
        j -= 1
    return i, j


#: Characters that already ARE a break opportunity inside a word: a hyphen a
#: writer put there ("Yagi-kun", "well-known") and the en-dash some scripts use
#: for the same job. Breaking right after one needs no new hyphen at all.
_INWORD_BREAK = "-‐‑–"


def hyphenate(word, lang="en", left=None, right=None):
    """Return the sorted character indices inside `word` where it may be broken
    across lines, honoring a minimum of `left` letters before and `right` after.
    When left/right are None the language's own minima are used. Attached
    punctuation is ignored (and stays with its part when the word is split).

    A word that already carries a hyphen breaks AT that hyphen: "Yagi-kun" gives
    "Yagi-" / "kun", never "Yagi--" / "kun" and never "Yag-" / "i-kun". Feeding
    such a compound to the syllable patterns as one string produced both of
    those, because the patterns treat the hyphen as just another character. So
    the compound is split on its own hyphens first, each part is hyphenated
    separately, and the position after each existing hyphen is offered as a
    break in its own right (`split_word` then adds no second hyphen).

    Empty list if the word is too short, not a plain word, or patterns are
    unavailable.
    """
    dl, dr = _HYPH_MINS.get(_norm_lang(lang), (2, 3))
    if left is None:
        left = dl
    if right is None:
        right = dr
    if not word:
        return []
    start, end = _core_span(word)
    core = word[start:end]
    if len(core) < left + right:
        return []
    if not _WORD_RE.match(core):
        return []

    def _ok(pos):
        """`pos` is an index inside `core`: enough characters on both sides?"""
        return left <= pos <= len(core) - right

    # the segments between the word's own hyphens, with their offsets in `core`
    segments, seg_start = [], 0
    breaks = []
    for i, ch in enumerate(core):
        if ch in _INWORD_BREAK:
            segments.append((seg_start, core[seg_start:i]))
            if _ok(i + 1):                  # break AFTER the existing hyphen
                breaks.append(start + i + 1)
            seg_start = i + 1
    segments.append((seg_start, core[seg_start:]))

    h = _get_hyphenator(lang)
    if h is not None:
        for off, seg in segments:
            # a part still needs enough letters of its own to be worth splitting
            if len(seg) < left + right or not seg:
                continue
            pieces = h.split(seg)
            if len(pieces) < 2:
                continue
            pos = 0
            for p in pieces[:-1]:
                pos += len(p)
                if _ok(off + pos):
                    breaks.append(start + off + pos)
    return sorted(set(breaks))


def split_word(word, i):
    """Split a Word at character index i; append a hyphen to the first part —
    unless it already ends with one, because the break landed on a hyphen the
    word already had ("Yagi-kun" -> "Yagi-" / "kun", not "Yagi--" / "kun").
    Returns (left, right) as Word objects, preserving the bold runs."""
    left_runs, right_runs = [], []
    pos = 0
    for (t, b) in word.runs:
        end = pos + len(t)
        if end <= i:
            left_runs.append((t, b))
        elif pos >= i:
            right_runs.append((t, b))
        else:
            cut = i - pos
            left_runs.append((t[:cut], b))
            right_runs.append((t[cut:], b))
        pos = end
    if left_runs:
        lt, lb = left_runs[-1]
        if not lt.endswith(tuple(_INWORD_BREAK)):
            left_runs[-1] = (lt + "-", lb)      # hyphen inherits previous bold
    else:
        left_runs = [("-", False)]
    left_text = "".join(t for t, _ in left_runs)
    right_text = "".join(t for t, _ in right_runs)
    left = Word(left_text, any(b for _, b in left_runs), left_runs)
    right = Word(right_text, any(b for _, b in right_runs), right_runs)
    return left, right


# A hyphen followed by whitespace and a letter: a word broken across a line in
# the SOURCE text (OCR, a previous typeset). The letters are left untouched; the
# match spans only the hyphen and the run of spaces, so the mask stays easy to
# realign.
_DEHYPH_RE = re.compile(r"(?<=[^\W\d_])-(\s+)(?=([^\W\d_]))")

#: Continuations that make the hyphen part of the NAME, not a line break.
#: Japanese honorifics are lowercase, so the capitalisation rule below cannot
#: see them and "Yagi- kun" would be rejoined as "Yagikun" — which is the same
#: blindness to an existing hyphen that made the shaper write "Yagi--". These
#: are the suffixes a manga script actually uses.
_KEEP_HYPHEN_SUFFIX = frozenset((
    "kun", "chan", "san", "sama", "senpai", "sempai", "sensei", "dono",
    "tan", "chin", "nee", "nii", "neesan", "niisan", "oneesan", "oniisan",
))
_SUFFIX_RE = re.compile(r"^[^\W\d_]+", re.UNICODE)


def dehyphenate(text, mask=None):
    """Undo source line-break hyphenation so the shaper can re-wrap freely: join
    a word that was split across a line ("embar- rassing" -> "embarrassing").

    A capitalised continuation is kept as a hyphenated compound instead
    ("Spider- Man" -> "Spider-Man"), on the assumption it is a real hyphenated
    name rather than a broken word — as is a Japanese honorific, which is
    lowercase and would otherwise be swallowed ("Yagi- kun" stays "Yagi-kun",
    not "Yagikun"). Only a hyphen *followed by whitespace* is touched, so an
    ordinary in-word hyphen ("X-ray") is left alone.

    Returns (new_text, new_mask) with the bold `mask` realigned to the shortened
    text. This is the inverse of the `hyphenate`/`split_word` pair above.
    """
    text = text or ""
    m = list(mask) if mask is not None else [False] * len(text)
    if len(m) < len(text):
        m += [False] * (len(text) - len(m))
    out_t, out_m, last = [], [], 0
    for mo in _DEHYPH_RE.finditer(text):
        s, e = mo.start(), mo.end()
        out_t.append(text[last:s])
        out_m.extend(m[last:s])
        tail = _SUFFIX_RE.match(text[e:])
        keep = (mo.group(2).isupper()      # capitalised -> a real compound
                or (tail and tail.group(0).lower() in _KEEP_HYPHEN_SUFFIX))
        if keep:
            out_t.append("-")
            out_m.append(m[s])             # the hyphen keeps its own bold bit
        # lowercase continuation -> drop the hyphen and the spaces entirely
        last = e
    out_t.append(text[last:])
    out_m.extend(m[last:])
    new_text = "".join(out_t)
    return new_text, out_m[:len(new_text)]


# Internal alias so shape_candidates' `dehyphenate` parameter can toggle the
# function without shadowing it.
_dehyphenate = dehyphenate


def _split_to_fit(word, avail, width_of, hyph):
    """Hyphenate `word` so its first part (incl. hyphen) is <= avail.
    Picks the latest valid break that still fits. Returns (left, right) or
    None. `hyph(word)` -> list of break indices."""
    breaks = hyph(word)
    if not breaks:
        return None
    best = None
    for b in breaks:                            # ascending -> latest that fits
        left, right = split_word(word, b)
        if width_of(left) <= avail:
            best = (left, right)
        else:
            break
    return best


def _fix_widows(lines, width_of, space_w, max_w):
    """Typography polish: avoid a 'widow' - a last line holding a single word.
    Pull the last word of the previous line down so the last line has two words,
    but only when it still fits and the pulled word is not a hyphenation
    left-part (which must stay glued to its continuation)."""
    if len(lines) < 2:
        return lines
    last, prev = lines[-1], lines[-2]
    if len(last) == 1 and len(prev) >= 2:
        moved = prev[-1]
        if not getattr(moved, "text", "").endswith("-"):
            new_last = [moved] + last
            if _line_width(new_last, width_of, space_w) <= max_w + 0.5:
                lines[-2] = prev[:-1]
                lines[-1] = new_last
    return lines


# Typographic limits for hyphenation, shared with the docker's preview wrap so
# both produce the same lines: at most this many lines in a row may end with a
# hyphen, and one word may be broken this often (1 = two parts).
HYPH_MAX_LADDER = 2
HYPH_MAX_WORD_SPLITS = 1


def wrap_greedy(words, width_of, space_w, max_w, hyph=None,
                max_ladder=HYPH_MAX_LADDER,
                max_word_splits=HYPH_MAX_WORD_SPLITS):
    """Greedily wrap words into lines, each line <= max_w. With `hyph` (a
    callable word -> break indices) a word that does not fit is split at a valid
    syllable break instead of overflowing. A widow-avoidance pass keeps a lone
    word off the last line when it can be paired without overflowing.

    Two typographic limits keep the result readable instead of shredded:
    `max_ladder` is the classic "hyphen ladder" cap (at most that many lines in
    a row may end with a hyphen) and `max_word_splits` is how often ONE word may
    be broken (1 = two parts, the norm in comic lettering). When a split is not
    allowed the wrap simply does not split — the size search then settles one
    step smaller, with cleaner breaks. 0 = no limit."""
    lines = [[]]
    cur_w = 0.0
    queue = list(words)
    guard = 0
    ladder = 0                                  # lines in a row ending with "-"
    splits = 0                                  # splits of the word in hand
    pending = None                              # the tail of the word in hand

    def may_split():
        return (bool(hyph)
                and (max_ladder <= 0 or ladder < max_ladder)
                and (max_word_splits <= 0 or splits < max_word_splits))

    while queue and guard < 100000:
        guard += 1
        w = queue.pop(0)
        if w is not pending:                    # a fresh word, not a tail
            splits = 0
        pending = None
        ww = width_of(w)
        cur = lines[-1]
        if not cur:
            if ww <= max_w:
                cur.append(w)
                cur_w = ww
                ladder = 0
            else:                               # too wide for a whole line
                res = _split_to_fit(w, max_w, width_of, hyph) \
                    if may_split() else None
                if res:
                    left, right = res
                    cur.append(left)
                    lines.append([])
                    cur_w = 0.0
                    ladder += 1
                    splits += 1
                    pending = right
                    queue.insert(0, right)
                else:
                    cur.append(w)               # give up -> overflow (as before)
                    cur_w = ww
                    ladder = 0
        elif cur_w + space_w + ww <= max_w:
            cur.append(w)
            cur_w += space_w + ww
        else:
            avail = max_w - cur_w - space_w
            res = _split_to_fit(w, avail, width_of, hyph) \
                if may_split() else None
            if res:
                left, right = res
                cur.append(left)
                lines.append([])
                cur_w = 0.0
                ladder += 1
                splits += 1
                pending = right
                queue.insert(0, right)
            elif ww > max_w and may_split():
                # Nothing of it fits into the rest of this line, and it is too
                # wide for a line of its own: start the new line and retry the
                # word there, where it can be split against the FULL width.
                lines.append([])
                cur_w = 0.0
                ladder = 0
                pending = w                     # same word: keep its split count
                queue.insert(0, w)
            else:
                lines.append([w])
                cur_w = ww
                ladder = 0
    if lines and not lines[-1]:
        lines.pop()
    return _fix_widows(lines, width_of, space_w, max_w)


def balance_even(words, width_of, space_w, usable_w, k):
    """Split the words into exactly k lines so the lines are as equal in length
    as possible (close to the average width). This avoids a single short last
    line ('widows') and yields a calm, oval block shape.

    Minimizes the sum of squared deviation of each line from the target width
    via dynamic programming. O(k * n^2).
    """
    n = len(words)
    if n == 0:
        return []
    if k <= 1:
        return [list(words)]

    w = [width_of(x) for x in words]
    prefix = [0.0] * (n + 1)
    for i in range(n):
        prefix[i + 1] = prefix[i] + w[i]

    def line_width(i, j):  # words i..j inclusive
        return (prefix[j + 1] - prefix[i]) + space_w * (j - i)

    # target width: average line width given k lines
    target = (prefix[n] + space_w * (n - k)) / k

    INF = float("inf")
    dp = [[INF] * (n + 1) for _ in range(k + 1)]
    nxt = [[-1] * (n + 1) for _ in range(k + 1)]
    dp[0][n] = 0.0

    for l in range(1, k + 1):
        for i in range(n - 1, -1, -1):
            best = INF
            bestj = -1
            for j in range(i, n):
                lw = line_width(i, j)
                over = lw > usable_w
                if over and j > i:
                    break
                rem = dp[l - 1][j + 1]
                if rem < INF:
                    # slight weighting: earlier lines should be fuller so a
                    # possibly shorter line tends to end up at the bottom
                    # (the usual look).
                    weight = 1.0 + 0.04 * l
                    cost = (target - lw) ** 2 * weight + rem
                    # phrase-aware break quality, scaled to the deviation cost so
                    # it only decides between near-equally-balanced splits:
                    t2 = target * target
                    if l > 1:                       # interior line (has a break)
                        if _word_is_stop(words[j]):
                            cost += 0.20 * t2       # don't dangle a function word
                        elif _ends_clause(words[j]):
                            cost -= 0.06 * t2        # ended a clause: nice break
                        elif j + 1 < n and _word_is_conj(words[j + 1]):
                            cost -= 0.06 * t2        # next line starts 'and…/but…'
                    elif l == 1 and i == n - 1:
                        cost += 0.30 * t2           # single-word last line (widow)
                    if cost < best:
                        best = cost
                        bestj = j
                if over:  # single overlong word: cannot be extended
                    break
            dp[l][i] = best
            nxt[l][i] = bestj

    if dp[k][0] == INF:  # emergency: greedy
        return wrap_greedy(words, width_of, space_w, usable_w)

    lines = []
    i = 0
    for l in range(k, 0, -1):
        j = nxt[l][i]
        if j < 0:
            break
        lines.append(words[i:j + 1])
        i = j + 1
    return lines


def _ellipse_line_widths(k, line_h, a, b):
    """Maximum line widths for k lines inside an ellipse (semi-axes a, b),
    vertically centered. Lines at the top/bottom are narrower."""
    mid = (k - 1) / 2.0
    out = []
    for i in range(k):
        dy = (i - mid) * line_h
        r = 1.0 - (dy / b) ** 2 if b > 0 else -1.0
        out.append(2.0 * a * math.sqrt(r) if r > 0 else 0.0)
    return out


def _line_width(words, width_of, space_w):
    """Total width of a line of words (with single spaces between them)."""
    if not words:
        return 0.0
    return (sum(width_of(w) for w in words) + space_w * (len(words) - 1))


def _wrap_schedule(words, width_of, space_w, widths, hyph=None):
    """Wrap greedily where line i may be at most widths[i] wide (extra lines use
    the narrowest/last width). With `hyph` an over-wide word is split at a valid
    syllable break instead of failing. Returns None if a word still does not fit
    on its own line."""
    def maxw(i):
        if not widths:
            return 0.0
        return widths[i] if i < len(widths) else widths[-1]

    lines = []
    cur = []
    cur_w = 0.0
    queue = list(words)
    guard = 0
    while queue and guard < 100000:
        guard += 1
        word = queue.pop(0)
        ww = width_of(word)
        limit = maxw(len(lines))
        if not cur:
            if ww <= limit:
                cur = [word]
                cur_w = ww
            elif hyph:
                res = _split_to_fit(word, limit, width_of, hyph)
                if not res:
                    return None
                left, right = res
                lines.append([left])
                queue.insert(0, right)
                cur, cur_w = [], 0.0
            else:
                return None
        elif cur_w + space_w + ww <= limit:
            cur.append(word)
            cur_w += space_w + ww
        else:
            # current line is full: close it and retry the word on a fresh line
            lines.append(cur)
            cur, cur_w = [], 0.0
            queue.insert(0, word)
    if cur:
        lines.append(cur)
    return lines


def wrap_ellipse(words, width_of, space_w, a, b, line_h, hyph=None):
    """Wrap words so they fit inside an ellipse (semi-axes a, b). Fixed-point
    iteration over the line count, because the allowed widths depend on the
    (centered) line count. Only a self-consistent result is returned (every
    line fits the line count its widths were computed for); otherwise None ->
    the caller picks a smaller font."""
    if not words:
        return []
    init = wrap_greedy(words, width_of, space_w, 2.0 * a, hyph)
    k = max(1, len(init))
    for _ in range(12):
        widths = _ellipse_line_widths(k, line_h, a, b)
        res = _wrap_schedule(words, width_of, space_w, widths, hyph)
        if res is None:
            return None
        if len(res) == k:
            return res          # consistent
        k = len(res)
        if k > 200:
            return None
    return None                 # did not converge -> smaller font


def fit_text(text, measurer, box_w, box_h, max_px, min_px, pad_frac,
             shape="rect", mask=None, hyphenate=False, lang="en"):
    """Find the largest font size at which the wrapped text fits.

    shape='rect'    : rectangular box, evenly balanced lines. Embedded line
                      breaks (\\n) are respected as hard breaks; each paragraph
                      is balanced on its own.
    shape='ellipse' : inscribed ellipse (round speech bubble); lines at the
                      top/bottom become narrower. Hard breaks become spaces here
                      (the ellipse shape drives the wrapping).

    mask: optional list of bool with the same length as text - marks bold
    characters (for partially bold text). None -> nothing bold.

    hyphenate: when True, words that are too wide for a line are split at valid
    syllable breaks (using `lang`'s patterns) instead of just forcing a smaller
    font. Default False keeps the exact previous behavior.

    Returns: (font_px, lines, line_h, ascent, descent, fitted)
    'lines' is a list of run lists ([(subtext, bold), ...] per line).
    """
    if mask is None:
        mask = [False] * len(text)

    # word -> valid break indices (None disables hyphenation entirely)
    hyph_fn = None
    if hyphenate:
        def hyph_fn(wd):
            return hyphenate_word_breaks(wd, lang)

    usable_w = box_w * (1.0 - pad_frac)
    usable_h = box_h * (1.0 - pad_frac)

    if shape == "ellipse":
        # \n counts as a space here
        flat = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
        fmask = list(mask)
        # lengths stay the same (1:1 replacements), so the mask still matches
        words = make_words(flat, fmask)
        if not words:
            return None
        a = usable_w / 2.0
        b = usable_h / 2.0

        def fits(px):
            width_of, space_w, line_h, _asc, _desc = measurer(px)
            res = wrap_ellipse(words, width_of, space_w, a, b, line_h, hyph_fn)
            if res is None:
                return None
            if len(res) * line_h > usable_h:
                return None
            return res
    else:
        norm = text.replace("\r\n", "\n").replace("\r", "\n")
        nmask = list(mask)
        paras = [make_words(pt, pm)
                 for (pt, pm) in split_paragraphs(norm, nmask)]
        if not any(paras):
            return None

        def fits(px):
            width_of, space_w, line_h, _asc, _desc = measurer(px)
            all_lines = []
            for words in paras:
                if not words:
                    all_lines.append([])           # intentional blank line
                    continue
                all_lines.extend(
                    wrap_greedy(words, width_of, space_w, usable_w, hyph_fn))
            if len(all_lines) * line_h > usable_h:
                return None
            # an unbreakable word wider than the box -> does not fit
            for ln in all_lines:
                if _line_width(ln, width_of, space_w) > usable_w + 0.5:
                    return None
            return all_lines

    lo = int(min_px)
    hi = int(max_px)
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if fits(mid) is not None:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best is None:
        best = int(min_px)
        fitted = False
    else:
        fitted = True

    width_of, space_w, line_h, ascent, descent = measurer(best)
    if shape == "ellipse":
        res = wrap_ellipse(words, width_of, space_w,
                           usable_w / 2.0, usable_h / 2.0, line_h, hyph_fn)
        if res is None:
            res = wrap_greedy(words, width_of, space_w, usable_w, hyph_fn)
        line_lists = res
    else:
        line_lists = []
        for words in paras:
            if not words:
                line_lists.append([])
                continue
            # keep the even balancing for normal paragraphs; only fall back to
            # the hyphenating greedy wrap when a word is too wide to fit at all.
            if hyph_fn is not None and any(width_of(w) > usable_w for w in words):
                line_lists.extend(
                    wrap_greedy(words, width_of, space_w, usable_w, hyph_fn))
            else:
                k = len(wrap_greedy(words, width_of, space_w, usable_w))
                line_lists.extend(
                    balance_even(words, width_of, space_w, usable_w, k))
    lines = [line_runs(ws) for ws in line_lists]
    return best, lines, line_h, ascent, descent, fitted


def hyphenate_word_breaks(word, lang="en"):
    """Helper: break indices for a Word object (uses its plain text)."""
    return hyphenate(getattr(word, "text", str(word)), lang)


# ---------------------------------------------------------------------------
# Layer naming
#
# Every inserted layer is named "TypeR NN — <snippet>" (NN = 1-based unit
# number). Building and matching that prefix lives here so the "replace
# previously inserted line" feature and the insert path share one definition
# (and it stays unit-testable without Krita).
# ---------------------------------------------------------------------------

def typer_layer_prefix(index):
    """Name prefix of the layer(s) TypeR inserted for the 1-based unit
    `index`, e.g. 3 -> 'TypeR 03 — '."""
    return "TypeR {:02d} — ".format(int(index))


def is_typer_layer_name(name, index):
    """True if `name` is a layer that TypeR created for unit `index`. The
    full prefix (including the em dash) must match, so hand-made layers or
    other units' layers are never mistaken."""
    return str(name or "").startswith(typer_layer_prefix(index))


# ---------------------------------------------------------------------------
# TextShapR: candidate text-shape arrangements
#
# The picker shows the SAME text wrapped into different line counts / aspect
# ratios (all auto-fit to the box) so the user can click the shape that looks
# best. Everything here is Qt-free and reuses the wrapping math above.
# ---------------------------------------------------------------------------

def runs_markup(runs):
    """Run list -> plain text with ``**`` around the bold sections (the inverse
    of parse_bold for one line)."""
    return "".join(("**" + t + "**") if b else t for (t, b) in runs)


def _search_px(check, max_px, min_px):
    """Binary-search the largest integer px in [min_px, max_px] for which
    `check(px)` returns a (non-None) result. Returns (px, result) or None."""
    lo, hi = int(min_px), int(max_px)
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        res = check(mid)
        if res is not None:
            best = (mid, res)
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def fit_lines_k(words, measurer, usable_w, usable_h, max_px, min_px, k):
    """Largest font size at which `words` balance into EXACTLY k lines that all
    fit (each line <= usable_w, k lines <= usable_h). Returns (px, lines) or
    None when no size yields exactly k fitting lines."""
    if not words or k < 1 or k > len(words):
        return None

    def check(px):
        width_of, space_w, line_h, _a, _d = measurer(px)
        if k * line_h > usable_h:
            return None
        lines = balance_even(words, width_of, space_w, usable_w, k)
        if len(lines) != k:
            return None
        for ln in lines:
            if _line_width(ln, width_of, space_w) > usable_w + 0.5:
                return None
        return lines

    return _search_px(check, max_px, min_px)


def fit_lines_width(words, measurer, usable_w, usable_h, max_px, min_px,
                    frac, hyph=None):
    """Greedy-wrap to a narrower target width (frac * usable_w) and find the
    largest font size that fits the box. With `hyph`, over-wide words split at
    syllable breaks. Returns (px, lines) or None."""
    if not words:
        return None
    target_w = usable_w * frac

    def check(px):
        width_of, space_w, line_h, _a, _d = measurer(px)
        lines = wrap_greedy(words, width_of, space_w, target_w, hyph)
        if len(lines) * line_h > usable_h:
            return None
        for ln in lines:
            if _line_width(ln, width_of, space_w) > usable_w + 0.5:
                return None
        return lines

    return _search_px(check, max_px, min_px)


def fit_fixed_lines(word_lines, measurer, usable_w, usable_h, max_px, min_px):
    """Largest font size at which the GIVEN arrangement fits the box. The line
    breaks are fixed: nothing is re-wrapped, only the size is searched. Used to
    re-fit a hand-edited arrangement after the style or box changed. Returns
    (px, lines) or None when it does not fit even at min_px."""
    lines = [ws for ws in word_lines if ws]
    if not lines:
        return None

    def check(px):
        width_of, space_w, line_h, _a, _d = measurer(px)
        if len(lines) * line_h > usable_h:
            return None
        for ln in lines:
            if _line_width(ln, width_of, space_w) > usable_w + 0.5:
                return None
        return lines

    return _search_px(check, max_px, min_px)


def fit_lines_ellipse(words, measurer, a, b, max_px, min_px, hyph=None):
    """Largest font size at which the words fit an ellipse with semi-axes a, b.
    Returns (px, lines) or None."""
    if not words or a <= 0 or b <= 0:
        return None

    def check(px):
        width_of, space_w, line_h, _asc, _desc = measurer(px)
        lines = wrap_ellipse(words, width_of, space_w, a, b, line_h, hyph)
        if lines is None or len(lines) * line_h > 2.0 * b:
            return None
        return lines

    return _search_px(check, max_px, min_px)


# sub-box scale factors that produce differently proportioned round bubbles
_ROUND_BOXES = ((1.0, 1.0), (0.9, 1.0), (0.8, 1.0), (0.7, 1.0), (0.6, 1.0),
                (0.5, 1.0), (1.0, 0.85), (1.0, 0.7), (1.0, 0.55),
                (0.85, 0.85), (0.7, 0.85))
# target-width fractions for the hyphenating width sweep
_WIDTH_FRACS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.42, 0.35, 0.28, 0.22)

# The fill ratio (text-block area / usable area) that reads most comfortably in
# a speech bubble: enough presence to not look lost, without touching the rim.
# Both a cramped (near-1.0) and a sparse (near-0.0) block score below this peak.
# Kept fairly high so the recommended card follows the user's size up (bigger,
# fuller text) instead of settling on a small, over-airy block. The block is
# ideal anywhere in [_TARGET_FILL, _FILL_SWEET_MAX]; only past the sweet max does
# it read as crowding the bubble rim.
_TARGET_FILL = 0.72
_FILL_SWEET_MAX = 0.88

# A line ending on one of these sits at a natural pause, so breaking there reads
# better than snapping a line mid-clause.
_CLAUSE_END = ".,;:!?…"          # . , ; : ! ? …

# Short function words that dangle badly at the END of a line in lettering
# (articles, prepositions, conjunctions, a couple of short pronouns). A line
# should not end on one of these — it belongs with the word that follows. Used
# as a tie-breaker so, among near-equally-balanced splits, the shaper picks the
# one that keeps these words attached.
_LINE_END_STOPS = frozenset((
    "a", "an", "the", "to", "of", "in", "on", "at", "by", "for", "and", "or",
    "but", "nor", "as", "so", "if", "is", "it", "my", "our", "your", "i",
    "with", "from", "into", "onto", "than", "up",
))
_TRIM_PUNCT = "\"'“”‘’.,;:!?—-…()[]{}*«»"


def _bare_last(text):
    """A word stripped of closing quotes/brackets and lower-cased, for stop-word
    tests. Returns '' when the word ends a clause (a fine place to break, so it
    must never count as a dangling stop word)."""
    t = str(text).rstrip("\"'“”‘’)]}»")
    if not t or t[-1] in _CLAUSE_END:
        return ""
    return t.strip(_TRIM_PUNCT).lower()


def _word_is_stop(word):
    return _bare_last(getattr(word, "text", word)) in _LINE_END_STOPS


# Coordinating/subordinating conjunctions + relative pronouns: a line that
# STARTS with one of these reads well (the phrase begins on its own line), so
# breaking right BEFORE it is a naturally good place.
_CONJ_START = frozenset((
    "and", "but", "or", "nor", "so", "yet", "because", "although", "though",
    "while", "when", "where", "which", "who", "since", "unless", "until", "if",
))


def _word_is_conj(word):
    return _bare_last(getattr(word, "text", word)) in _CONJ_START


def _ends_clause(word):
    """True if the word ends with clause punctuation (a natural break point)."""
    t = str(getattr(word, "text", word)).rstrip("\"'”’)]}»")
    return bool(t) and t[-1] in _CLAUSE_END
# Comfortable reading measure: lines longer than this (in characters) are
# penalised even when they still fit the box, the way a letterer caps line
# length for legibility (cf. the PSD TextShapeR's per-mode maxLineWidth).
_MAX_LINE_CHARS = 30

# A line shorter than this fraction of the longest one reads as a gap in the
# block, so interior stub lines are penalised (the LAST line is left to the
# gentler `last_term`, since a slightly short final line is normal).
_MIN_LINE_RATIO = 0.4

# Legacy default kept so old callers that pass `line_target=` keep working.
_LINE_TARGET = 4
_LINE_TARGET_WEIGHT = 0.25

# --- per-mode profiles ------------------------------------------------------
# The Photoshop original (ScanR TypeR, `app_src/textShapeR.js` → PROFILE_PRESETS)
# keeps ONE of these tables per mode; this port used to hard-code the "balanced"
# column for every mode, which is why Tall degenerated into a ladder of one-word
# lines and why a tall bubble was judged against a 4-line ideal. Values are that
# reference's, with the line band widened where our generator legitimately needs
# it (a very tall bubble really does want more lines than the reference's cap).
#
#   lines       soft band for the line count; outside it the count is charged
#   line_target where the mode leans WITHIN what the geometry allows
#   max_chars   reading measure, per mode
#   min_ratio   below this fraction of the longest line an interior line is a stub
_PROFILES = {
    "balanced": {"lines": (2, 8), "line_target": 4, "max_chars": 26,
                 "min_ratio": 0.40},
    "round":    {"lines": (3, 7), "line_target": 4, "max_chars": 22,
                 "min_ratio": 0.38},
    "tall":     {"lines": (4, 12), "line_target": 6, "max_chars": 18,
                 "min_ratio": 0.36},
    "wide":     {"lines": (1, 5), "line_target": 3, "max_chars": 34,
                 "min_ratio": 0.50},
}
#: How far the line count may sit from the ideal before the charge bites, and
#: the most it can ever cost. Capped deliberately: the old uncapped
#: `abs(k - 4) ** 1.5` charge could reach 2.8 points and overrule every
#: aesthetic term at once (a quarter-full block beat a well-filled one).
_LINE_SPREAD = 1.6
_LINE_PEN_MAX = 0.55


def profile_for(mode):
    """The scoring profile for a shaper mode (unknown modes -> balanced)."""
    return _PROFILES.get(mode or "balanced", _PROFILES["balanced"])


def ideal_line_count(total_w, line_h, box_aspect, profile=None, max_fit=None):
    """How many lines this text WANTS in a box of this shape.

    Splitting a text of total advance width `total_w` into k lines gives a block
    roughly `total_w / k` wide and `k * line_h` tall, so the block matches the
    box when ``(total_w / k) / (k * line_h) == box_aspect`` — i.e.

        k = sqrt(total_w / (line_h * box_aspect))

    `total_w / line_h` is a pure ratio, so this is scale-free: the answer does
    not move when the fitted size does. That is the whole point — the ideal
    count has to come from the bubble's proportions, not from a constant, or a
    tall bubble gets judged against a 4-line ideal and stays three-quarters
    empty. The result is clamped to the mode's band and to what actually fits.
    """
    if total_w <= 0 or line_h <= 0 or box_aspect <= 0:
        return 1.0
    k = math.sqrt(total_w / (line_h * box_aspect))
    prof = profile or _PROFILES["balanced"]
    lo, hi = prof["lines"]
    if max_fit:
        hi = min(hi, max(1, int(max_fit)))
        lo = min(lo, hi)
    return max(float(lo), min(float(hi), k))


def _arr_metrics(cand, measurer):
    """Geometry of an arrangement at its own fitted size: returns
    (px, k, line_widths, block_w, block_h, line_h). `block_w` is the widest
    line, `block_h` is k*line_h. Qt-free; uses the same `measurer` and run
    lists as the generator so it measures exactly what will be inserted."""
    lines = cand.get("lines") or []
    k = len(lines)
    px = max(1, int(cand.get("px", 1)))
    width_of, _space_w, line_h, _asc, _desc = measurer(px)
    line_ws = [width_of(runs) for runs in lines]
    block_w = max(line_ws) if line_ws else 0.0
    return px, k, line_ws, block_w, line_h * k, line_h


#: A sampled bubble outline never goes below this fraction of the widest row —
#: a balloon's very top and bottom taper to nothing, and a line placed there
#: would be judged against a target width of ~0.
_ROW_FLOOR = 0.12


def shape_row_width(rows, t):
    """Normalised bubble width at relative height `t` (0 = top, 1 = bottom).

    `rows` is the sampled outline: one width fraction per row, top to bottom,
    normalised so the widest row is 1.0. Linear interpolation between samples;
    an empty/invalid profile answers 1.0, i.e. "rectangular".
    """
    if not rows:
        return 1.0
    n = len(rows)
    if n == 1:
        return max(_ROW_FLOOR, float(rows[0]))
    x = min(max(float(t), 0.0), 1.0) * (n - 1)
    i = int(x)
    if i >= n - 1:
        return max(_ROW_FLOOR, float(rows[-1]))
    frac = x - i
    val = float(rows[i]) * (1.0 - frac) + float(rows[i + 1]) * frac
    return max(_ROW_FLOOR, val)


def line_row_targets(rows, k, block_h=None, usable_h=None):
    """The bubble's own width at each of `k` line positions.

    The text block is set in the MIDDLE of the bubble and is usually shorter
    than it, so line *i* sits at ``(gap + (i+0.5)*line_h) / usable_h`` of the
    outline, not at ``(i+0.5)/k`` of it. Getting that wrong maps the first line
    onto the balloon's tapering top edge and declares every arrangement to be
    bursting out of the bubble. Falls back to spreading the lines over the full
    height when the block's geometry isn't given, and to 1.0 without an outline.
    """
    if k <= 0:
        return []
    if not rows:
        return [1.0] * k
    if block_h and usable_h and usable_h > 0:
        span = min(float(block_h), float(usable_h))
        gap = max(0.0, (usable_h - span) / 2.0)      # vertically centred
        line_h = span / k
        return [shape_row_width(rows, (gap + (i + 0.5) * line_h) / usable_h)
                for i in range(k)]
    return [shape_row_width(rows, (i + 0.5) / k) for i in range(k)]


def _phrase_break_penalty(texts, line_ws, space_w, usable_w):
    """Charge for line breaks that tear a short phrase apart *avoidably*.

    ``What?! / No / way!`` splits a two-word exclamation across lines; a letterer
    sets ``What?! / No way!``. But in a narrow bubble one-word lines are simply
    what fits, and charging those would punish the only sensible shape. So a
    break is only charged when the next line's first word would still have fitted
    on this one — i.e. when the split was a choice, not the geometry.
    """
    if len(texts) < 3:
        return 0.0
    pen = 0.0
    for i in range(len(texts) - 1):
        parts = texts[i].split()
        if not parts or len(parts) > 2:
            continue
        if _ends_clause(parts[-1]):
            continue                       # a clause ended here: fine to break
        nxt = texts[i + 1].split()
        if not nxt:
            continue
        # width of this line + a space + the next line's first word
        joined = line_ws[i] + space_w + len(nxt[0]) / max(1, len(texts[i + 1])) \
            * line_ws[i + 1]
        if joined <= usable_w:
            pen += 1.0
    return pen


def _sentence_break_penalty(texts):
    """Charge for an interior line that carries a sentence end with more words
    behind it (``a trap. Now``): the next sentence starts at the end of a line
    where it could have started on its own."""
    pen = 0
    for t in texts[:-1]:
        stripped = t.rstrip()
        for i, ch in enumerate(stripped[:-1]):
            if ch in ".!?…" and stripped[i + 1] == " ":
                pen += 1
                break
    return pen


def score_arrangement(cand, measurer, usable_w, usable_h, px_ref=None,
                      max_chars=None, line_target=None, mode=None,
                      total_w=None, shape_rows=None):
    """Typographic quality of a candidate arrangement (higher = better).

    Combines the judgements a letterer makes by eye, so the recommended shape is
    the one that *reads* best rather than merely the largest that fits.

    **The order of judgement is deliberate.** The four terms describing the
    SHAPE of the block outweigh the two describing its bulk::

        shape   aspect 1.1 + balance 0.8 + step 0.6 + break quality 0.5 = 3.0
        bulk    fill 1.15 + size 1.0                                    = 2.15

    Size and fill used to carry 2.7 between them against a hard fill plateau,
    which made "biggest and fullest" win nearly every ranking — the shape terms
    could only break ties. Reversing that is what stops the shaper recommending
    a cramped block over a calm one.

    The terms:

    * size, with diminishing returns (normalised against `px_ref`, the biggest
      size in the candidate set, so a one-pixel gain can't beat a better shape);
    * fill ratio on one smooth curve around ``[_TARGET_FILL, _FILL_SWEET_MAX]``,
      judged against the bubble's real area when `shape_rows` is given;
    * rim clearance — a block running edge to edge in EITHER direction is
      charged, which an area ratio alone cannot see;
    * aspect match between the text block and the bubble;
    * line balance and line-to-line smoothness — a stack that tapers away is
      charged by the step term even when its variance looks acceptable;
    * break quality — a bonus for lines ending at a clause boundary, charges for
      a sentence starting at the end of a line, for a short phrase torn apart
      when it would have fitted, for dangling function words and hyphens;
    * reading measure and stub lines, both per mode (see `_PROFILES`);
    * line count, against the count the bubble's proportions imply
      (`ideal_line_count`) — capped, so it can never overrule the rest.

    With `shape_rows` (a sampled selection outline) every line-length judgement
    is made relative to the bubble's width AT THAT LINE'S HEIGHT, so "even" means
    "each line uses its share of the room it has" — a lens in a balloon, a
    rectangle in a caption box.

    `line_target` and `max_chars` override the profile for callers that want the
    old absolute behaviour. Qt-free and O(k): safe to call for every candidate on
    each refresh.
    """
    lines = cand.get("lines") or []
    px, k, line_ws, block_w, block_h, line_h = _arr_metrics(cand, measurer)
    if k == 0 or block_w <= 0 or usable_w <= 0 or usable_h <= 0:
        return float("-inf")
    prof = profile_for(mode)
    if max_chars is None:
        max_chars = prof["max_chars"]
    min_ratio = prof["min_ratio"]

    ref = float(px_ref) if px_ref else float(px)
    size_term = (px / ref) ** 0.5 if ref > 0 else 1.0        # sqrt: diminishing

    # Fill: one smooth curve, not a plateau between two cliffs. The old shape
    # was flat across [0.72, 0.88] — so it stopped telling candidates apart
    # exactly where the interesting choices live — and collapsed below it
    # (fill 0.43 scored 0.32, fill 0.25 scored 0.03), which let "big and full"
    # decide almost every ranking on its own. A single Gaussian around the
    # comfortable band is gentler on both sides while still preferring a bubble
    # that is used; crowding past the sweet max still falls away fast.
    # With a sampled outline the bubble is no longer a rectangle: an ellipse
    # holds ~78% of its bounding box, so the same block covers proportionally
    # more of what is actually available. Judging fill against the raw box is
    # what made a comfortable block in a round balloon look "half empty".
    row_targets = (line_row_targets(shape_rows, k, block_h, usable_h)
                   if shape_rows else None)
    area_frac = (sum(shape_rows) / len(shape_rows)) if shape_rows else 1.0
    area_frac = max(_ROW_FLOOR, min(1.0, area_frac))

    fill = (block_w * block_h) / (usable_w * usable_h * area_frac)
    if fill <= _FILL_SWEET_MAX:
        centre = 0.5 * (_TARGET_FILL + _FILL_SWEET_MAX)
        fill_term = math.exp(-((fill - centre) / 0.34) ** 2)
        if fill >= _TARGET_FILL:
            fill_term = max(fill_term, 0.92)
    else:
        fill_term = max(0.10, 1.0 - (fill - _FILL_SWEET_MAX) * 8.0)

    # Rim clearance. An AREA ratio cannot see a block that runs edge to edge in
    # one direction while staying short in the other: `What?! / No / way!` fills
    # 0.73 of the area yet its longest line is exactly as wide as the usable box.
    # What the eye reads as cramped is a block touching the rim in EITHER
    # direction, so measure that directly.
    # With an outline this becomes exact: every line is measured against the
    # bubble's width AT ITS OWN HEIGHT, so a long line near the tapering top or
    # bottom of a balloon is caught even when the block as a whole looks fine.
    if row_targets:
        crowd = max(block_h / usable_h,
                    max(w / (usable_w * t) for w, t in zip(line_ws, row_targets)))
    else:
        crowd = max(block_w / usable_w, block_h / usable_h)
    crowd_pen = ((crowd - 0.90) / 0.10) ** 2 if crowd > 0.90 else 0.0

    # Every judgement about line LENGTHS below is made on these: each line's
    # width relative to the bubble's width at its own height. Without an outline
    # that is just the width itself, so a rectangle is judged against flatness
    # exactly as before. With one, "even" stops meaning "all the same length"
    # and starts meaning "each line uses its share of the room it has" — which
    # is why a lens (short-long-short) is the calm shape in a balloon and a
    # rectangle is the ragged one. Measuring both against the same profile also
    # keeps the silhouette from being scored twice, once for and once against.
    rel_ws = ([w / t for w, t in zip(line_ws, row_targets)] if row_targets
              else list(line_ws))
    rel_max = max(rel_ws) if rel_ws else 0.0

    block_aspect = block_w / block_h if block_h > 0 else 0.0
    box_aspect = usable_w / usable_h
    if block_aspect > 0 and box_aspect > 0:
        aspect_term = math.exp(-(math.log(block_aspect / box_aspect) / 0.9) ** 2)
    else:
        aspect_term = 0.0

    if k >= 2 and rel_max > 0:
        avg = sum(rel_ws) / k
        rag = (sum((w - avg) ** 2 for w in rel_ws) / k) ** 0.5 / rel_max
        balance_term = math.exp(-(rag / 0.42) ** 2)
    else:
        balance_term = 1.0

    # Line-to-line smoothness. Global variance alone cannot see a block that
    # tapers away line by line (a triangle scored 0.71 where an even stack
    # scored 0.76 — 0.05 apart, which no eye agrees with). What reads as ragged
    # is the STEP between neighbours, so charge that directly, the way the
    # reference shaper's `smoothnessWeight` does.
    if k >= 3 and rel_max > 0:
        steps = [abs(rel_ws[i] - rel_ws[i - 1]) / rel_max for i in range(1, k)]
        step_rms = (sum(s * s for s in steps) / len(steps)) ** 0.5
        step_term = math.exp(-(step_rms / 0.34) ** 2)
    else:
        step_term = 1.0

    last_term = 1.0
    if k >= 2 and rel_max > 0:
        last_frac = rel_ws[-1] / rel_max
        if last_frac < 0.5:
            last_term = min(1.0, 0.6 + 0.8 * last_frac)
    # a very short FIRST line (an orphan) reads as badly as a short last line;
    # penalise it symmetrically once there are enough lines for it to look odd.
    first_term = 1.0
    if k >= 3 and rel_max > 0:
        first_frac = rel_ws[0] / rel_max
        if first_frac < 0.5:
            first_term = min(1.0, 0.6 + 0.8 * first_frac)

    # break quality: fraction of the internal breaks (all lines but the last)
    # that land right after clause punctuation, minus lines of only punctuation.
    texts = [runs_text(runs).strip() for runs in lines]
    punct_term = 0.0
    if k >= 2:
        good = sum(1 for t in texts[:-1]
                   if t and t[-1] in _CLAUSE_END and any(c.isalnum() for c in t))
        punct_term = good / (k - 1)
    punct_only = sum(1 for t in texts
                     if t and not any(c.isalnum() for c in t))

    # reading measure: quadratic overflow past max_chars, summed over the lines.
    over = 0.0
    if max_chars and max_chars > 0:
        for t in texts:
            n = len(t)
            if n > max_chars:
                frac = (n - max_chars) / float(max_chars)
                over += frac * frac

    # interior stub lines: a short line between longer ones (not the last line)
    short = 0.0
    for w in rel_ws[:-1]:
        r = w / rel_max if rel_max else 0.0
        if r < min_ratio:
            d = (min_ratio - r) / min_ratio
            short += d * d

    # Line count. `line_target` (an explicit count from the caller) keeps the
    # old absolute behaviour for compatibility; otherwise the ideal comes from
    # the bubble's proportions, so a tall bubble asks for a tall stack instead
    # of being judged against a constant. Either way the charge is CAPPED: it
    # is a tie-breaker between shapes, never a veto over fill and silhouette.
    if line_target:
        target_pen = abs(k - line_target) ** 1.5
    else:
        total = float(total_w) if total_w else (sum(line_ws) + 0.0)
        ideal = ideal_line_count(total, line_h, box_aspect, prof,
                                 max_fit=usable_h / line_h if line_h else None)
        # the mode leans within what the geometry allows, it does not overrule it
        lean = prof["line_target"] - _PROFILES["balanced"]["line_target"]
        ideal = max(prof["lines"][0], min(prof["lines"][1], ideal + 0.5 * lean))
        d = (k - ideal) / _LINE_SPREAD
        target_pen = min(_LINE_PEN_MAX, d * d) / _LINE_TARGET_WEIGHT

    # hyphenation is a last resort: a line broken mid-word (ending in '-') reads
    # worse than the same shape without the split, so each such line is penalised
    # — a clean N-line block beats a hyphenated N-line block.
    hyph_pen = sum(1 for t in texts[:-1] if t.endswith("-"))

    # dangling function words: an interior line that ends on a short article/
    # preposition/conjunction reads worse than one that keeps it with its noun.
    stop_pen = 0
    for t in texts[:-1]:
        parts = t.split()
        if parts and _bare_last(parts[-1]) in _LINE_END_STOPS:
            stop_pen += 1

    _wof, space_w, _lh, _a, _d = measurer(px)
    phrase_pen = _phrase_break_penalty(texts, line_ws, space_w, usable_w)
    sentence_pen = _sentence_break_penalty(texts)

    # Weights. Size and fill used to carry 2.7 of ~5 points between them, so
    # "biggest and fullest" won nearly every ranking and the shape terms only
    # broke ties. They now weigh less than the four terms that describe the
    # SHAPE of the block (aspect + balance + step + break quality = 3.0), which
    # is the order a letterer judges in: first does it sit right in the bubble,
    # then is it big.
    quality = (1.0 * size_term
               + 1.15 * fill_term
               + 1.1 * aspect_term
               + 0.8 * balance_term
               + 0.6 * step_term
               + 0.5 * punct_term) * last_term * first_term
    return (quality
            - 0.6 * over
            - 0.5 * punct_only
            - 0.6 * short
            - 0.5 * hyph_pen
            - 0.3 * stop_pen
            - 0.45 * sentence_pen
            - 0.4 * phrase_pen
            - 0.5 * crowd_pen
            - _LINE_TARGET_WEIGHT * target_pen)


#: Below this fill the whole candidate set counts as starved and the shaper
#: retries with hyphenation on its own (see `shape_candidates`).
_STARVED_FILL = 0.25


def _block_fill(cand, measurer, usable_w, usable_h):
    """Fraction of the usable box the arrangement's block covers."""
    _px, _k, _lw, block_w, block_h, _lh = _arr_metrics(cand, measurer)
    if usable_w <= 0 or usable_h <= 0:
        return 0.0
    return (block_w * block_h) / (usable_w * usable_h)


def _dedup_similar(cands, measurer):
    """Collapse near-identical arrangements so the picker offers *distinct*
    shapes. Two candidates are 'the same shape' when they have the same line
    count and the same relative line-width profile (rounded to 10%); the same
    block set slightly bigger or smaller is not a second choice worth a slot.
    Keeps the first of each group, so `cands` must already be sorted best-first.
    """
    kept, seen = [], set()
    for c in cands:
        _px, k, line_ws, block_w, _bh, _lh = _arr_metrics(c, measurer)
        prof = tuple(round(w / block_w, 1) for w in line_ws) if block_w else ()
        sig = (k, prof)
        if sig in seen:
            continue
        seen.add(sig)
        kept.append(c)
    return kept


def shape_candidates(text, measurer, box_w, box_h, max_px, min_px, pad_frac,
                     mode="balanced", hyphenate=False, lang="en", mask=None,
                     limit=10, dehyphenate=False, inset=0.0, shape_rows=None):
    """Generate candidate arrangements of `text` for the TextShapR picker.

    mode: 'balanced' (evenly balanced lines, biggest size first),
          'tall' (more lines / narrow block first),
          'wide' (fewer lines / wide block first),
          'round' (fit differently proportioned ellipses).
    hyphenate: allow syllable breaks (uses `lang`'s patterns).
    dehyphenate: first rejoin words the source split across a line (see
        `dehyphenate`), so the shaper is free to re-wrap them.
    shape_rows: optional sampled outline of the selection — one normalised
        width per row, top to bottom (see `shape_row_width`). When given, fill,
        rim clearance and silhouette are judged against the real bubble instead
        of its bounding box. Absent, everything behaves rectangularly.

    Embedded line breaks become spaces (the candidates create their own
    breaks). Returns a list of dicts {'px': int, 'k': int, 'lines': [run list
    per line]}, deduplicated, at most `limit` entries. The chosen candidate can
    be applied by joining runs_markup() of its lines with '\\n' and inserting
    that as hard-broken text capped at 'px'.
    """
    if mask is None:
        mask = [False] * len(text)
    flat = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    if dehyphenate:
        flat, mask = _dehyphenate(flat, list(mask))
    words = make_words(flat, list(mask))
    if not words:
        return []
    # `inset` (px per side) leaves room for a fixed-width outline/stroke so
    # outlined text doesn't overflow the bubble — the outline adds the same px
    # margin at any font size, so it's subtracted as a constant, not scaled.
    usable_w = box_w * (1.0 - pad_frac) - 2.0 * max(0.0, inset)
    usable_h = box_h * (1.0 - pad_frac) - 2.0 * max(0.0, inset)
    if usable_w <= 0 or usable_h <= 0:
        return []

    hyph_fn = None
    if hyphenate:
        def hyph_fn(wd):
            return hyphenate_word_breaks(wd, lang)

    cands = []
    seen = set()

    def add(res):
        if res is None:
            return
        px, word_lines = res
        runs = [line_runs(ws) for ws in word_lines]
        key = tuple(runs_text(r) for r in runs)
        if key in seen:
            return
        seen.add(key)
        # keep the word-level grouping too, so the manual break editor can
        # regroup this candidate without re-tokenising.
        cands.append({"px": px, "k": len(runs), "lines": runs,
                      "words": [list(ws) for ws in word_lines]})

    if mode == "round":
        a, b = usable_w / 2.0, usable_h / 2.0
        for fw, fh in _ROUND_BOXES:
            add(fit_lines_ellipse(words, measurer, a * fw, b * fh,
                                  max_px, min_px, hyph_fn))
    elif hyphenate:
        # exact-k balancing cannot split words, so hyphenated candidates come
        # from greedily wrapping to a sweep of narrower target widths
        for f in _WIDTH_FRACS:
            add(fit_lines_width(words, measurer, usable_w, usable_h,
                                max_px, min_px, f, hyph_fn))
    else:
        # (a) the width-balanced shape for each line count
        for k in range(1, min(len(words), 12) + 1):
            add(fit_lines_k(words, measurer, usable_w, usable_h,
                            max_px, min_px, k))
        # (b) a sweep of narrower target widths -> alternative proportions the
        # k-balancer alone never produces (some top-heavy, some tighter);
        for f in _WIDTH_FRACS:
            add(fit_lines_width(words, measurer, usable_w, usable_h,
                                max_px, min_px, f, None))
        # (c) a few lens/oval shapes (short-long-short) that fill round-ish
        # bubbles more naturally than a rectangle. Duplicates collapse in
        # `add`/`_dedup_similar`, and the score decides which actually surface.
        _a, _b = usable_w / 2.0, usable_h / 2.0
        for fw, fh in _ROUND_BOXES[:4]:
            add(fit_lines_ellipse(words, measurer, _a * fw, _b * fh,
                                  max_px, min_px, None))

    # Starved set: when the best thing on offer leaves the bubble nearly empty,
    # a long word is holding the size down (`Unbelievable!` in a narrow bubble
    # fits at 13px and fills a tenth of it). Rather than shrug, try the width
    # sweep again WITH syllable breaks, even though the user did not ask for
    # them: the hyphen penalty keeps those candidates out of the way whenever a
    # clean shape exists, so this can only add options, never take one away.
    if cands and not hyphenate and mode != "round":
        best_fill = max(_block_fill(c, measurer, usable_w, usable_h)
                        for c in cands)
        if best_fill < _STARVED_FILL:
            def _rescue(wd):
                return hyphenate_word_breaks(wd, lang)
            for f in _WIDTH_FRACS:
                add(fit_lines_width(words, measurer, usable_w, usable_h,
                                    max_px, min_px, f, _rescue))

    if not cands:
        return []
    # Rank by the typographic quality score for EVERY mode, so the recommended
    # (first) card is always the best-looking shape. The mode enters through its
    # profile (line band, reading measure, stub ratio) and through the ideal line
    # count the bubble's proportions imply — never as a hard sort key, so 'tall'
    # leans tall but a degenerate, over-hyphenated block never wins.
    px_ref = max(c["px"] for c in cands) or 1
    for c in cands:
        c["score"] = score_arrangement(c, measurer, usable_w, usable_h, px_ref,
                                       mode=mode, shape_rows=shape_rows)
    # Every mode ranks by the score, round included: it used to sort by size
    # first (`-px`, score only as a tie-break), which put a lower-scoring card
    # in the ★ slot — in a round bubble the biggest fit is exactly the shape
    # that crowds the rim.
    cands.sort(key=lambda c: -c["score"])
    return _dedup_similar(cands, measurer)[:limit]


def vertical_start(valign, box_y, box_h, pad_frac, k, line_h, ascent, descent,
                   cap=None):
    """Baseline of the FIRST line depending on vertical alignment.

    valign='middle' : block centered around the box center (default).
    valign='top'    : block at the top of the box (with padding).
    valign='bottom' : block at the bottom of the box (with padding).

    `cap` (the font's cap height) makes the centering OPTICAL rather than by the
    em box: `ascent` includes the empty ascender/accent space above the capitals,
    which differs from font to font and would leave all-caps lettering looking a
    touch too high or low. Measuring the top from the cap height instead lands
    the visible glyphs on the box centre. Falls back to `ascent` when unknown.
    """
    # clamp the cap height to a sane share of the ascent so a bogus font metric
    # can never shift the text the wrong way or by an absurd amount
    use_cap = bool(cap and cap > 0 and ascent > 0)
    c = max(0.55 * ascent, min(float(cap), ascent)) if use_cap else ascent
    pad = box_h * pad_frac / 2.0
    if valign == "top":
        return box_y + pad + c
    if valign == "bottom":
        return box_y + box_h - pad - descent - (k - 1) * line_h
    cy = box_y + box_h / 2.0
    if use_cap:
        # optical: centre the CAP block (cap-top of the first line to the
        # baseline of the last) on the box centre, so all-caps lettering sits
        # dead centre — the empty ascender space and the descent are ignored.
        return cy - ((k - 1) * line_h - c) / 2.0
    # no cap height known: centre the em box (ascent + descent)
    return cy - ((k - 1) * line_h + descent - ascent) / 2.0


def line_x_positions(line_widths, align, left, center, right):
    """Absolute LEFT x for each line so it renders correctly with the default
    SVG 'start' anchor (the lines are pre-centered/-aligned here instead of
    relying on text-anchor='middle').

    Krita's text tool keeps an absolute-x / 'start'-anchor position when you
    edit the shape, but it drops a 'middle'/'end' anchor and snaps the text to
    the corner – so we encode the alignment as explicit per-line x instead.

    align: 'left' -> all lines start at `left`;
           'right' -> each line ends at `right` (x = right - width);
           anything else (center) -> each line centered on `center`.
    """
    if align == "left":
        return [float(left) for _ in line_widths]
    if align == "right":
        return [float(right) - w for w in line_widths]
    return [float(center) - w / 2.0 for w in line_widths]


# --- vertical text (tategaki) ---------------------------------------------
# Vertical text turns the page's axes around: a "line" is a column running
# downwards, and successive columns march LEFTWARDS (writing-mode
# 'vertical-rl'). The fitter is axis-agnostic — it only ever asks the measurer
# how long a run is along the line and how far apart lines sit — so vertical
# text reuses fit_text with the box passed in transposed (box_h as the width)
# and a measurer that measures DOWN the column. See _make_vertical_measurer in
# typer_kr.py: measuring horizontal advances here would be silently wrong.
#
# The two controls keep their literal meaning: `align` (left/center/right)
# places the block of columns horizontally, `valign` (top/middle/bottom) places
# the text along each column.

def vertical_measurer(line_spacing):
    """measurer(px) -> (width_of, space_w, line_h, ascent, descent) for vertical
    text, in the same shape as typer_kr's Qt measurer so fit_text can use it.

    THE POINT OF THIS FUNCTION: with text-orientation 'upright' every glyph
    advances by roughly one em DOWNWARDS, so a run's length along its column is
    `characters * px`. A font's horizontal advance is the wrong tape measure
    here — "I" and "W" differ wildly in width but stack to exactly the same
    height — and feeding it to fit_text makes wrap and auto-fit systematically
    wrong. `line_h` is the column-to-column advance, across the columns.

    Neither the family nor bold/italic enter into it: the upright advance is the
    em box whatever the face, which is why this needs no Qt. ascent/descent are
    the em half-box; vertical text places its block with horizontal_start(),
    which doesn't consult them.
    """
    def measurer(px):
        px = max(1, int(round(px)))
        em = float(px)

        def width_of(x):
            runs = getattr(x, "runs", None)
            if runs is None:
                if isinstance(x, (list, tuple)):
                    runs = x          # a plain run list [(text, bold), ...]
                else:
                    return len(x) * em          # a plain string
            return sum(len(t) for (t, _b) in runs) * em

        return width_of, em, em * line_spacing, em / 2.0, em / 2.0
    return measurer


_VALIGN_ANCHOR = {"top": "left", "bottom": "right"}


def column_y_positions(line_lengths, valign, top, center, bottom):
    """Absolute TOP y for each column of vertical text.

    `line_lengths` are column lengths as returned by a vertical measurer
    (character count * font size, not glyph advance widths).
    """
    return line_x_positions(line_lengths, _VALIGN_ANCHOR.get(valign, "center"),
                            top, center, bottom)


def horizontal_start(align, box_x, box_w, pad_frac, k, line_h):
    """Center x of the FIRST column of vertical-rl text (k columns total).

    Vertical-rl starts at the right and runs leftwards, so column i sits at
    ``horizontal_start(...) - i * line_h``.
    """
    pad = box_w * pad_frac / 2.0
    block_w = k * line_h
    if align == "left":
        right = box_x + pad + block_w
    elif align == "right":
        right = box_x + box_w - pad
    else:
        right = box_x + box_w / 2.0 + block_w / 2.0
    return right - line_h / 2.0
