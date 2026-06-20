# -*- coding: utf-8 -*-
"""Pure layout logic: line wrapping, even balancing, ellipse fitting (round
speech bubbles) and auto-sizing.

Deliberately free of any Qt dependency so it can be unit-tested in isolation.
Text widths come from a 'measurer(px)' function that returns:
    (width_of, space_w, line_h, ascent, descent)
"""

import math


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



def wrap_greedy(words, width_of, space_w, max_w):
    """Greedily wrap words into lines, each line <= max_w."""
    lines = []
    cur = []
    cur_w = 0.0
    for w in words:
        ww = width_of(w)
        if not cur:
            cur = [w]
            cur_w = ww
        elif cur_w + space_w + ww <= max_w:
            cur.append(w)
            cur_w += space_w + ww
        else:
            lines.append(cur)
            cur = [w]
            cur_w = ww
    if cur:
        lines.append(cur)
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


def _wrap_schedule(words, width_of, space_w, widths):
    """Wrap greedily where line i may be at most widths[i] wide (extra lines use
    the narrowest/last width). Returns None if a single word does not even fit
    on its own line."""
    def maxw(i):
        if not widths:
            return 0.0
        return widths[i] if i < len(widths) else widths[-1]

    lines = []
    cur = []
    cur_w = 0.0
    for word in words:
        ww = width_of(word)
        if not cur:
            if ww > maxw(len(lines)):
                return None
            cur = [word]
            cur_w = ww
        elif cur_w + space_w + ww <= maxw(len(lines)):
            cur.append(word)
            cur_w += space_w + ww
        else:
            lines.append(cur)
            if ww > maxw(len(lines)):
                return None
            cur = [word]
            cur_w = ww
    if cur:
        lines.append(cur)
    return lines


def wrap_ellipse(words, width_of, space_w, a, b, line_h):
    """Wrap words so they fit inside an ellipse (semi-axes a, b). Fixed-point
    iteration over the line count, because the allowed widths depend on the
    (centered) line count. Only a self-consistent result is returned (every
    line fits the line count its widths were computed for); otherwise None ->
    the caller picks a smaller font."""
    if not words:
        return []
    init = wrap_greedy(words, width_of, space_w, 2.0 * a)
    k = max(1, len(init))
    for _ in range(12):
        widths = _ellipse_line_widths(k, line_h, a, b)
        res = _wrap_schedule(words, width_of, space_w, widths)
        if res is None:
            return None
        if len(res) == k:
            return res          # consistent
        k = len(res)
        if k > 200:
            return None
    return None                 # did not converge -> smaller font


def fit_text(text, measurer, box_w, box_h, max_px, min_px, pad_frac,
             shape="rect", mask=None):
    """Find the largest font size at which the wrapped text fits.

    shape='rect'    : rectangular box, evenly balanced lines. Embedded line
                      breaks (\\n) are respected as hard breaks; each paragraph
                      is balanced on its own.
    shape='ellipse' : inscribed ellipse (round speech bubble); lines at the
                      top/bottom become narrower. Hard breaks become spaces here
                      (the ellipse shape drives the wrapping).

    mask: optional list of bool with the same length as text - marks bold
    characters (for partially bold text). None -> nothing bold.

    Returns: (font_px, lines, line_h, ascent, descent, fitted)
    'lines' is a list of run lists ([(subtext, bold), ...] per line).
    """
    if mask is None:
        mask = [False] * len(text)

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
            res = wrap_ellipse(words, width_of, space_w, a, b, line_h)
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
                if max(width_of(w) for w in words) > usable_w:
                    return None
                all_lines.extend(wrap_greedy(words, width_of, space_w, usable_w))
            if len(all_lines) * line_h > usable_h:
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
                           usable_w / 2.0, usable_h / 2.0, line_h)
        if res is None:
            res = wrap_greedy(words, width_of, space_w, usable_w)
        line_lists = res
    else:
        line_lists = []
        for words in paras:
            if not words:
                line_lists.append([])
                continue
            k = len(wrap_greedy(words, width_of, space_w, usable_w))
            line_lists.extend(balance_even(words, width_of, space_w, usable_w, k))
    lines = [line_runs(ws) for ws in line_lists]
    return best, lines, line_h, ascent, descent, fitted


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
