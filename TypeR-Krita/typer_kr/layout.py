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


def hyphenate(word, lang="en", left=None, right=None):
    """Return the sorted character indices inside `word` where a hyphen may be
    placed (valid syllable breaks), honoring a minimum of `left` letters before
    and `right` letters after a break. When left/right are None the language's
    own minima are used. Empty list if the word is too short, not a plain word,
    or patterns are unavailable."""
    dl, dr = _HYPH_MINS.get(_norm_lang(lang), (2, 3))
    if left is None:
        left = dl
    if right is None:
        right = dr
    if not word or len(word) < left + right:
        return []
    if not _WORD_RE.match(word):
        return []
    h = _get_hyphenator(lang)
    if h is None:
        return []
    pieces = h.split(word)
    if len(pieces) < 2:
        return []
    breaks = []
    pos = 0
    for p in pieces[:-1]:
        pos += len(p)
        if left <= pos <= len(word) - right:
            breaks.append(pos)
    return breaks


def split_word(word, i):
    """Split a Word at character index i; append a hyphen to the first part.
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
        left_runs[-1] = (lt + "-", lb)          # hyphen inherits previous bold
    else:
        left_runs = [("-", False)]
    left_text = "".join(t for t, _ in left_runs)
    right_text = "".join(t for t, _ in right_runs)
    left = Word(left_text, any(b for _, b in left_runs), left_runs)
    right = Word(right_text, any(b for _, b in right_runs), right_runs)
    return left, right


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


def wrap_greedy(words, width_of, space_w, max_w, hyph=None):
    """Greedily wrap words into lines, each line <= max_w. With `hyph` (a
    callable word -> break indices) a word that does not fit is split at a valid
    syllable break instead of overflowing."""
    lines = [[]]
    cur_w = 0.0
    queue = list(words)
    guard = 0
    while queue and guard < 100000:
        guard += 1
        w = queue.pop(0)
        ww = width_of(w)
        cur = lines[-1]
        if not cur:
            if ww <= max_w:
                cur.append(w)
                cur_w = ww
            else:                               # too wide for a whole line
                res = _split_to_fit(w, max_w, width_of, hyph) if hyph else None
                if res:
                    left, right = res
                    cur.append(left)
                    lines.append([])
                    cur_w = 0.0
                    queue.insert(0, right)
                else:
                    cur.append(w)               # give up -> overflow (as before)
                    cur_w = ww
        elif cur_w + space_w + ww <= max_w:
            cur.append(w)
            cur_w += space_w + ww
        else:
            avail = max_w - cur_w - space_w
            res = _split_to_fit(w, avail, width_of, hyph) if hyph else None
            if res:
                left, right = res
                cur.append(left)
                lines.append([])
                cur_w = 0.0
                queue.insert(0, right)
            else:
                lines.append([w])
                cur_w = ww
    if lines and not lines[-1]:
        lines.pop()
    return lines


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


def shape_candidates(text, measurer, box_w, box_h, max_px, min_px, pad_frac,
                     mode="balanced", hyphenate=False, lang="en", mask=None,
                     limit=10):
    """Generate candidate arrangements of `text` for the TextShapR picker.

    mode: 'balanced' (evenly balanced lines, biggest size first),
          'tall' (more lines / narrow block first),
          'wide' (fewer lines / wide block first),
          'round' (fit differently proportioned ellipses).
    hyphenate: allow syllable breaks (uses `lang`'s patterns).

    Embedded line breaks become spaces (the candidates create their own
    breaks). Returns a list of dicts {'px': int, 'k': int, 'lines': [run list
    per line]}, deduplicated, at most `limit` entries. The chosen candidate can
    be applied by joining runs_markup() of its lines with '\\n' and inserting
    that as hard-broken text capped at 'px'.
    """
    if mask is None:
        mask = [False] * len(text)
    flat = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    words = make_words(flat, list(mask))
    if not words:
        return []
    usable_w = box_w * (1.0 - pad_frac)
    usable_h = box_h * (1.0 - pad_frac)
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
        cands.append({"px": px, "k": len(runs), "lines": runs})

    if mode == "round":
        a, b = usable_w / 2.0, usable_h / 2.0
        for fw, fh in _ROUND_BOXES:
            add(fit_lines_ellipse(words, measurer, a * fw, b * fh,
                                  max_px, min_px, hyph_fn))
        cands.sort(key=lambda c: (-c["px"], c["k"]))
    elif hyphenate:
        # exact-k balancing cannot split words, so hyphenated candidates come
        # from greedily wrapping to a sweep of narrower target widths
        for f in _WIDTH_FRACS:
            add(fit_lines_width(words, measurer, usable_w, usable_h,
                                max_px, min_px, f, hyph_fn))
        if mode == "tall":
            cands.sort(key=lambda c: (-c["k"], -c["px"]))
        elif mode == "wide":
            cands.sort(key=lambda c: (c["k"], -c["px"]))
        else:
            cands.sort(key=lambda c: (-c["px"], c["k"]))
    else:
        for k in range(1, min(len(words), 12) + 1):
            add(fit_lines_k(words, measurer, usable_w, usable_h,
                            max_px, min_px, k))
        if mode == "tall":
            cands.sort(key=lambda c: -c["k"])
        elif mode == "wide":
            cands.sort(key=lambda c: c["k"])
        else:
            cands.sort(key=lambda c: (-c["px"], c["k"]))
    return cands[:limit]


def vertical_start(valign, box_y, box_h, pad_frac, k, line_h, ascent, descent):
    """Baseline of the FIRST line depending on vertical alignment.

    valign='middle' : block centered around the box center (default).
    valign='top'    : block at the top of the box (with padding).
    valign='bottom' : block at the bottom of the box (with padding).
    """
    pad = box_h * pad_frac / 2.0
    if valign == "top":
        return box_y + pad + ascent
    if valign == "bottom":
        return box_y + box_h - pad - descent - (k - 1) * line_h
    cy = box_y + box_h / 2.0
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
